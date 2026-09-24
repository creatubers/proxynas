#!/usr/bin/env python3
"""Portable FFmpeg encoder diagnostics for Proxynas."""

import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

import backup_gui
import proxygenerator


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG = backup_gui.FFMPEG_BIN
FFPROBE = backup_gui.FFPROBE_BIN
ALL_ENCODERS = (
    "av1_nvenc",
    "av1_amf",
    "av1_qsv",
    "hevc_nvenc",
    "hevc_amf",
    "hevc_qsv",
    "libx265",
)
HEVC_ENCODERS = ALL_ENCODERS[3:]


def command_text(command):
    return subprocess.list2cmdline([str(item) for item in command])


def run_logged(command, log, timeout=90, stdin=None):
    log.write(f"\n$ {command_text(command)}\n")
    try:
        result = subprocess.run(
            command,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = result.stdout or ""
        log.write(output)
        log.write(f"\n[exit_code={result.returncode}]\n")
        return result.returncode == 0, result.returncode, output
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        log.write(str(output))
        log.write(f"\n[timeout={timeout}s]\n")
        return False, "timeout", str(output)
    except Exception as exc:
        log.write(f"\n[exception={exc!r}]\n")
        return False, "exception", str(exc)


def tail(text, lines=12):
    values = [line for line in text.splitlines() if line.strip()]
    return "\n".join(values[-lines:])


def make_sources(work_dir, log):
    specs = {
        "8bit": ("yuv420p", "ffv1"),
        "10bit": ("yuv420p10le", "ffv1"),
        "12bit_444": ("yuv444p12le", "prores_ks"),
    }
    sources = {}
    for name, (pixel_format, codec) in specs.items():
        extension = ".mov" if codec == "prores_ks" else ".mkv"
        path = os.path.join(work_dir, f"source_{name}{extension}")
        command = [
            FFMPEG,
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=3840x2160:rate=25:duration=1",
            "-vf",
            f"format={pixel_format},setparams=range=tv:colorspace=bt709:"
            "color_trc=bt709:color_primaries=bt709",
            "-c:v",
            codec,
        ]
        if codec == "prores_ks":
            command.extend(["-profile:v", "4", "-pix_fmt", pixel_format])
        command.extend(["-an", path])
        ok, _, _ = run_logged(command, log, timeout=120)
        if ok:
            sources[name] = path
    return sources


def probe_output(path, log):
    return run_logged(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,color_range,color_space,"
            "color_transfer,color_primaries",
            "-of",
            "json",
            path,
        ],
        log,
        timeout=20,
    )


def test_backup_encoder(encoder, source_name, source_path, work_dir, log):
    family = "av1" if encoder.startswith("av1_") else "hevc"
    output = os.path.join(work_dir, f"backup_{encoder}_{source_name}.mp4")
    command = [FFMPEG, "-hide_banner", "-y"]
    command.extend(backup_gui.encoder_input_options(encoder))
    command.extend(["-i", source_path])
    command.extend(backup_gui.encoder_options(encoder, "3M"))
    if family == "hevc":
        command.extend(["-tag:v", "hvc1"])
    command.extend(["-an", "-map", "0:v:0", output])
    ok, code, output_text = run_logged(command, log, timeout=120)
    if ok:
        probe_output(output, log)
    return {
        "ok": ok,
        "exit_code": code,
        "error_tail": "" if ok else tail(output_text),
    }


def test_proxy_encoder(encoder, source_path, work_dir, log):
    output = os.path.join(work_dir, f"proxy_{encoder}.mov")
    command = [
        FFMPEG,
        "-hide_banner",
        "-y",
        "-i",
        source_path,
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
    ]
    command.extend(proxygenerator.proxy_encoder_options(encoder))
    command.extend(
        [
            "-vf",
            proxygenerator.standard_proxy_filter(source_path, encoder),
            *proxygenerator.get_color_args(source_path),
            *proxygenerator.preserve_container_metadata_args(),
            output,
        ]
    )
    ok, code, output_text = run_logged(command, log, timeout=120)
    if ok:
        probe_output(output, log)
    return {
        "ok": ok,
        "exit_code": code,
        "error_tail": "" if ok else tail(output_text),
    }


def test_braw_encoder(encoder, braw_path, work_dir, log):
    try:
        info = proxygenerator.get_braw_info(braw_path)
    except Exception as exc:
        return {"ok": False, "exit_code": "info_error", "error_tail": str(exc)}

    output = os.path.join(work_dir, f"braw_{encoder}.mov")
    decode_command = [
        proxygenerator.BRAW_DECODE,
        "--raw",
        "--sdk",
        proxygenerator.SDK_DIR,
        "--scale",
        proxygenerator.BRAW_SCALE,
        braw_path,
    ]
    encode_command = [
        FFMPEG,
        "-hide_banner",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        proxygenerator.BRAW_RAW_PIX_FMT,
        "-s",
        f"{info['width']}x{info['height']}",
        "-r",
        str(info["frame_rate"]),
        "-i",
        "-",
        "-frames:v",
        "15",
        *proxygenerator.proxy_encoder_options(encoder),
        *proxygenerator.proxy_scale_filter(info["width"]),
        *proxygenerator.proxy_color_args(),
        *proxygenerator.get_color_args(braw_path),
        output,
    ]
    log.write(f"\n$ {command_text(decode_command)} | {command_text(encode_command)}\n")
    decoder = None
    encoder_process = None
    try:
        decoder = subprocess.Popen(
            decode_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(braw_path),
        )
        encoder_process = subprocess.Popen(
            encode_command,
            stdin=decoder.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        decoder.stdout.close()
        output_text = encoder_process.communicate(timeout=120)[0] or ""
        log.write(output_text)
        ok = encoder_process.returncode == 0 and os.path.isfile(output)
        code = encoder_process.returncode
    except Exception as exc:
        output_text = str(exc)
        log.write(f"\n[exception={exc!r}]\n")
        ok = False
        code = "exception"
    finally:
        if encoder_process and encoder_process.poll() is None:
            encoder_process.kill()
        if decoder and decoder.poll() is None:
            decoder.kill()
        if decoder:
            try:
                decoder.communicate(timeout=5)
            except Exception:
                pass
    if ok:
        probe_output(output, log)
    return {
        "ok": ok,
        "exit_code": code,
        "error_tail": "" if ok else tail(output_text),
    }


def collect_system_info(log):
    info = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "gpu_detected_by_app": backup_gui.get_gpu_name(),
        "ffmpeg": FFMPEG,
    }
    commands = [
        [FFMPEG, "-version"],
        [FFMPEG, "-hide_banner", "-encoders"],
        ["nvidia-smi"],
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,DriverVersion,VideoProcessor,AdapterRAM | "
            "Format-List",
        ],
    ]
    for command in commands:
        if shutil.which(command[0]) or os.path.isfile(command[0]):
            run_logged(command, log, timeout=30)
    return info


def write_summary(path, report):
    lines = [
        "Proxynas - resumen de diagnostico",
        f"Equipo: {report['system']['platform']}",
        f"GPU: {report['system']['gpu_detected_by_app']}",
        "",
    ]
    for section in ("backup", "proxy", "braw"):
        if not report.get(section):
            continue
        lines.append(section.upper())
        for encoder, tests in report[section].items():
            if isinstance(tests, dict) and "ok" in tests:
                lines.append(f"  {encoder}: {'OK' if tests['ok'] else 'FALLO'}")
            else:
                passed = sum(1 for result in tests.values() if result["ok"])
                lines.append(f"  {encoder}: {passed}/{len(tests)} OK")
        lines.append("")
    with open(path, "w", encoding="utf-8") as summary:
        summary.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("braw", nargs="?", help="BRAW opcional para la prueba real")
    args = parser.parse_args()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = os.path.join(SCRIPT_DIR, "diagnosticos")
    report_dir = os.path.join(output_root, f"diagnostico_encoders_{timestamp}")
    os.makedirs(report_dir, exist_ok=True)
    log_path = os.path.join(report_dir, "ffmpeg_completo.log")
    report = {"system": {}, "backup": {}, "proxy": {}, "braw": {}}

    print("Proxynas - diagnostico de encoders")
    print("Puede tardar varios minutos. Los fallos de GPU no instalada son normales.\n")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        report["system"] = collect_system_info(log)
        with tempfile.TemporaryDirectory(prefix="proxynas_diag_") as work_dir:
            sources = make_sources(work_dir, log)
            for encoder in ALL_ENCODERS:
                print(f"Backup: {encoder}")
                report["backup"][encoder] = {}
                for source_name, source_path in sources.items():
                    report["backup"][encoder][source_name] = test_backup_encoder(
                        encoder, source_name, source_path, work_dir, log
                    )

            proxy_source = sources.get("12bit_444")
            if proxy_source:
                for encoder in HEVC_ENCODERS:
                    print(f"Proxy:  {encoder}")
                    report["proxy"][encoder] = test_proxy_encoder(
                        encoder, proxy_source, work_dir, log
                    )

            if args.braw:
                braw_path = os.path.abspath(args.braw)
                if os.path.isfile(braw_path):
                    for encoder in HEVC_ENCODERS:
                        print(f"BRAW:   {encoder}")
                        report["braw"][encoder] = test_braw_encoder(
                            encoder, braw_path, work_dir, log
                        )
                else:
                    report["braw"]["error"] = {
                        "ok": False,
                        "exit_code": "not_found",
                        "error_tail": f"No existe: {braw_path}",
                    }

    with open(os.path.join(report_dir, "resultados.json"), "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    write_summary(os.path.join(report_dir, "RESUMEN.txt"), report)

    zip_path = report_dir + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in os.listdir(report_dir):
            archive.write(os.path.join(report_dir, filename), arcname=filename)

    print(f"\nTerminado.\nZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

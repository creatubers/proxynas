import json
import os
import subprocess
import sys
import threading
import time


VIDEO_EXTENSIONS = (".braw", ".mov", ".mp4", ".mxf", ".r3d")
STABILITY_WAIT_SECONDS = 2
STABILITY_CHECKS = 3
PARTIAL_MARKER = ".partial"
PROXY_SUBDIR_NAME = "Proxy"

BRAW_SCALE = "1"
PROXY_WIDTH = 1920
VIDEO_BITRATE = "8M"
BRAW_RAW_PIX_FMT = "rgba64le"
HEVC_ENCODER_CANDIDATES = ("hevc_nvenc", "hevc_amf", "hevc_qsv", "libx265")
_PROXY_ENCODER_CACHE = None


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTABLE_DIR = os.path.join(SCRIPT_DIR, "portable")
BIN_DIR = os.path.join(PORTABLE_DIR, "bin")
SDK_DIR = os.path.join(PORTABLE_DIR, "sdk")

FFMPEG = os.path.join(BIN_DIR, "ffmpeg.exe")
FFPROBE = os.path.join(BIN_DIR, "ffprobe.exe")
BRAW_DECODE = os.path.join(BIN_DIR, "braw_decode.exe")


def proxy_extension_for(source_path):
    return ".MOV" if os.path.splitext(source_path)[1] == ".MOV" else ".mov"


def require_file(path, label):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} no encontrado: {path}")


def check_portable_tools():
    require_file(FFMPEG, "FFmpeg portable")
    require_file(FFPROBE, "FFprobe portable")
    require_file(BRAW_DECODE, "Decodificador BRAW portable")
    require_file(os.path.join(SDK_DIR, "BlackmagicRawAPI.dll"), "SDK BRAW portable")
    get_proxy_encoder()


def get_ffmpeg_video_encoders():
    try:
        output = subprocess.check_output(
            [FFMPEG, "-hide_banner", "-encoders"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except Exception:
        return set()

    encoders = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    return encoders


def proxy_encoder_options(encoder):
    if encoder == "hevc_nvenc":
        return ["-c:v", encoder, "-pix_fmt", proxy_output_pix_fmt(encoder), "-preset", "p5", "-b:v", VIDEO_BITRATE, "-tag:v", "hvc1"]
    if encoder == "hevc_amf":
        return ["-c:v", encoder, "-pix_fmt", proxy_output_pix_fmt(encoder), "-quality", "balanced", "-b:v", VIDEO_BITRATE, "-tag:v", "hvc1"]
    if encoder == "hevc_qsv":
        return ["-c:v", encoder, "-pix_fmt", proxy_output_pix_fmt(encoder), "-preset", "medium", "-b:v", VIDEO_BITRATE, "-tag:v", "hvc1"]
    if encoder == "libx265":
        return [
            "-c:v", encoder,
            "-pix_fmt", "yuv420p10le",
            "-preset", "medium",
            "-x265-params", "log-level=error",
            "-b:v", VIDEO_BITRATE,
            "-tag:v", "hvc1",
        ]
    return ["-c:v", encoder, "-pix_fmt", "yuv420p10le", "-b:v", VIDEO_BITRATE, "-tag:v", "hvc1"]


def test_proxy_encoder(encoder):
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30",
        "-frames:v", "15",
    ]
    cmd.extend(proxy_encoder_options(encoder))
    cmd.extend(["-f", "null", "-"])
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        return True, ""
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        return False, detail[-1] if detail else f"ffmpeg codigo {exc.returncode}"
    except Exception as exc:
        return False, str(exc)


def detect_proxy_encoder(force=False):
    global _PROXY_ENCODER_CACHE
    if _PROXY_ENCODER_CACHE is not None and not force:
        return _PROXY_ENCODER_CACHE

    available = get_ffmpeg_video_encoders()
    tested = []
    for encoder in HEVC_ENCODER_CANDIDATES:
        if encoder not in available:
            tested.append(f"{encoder}: no listado por ffmpeg")
            continue
        ok, detail = test_proxy_encoder(encoder)
        tested.append(f"{encoder}: {'OK' if ok else detail}")
        if ok:
            _PROXY_ENCODER_CACHE = {
                "encoder": encoder,
                "available": True,
                "tested": tested,
                "reason": "",
            }
            return _PROXY_ENCODER_CACHE

    _PROXY_ENCODER_CACHE = {
        "encoder": None,
        "available": False,
        "tested": tested,
        "reason": tested[-1] if tested else "ffmpeg no lista encoders HEVC",
    }
    return _PROXY_ENCODER_CACHE


def get_proxy_encoder():
    result = detect_proxy_encoder()
    if not result.get("available"):
        raise RuntimeError(f"Sin encoder HEVC para proxies: {result.get('reason')}")
    return result["encoder"]


def is_file_stable(filepath):
    try:
        previous_size = os.path.getsize(filepath)
        if previous_size == 0:
            return False
        for _ in range(STABILITY_CHECKS):
            time.sleep(STABILITY_WAIT_SECONDS)
            current_size = os.path.getsize(filepath)
            if current_size == 0 or current_size != previous_size:
                return False
            previous_size = current_size
        return True
    except OSError:
        return False


def temporary_output_path(output_path):
    root, ext = os.path.splitext(output_path)
    if ext:
        return f"{root}{PARTIAL_MARKER}{ext}"
    return f"{output_path}{PARTIAL_MARKER}"


def remove_partial_output(output_path):
    partial_path = temporary_output_path(output_path)
    try:
        if os.path.exists(partial_path):
            os.remove(partial_path)
    except OSError:
        pass


def promote_partial_output(partial_path, output_path):
    if not os.path.exists(partial_path) or os.path.getsize(partial_path) == 0:
        raise RuntimeError(f"Salida temporal invalida: {partial_path}")
    os.replace(partial_path, output_path)


def process_error_message(label, returncode, output_lines):
    tail = "\n".join(output_lines[-12:]).strip()
    if tail:
        return f"{label} finalizo con codigo {returncode}:\n{tail}"
    return f"{label} finalizo con codigo {returncode}"


def get_color_args(video_path):
    entries = "stream=color_range,color_space,color_transfer,color_primaries"
    command = [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", entries, "-of", "json", video_path]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    except json.JSONDecodeError:
        return []
    mapping = {
        "color_range": "-color_range",
        "color_space": "-colorspace",
        "color_transfer": "-color_trc",
        "color_primaries": "-color_primaries",
    }
    args = []
    for key, ffmpeg_key in mapping.items():
        value = stream.get(key)
        if value and value != "unknown":
            args.extend([ffmpeg_key, value])
    return args


def get_video_color_info(video_path):
    entries = "stream=color_range,color_space,color_transfer,color_primaries"
    command = [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", entries, "-of", "json", video_path]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return (json.loads(result.stdout).get("streams") or [{}])[0]
    except json.JSONDecodeError:
        return {}


def proxy_output_pix_fmt(encoder):
    return "p010le" if encoder != "libx265" else "yuv420p10le"


def standard_proxy_filter(source_path, encoder):
    info = get_video_color_info(source_path)
    setparams = []
    mapping = {
        "color_range": "range",
        "color_space": "colorspace",
        "color_transfer": "color_trc",
        "color_primaries": "color_primaries",
    }
    for key, filter_key in mapping.items():
        value = info.get(key)
        if value and value != "unknown":
            setparams.append(f"{filter_key}={value}")

    filters = []
    if setparams:
        filters.append("setparams=" + ":".join(setparams))
    filters.append(f"scale={PROXY_WIDTH}:-2")
    filters.append(f"format={proxy_output_pix_fmt(encoder)}")
    return ",".join(filters)


def get_format_metadata_args(video_path):
    command = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format_tags",
        "-of",
        "json",
        video_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        tags = (json.loads(result.stdout).get("format") or {}).get("tags") or {}
    except json.JSONDecodeError:
        return []

    args = []
    for key, value in sorted(tags.items()):
        if value is None:
            continue
        value = str(value).strip()
        if value:
            args.extend(["-metadata", f"{key}={value}"])
    return args


def preserve_container_metadata_args():
    return ["-movflags", "+use_metadata_tags"]


def proxy_color_args():
    return [
        "-color_range", "pc",
    ]


def get_timecode(video_path):
    command = [
        FFPROBE,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream_tags=timecode",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    timecode = result.stdout.strip()
    return timecode or "00:00:00:00"


def get_braw_info(source_path):
    command = [
        BRAW_DECODE,
        "--info",
        "--sdk",
        SDK_DIR,
        "--scale",
        BRAW_SCALE,
        source_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def proxy_scale_filter(width):
    if int(width) == PROXY_WIDTH:
        return []
    return ["-vf", f"scale={PROXY_WIDTH}:-2"]


def create_braw_proxy(source_path, output_path):
    partial_output_path = temporary_output_path(output_path)
    remove_partial_output(output_path)

    info = get_braw_info(source_path)
    width = int(info["width"])
    height = int(info["height"])
    frame_rate = str(info["frame_rate"])
    timecode = info.get("timecode") or "00:00:00:00"
    encoder = get_proxy_encoder()

    decode_command = [
        BRAW_DECODE,
        "--raw",
        "--sdk",
        SDK_DIR,
        "--scale",
        BRAW_SCALE,
        source_path,
    ]
    ffmpeg_command = [
        FFMPEG,
        "-hide_banner",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        BRAW_RAW_PIX_FMT,
        "-s",
        f"{width}x{height}",
        "-r",
        frame_rate,
        "-i",
        "-",
        "-i",
        source_path,
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:a",
        "copy",
        "-timecode",
        timecode,
        *get_format_metadata_args(source_path),
        *proxy_encoder_options(encoder),
        *proxy_scale_filter(width),
        *proxy_color_args(),
        *get_color_args(source_path),
        *preserve_container_metadata_args(),
        partial_output_path,
    ]

    print(
        f"BRAW SDK: {width}x{height}, {frame_rate} fps, "
        f"{info['frame_count']} frames, TC {timecode}, encoder {encoder}"
    )

    decoder = subprocess.Popen(
        decode_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(source_path),
    )
    ffmpeg = subprocess.Popen(
        ffmpeg_command,
        stdin=decoder.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
    )
    decoder.stdout.close()

    decoder_stderr_chunks = []

    def drain_decoder_stderr():
        try:
            for line in decoder.stderr:
                decoder_stderr_chunks.append(line)
        except Exception:
            pass

    stderr_thread = threading.Thread(target=drain_decoder_stderr, daemon=True)
    stderr_thread.start()

    ffmpeg_output = []
    for line in ffmpeg.stdout:
        ffmpeg_output.append(line.strip())
        if len(ffmpeg_output) > 80:
            ffmpeg_output = ffmpeg_output[-80:]
        print(line.strip())

    ffmpeg_return = ffmpeg.wait()
    stderr_thread.join()
    decoder_return = decoder.wait()
    decoder_errors = b"".join(decoder_stderr_chunks).decode("utf-8", errors="replace").strip()

    if decoder_errors:
        print(decoder_errors)
    if decoder_return != 0:
        remove_partial_output(output_path)
        raise RuntimeError(f"braw_decode finalizo con codigo {decoder_return}")
    if ffmpeg_return != 0:
        remove_partial_output(output_path)
        raise RuntimeError(process_error_message("ffmpeg", ffmpeg_return, ffmpeg_output))
    promote_partial_output(partial_output_path, output_path)


def create_standard_proxy(source_path, output_path):
    partial_output_path = temporary_output_path(output_path)
    remove_partial_output(output_path)
    timecode = get_timecode(source_path)
    encoder = get_proxy_encoder()
    command = [
        FFMPEG,
        "-hide_banner",
        "-y",
        "-i",
        source_path,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:a",
        "copy",
        "-sn",
        "-dn",
        "-map_metadata",
        "0",
        "-timecode",
        timecode,
        *get_format_metadata_args(source_path),
        *proxy_encoder_options(encoder),
        "-vf",
        standard_proxy_filter(source_path, encoder),
        *get_color_args(source_path),
        *preserve_container_metadata_args(),
        partial_output_path,
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
    )
    ffmpeg_output = []
    for line in process.stdout:
        ffmpeg_output.append(line.strip())
        if len(ffmpeg_output) > 80:
            ffmpeg_output = ffmpeg_output[-80:]
        print(line.strip())
    if process.wait() != 0:
        remove_partial_output(output_path)
        raise RuntimeError(process_error_message("ffmpeg", process.returncode, ffmpeg_output))
    promote_partial_output(partial_output_path, output_path)


def find_video_files(root_dir):
    video_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        if PROXY_SUBDIR_NAME in dirpath.split(os.sep):
            continue
        if os.path.abspath(dirpath).startswith(os.path.abspath(PORTABLE_DIR)):
            continue
        for filename in filenames:
            if filename.lower().endswith(VIDEO_EXTENSIONS):
                video_files.append(os.path.join(dirpath, filename))
    return sorted(video_files)


def run_proxy_creation(root_dir):
    check_portable_tools()

    print(f"\nBuscando videos en: {root_dir}")
    video_files = find_video_files(root_dir)
    if not video_files:
        print("No se encontraron videos para analizar.")
        return

    jobs = []
    print("\nAnalizando archivos y proxies existentes...")
    for source_path in video_files:
        base_name_no_ext = os.path.splitext(os.path.basename(source_path))[0]
        proxy_dir = os.path.join(os.path.dirname(source_path), PROXY_SUBDIR_NAME)
        output_path = os.path.join(proxy_dir, f"{base_name_no_ext}{proxy_extension_for(source_path)}")

        if os.path.exists(output_path):
            continue
        if not is_file_stable(source_path):
            print(f"-> Saltando {os.path.basename(source_path)}: parece estar en transferencia.")
            continue
        jobs.append((source_path, output_path))

    if not jobs:
        print("\nTodo actualizado. No hay videos nuevos que procesar.")
        return

    print(f"\nSe procesaran {len(jobs)} videos nuevos.")
    for index, (source_path, output_path) in enumerate(jobs, start=1):
        print("-" * 70)
        print(f"TRABAJO {index}/{len(jobs)}: {os.path.basename(source_path)}")
        print(f"Destino: {output_path}")
        print("-" * 70)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            if source_path.lower().endswith(".braw"):
                create_braw_proxy(source_path, output_path)
            else:
                create_standard_proxy(source_path, output_path)
            print(f"\nEXITO: Proxy creado para {os.path.basename(source_path)}")
        except Exception as exc:
            remove_partial_output(output_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            print(f"\nERROR: {exc}")

    print("\n--- Proceso de creacion de proxies finalizado ---")


if __name__ == "__main__":
    try:
        print("--- Generador de Proxies Portable BRAW SDK ---")
        print(f"Directorio de trabajo: {SCRIPT_DIR}")
        run_proxy_creation(SCRIPT_DIR)
    except Exception as exc:
        print(f"\nERROR CRITICO: {exc}")
        sys.exit(1)

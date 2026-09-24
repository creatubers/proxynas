import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile


VIDEO_EXTENSIONS = (".braw", ".mov", ".mp4", ".mxf", ".r3d")
STABILITY_WAIT_SECONDS = 2
STABILITY_CHECKS = 3
PARTIAL_MARKER = ".partial"
PROXY_SUBDIR_NAME = "Proxy"

BRAW_SCALE = "1"
PROXY_WIDTH = 1920
VIDEO_BITRATE = "8M"
BRAW_RAW_PIX_FMT = "rgba64le"
# Candidatos por familia de codec y aceleracion. "auto" prueba hardware y cae a software.
PROXY_CODECS = ("hevc", "h264")
PROXY_CODEC_LABELS = {"hevc": "H.265", "h264": "H.264"}
PROXY_ACCELS = ("auto", "hw", "sw")
DEFAULT_PROXY_CODEC = "hevc"
DEFAULT_PROXY_ACCEL = "auto"
PROXY_ENCODERS = {
    "hevc": {"hw": ("hevc_nvenc", "hevc_amf", "hevc_qsv"), "sw": ("libx265",)},
    "h264": {"hw": ("h264_nvenc", "h264_amf", "h264_qsv"), "sw": ("libx264",)},
}
_PROXY_ENCODER_CACHE = {}


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTABLE_DIR = os.path.join(SCRIPT_DIR, "portable")
BIN_DIR = os.path.join(PORTABLE_DIR, "bin")
SDK_DIR = os.path.join(PORTABLE_DIR, "sdk")

def resolve_tool(name):
    """Binario portable si esta descargado; si no, el que haya en PATH."""
    portable = os.path.join(BIN_DIR, name + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(portable):
        return portable
    return shutil.which(name) or portable


FFMPEG = resolve_tool("ffmpeg")
FFPROBE = resolve_tool("ffprobe")
BRAW_DECODE = resolve_tool("braw_decode")

BRAW_SDK_DLLS = ("BlackmagicRawAPI.dll", "DecoderCUDA.dll", "DecoderOpenCL.dll")


def proxy_extension_for(source_path):
    return ".MOV" if os.path.splitext(source_path)[1] == ".MOV" else ".mov"


def require_file(path, label):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No se encuentra el {label}: {path}")


def check_braw_tools(require_braw=True):
    require_file(BRAW_DECODE, "Decodificador BRAW portable")
    if require_braw:
        require_file(os.path.join(SDK_DIR, "BlackmagicRawAPI.dll"), "SDK BRAW portable")


def check_portable_tools(require_braw=True, codec=DEFAULT_PROXY_CODEC, accel=DEFAULT_PROXY_ACCEL):
    require_file(FFMPEG, "FFmpeg")
    require_file(FFPROBE, "FFprobe")
    check_braw_tools(require_braw)
    get_proxy_encoder(codec, accel)


def _extract_member(archive, member, target):
    with archive.open(member) as source, open(target, "wb") as destination:
        shutil.copyfileobj(source, destination)
    return target


def _arch_rank(zip_name):
    lowered = zip_name.lower()
    if "x64" in lowered or "amd64" in lowered:
        return 2
    if "x86" in lowered or "arm" in lowered or "win32" in lowered:
        return 0
    return 1


def braw_sdk_entries(zip_names):
    """Elige un fichero por nombre dentro del zip del SDK.

    El zip oficial trae cabeceras, libs y varias arquitecturas, y su estructura
    cambia entre versiones, así que se busca por nombre de fichero (prefiriendo
    x64) en lugar de por rutas fijas.
    """
    wanted_dlls = tuple(name.lower() for name in BRAW_SDK_DLLS)
    picked = {}
    for name in zip_names:
        base = os.path.basename(name).lower()
        if not (_is_wanted_dll(base) or base == "braw_decode.exe"):
            continue
        if base not in picked or _arch_rank(name) > _arch_rank(picked[base]):
            picked[base] = name
    return picked


def _is_wanted_dll(name):
    lower = name.lower()
    return lower.endswith(".dll") and (
        lower in tuple(dll.lower() for dll in BRAW_SDK_DLLS)
        or lower.startswith("instructionsetservices")
    )


def _pe_machine(path):
    """Arquitectura del PE (0x8664 = x64) o None si no se puede leer."""
    try:
        with open(path, "rb") as handle:
            offset = int.from_bytes(handle.read(0x40)[0x3C:0x40], "little")
            handle.seek(offset + 4)
            return int.from_bytes(handle.read(2), "little")
    except OSError:
        return None


def sdk_folder_in_tree(root):
    """Directorio no-ARM con un BlackmagicRawAPI.dll x64 (prefiere el del SDK)."""
    candidates = []
    for base, dirs, files in os.walk(root):
        if "arm" in base.lower():
            dirs[:] = []
            continue
        if "blackmagicrawapi.dll" not in {name.lower() for name in files}:
            continue
        if _pe_machine(os.path.join(base, "BlackmagicRawAPI.dll")) != 0x8664:
            continue
        lowered = base.lower()
        rank = 2 if "libraries" in lowered else 1 if "sdk" in lowered else 0
        candidates.append((rank, base))
    return max(candidates)[1] if candidates else None


def _copy_wanted_dlls(source_dir):
    copied = []
    for name in sorted(os.listdir(source_dir)):
        if _is_wanted_dll(name):
            copied.append(shutil.copyfile(os.path.join(source_dir, name),
                                         os.path.join(SDK_DIR, name)))
    return copied


def _import_from_installer_zip(archive):
    """El zip de Windows trae instaladores (.msi), no DLL sueltos.

    Se extraen con msiexec /a (sin instalar nada) y se copian los DLL de dentro.
    """
    installers = [name for name in archive.namelist()
                  if name.lower().endswith(".msi")
                  and "arm" not in os.path.basename(name).lower()]
    if not installers:
        raise ValueError("El zip no trae ni DLL ni instalador (.msi) del SDK BRAW.")
    installer = max(installers, key=lambda name: _arch_rank(os.path.basename(name)))
    with tempfile.TemporaryDirectory(prefix="proxynas-braw-sdk-") as work:
        msi = _extract_member(archive, installer, os.path.join(work, "sdk.msi"))
        extracted = os.path.join(work, "extracted")
        done = subprocess.run(["msiexec", "/a", msi, "/qn", f"TARGETDIR={extracted}"],
                              capture_output=True)
        if done.returncode != 0:
            raise ValueError(f"msiexec no pudo extraer el SDK (código {done.returncode}).")
        folder = sdk_folder_in_tree(extracted)
        if not folder:
            raise ValueError("El instalador no traía un BlackmagicRawAPI.dll x64.")
        copied = _copy_wanted_dlls(folder)
    return copied, {os.path.basename(path).lower(): path for path in copied}


def import_braw_sdk(zip_path):
    """Copia a portable/ los DLL del SDK, venga el zip con DLL o con instaladores."""
    with zipfile.ZipFile(zip_path) as archive:
        picked = braw_sdk_entries(archive.namelist())
        dlls = {base: name for base, name in picked.items() if base.endswith(".dll")}
        os.makedirs(SDK_DIR, exist_ok=True)
        if dlls:
            copied = [
                _extract_member(archive, name, os.path.join(SDK_DIR, base))
                for base, name in sorted(dlls.items())
            ]
        else:
            copied, dlls = _import_from_installer_zip(archive)

        decoder_name = picked.get("braw_decode.exe")
        if decoder_name:
            os.makedirs(BIN_DIR, exist_ok=True)
            copied.append(_extract_member(archive, decoder_name, BRAW_DECODE))

    return {
        "copied": copied,
        "missing": [name for name in BRAW_SDK_DLLS if name.lower() not in dlls],
        "decoder": os.path.isfile(BRAW_DECODE),
    }

def ffmpeg_encoder_list():
    """(encoders, error). error es None solo si ffmpeg respondio de verdad."""
    try:
        output = subprocess.check_output(
            [FFMPEG, "-hide_banner", "-encoders"],
            text=True,
            stderr=subprocess.STDOUT,
            # Holgado a proposito: la primera vez que se lanza, el antivirus
            # revisa los 145 MB de ffmpeg antes de dejarlo arrancar.
            timeout=60,
        )
    except Exception as exc:
        return set(), f"ffmpeg no responde en {FFMPEG}: {exc}"

    encoders = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    if not encoders:
        return set(), "ffmpeg no lista ningun encoder de video"
    return encoders, None


def get_ffmpeg_video_encoders():
    """Nombres de encoders de video de este ffmpeg (vacio si no responde)."""
    return ffmpeg_encoder_list()[0]


def proxy_video_tag(encoder):
    """Etiqueta de codec del contenedor; None si ffmpeg ya elige la correcta."""
    if "hevc" in encoder or "265" in encoder:
        return "hvc1"
    if "h264" in encoder or "264" in encoder:
        return "avc1"
    return None


def proxy_encoder_options(encoder):
    options = ["-c:v", encoder, "-pix_fmt", proxy_output_pix_fmt(encoder)]
    if encoder.endswith("_nvenc"):
        options.extend(["-preset", "p5"])
    elif encoder.endswith("_amf"):
        options.extend(["-quality", "balanced"])
    elif encoder.endswith("_qsv"):
        options.extend(["-preset", "medium"])
    elif encoder == "libx265":
        options.extend(["-preset", "medium", "-x265-params", "log-level=error"])
    elif encoder == "libx264":
        options.extend(["-preset", "medium"])
    options.extend(["-b:v", VIDEO_BITRATE])
    tag = proxy_video_tag(encoder)
    if tag:
        options.extend(["-tag:v", tag])
    return options


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
            timeout=60,
        )
        return True, ""
    except subprocess.CalledProcessError as exc:
        lines = [line.strip() for line in (exc.stderr or "").splitlines() if line.strip()]
        # La primera linea es el motivo real ("No capable devices found"); la
        # ultima suele ser el generico "Nothing was written into output file".
        return False, lines[0] if lines else f"ffmpeg código {exc.returncode}"
    except Exception as exc:
        return False, str(exc)


def proxy_encoder_candidates(codec, accel):
    """Encoders a probar, en orden, para el codec y la aceleracion pedidos."""
    table = PROXY_ENCODERS.get(codec) or PROXY_ENCODERS[DEFAULT_PROXY_CODEC]
    if accel == "hw":
        return table["hw"]
    if accel == "sw":
        return table["sw"]
    return table["hw"] + table["sw"]


def detect_proxy_encoder(codec=DEFAULT_PROXY_CODEC, accel=DEFAULT_PROXY_ACCEL, force=False):
    """Que encoder usaria un proxy de este codec con esta aceleracion."""
    key = (codec, accel)
    cached = _PROXY_ENCODER_CACHE.get(key)
    if cached is not None and not force:
        return cached

    available, list_error = ffmpeg_encoder_list()
    tested = []
    if list_error:
        # Antes, no poder ni arrancar ffmpeg se reportaba como "libx265 no
        # listado por ffmpeg": culpaba al encoder cuando el problema era otro.
        tested.append(list_error)
    else:
        for encoder in proxy_encoder_candidates(codec, accel):
            if encoder not in available:
                tested.append(f"{encoder}: no listado por ffmpeg")
                continue
            ok, detail = test_proxy_encoder(encoder)
            tested.append(f"{encoder}: {'OK' if ok else detail}")
            if ok:
                result = {
                    "encoder": encoder,
                    "codec": codec,
                    "accel": accel,
                    "available": True,
                    "tested": tested,
                    "reason": "",
                }
                _PROXY_ENCODER_CACHE[key] = result
                return result

    result = {
        "encoder": None,
        "codec": codec,
        "accel": accel,
        "available": False,
        "tested": tested,
        "reason": tested[-1] if tested else "ffmpeg no lista encoders de vídeo",
    }
    _PROXY_ENCODER_CACHE[key] = result
    return result


def reset_proxy_encoder_cache():
    """Olvida la deteccion hecha antes de tener ffmpeg: esos resultados ya no valen."""
    _PROXY_ENCODER_CACHE.clear()


def get_proxy_encoder(codec=DEFAULT_PROXY_CODEC, accel=DEFAULT_PROXY_ACCEL):
    result = detect_proxy_encoder(codec, accel)
    if not result.get("available"):
        label = PROXY_CODEC_LABELS.get(codec, codec)
        modo = {"hw": " de hardware", "sw": " de software"}.get(accel, "")
        raise RuntimeError(f"Sin encoder {label}{modo} para proxies: {result.get('reason')}")
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
        raise RuntimeError(f"Salida temporal inválida: {partial_path}")
    os.replace(partial_path, output_path)


def process_error_message(label, returncode, output_lines):
    tail = "\n".join(output_lines[-12:]).strip()
    if tail:
        return f"{label} finalizó con código {returncode}:\n{tail}"
    return f"{label} finalizó con código {returncode}"


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
    # Misma profundidad en todos los codecs de proxy (10 bits): un H.264 y un
    # H.265 del mismo material tienen que coincidir, y es el formato que ya
    # usaban los proxies antes de poder elegir codec.
    return "yuv420p10le" if encoder in ("libx265", "libx264") else "p010le"


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
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(process_error_message("braw_decode", result.returncode, [result.stderr.strip()]))
    return json.loads(result.stdout)


def proxy_scale_filter(width):
    if int(width) == PROXY_WIDTH:
        return []
    return ["-vf", f"scale={PROXY_WIDTH}:-2"]


def create_braw_proxy(source_path, output_path, codec=DEFAULT_PROXY_CODEC, accel=DEFAULT_PROXY_ACCEL):
    partial_output_path = temporary_output_path(output_path)
    remove_partial_output(output_path)

    info = get_braw_info(source_path)
    width = int(info["width"])
    height = int(info["height"])
    frame_rate = str(info["frame_rate"])
    timecode = info.get("timecode") or "00:00:00:00"
    encoder = get_proxy_encoder(codec, accel)

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
        raise RuntimeError(process_error_message("braw_decode", decoder_return, [decoder_errors]))
    if ffmpeg_return != 0:
        remove_partial_output(output_path)
        raise RuntimeError(process_error_message("ffmpeg", ffmpeg_return, ffmpeg_output))
    promote_partial_output(partial_output_path, output_path)


def create_standard_proxy(source_path, output_path, codec=DEFAULT_PROXY_CODEC, accel=DEFAULT_PROXY_ACCEL):
    partial_output_path = temporary_output_path(output_path)
    remove_partial_output(output_path)
    timecode = get_timecode(source_path)
    encoder = get_proxy_encoder(codec, accel)
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


def run_proxy_creation(root_dir, codec=DEFAULT_PROXY_CODEC, accel=DEFAULT_PROXY_ACCEL):
    print(f"\nBuscando vídeos en: {root_dir}")
    video_files = find_video_files(root_dir)
    if not video_files:
        print("No se encontraron vídeos para analizar.")
        return

    # El material sin .braw no necesita el SDK, así que solo se exige si hay alguno.
    check_portable_tools(
        require_braw=any(path.lower().endswith(".braw") for path in video_files),
        codec=codec,
        accel=accel,
    )

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
        print("\nTodo actualizado. No hay vídeos nuevos que procesar.")
        return

    print(f"\nSe procesarán {len(jobs)} vídeos nuevos.")
    for index, (source_path, output_path) in enumerate(jobs, start=1):
        print("-" * 70)
        print(f"TRABAJO {index}/{len(jobs)}: {os.path.basename(source_path)}")
        print(f"Destino: {output_path}")
        print("-" * 70)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            if source_path.lower().endswith(".braw"):
                create_braw_proxy(source_path, output_path, codec, accel)
            else:
                create_standard_proxy(source_path, output_path, codec, accel)
            print(f"\nÉXITO: proxy creado para {os.path.basename(source_path)}")
        except Exception as exc:
            remove_partial_output(output_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            print(f"\nERROR: {exc}")

    print("\n--- Proceso de creación de proxies finalizado ---")


if __name__ == "__main__":
    try:
        print("--- Generador de Proxies Portable BRAW SDK ---")
        print(f"Directorio de trabajo: {SCRIPT_DIR}")
        run_proxy_creation(SCRIPT_DIR)
    except Exception as exc:
        print(f"\nERROR CRÍTICO: {exc}")
        sys.exit(1)

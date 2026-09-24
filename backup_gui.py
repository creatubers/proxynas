#!/usr/bin/env python3
"""
Proxynas - Proxies Blackmagic RAW y backup AV1 portable
Compatible con Windows y Linux.
Transcodifica vídeo a AV1 (hardware), audio a Opus, imágenes RAW a PNG.
"""

import os
import sys
import platform
import subprocess
import shutil
import json
import re
import tempfile
import filecmp
import time
import threading
import urllib.error
import urllib.request
import webbrowser
import zipfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from os.path import basename

import proxygenerator as braw_proxy
from proxyregistry import ProxyRegistry

# ─────────────────────────────────────────────
# Constantes y extensiones
# ─────────────────────────────────────────────

AUDIO_EXTENSIONS = {'.wav', '.flac'}
IMAGE_EXTENSIONS = {'.tiff', '.rw2', '.cr2', '.arw'}
BRAW_EXTENSIONS = {'.braw'}
# El aviso al elegir carpeta no baja más de aquí: las tarjetas de camara son
# poco profundas y así no se recorre entero un archivo grande (solo afecta al aviso,
# no a los gates de proxy/backup, que siguen mirando el arbol completo).
BRAW_SCAN_DEPTH = 3
VIDEO_EXTENSIONS = {'.mov', '.webm', '.avi', '.mp4', '.mkv', '.mpg', '.mpeg', '.wmv', '.mts'} | BRAW_EXTENSIONS
ALL_PROCESSED_EXTENSIONS = AUDIO_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'


# ffmpeg, ffprobe y braw_decode son aplicaciones de consola: en un ejecutable
# sin consola cada llamada abre una ventana que parpadea. Todos los procesos
# hijos pasan por Popen, así que se parchea ahi una sola vez en lugar de
# repetir creationflags en cada subprocess.run del proyecto.
def _hide_child_console_windows():
    original_init = subprocess.Popen.__init__

    def patched_init(self, *args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = patched_init


if IS_WINDOWS:
    _hide_child_console_windows()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(SCRIPT_DIR, 'vendor')
if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)
PORTABLE_BIN_DIR = os.path.join(SCRIPT_DIR, 'portable', 'bin')
PORTABLE_SDK_DIR = os.path.join(SCRIPT_DIR, 'portable', 'sdk')
FFMPEG_DOWNLOAD_URL = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
FFMPEG_MIN_BUILD_DATE = '20260819'
# braw_decode.exe es un binario de Windows, así que el SDK útil es el de Windows.
BRAW_SDK_URL = 'https://www.blackmagicdesign.com/support/latest-download/braw-sdk/windows'
BRAW_SDK_HELP = (
    'El SDK de Blackmagic RAW no se puede distribuir con Proxynas, así que hay que\n'
    'descargarlo una vez desde la web oficial de Blackmagic:\n\n'
    f'  {BRAW_SDK_URL}\n\n'
    '  1. Abre esa página y descarga el SDK para Windows.\n'
    '  2. Vuelve a Proxynas y pulsa «Importar SDK BRAW (zip)».\n'
    '  3. Elige el zip descargado: Proxynas copiará los ficheros necesarios.\n\n'
    'Sin el SDK, todo sigue funcionando excepto los ficheros .braw.'
)

FFMPEG_HELP = (
    'Proxynas descarga FFmpeg automáticamente al arrancar, así que lo más\n'
    'probable es que esa descarga no llegara a completarse.\n\n'
    'Cierra y vuelve a abrir Proxynas para reintentarla. Si el problema\n'
    'continúa, comprueba la conexión a Internet.'
)


# La resolucion de herramientas vive en proxygenerator, que es quien lanza
# ffmpeg: duplicarla hacia que la GUI encontrara ffmpeg en el PATH y el
# generador de proxies no, y el fallo se veia como un encoder inexistente.
FFMPEG_BIN = braw_proxy.resolve_tool('ffmpeg')
FFPROBE_BIN = braw_proxy.resolve_tool('ffprobe')
APP_NAME = 'Proxynas'
APP_SUBTITLE = 'Proxies Blackmagic RAW y backup AV1 portable'
ICON_PATH = os.path.join(SCRIPT_DIR, 'proxynas.png')
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'proxynas_config.json')
LEGACY_CONFIG_PATH = os.path.join(SCRIPT_DIR, 'backup_gui_config.json')
REGISTRY_PATH = os.path.join(SCRIPT_DIR, 'proxynas_registry.json')
BRAW_BACKUP_SCALE = "1"
BRAW_BACKUP_WIDTH = 1920

CODEC_AV1_HW = 'av1_hw'
CODEC_HEVC_HW = 'hevc_hw'
CODEC_HEVC_SW = 'hevc_sw'
DEFAULT_CODEC_PRESET = CODEC_AV1_HW

AUDIO_NO_TRANSCODE = 'no_transcode'
AUDIO_WAV_PCM = 'wav_pcm'
AUDIO_AAC_M4A = 'aac_m4a'
AUDIO_OPUS_MP4 = 'opus_mp4'
DEFAULT_AUDIO_PRESET = AUDIO_NO_TRANSCODE

ACCEL_GPU = 'hw'
ACCEL_CPU = 'sw'
ACCEL_LABELS = {
    ACCEL_GPU: 'GPU (hardware)',
    ACCEL_CPU: 'CPU (software)',
}

CODEC_PRESET_LABELS = {
    CODEC_AV1_HW: 'AV1 hardware',
    CODEC_HEVC_HW: 'H.265 hardware',
    CODEC_HEVC_SW: 'H.265 software',
}

AUDIO_PRESET_LABELS = {
    AUDIO_NO_TRANSCODE: 'No transcodificar',
    AUDIO_WAV_PCM: 'WAV PCM',
    AUDIO_AAC_M4A: 'AAC M4A',
    AUDIO_OPUS_MP4: 'Opus MP4',
}

CODEC_PRESET_TARGETS = {
    CODEC_AV1_HW: 'av1',
    CODEC_HEVC_HW: 'hevc',
    CODEC_HEVC_SW: 'hevc',
}

HARDWARE_ENCODERS = {
    CODEC_AV1_HW: {
        'nvidia': 'av1_nvenc',
        'amd': 'av1_amf',
        'intel': 'av1_qsv',
    },
    CODEC_HEVC_HW: {
        'nvidia': 'hevc_nvenc',
        'amd': 'hevc_amf',
        'intel': 'hevc_qsv',
    },
}

SOFTWARE_ENCODERS = {
    CODEC_HEVC_SW: 'libx265',
}

_ENCODER_CAPABILITIES_CACHE = None

class RoundedButton(tk.Canvas):
    def __init__(self, master, app, text, command=None, kind='secondary', bg_key='surface', min_width=None):
        self.app = app
        self.text = text
        self.command = command
        self.kind = kind
        self.bg_key = bg_key
        self._state = 'normal'
        self._hover = False
        self._font = tkfont.Font(family='Segoe UI Semibold' if kind == 'primary' else 'Segoe UI', size=10)
        width = max(min_width or 0, self._font.measure(text) + 46)
        super().__init__(master, width=width, height=46, highlightthickness=0, bd=0, relief='flat', cursor='hand2')
        self.bind('<Configure>', lambda _event: self._draw())
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Button-1>', self._on_click)
        self._draw()

    def _palette(self):
        c = getattr(self.app, 'colors', self.app._palette())
        if self.kind == 'primary':
            normal = c['text'] if not self.app.dark_mode_var.get() else c['accent']
            return {
                'bg': c.get(self.bg_key, c['surface']),
                'fill': c['border'] if self._state == 'disabled' else (c['accent_2'] if self._hover else normal),
                'outline': None,
                'text': c['muted'] if self._state == 'disabled' else (c['surface'] if self.app.dark_mode_var.get() else '#ffffff'),
            }
        if self.kind == 'danger':
            return {
                'bg': c.get(self.bg_key, c['surface']),
                'fill': c['border'] if self._hover and self._state != 'disabled' else c['surface_2'],
                'outline': c['border'],
                'text': c['muted'] if self._state == 'disabled' else c['danger'],
            }
        return {
            'bg': c.get(self.bg_key, c['surface']),
            'fill': c['border'] if self._hover and self._state != 'disabled' else c['surface_2'],
            'outline': c['border'],
            'text': c['muted'] if self._state == 'disabled' else c['text'],
        }

    def _rounded_rect(self, x1, y1, x2, y2, radius, fill, outline=None):
        self.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline='')
        self.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline='')
        self.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, fill=fill, outline='')
        self.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, fill=fill, outline='')
        self.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, fill=fill, outline='')
        self.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, fill=fill, outline='')
        if outline:
            self.create_arc(x1, y1, x1 + radius * 2, y1 + radius * 2, start=90, extent=90, outline=outline, width=1, style='arc')
            self.create_arc(x2 - radius * 2, y1, x2, y1 + radius * 2, start=0, extent=90, outline=outline, width=1, style='arc')
            self.create_arc(x2 - radius * 2, y2 - radius * 2, x2, y2, start=270, extent=90, outline=outline, width=1, style='arc')
            self.create_arc(x1, y2 - radius * 2, x1 + radius * 2, y2, start=180, extent=90, outline=outline, width=1, style='arc')
            self.create_line(x1 + radius, y1, x2 - radius, y1, fill=outline)
            self.create_line(x2, y1 + radius, x2, y2 - radius, fill=outline)
            self.create_line(x1 + radius, y2, x2 - radius, y2, fill=outline)
            self.create_line(x1, y1 + radius, x1, y2 - radius, fill=outline)

    def _draw(self):
        p = self._palette()
        super().configure(bg=p['bg'])
        self.delete('all')
        w = max(self.winfo_width(), int(float(self['width'])))
        h = max(self.winfo_height(), int(float(self['height'])))
        try:
            from PIL import Image, ImageDraw, ImageTk

            ss = 3
            img = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            def hex_to_rgb(value):
                value = value.lstrip('#')
                return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

            box = [1 * ss, 1 * ss, (w - 2) * ss, (h - 2) * ss]
            draw.rounded_rectangle(
                box,
                radius=8 * ss,
                fill=hex_to_rgb(p['fill']),
                outline=hex_to_rgb(p['outline']) if p['outline'] else None,
                width=1 * ss,
            )
            img = img.resize((w, h), Image.LANCZOS)
            self._bg_image = ImageTk.PhotoImage(img)
            self.create_image(0, 0, image=self._bg_image, anchor='nw')
        except Exception:
            self._rounded_rect(1, 1, w - 2, h - 2, 8, p['fill'], p['outline'])
        self.create_text(w / 2, h / 2, text=self.text, fill=p['text'], font=self._font)

    def _on_enter(self, _event):
        self._hover = True
        self._draw()

    def _on_leave(self, _event):
        self._hover = False
        self._draw()

    def _on_click(self, _event):
        if self._state != 'disabled' and self.command:
            self.command()

    def configure(self, cnf=None, **kwargs):
        cnf = cnf or {}
        if isinstance(cnf, str):
            return super().configure(cnf)
        kwargs.update(cnf)
        redraw = False
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
            super().configure(cursor='arrow' if self._state == 'disabled' else 'hand2')
            redraw = True
        if 'text' in kwargs:
            self.text = kwargs.pop('text')
            redraw = True
        if 'command' in kwargs:
            self.command = kwargs.pop('command')
        result = super().configure(**kwargs)
        if redraw:
            self._draw()
        return result

    config = configure

    def refresh_theme(self):
        self._draw()

# ─────────────────────────────────────────────
# Utilidades multiplataforma
# ─────────────────────────────────────────────

def enable_high_dpi():
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def load_config():
    for config_path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            with open(config_path, 'r', encoding='utf-8') as config_file:
                return json.load(config_file)
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def save_config(config):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as config_file:
            json.dump(config, config_file, indent=2)
    except OSError:
        pass


def _portable_ffmpeg_is_current():
    if not (os.path.isfile(FFMPEG_BIN) and os.path.isfile(FFPROBE_BIN)):
        return False
    try:
        result = subprocess.run(
            [FFMPEG_BIN, '-hide_banner', '-version'],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    build_dates = re.findall(r'20\d{6}', result.stdout.splitlines()[0])
    return any(date >= FFMPEG_MIN_BUILD_DATE for date in build_dates)


def ensure_ffmpeg():
    """Actualiza FFmpeg portable si falta o es anterior al snapshot requerido."""
    portable_pair = (
        os.path.isfile(os.path.join(PORTABLE_BIN_DIR, 'ffmpeg.exe')) and
        os.path.isfile(os.path.join(PORTABLE_BIN_DIR, 'ffprobe.exe'))
    )
    if portable_pair and _portable_ffmpeg_is_current():
        return True
    if not portable_pair and shutil.which('ffmpeg') and shutil.which('ffprobe'):
        return True
    if not IS_WINDOWS:
        return False

    archive_path = os.path.join(tempfile.gettempdir(), 'proxynas-ffmpeg.zip')
    try:
        os.makedirs(PORTABLE_BIN_DIR, exist_ok=True)
        urllib.request.urlretrieve(FFMPEG_DOWNLOAD_URL, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            for filename, target in (('ffmpeg.exe', FFMPEG_BIN), ('ffprobe.exe', FFPROBE_BIN)):
                entry = next(name for name in names if name.lower().endswith(f'/bin/{filename}'))
                temporary_target = f'{target}.download'
                with archive.open(entry) as source, open(temporary_target, 'wb') as destination:
                    shutil.copyfileobj(source, destination)
                os.replace(temporary_target, target)
        return os.path.isfile(FFMPEG_BIN) and os.path.isfile(FFPROBE_BIN)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, StopIteration):
        return False
    finally:
        try:
            os.remove(archive_path)
        except OSError:
            pass


def find_google_drive_path():
    """Intenta encontrar Google Drive montado como volumen (solo Windows)."""
    if not IS_WINDOWS:
        return None
    try:
        import psutil
        import win32api
        drives = [i.mountpoint for i in psutil.disk_partitions()
                  if 'cdrom' not in i.opts and i.mountpoint]
        for drive in drives:
            try:
                if os.path.isdir(drive):
                    vol_name = win32api.GetVolumeInformation(drive)[0]
                    if vol_name == 'Google Drive':
                        return drive
            except Exception:
                continue
    except ImportError:
        pass
    return None


def get_gpu_name():
    """Detecta la GPU del sistema de forma multiplataforma."""
    if IS_WINDOWS:
        try:
            cmd = [
                "powershell", "-Command",
                "Get-CimInstance -ClassName Win32_VideoController | "
                "Select-Object -ExpandProperty Name"
            ]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            return " ".join(lines)
        except Exception:
            return ""
    else:  # Linux
        # Intentar lspci primero
        try:
            output = subprocess.check_output(
                ["lspci"], text=True, stderr=subprocess.DEVNULL
            )
            for line in output.splitlines():
                low = line.lower()
                if 'vga' in low or '3d controller' in low or 'display' in low:
                    return line.split(': ', 1)[-1] if ': ' in line else line
        except Exception:
            pass
        # Intentar nvidia-smi
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                text=True, stderr=subprocess.DEVNULL
            )
            name = output.strip()
            if name:
                return name
        except Exception:
            pass
        # Intentar vainfo (Intel/AMD)
        try:
            output = subprocess.check_output(
                ["vainfo"], text=True, stderr=subprocess.DEVNULL
            )
            if output:
                return f"VA-API device: {output.splitlines()[0]}"
        except Exception:
            pass
        return ""


def select_av1_encoder():
    """Selecciona el codificador AV1 hardware según la GPU detectada."""
    gpu = get_gpu_name().lower()
    if not gpu:
        return None, ""
    if "nvidia" in gpu:
        return "av1_nvenc", gpu
    elif "amd" in gpu or "radeon" in gpu:
        return "av1_amf", gpu
    elif "intel" in gpu or "uhd" in gpu or "arc" in gpu or "iris" in gpu:
        return "av1_qsv", gpu
    return None, gpu


def gpu_vendor_order(gpu_name):
    """Ordena proveedores probables sin descartar otros encoders disponibles."""
    gpu = (gpu_name or '').lower()
    vendors = []
    if 'nvidia' in gpu:
        vendors.append('nvidia')
    if 'amd' in gpu or 'radeon' in gpu:
        vendors.append('amd')
    if any(x in gpu for x in ('intel', 'uhd', 'arc', 'iris')):
        vendors.append('intel')
    for vendor in ('nvidia', 'amd', 'intel'):
        if vendor not in vendors:
            vendors.append(vendor)
    return vendors


def encoder_options(encoder, bitrate='1500k', probe=False):
    """Opciones específicas por familia de encoder."""
    if encoder.endswith('_nvenc'):
        pix_fmt = 'p010le' if encoder.startswith(('av1_', 'hevc_')) else 'yuv420p'
        return [
            '-c:v', encoder,
            '-pix_fmt', pix_fmt,
            '-preset', 'p5',
            '-b:v', bitrate,
        ]
    if encoder.endswith('_amf'):
        pix_fmt = 'p010le' if encoder.startswith(('av1_', 'hevc_')) else 'yuv420p'
        return [
            '-c:v', encoder,
            '-pix_fmt', pix_fmt,
            '-quality', 'balanced',
            '-b:v', bitrate,
        ]
    if encoder.endswith('_qsv'):
        pix_fmt = 'p010le' if encoder.startswith(('av1_', 'hevc_')) else 'yuv420p'
        return [
            '-c:v', encoder,
            '-pix_fmt', pix_fmt,
            '-preset', 'medium',
            '-b:v', bitrate,
        ]
    if encoder == 'libx265':
        return [
            '-c:v', encoder,
            '-pix_fmt', 'yuv420p10le',
            '-preset', 'medium',
            '-x265-params', 'log-level=error',
            '-b:v', bitrate,
        ]
    return ['-c:v', encoder, '-pix_fmt', 'yuv420p', '-b:v', bitrate]


def encoder_input_options(encoder):
    # QSV is required for encoding only. Forcing QSV decoding here rejects
    # formats the Intel decoder does not support, such as ProRes or FFV1.
    return []


def test_encoder(encoder):
    """Prueba el encoder real con ffmpeg y opciones equivalentes al backup."""
    cmd = [
        FFMPEG_BIN, '-hide_banner', '-loglevel', 'error',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30',
        '-frames:v', '15', '-an',
    ]
    cmd.extend(encoder_options(encoder, '600k', probe=True))
    cmd.extend(['-f', 'null', '-'])
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        return True, ''
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or '').strip().splitlines()
        return False, detail[-1] if detail else f'ffmpeg código {e.returncode}'
    except Exception as e:
        return False, str(e)


def detect_encoder_capabilities(force=False):
    """Detecta presets disponibles probando encoders reales de este equipo."""
    global _ENCODER_CAPABILITIES_CACHE
    if _ENCODER_CAPABILITIES_CACHE is not None and not force:
        return _ENCODER_CAPABILITIES_CACHE

    gpu_name = get_gpu_name()
    available, ffmpeg_error = braw_proxy.ffmpeg_encoder_list()
    # Si ffmpeg ni responde, decirlo; 'no listado por ffmpeg' para todos los
    # codecs parecia un problema de los encoders y era de ffmpeg.
    list_reason = ffmpeg_error or 'no listado por ffmpeg'
    capabilities = {
        'gpu': gpu_name,
        'presets': {},
        'encoders': available,
    }

    for preset, vendor_map in HARDWARE_ENCODERS.items():
        tested = []
        selected = None
        reason = 'Sin encoder compatible en este ffmpeg'
        for vendor in gpu_vendor_order(gpu_name):
            encoder = vendor_map[vendor]
            if encoder not in available:
                tested.append(f'{encoder}: {list_reason}')
                continue
            ok, detail = test_encoder(encoder)
            tested.append(f'{encoder}: {"OK" if ok else detail}')
            if ok:
                selected = encoder
                reason = ''
                break
            reason = f'{encoder}: {detail}'
        capabilities['presets'][preset] = {
            'available': selected is not None,
            'encoder': selected,
            'reason': reason,
            'tested': tested,
        }

    for preset, encoder in SOFTWARE_ENCODERS.items():
        reason = list_reason
        selected = None
        tested = []
        if encoder in available:
            ok, detail = test_encoder(encoder)
            tested.append(f'{encoder}: {"OK" if ok else detail}')
            if ok:
                selected = encoder
                reason = ''
            else:
                reason = f'{encoder}: {detail}'
        else:
            tested.append(f'{encoder}: {list_reason}')
        capabilities['presets'][preset] = {
            'available': selected is not None,
            'encoder': selected,
            'reason': reason,
            'tested': tested,
        }

    _ENCODER_CAPABILITIES_CACHE = capabilities
    return capabilities


def select_encoder_for_preset(preset, capabilities=None):
    capabilities = capabilities or detect_encoder_capabilities()
    data = capabilities.get('presets', {}).get(preset, {})
    return data.get('encoder') if data.get('available') else None


def select_av1_encoder():
    """Compatibilidad con código antiguo: selecciona AV1 hardware validado."""
    caps = detect_encoder_capabilities()
    return select_encoder_for_preset(CODEC_AV1_HW, caps), caps.get('gpu', '')


def check_ffmpeg():
    """Verifica que ffmpeg y ffprobe esten disponibles (portable o PATH)."""
    for tool_path, tool_name in ((FFMPEG_BIN, 'ffmpeg'), (FFPROBE_BIN, 'ffprobe')):
        if not os.path.isfile(tool_path) and shutil.which(tool_name) is None:
            return False, tool_name
    return True, None


def check_braw_tools():
    """Verifica el decodificador BRAW y el SDK portable (no FFmpeg)."""
    try:
        braw_proxy.check_braw_tools()
        return True, None
    except FileNotFoundError as exc:
        return False, str(exc)


def check_magick():
    """Verifica que ImageMagick este disponible."""
    return shutil.which('magick') is not None


def proxy_extension_for(source_path):
    return ".MOV" if os.path.splitext(source_path)[1] == ".MOV" else ".mov"



NAS_STABILITY_WAIT_SECONDS = 2
NAS_STABILITY_CHECKS = 3
PARTIAL_MARKER = '.partial'


class BackupCancelled(Exception):
    pass


def is_source_ready(filepath, cancel_check=None):
    try:
        previous_size = os.path.getsize(filepath)
        if previous_size == 0:
            return False
        for _ in range(NAS_STABILITY_CHECKS):
            for _ in range(int(NAS_STABILITY_WAIT_SECONDS * 10)):
                if cancel_check and cancel_check():
                    raise BackupCancelled()
                time.sleep(0.1)
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
        return f'{root}{PARTIAL_MARKER}{ext}'
    return f'{output_path}{PARTIAL_MARKER}'


def remove_file_quietly(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def promote_partial_output(partial_path, output_path):
    if not os.path.exists(partial_path) or os.path.getsize(partial_path) == 0:
        raise RuntimeError(f'Salida temporal inválida: {partial_path}')
    os.replace(partial_path, output_path)


def atomic_copyfile(source_path, output_path):
    partial_path = temporary_output_path(output_path)
    remove_file_quietly(partial_path)
    try:
        shutil.copyfile(source_path, partial_path)
        promote_partial_output(partial_path, output_path)
    except Exception:
        remove_file_quietly(partial_path)
        raise


def contains_files(root_dir, extensions, max_depth=None):
    for root, dirs, files in os.walk(root_dir):
        if max_depth is not None and os.path.relpath(root, root_dir).count(os.sep) >= max_depth:
            dirs[:] = []
        for filename in files:
            if os.path.splitext(filename)[1].lower() in extensions:
                return True
    return False


# ─────────────────────────────────────────────
# Lógica de procesamiento
# ─────────────────────────────────────────────

class BackupProcessor:
    """Motor de backup con callbacks para la GUI."""

    def __init__(self, src_dir, dst_dir, log_callback=None, progress_callback=None, detail_callback=None, backup_braw_originals=False, codec_preset=DEFAULT_CODEC_PRESET, encoder_capabilities=None, audio_preset=DEFAULT_AUDIO_PRESET):
        self.src_dir = src_dir
        self.dst_dir = dst_dir
        self.log = log_callback or print
        self.progress = progress_callback or (lambda *a: None)
        self.detail = detail_callback or (lambda *a: None)
        self.backup_braw_originals = backup_braw_originals
        self.codec_preset = codec_preset
        self.encoder_capabilities = encoder_capabilities or detect_encoder_capabilities()
        self.audio_preset = audio_preset
        self.cancelled = False
        self._active_processes = set()
        self.stats = {
            'videos': 0, 'audio': 0, 'images': 0,
            'copied': 0, 'skipped': 0, 'errors': 0
        }

    def cancel(self):
        self.cancelled = True
        for process in list(self._active_processes):
            try:
                process.kill()
            except OSError:
                pass

    def _run_ffmpeg(self, cmd, duration=0, label=''):
        if self.cancelled:
            raise BackupCancelled()
        process = subprocess.Popen(
            [*cmd, '-nostats', '-progress', 'pipe:2'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self._active_processes.add(process)
        try:
            stderr_lines = []
            progress_data = {}
            if process.stderr:
                for line in process.stderr:
                    if self.cancelled:
                        process.kill()
                        raise BackupCancelled()
                    line = line.strip()
                    if '=' not in line:
                        stderr_lines.append(line)
                        continue
                    key, value = line.split('=', 1)
                    progress_data[key] = value
                    if key in ('out_time_ms', 'speed') and duration:
                        try:
                            seconds = int(progress_data.get('out_time_ms', 0)) / 1_000_000
                            percent = min(100, seconds / duration * 100)
                            self.detail(label, percent, progress_data.get('speed', ''))
                        except ValueError:
                            pass
            process.wait()
            if self.cancelled:
                raise BackupCancelled()
            stderr = '\n'.join(stderr_lines)
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, cmd, stderr=stderr)
            return stderr
        finally:
            self._active_processes.discard(process)

    @staticmethod
    def _media_duration(path):
        try:
            result = subprocess.check_output([
                FFPROBE_BIN, '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', path,
            ], stderr=subprocess.DEVNULL, text=True)
            return float(result.strip())
        except (OSError, ValueError, subprocess.CalledProcessError):
            return 0

    def count_files(self, extensions):
        """Cuenta archivos que coinciden con las extensiones dadas."""
        count = 0
        for root, dirs, files in os.walk(self.src_dir):
            for f in files:
                _, suffix = os.path.splitext(f)
                if suffix.lower() in extensions:
                    count += 1
        return count

    def count_remaining_files(self):
        """Cuenta archivos que no son procesados (para copia directa)."""
        count = 0
        for root, dirs, files in os.walk(self.src_dir):
            for f in files:
                _, suffix = os.path.splitext(f)
                if suffix.lower() not in ALL_PROCESSED_EXTENSIONS and f.lower() != 'thumbs.db':
                    count += 1
        return count

    def process_files(self, extensions, process_function):
        """Itera sobre archivos con extensiones dadas y aplica la función."""
        for root, dirs, files in os.walk(self.src_dir):
            if self.cancelled:
                return
            for f in files:
                if self.cancelled:
                    return
                prefix, suffix = os.path.splitext(f)
                if suffix.lower() in extensions:
                    abspath_in = os.path.join(root, f)
                    rel_path = os.path.relpath(root, self.src_dir)
                    dir_out = os.path.normpath(os.path.join(self.dst_dir, rel_path))
                    Path(dir_out).mkdir(parents=True, exist_ok=True)
                    try:
                        if not is_source_ready(abspath_in, lambda: self.cancelled):
                            self.log(f'  En transferencia, se reintentará más tarde: {f}')
                            self.stats['skipped'] += 1
                            continue
                        process_function(abspath_in, dir_out, prefix, suffix)
                    except BackupCancelled:
                        self.log(f'  ⚠ Cancelado: {f}')
                        return
                    except Exception as e:
                        self.log(f"  ✗ Error procesando {f}: {e}")
                        self.stats['errors'] += 1
                    finally:
                        self.progress()

    def process_audio(self, abspath_in, dir_out, prefix, suffix):
        if self.audio_preset == AUDIO_NO_TRANSCODE:
            abspath_out = os.path.join(dir_out, prefix + suffix)
        else:
            audio_suffix = 'AUDIO' if prefix.isupper() else 'audio'
            if self.audio_preset == AUDIO_WAV_PCM:
                ext = '.WAV' if prefix.isupper() else '.wav'
            elif self.audio_preset == AUDIO_AAC_M4A:
                ext = '.M4A' if prefix.isupper() else '.m4a'
            elif self.audio_preset == AUDIO_OPUS_MP4:
                ext = '.MP4' if prefix.isupper() else '.mp4'
            else:
                ext = suffix
            abspath_out = os.path.join(dir_out, f"{prefix}.{audio_suffix}{ext}")

        if os.path.exists(abspath_out):
            self.stats['skipped'] += 1
            return

        if self.audio_preset == AUDIO_NO_TRANSCODE:
            self.log(f"  Audio original: {basename(abspath_in)}")
            atomic_copyfile(abspath_in, abspath_out)
            self.stats['audio'] += 1
            return

        self.log(f"  Audio {AUDIO_PRESET_LABELS.get(self.audio_preset, self.audio_preset)}: {basename(abspath_in)}")
        partial_out = temporary_output_path(abspath_out)
        remove_file_quietly(partial_out)
        try:
            cmd = [FFMPEG_BIN, '-i', abspath_in, '-vn', '-sn', '-dn']
            if self.audio_preset == AUDIO_WAV_PCM:
                cmd.extend(['-c:a', 'pcm_s24le'])
            elif self.audio_preset == AUDIO_AAC_M4A:
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
            elif self.audio_preset == AUDIO_OPUS_MP4:
                cmd.extend(['-c:a', 'libopus', '-vbr', 'on', '-compression_level', '10', '-frame_duration', '60'])
            else:
                raise ValueError(f"Perfil de audio desconocido: {self.audio_preset}")
            cmd.extend(['-map', '0:a:0', '-y', partial_out])
            self._run_ffmpeg(cmd, self._media_duration(abspath_in), basename(abspath_in))
            promote_partial_output(partial_out, abspath_out)
            self.stats['audio'] += 1
        except Exception:
            remove_file_quietly(partial_out)
            raise
    def process_images(self, abspath_in, dir_out, prefix, suffix):
        ext = '.PNG' if prefix.isupper() else '.png'
        abspath_out = os.path.join(dir_out, prefix + ext)

        if os.path.exists(abspath_out):
            self.stats['skipped'] += 1
            return

        self.log(f"  Imagen: {basename(abspath_in)}")
        partial_out = temporary_output_path(abspath_out)
        remove_file_quietly(partial_out)
        try:
            subprocess.run([
                'magick', '-quality', '95', abspath_in, '-auto-orient', partial_out
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            promote_partial_output(partial_out, abspath_out)
            self.stats['images'] += 1
        except Exception:
            remove_file_quietly(partial_out)
            raise
    def process_braw(self, abspath_in, dir_out, prefix, suffix, create_proxy=True):
        """Convierte BRAW a MP4 de backup y opcionalmente copia el original."""
        abspath_out = os.path.join(dir_out, prefix + suffix)
        mp4_ext = '.MP4' if prefix.isupper() else '.mp4'
        mp4_out = os.path.join(dir_out, prefix + mp4_ext)
        changed = False

        should_copy_original = self.backup_braw_originals or not create_proxy
        if should_copy_original and not os.path.exists(abspath_out):
            self.log(f"  BRAW original: {basename(abspath_in)}")
            atomic_copyfile(abspath_in, abspath_out)
            changed = True

        if create_proxy:
            if not os.path.exists(mp4_out):
                self.log(f"  BRAW a {CODEC_PRESET_LABELS.get(self.codec_preset, self.codec_preset)}: {basename(mp4_out)}")
                self.create_braw_backup_video(abspath_in, mp4_out)
                changed = True

        if changed:
            self.stats['videos'] += 1
        else:
            self.stats['skipped'] += 1

    def create_braw_backup_video(self, abspath_in, abspath_out):
        ok, missing = check_braw_tools()
        if not ok:
            raise RuntimeError(f"Herramientas BRAW no disponibles: {missing}")

        target_codec = select_encoder_for_preset(self.codec_preset, self.encoder_capabilities)
        if not target_codec:
            preset_data = self.encoder_capabilities.get('presets', {}).get(self.codec_preset, {})
            reason = preset_data.get('reason') or 'no disponible'
            raise RuntimeError(f"Encoder {CODEC_PRESET_LABELS.get(self.codec_preset, self.codec_preset)} no disponible: {reason}")

        info = self.get_braw_backup_info(abspath_in)
        width = int(info["width"])
        height = int(info["height"])
        frame_rate = str(info["frame_rate"])
        timecode = info.get("timecode") or "00:00:00:00"

        partial_out = temporary_output_path(abspath_out)
        remove_file_quietly(partial_out)
        decode_cmd = [
            braw_proxy.BRAW_DECODE,
            "--raw",
            "--sdk",
            braw_proxy.SDK_DIR,
            "--scale",
            BRAW_BACKUP_SCALE,
            abspath_in,
        ]
        cmd = [
            FFMPEG_BIN,
            "-hide_banner",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", braw_proxy.BRAW_RAW_PIX_FMT,
            "-s", f"{width}x{height}",
            "-r", frame_rate,
            "-i", "-",
            "-timecode", timecode,
            *braw_proxy.get_format_metadata_args(abspath_in),
        ]
        cmd.extend(encoder_options(target_codec, braw_proxy.VIDEO_BITRATE))
        if width != BRAW_BACKUP_WIDTH:
            cmd.extend(["-vf", f"scale={BRAW_BACKUP_WIDTH}:-2"])
        if CODEC_PRESET_TARGETS.get(self.codec_preset) == 'hevc':
            cmd.extend(["-tag:v", "hvc1"])
        cmd.extend([
            "-color_range", "pc",
            "-movflags", "+faststart+use_metadata_tags",
        ])
        cmd.extend([
            *braw_proxy.get_color_args(abspath_in),
            partial_out,
        ])

        decoder = subprocess.Popen(
            decode_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(abspath_in),
        )
        ffmpeg = subprocess.Popen(
            cmd,
            stdin=decoder.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        decoder.stdout.close()
        decoder_stderr_chunks = []

        def drain_decoder_stderr():
            try:
                for chunk in decoder.stderr:
                    decoder_stderr_chunks.append(chunk)
            except Exception:
                pass

        stderr_thread = threading.Thread(target=drain_decoder_stderr, daemon=True)
        stderr_thread.start()
        ffmpeg_stderr = ffmpeg.communicate()[1]
        stderr_thread.join()
        decoder_stderr = b"".join(decoder_stderr_chunks).decode("utf-8", errors="replace")
        decoder_return = decoder.wait()
        if decoder_return != 0:
            remove_file_quietly(partial_out)
            raise RuntimeError(f"braw_decode finalizó con código {decoder_return}: {decoder_stderr.strip()}")
        if ffmpeg.returncode != 0:
            remove_file_quietly(partial_out)
            raise RuntimeError(f"ffmpeg finalizó con código {ffmpeg.returncode}: {(ffmpeg_stderr or '').strip()}")
        promote_partial_output(partial_out, abspath_out)

    def get_braw_backup_info(self, abspath_in):
        result = subprocess.run(
            [
                braw_proxy.BRAW_DECODE,
                "--info",
                "--sdk",
                braw_proxy.SDK_DIR,
                "--scale",
                BRAW_BACKUP_SCALE,
                abspath_in,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def process_videos(self, abspath_in, dir_out, prefix, suffix):
        rel_dir = os.path.relpath(os.path.dirname(abspath_in), self.src_dir)
        if any(part.lower() == 'proxy' for part in rel_dir.split(os.sep)):
            self.process_videos_copy(abspath_in, dir_out, prefix, suffix)
            return

        ext = suffix.lower()
        if ext in BRAW_EXTENSIONS:
            self.process_braw(abspath_in, dir_out, prefix, suffix, create_proxy=True)
            return
        if ext == '.mkv':
            extension = '.mkv'
        else:
            extension = '.mp4'
        if prefix.isupper():
            extension = extension.upper()

        abspath_out = os.path.join(dir_out, prefix + extension)

        if os.path.exists(abspath_out):
            self.stats['skipped'] += 1
            return

        # Detectar códec actual
        codec_output = ""
        pixel_format = ""
        try:
            codec_cmd = [
                FFPROBE_BIN, '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'default=noprint_wrappers=1:nokey=1', abspath_in
            ]
            codec_output = subprocess.check_output(
                codec_cmd, stderr=subprocess.DEVNULL
            ).decode('utf-8').strip().lower()
        except subprocess.CalledProcessError:
            pass
        try:
            pixel_format = subprocess.check_output([
                FFPROBE_BIN, '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=pix_fmt',
                '-of', 'default=noprint_wrappers=1:nokey=1', abspath_in
            ], stderr=subprocess.DEVNULL).decode('utf-8').strip().lower()
        except subprocess.CalledProcessError:
            pass

        target_family = CODEC_PRESET_TARGETS.get(self.codec_preset, 'av1')
        already_target = (
            target_family == 'av1' and 'av1' in codec_output
        ) or (
            target_family == 'hevc' and ('hevc' in codec_output or 'h265' in codec_output)
        )

        if already_target:
            self.log(f"  Ya {CODEC_PRESET_LABELS.get(self.codec_preset, target_family)}, copiando: {basename(abspath_in)}")
            atomic_copyfile(abspath_in, abspath_out)
            self.stats['videos'] += 1
            return

        target_codec = select_encoder_for_preset(self.codec_preset, self.encoder_capabilities)
        if not target_codec:
            preset_data = self.encoder_capabilities.get('presets', {}).get(self.codec_preset, {})
            reason = preset_data.get('reason') or 'no disponible'
            self.log(f"  Encoder {CODEC_PRESET_LABELS.get(self.codec_preset, self.codec_preset)} no disponible ({reason}). Copiando original: {basename(abspath_in)}")
            self._copy_original_video_fallback(abspath_in, dir_out, prefix, suffix)
            self.stats['errors'] += 1
            return

        # Calcular bitrate
        bitrate = 0
        try:
            br_cmd = [
                FFPROBE_BIN, abspath_in,
                '-show_entries', 'format=bit_rate',
                '-v', 'quiet', '-of', 'json'
            ]
            br_output = subprocess.check_output(br_cmd).decode('utf-8')
            br_data = json.loads(br_output)
            if 'format' in br_data and 'bit_rate' in br_data['format']:
                bitrate = int(br_data['format']['bit_rate']) / 1000
        except Exception:
            pass

        bitratefinal = '3000k' if bitrate > 4000 else '1500k'

        self.log(f"  🎬 Transcodificando ({target_codec}, {bitratefinal}): {basename(abspath_in)}")

        partial_out = temporary_output_path(abspath_out)
        remove_file_quietly(partial_out)
        try:
            cmd = [FFMPEG_BIN]
            cmd.extend(encoder_input_options(target_codec))
            cmd.extend(['-i', abspath_in])
            cmd.extend(encoder_options(target_codec, bitratefinal))
            cmd.extend([
                '-c:a', 'aac',
                '-map', '0', '-map', '-0:d',
                '-sn',
                '-y', partial_out
            ])

            try:
                self._run_ffmpeg(cmd, self._media_duration(abspath_in), basename(abspath_in))
            except subprocess.CalledProcessError as e:
                if target_codec == 'av1_nvenc' and pixel_format.startswith(('yuv422', 'yuv444')):
                    retry_cmd = cmd.copy()
                    encoder_pos = retry_cmd.index('-c:v')
                    retry_cmd[encoder_pos:encoder_pos] = ['-vf', 'libplacebo=format=p010le']
                    if pixel_format.startswith('yuv444'):
                        output_pos = retry_cmd.index('-y')
                        retry_cmd[output_pos:output_pos] = [
                            '-color_range', 'tv',
                            '-colorspace', 'bt709',
                            '-color_trc', 'bt709',
                            '-color_primaries', 'bt709',
                        ]
                    self.log(f"  ↻ Reintentando {target_codec} con conversión libplacebo ({pixel_format})")
                    try:
                        self._run_ffmpeg(retry_cmd, self._media_duration(abspath_in), basename(abspath_in))
                    except subprocess.CalledProcessError as retry_error:
                        e = retry_error
                    else:
                        promote_partial_output(partial_out, abspath_out)
                        self.stats['videos'] += 1
                        return
                raise e
            promote_partial_output(partial_out, abspath_out)
            self.stats['videos'] += 1

        except BackupCancelled:
            remove_file_quietly(partial_out)
            raise
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or '').strip()
            self.log(f"  ✗ Error de códec {target_codec} (código {e.returncode}): {detail or 'sin detalle de FFmpeg'}")
            remove_file_quietly(partial_out)
            self._copy_original_video_fallback(abspath_in, dir_out, prefix, suffix)
            self.stats['errors'] += 1
        except Exception as e:
            self.log(f"  ✗ Error de códec {target_codec}: {e}")
            remove_file_quietly(partial_out)
            self._copy_original_video_fallback(abspath_in, dir_out, prefix, suffix)
            self.stats['errors'] += 1

    def _copy_original_video_fallback(self, abspath_in, dir_out, prefix, suffix):
        fallback_out = os.path.join(dir_out, prefix + suffix)
        if os.path.exists(fallback_out):
            self.stats['skipped'] += 1
            return
        atomic_copyfile(abspath_in, fallback_out)
        self.stats['videos'] += 1

    def process_videos_copy(self, abspath_in, dir_out, prefix, suffix):
        """Copia vídeos sin transcodificar."""
        if suffix.lower() in BRAW_EXTENSIONS:
            self.process_braw(abspath_in, dir_out, prefix, suffix, create_proxy=False)
            return
        ext = suffix  # mantener extensión original
        abspath_out = os.path.join(dir_out, prefix + ext)

        if os.path.exists(abspath_out):
            self.stats['skipped'] += 1
            return

        self.log(f"  📹 Copiando vídeo: {basename(abspath_in)}")
        atomic_copyfile(abspath_in, abspath_out)
        self.stats['videos'] += 1

    def copy_remaining_files(self):
        """Copia archivos que no son audio/imagen/vídeo."""
        for root, dirs, files in os.walk(self.src_dir):
            if self.cancelled:
                return
            for f in files:
                if self.cancelled:
                    return
                _, suffix = os.path.splitext(f)
                if suffix.lower() not in ALL_PROCESSED_EXTENSIONS and f.lower() != 'thumbs.db':
                    abspath_in = os.path.join(root, f)
                    rel_path = os.path.relpath(root, self.src_dir)
                    dir_out = os.path.normpath(os.path.join(self.dst_dir, rel_path))
                    Path(dir_out).mkdir(parents=True, exist_ok=True)
                    abspath_out = os.path.join(dir_out, f)

                    if not is_source_ready(abspath_in, lambda: self.cancelled):
                        self.log(f'  En transferencia, se reintentará más tarde: {f}')
                        self.stats['skipped'] += 1
                        self.progress()
                        continue

                    if not os.path.exists(abspath_out):
                        atomic_copyfile(abspath_in, abspath_out)
                        self.log(f"  📄 Copiado: {f}")
                        self.stats['copied'] += 1
                        self.progress()
                    else:
                        self.stats['skipped'] += 1


# ─────────────────────────────────────────────
# Interfaz gráfica
# ─────────────────────────────────────────────

class BackupApp:
    """Aplicación de backup con interfaz Tkinter."""

    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.minsize(1180, 760)
        self.running = False
        self.proxy_running = False
        self.processor = None
        self.total_files = 0
        self.processed_files = 0
        self.config = load_config()
        self._native_drop_callback = None
        self._native_drop_old_procs = {}
        self._toggle_widgets = []

        self.watch_folder_var = tk.StringVar(value=self.config.get('watch_folder', SCRIPT_DIR))
        self.src_var = tk.StringVar(value=self.watch_folder_var.get())
        self.dst_var = tk.StringVar(value=self.config.get('dst_dir', ''))
        self.mode_var = tk.StringVar(value=self.config.get('mode', 'todo'))
        self.transcode_var = tk.BooleanVar(value=self.config.get('transcode', True))
        self.codec_preset_var = tk.StringVar(value=self.config.get('codec_preset', DEFAULT_CODEC_PRESET))
        self.proxy_codec_var = tk.StringVar(value=self.config.get('proxy_codec', braw_proxy.DEFAULT_PROXY_CODEC))
        # Por defecto GPU: si el equipo no tiene encoder de hardware validado
        # para ese codec, la deteccion lo pasa a CPU y deshabilita la opcion.
        self.proxy_accel_var = tk.StringVar(value=self.config.get('proxy_accel', ACCEL_GPU))
        self.audio_preset_var = tk.StringVar(value=self.config.get('audio_preset', DEFAULT_AUDIO_PRESET))
        self.backup_braw_originals_var = tk.BooleanVar(value=self.config.get('backup_braw_originals', False))
        self.proxy_live_var = tk.BooleanVar(value=False)
        self.backup_live_var = tk.BooleanVar(value=False)
        self.proxy_live_thread = None
        self.backup_live_thread = None
        self.dark_mode_var = tk.BooleanVar(value=self.config.get('dark_mode', False))
        self.shutdown_var = tk.BooleanVar(value=False)
        self.shutdown_min_var = tk.StringVar(value='5')
        self.encoder_capabilities = None
        self.codec_radio_buttons = {}
        self.audio_radio_buttons = {}
        self.proxy_codec_radio_buttons = {}
        self.proxy_accel_radio_buttons = {}

        self.style = ttk.Style(self.root)
        try:
            self.root.tk.call('tk', 'scaling', max(float(self.root.tk.call('tk', 'scaling')), 1.25))
        except Exception:
            pass
        self._set_window_icon()
        self._build_ui()
        self._apply_theme()
        self._set_initial_geometry()
        self._detect_defaults()
        self.dst_var.trace_add('write', self._on_dst_change)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.registry = ProxyRegistry(
            registry_path=REGISTRY_PATH,
            ffprobe_bin=FFPROBE_BIN,
            braw_decode_bin=braw_proxy.BRAW_DECODE,
            sdk_dir=braw_proxy.SDK_DIR,
            log_callback=self._log,
        )

    def _set_initial_geometry(self):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        req_w = self.root.winfo_reqwidth()
        req_h = self.root.winfo_reqheight()
        margin = 60
        width = min(max(req_w, 1180), screen_w - margin)
        height = min(max(req_h, 760), screen_h - margin)
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _set_window_icon(self):
        if not os.path.isfile(ICON_PATH):
            return
        try:
            self.app_icon = tk.PhotoImage(file=ICON_PATH)
            self.root.iconphoto(True, self.app_icon)
        except tk.TclError:
            pass
        if IS_WINDOWS:
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Proxynas.App")
            except Exception:
                pass

    def _persist_config(self):
        self.config.update({
            'dark_mode': self.dark_mode_var.get(),
            'watch_folder': self.watch_folder_var.get(),
            'dst_dir': self.dst_var.get(),
            'mode': self.mode_var.get(),
            'transcode': self.transcode_var.get(),
            'codec_preset': self.codec_preset_var.get(),
            'proxy_codec': self.proxy_codec_var.get(),
            'proxy_accel': self.proxy_accel_var.get(),
            'audio_preset': self.audio_preset_var.get(),
            'backup_braw_originals': self.backup_braw_originals_var.get(),
        })
        save_config(self.config)

    def _on_dst_change(self, *_args):
        if hasattr(self, 'config'):
            self._persist_config()

    def _on_close(self):
        self._persist_config()
        self.root.destroy()

    def _toggle_dark_mode(self):
        self._persist_config()
        self._apply_theme()

    def _palette(self):
        if self.dark_mode_var.get():
            return {
                'bg': '#111318',
                'surface': '#1a1d24',
                'surface_2': '#232833',
                'border': '#333a47',
                'text': '#f4f6fb',
                'muted': '#aeb7c5',
                'field': '#12151b',
                'accent': '#a8cce2',
                'accent_2': '#8fb5cd',
                'danger': '#ff6b6b',
                'log_bg': '#0b0d12',
            }
        return {
            'bg': '#f3f5f8',
            'surface': '#ffffff',
            'surface_2': '#f7f9fc',
            'border': '#d9e0ea',
            'text': '#172033',
            'muted': '#647084',
            'field': '#ffffff',
            'accent': '#79a7c5',
            'accent_2': '#628fae',
            'danger': '#c43e3e',
            'log_bg': '#10141c',
        }

    def _dpi_scale(self):
        """Factor de escala basado en el DPI real de la pantalla."""
        try:
            dpi = self.root.winfo_fpixels('1i')
            return max(1.0, dpi / 72.0)
        except Exception:
            return 1.25

    def _make_hidpi_indicator_images(self, size, colors):
        """Genera indicadores modernos (esquinas redondeadas, anti-aliasing) escalados al DPI."""
        from PIL import Image, ImageTk, ImageDraw

        SS = 4
        big = size * SS

        def hex2rgb(h):
            h = h.lstrip('#')
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

        border_color = hex2rgb(colors['border'])
        accent = hex2rgb(colors['accent'])
        disabled_color = hex2rgb(colors['border'])
        check_mark_color = (17, 17, 17)

        radius = max(2, big // 5)
        stroke = max(2, big // 14)
        check_stroke = max(3, big // 9)
        can_round = hasattr(ImageDraw.ImageDraw, 'rounded_rectangle')

        def make_check(selected, enabled=True):
            img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            box = [0, 0, big - 1, big - 1]
            if selected:
                fill = accent if enabled else disabled_color
                if can_round:
                    d.rounded_rectangle(box, radius=radius, fill=fill)
                else:
                    d.rectangle(box, fill=fill)
                check = check_mark_color if enabled else disabled_color
                d.line(
                    [(big * 0.22, big * 0.52), (big * 0.42, big * 0.72), (big * 0.78, big * 0.28)],
                    fill=check, width=check_stroke, joint='curve',
                )
            else:
                outline = border_color if enabled else disabled_color
                if can_round:
                    d.rounded_rectangle(box, radius=radius, outline=outline, width=stroke)
                else:
                    d.rectangle(box, outline=outline, width=stroke)
            img = img.resize((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(img)

        def make_radio(selected, enabled=True):
            img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            outline = border_color if enabled else disabled_color
            d.ellipse([0, 0, big - 1, big - 1], outline=outline, width=stroke)
            if selected:
                fill = accent if enabled else disabled_color
                margin = big // 4
                d.ellipse([margin, margin, big - 1 - margin, big - 1 - margin], fill=fill)
            img = img.resize((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(img)

        return {
            'check_off': make_check(False),
            'check_on': make_check(True),
            'check_off_disabled': make_check(False, enabled=False),
            'check_on_disabled': make_check(True, enabled=False),
            'radio_off': make_radio(False),
            'radio_on': make_radio(True),
            'radio_off_disabled': make_radio(False, enabled=False),
            'radio_on_disabled': make_radio(True, enabled=False),
        }

    def _apply_hidpi_indicators(self):
        """Layout plano para check/radio sin sombra inferior; usa indicadores HiDPI si PIL está disponible."""
        check_elem = 'Checkbutton.indicator'
        radio_elem = 'Radiobutton.indicator'
        indicator_size = 18

        try:
            from PIL import Image  # noqa: F401
            scale = self._dpi_scale()
            indicator_size = min(max(18, int(round(16 * scale))), 28)
            images = self._make_hidpi_indicator_images(indicator_size, self.colors)
            self._indicator_images = images

            self._indicator_counter = getattr(self, '_indicator_counter', 0) + 1
            check_elem = f'HiDPI.Check.ind{self._indicator_counter}'
            radio_elem = f'HiDPI.Radio.ind{self._indicator_counter}'

            self.style.element_create(
                check_elem, 'image', images['check_off'],
                ('selected', images['check_on']),
                ('disabled', images['check_off_disabled']),
                ('selected disabled', images['check_on_disabled']),
                width=indicator_size, height=indicator_size,
            )
            self.style.element_create(
                radio_elem, 'image', images['radio_off'],
                ('selected', images['radio_on']),
                ('disabled', images['radio_off_disabled']),
                ('selected disabled', images['radio_on_disabled']),
                width=indicator_size, height=indicator_size,
            )
        except Exception:
            pass

        try:
            self.style.layout('TCheckbutton', [
                (check_elem, {'side': 'left', 'sticky': ''}),
                ('Checkbutton.label', {'side': 'left', 'sticky': 'w'})
            ])
            self.style.layout('TRadiobutton', [
                (radio_elem, {'side': 'left', 'sticky': ''}),
                ('Radiobutton.label', {'side': 'left', 'sticky': 'w'})
            ])
            self.style.configure('TCheckbutton', borderwidth=0, relief='flat')
            self.style.configure('TRadiobutton', borderwidth=0, relief='flat')
        except tk.TclError:
            pass

    def _apply_theme(self):
        self.colors = self._palette()
        c = self.colors
        self.root.configure(bg=c['bg'])
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass

        self._apply_hidpi_indicators()

        base_font = ('Segoe UI', 10)
        self.style.configure('.', font=base_font, background=c['bg'], foreground=c['text'])
        self.style.configure('App.TFrame', background=c['bg'])
        self.style.configure('Card.TFrame', background=c['surface'], relief='flat')
        self.style.configure('Subtle.TFrame', background=c['surface_2'])
        self.style.configure('Header.TLabel', background=c['bg'], foreground=c['text'], font=('Segoe UI Semibold', 18))
        self.style.configure('HeaderMuted.TLabel', background=c['bg'], foreground=c['muted'], font=('Segoe UI', 10))
        self.style.configure('Header.TCheckbutton', background=c['bg'], foreground=c['text'], font=base_font)
        self.style.map('Header.TCheckbutton', background=[('active', c['bg'])], foreground=[('active', c['text']), ('disabled', c['muted'])])
        self.style.configure('Title.TLabel', background=c['surface'], foreground=c['text'], font=('Segoe UI Semibold', 14))
        self.style.configure('Body.TLabel', background=c['surface'], foreground=c['text'], font=base_font)
        self.style.configure('Muted.TLabel', background=c['surface'], foreground=c['muted'], font=('Segoe UI', 9))
        self.style.configure('Status.TLabel', background=c['surface_2'], foreground=c['text'], font=('Segoe UI', 9))
        self.style.configure('TCheckbutton', background=c['surface'], foreground=c['text'], font=base_font)
        self.style.map('TCheckbutton', background=[('active', c['surface'])], foreground=[('active', c['text'])])
        self.style.configure('TRadiobutton', background=c['surface'], foreground=c['text'], font=base_font)
        self.style.map('TRadiobutton', background=[('active', c['surface'])], foreground=[('active', c['text'])])
        self.style.configure('TEntry', fieldbackground=c['field'], foreground=c['text'], insertcolor=c['text'], bordercolor=c['border'], lightcolor=c['border'], darkcolor=c['border'], padding=6)
        primary_bg = c['text'] if not self.dark_mode_var.get() else c['accent']
        primary_fg = c['surface'] if self.dark_mode_var.get() else '#ffffff'
        self.style.configure('Primary.TButton', font=('Segoe UI Semibold', 10), background=primary_bg, foreground=primary_fg, borderwidth=0, focusthickness=0, padding=(14, 9))
        self.style.map('Primary.TButton', background=[('active', c['accent_2']), ('disabled', c['border'])], foreground=[('disabled', c['muted'])])
        self.style.configure('Secondary.TButton', font=('Segoe UI', 10), background=c['surface_2'], foreground=c['text'], borderwidth=1, bordercolor=c['border'], padding=(12, 8))
        self.style.map('Secondary.TButton', background=[('active', c['border']), ('disabled', c['surface_2'])], foreground=[('disabled', c['muted'])])
        self.style.configure('Danger.TButton', font=('Segoe UI', 10), background=c['surface_2'], foreground=c['danger'], borderwidth=1, bordercolor=c['border'], padding=(12, 8))
        self.style.configure('Modern.Horizontal.TProgressbar', troughcolor=c['surface_2'], background=c['accent'], bordercolor=c['surface_2'], lightcolor=c['accent'], darkcolor=c['accent'])
        self.style.configure('Horizontal.TSeparator', background=c['border'])

        for frame in getattr(self, '_card_frames', []):
            try:
                frame.configure(bg=c['surface'], highlightbackground=c['border'], highlightthickness=1)
            except tk.TclError:
                frame.configure(style='Card.TFrame')
        for frame in getattr(self, '_subtle_frames', []):
            frame.configure(style='Subtle.TFrame')
        if hasattr(self, 'log_text'):
            self.log_text.configure(
                background=c['log_bg'],
                foreground='#d7e0ea',
                insertbackground='#d7e0ea',
                selectbackground=c['accent'],
                selectforeground='#ffffff',
                relief='flat',
                borderwidth=0,
                padx=12,
                pady=10,
                font=('Cascadia Mono', 9) if IS_WINDOWS else ('monospace', 9),
            )
        if hasattr(self, 'drop_canvas'):
            self._draw_drop_zone()
        for button in getattr(self, '_rounded_buttons', []):
            button.refresh_theme()
        self._refresh_toggle_widgets()

    def _refresh_toggle_widgets(self):
        c = self.colors
        for widget, variable, label in getattr(self, '_toggle_widgets', []):
            active = variable.get()
            widget.configure(
                text=f"{label}: {'activo' if active else 'inactivo'}",
                bg=c['accent'] if active else c['surface_2'],
                fg='#111111' if active else c['text'],
                activebackground=c['accent_2'] if active else c['border'],
                activeforeground='#111111' if active else c['text'],
                selectcolor=c['accent'],
                highlightbackground=c['border'],
                highlightcolor=c['accent'],
            )

    def _make_toggle(self, parent, text, variable, command=None):
        def on_click():
            if command:
                command()
            self._refresh_toggle_widgets()
        widget = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=on_click,
            indicatoron=False,
            relief='flat',
            bd=0,
            padx=14,
            pady=8,
            font=('Segoe UI Semibold', 10),
            cursor='hand2',
        )
        self._toggle_widgets.append((widget, variable, text))
        return widget

    def _make_button(self, parent, text, command, kind='secondary', bg_key='surface', min_width=None):
        button = RoundedButton(parent, self, text=text, command=command, kind=kind, bg_key=bg_key, min_width=min_width)
        self._rounded_buttons.append(button)
        return button

    def _card(self, parent, title, subtitle=None):
        c = getattr(self, 'colors', self._palette())
        card = tk.Frame(parent, bg=c['surface'], highlightbackground=c['border'], highlightthickness=1, bd=0, padx=16, pady=14)
        self._card_frames.append(card)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        ttk.Label(card, text=title, style='Title.TLabel').grid(row=0, column=0, sticky='w')
        if subtitle:
            ttk.Label(card, text=subtitle, style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(3, 8))
        body = ttk.Frame(card, style='Card.TFrame')
        body.grid(row=3, column=0, sticky='nsew', pady=(4, 0))
        body.columnconfigure(0, weight=1)
        card.body = body
        return card

    def _build_ui(self):
        self._card_frames = []
        self._subtle_frames = []
        self._rounded_buttons = []
        root_frame = ttk.Frame(self.root, style='App.TFrame', padding=16)
        root_frame.pack(fill='both', expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(1, weight=1)

        header = ttk.Frame(root_frame, style='App.TFrame')
        header.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, style='Header.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(header, text=APP_SUBTITLE, style='HeaderMuted.TLabel').grid(row=1, column=0, sticky='w', pady=(3, 0))
        header_actions = ttk.Frame(header, style='App.TFrame')
        header_actions.grid(row=0, column=1, rowspan=2, sticky='e')
        self._make_button(header_actions, 'Minimizar al área de notificaciones', self._minimize_to_tray, bg_key='bg').pack(side='left', padx=(0, 10))
        ttk.Checkbutton(header_actions, text='Modo oscuro', variable=self.dark_mode_var, command=self._toggle_dark_mode, style='Header.TCheckbutton').pack(side='left')

        main = ttk.Frame(root_frame, style='App.TFrame')
        main.grid(row=1, column=0, sticky='nsew')
        main.columnconfigure(0, weight=1, uniform='main')
        main.columnconfigure(1, weight=1, uniform='main')
        main.rowconfigure(1, weight=1)

        watch_card = self._card(main, 'Carpeta vigilada', 'Arrastra una carpeta o selecciónala. Proxies y backup trabajarán sobre este directorio.')
        watch_card.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        self._build_watch_folder_panel(watch_card.body)

        proxy_card = self._card(main, 'Proxies', 'Genera proxies Resolve para BRAW y ProRes cuando falten.')
        proxy_card.grid(row=1, column=0, sticky='nsew', padx=(0, 8))
        backup_card = self._card(main, 'Backup', 'Sincroniza lo nuevo hacia un destino y convierte vídeo a formatos ligeros.')
        backup_card.grid(row=1, column=1, sticky='nsew', padx=(8, 0))
        proxy_card.body.rowconfigure(4, weight=1)
        backup_card.body.rowconfigure(4, weight=1)

        self._build_proxy_panel(proxy_card.body)
        self._build_backup_panel(backup_card.body)

    def _build_watch_folder_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        drop = tk.Canvas(parent, height=118, highlightthickness=0, bd=0)
        drop.grid(row=0, column=0, sticky='ew')
        self.drop_canvas = drop
        self._draw_drop_zone()
        drop.bind('<Configure>', lambda _event: self._draw_drop_zone())
        drop.bind('<Button-1>', lambda _event: self._browse_watch_folder())
        self._enable_drag_and_drop()

        row = ttk.Frame(parent, style='Card.TFrame')
        row.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self.watch_folder_var).grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self._make_button(row, 'Abrir carpeta', self._browse_watch_folder).grid(row=0, column=1)

    def _draw_drop_zone(self):
        if not hasattr(self, 'drop_canvas'):
            return
        c = getattr(self, 'colors', self._palette())
        canvas = self.drop_canvas
        canvas.configure(bg=c['surface'])
        canvas.delete('all')
        w = max(canvas.winfo_width(), 300)
        h = max(canvas.winfo_height(), 130)
        canvas.create_rectangle(12, 12, w - 12, h - 12, outline=c['border'], width=2, dash=(8, 6))
        canvas.create_text(w / 2, h / 2 - 14, text='Arrastra la carpeta aquí', fill=c['text'], font=('Segoe UI Semibold', 18))
        canvas.create_text(w / 2, h / 2 + 26, text='o haz clic para abrirla', fill=c['muted'], font=('Segoe UI', 10))

    def _enable_drag_and_drop(self):
        enabled = False
        try:
            from tkinterdnd2 import DND_FILES
            self.drop_canvas.drop_target_register(DND_FILES)
            self.drop_canvas.dnd_bind('<<Drop>>', self._on_folder_drop)
            enabled = True
        except Exception:
            pass
        if not enabled and IS_WINDOWS:
            self.root.after(200, self._enable_windows_drop)
        return enabled

    def _enable_windows_drop(self):
        if not IS_WINDOWS:
            return
        try:
            import ctypes
            from ctypes import wintypes
            shell32 = ctypes.windll.shell32
            user32 = ctypes.windll.user32
            WM_DROPFILES = 0x0233
            GWLP_WNDPROC = -4

            LRESULT = wintypes.LPARAM
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

            user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallWindowProcW.restype = LRESULT
            user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.DefWindowProcW.restype = LRESULT
            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            shell32.DragFinish.argtypes = [wintypes.HANDLE]

            is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
            if is_64bit:
                user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            else:
                user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
                user32.SetWindowLongW.restype = ctypes.c_long

            def read_drop_path(hdrop):
                count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                if count < 1:
                    return None
                length = shell32.DragQueryFileW(hdrop, 0, None, 0) + 1
                buffer = ctypes.create_unicode_buffer(length)
                shell32.DragQueryFileW(hdrop, 0, buffer, length)
                return buffer.value

            def call_previous(hwnd, msg, wparam, lparam):
                old_proc = self._native_drop_old_procs.get(hwnd)
                if old_proc:
                    return user32.CallWindowProcW(ctypes.c_void_p(old_proc), hwnd, msg, wparam, lparam)
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            def wndproc(hwnd, msg, wparam, lparam):
                try:
                    if msg == WM_DROPFILES:
                        dropped = read_drop_path(wparam)
                        shell32.DragFinish(wparam)
                        if dropped and os.path.isdir(dropped):
                            self.root.after(0, lambda p=dropped: self._set_watch_folder(p))
                        return 0
                    return call_previous(hwnd, msg, wparam, lparam)
                except Exception:
                    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            callback = WNDPROC(wndproc)
            self._native_drop_callback = callback
            callback_ptr = ctypes.cast(callback, ctypes.c_void_p)
            hwnds = {self.root.winfo_id(), self.drop_canvas.winfo_id()}
            for hwnd in hwnds:
                if hwnd in self._native_drop_old_procs:
                    continue
                shell32.DragAcceptFiles(hwnd, True)
                if is_64bit:
                    old_proc = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, callback_ptr)
                    old_value = old_proc if isinstance(old_proc, int) else old_proc.value
                else:
                    old_value = user32.SetWindowLongW(hwnd, GWLP_WNDPROC, callback_ptr.value)
                if old_value:
                    self._native_drop_old_procs[hwnd] = int(old_value)
        except Exception as exc:
            self._log(f'Drag & drop nativo no disponible: {exc}')

    def _on_folder_drop(self, event):
        candidates = []
        try:
            candidates = list(self.root.tk.splitlist(event.data))
        except tk.TclError:
            raw = event.data.strip()
            if raw.startswith('{') and raw.endswith('}'):
                raw = raw[1:-1]
            candidates = [raw]
        for candidate in candidates:
            candidate = candidate.strip().strip('"')
            if os.path.isdir(candidate):
                self._set_watch_folder(candidate)
                return
        self.proxy_status_var.set('Lo que has soltado no parece una carpeta válida.')

    def _browse_watch_folder(self):
        folder = filedialog.askdirectory(title='Seleccionar carpeta vigilada')
        if folder:
            self._set_watch_folder(folder)

    def _set_watch_folder(self, folder):
        folder = os.path.abspath(folder)
        self.watch_folder_var.set(folder)
        self.src_var.set(folder)
        self.proxy_status_var.set('Carpeta lista. Puedes crear proxies o activar el modo live.')
        self._persist_config()
        self._draw_drop_zone()
        # os.walk sobre una carpeta de red puede tardar, así que se busca en segundo plano.
        threading.Thread(target=self._check_braw_sdk_for_folder, args=(folder,), daemon=True).start()

    def _build_proxy_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        ttk.Label(
            parent,
            text='Crea proxies para el material profesional detectado en la carpeta vigilada: ahora, Blackmagic RAW y ProRes.',
            style='Body.TLabel',
        ).grid(row=0, column=0, sticky='ew')

        codec_box = ttk.Frame(parent, style='Card.TFrame')
        codec_box.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        ttk.Label(codec_box, text='Códec del proxy', style='Muted.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 4))

        families = ttk.Frame(codec_box, style='Card.TFrame')
        families.grid(row=1, column=0, sticky='w')
        for column, codec in enumerate(braw_proxy.PROXY_CODECS):
            radio = ttk.Radiobutton(
                families,
                text=braw_proxy.PROXY_CODEC_LABELS[codec],
                variable=self.proxy_codec_var,
                value=codec,
                command=self._on_proxy_codec_change,
            )
            radio.grid(row=0, column=column, sticky='w', padx=(0, 14))
            self.proxy_codec_radio_buttons[codec] = radio

        accelerations = ttk.Frame(codec_box, style='Card.TFrame')
        accelerations.grid(row=2, column=0, sticky='w', pady=(4, 0))
        for column, accel in enumerate((ACCEL_GPU, ACCEL_CPU)):
            radio = ttk.Radiobutton(
                accelerations,
                text=ACCEL_LABELS[accel],
                variable=self.proxy_accel_var,
                value=accel,
                command=self._persist_config,
            )
            radio.grid(row=0, column=column, sticky='w', padx=(0, 14))
            self.proxy_accel_radio_buttons[accel] = radio

        self.proxy_codec_status_label = ttk.Label(codec_box, text='Detectando códecs...', style='Muted.TLabel', wraplength=280, justify='left')
        self.proxy_codec_status_label.grid(row=3, column=0, sticky='w', pady=(6, 0))

        status_box = ttk.Frame(parent, style='Subtle.TFrame', padding=12)
        self._subtle_frames.append(status_box)
        status_box.grid(row=2, column=0, sticky='ew', pady=(14, 14))
        self.proxy_status_var = tk.StringVar(value='Selecciona una carpeta y crea proxies pendientes.')
        ttk.Label(status_box, textvariable=self.proxy_status_var, style='Status.TLabel', wraplength=520, justify='left').pack(anchor='w')

        controls = ttk.Frame(parent, style='Card.TFrame')
        controls.grid(row=3, column=0, sticky='ew')
        controls.columnconfigure(0, weight=1)
        self._make_toggle(controls, 'Modo live', self.proxy_live_var, self._toggle_proxy_live).grid(row=0, column=0, sticky='ew', pady=(0, 12))
        self.proxy_button = self._make_button(controls, 'Crear proxies pendientes', self._start_proxy_creation, kind='primary')
        self.proxy_button.grid(row=1, column=0, sticky='ew')
        self._make_button(controls, 'Importar SDK BRAW (zip)', self._import_braw_sdk).grid(
            row=2, column=0, sticky='ew', pady=(8, 0)
        )

        # Hueco flexible: se lleva el alto sobrante de la tarjeta.
        ttk.Frame(parent, style='Card.TFrame').grid(row=4, column=0, sticky='nsew')

    def _build_backup_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        dirs = ttk.Frame(parent, style='Card.TFrame')
        dirs.grid(row=0, column=0, sticky='ew')
        dirs.columnconfigure(0, weight=1)
        ttk.Label(dirs, text='Origen: carpeta vigilada superior', style='Muted.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(dirs, textvariable=self.watch_folder_var, style='Body.TLabel').grid(row=1, column=0, sticky='w', pady=(4, 12))
        ttk.Label(dirs, text='Destino del backup', style='Muted.TLabel').grid(row=2, column=0, sticky='w')
        dest_row = ttk.Frame(dirs, style='Card.TFrame')
        dest_row.grid(row=3, column=0, sticky='ew', pady=(4, 0))
        dest_row.columnconfigure(0, weight=1)
        ttk.Entry(dest_row, textvariable=self.dst_var).grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self._make_button(dest_row, 'Examinar', self._browse_dst).grid(row=0, column=1)

        ttk.Separator(parent, orient='horizontal').grid(row=1, column=0, sticky='ew', pady=10)

        opts = ttk.Frame(parent, style='Card.TFrame')
        opts.grid(row=2, column=0, sticky='ew')
        opts.columnconfigure(0, weight=1)
        ttk.Label(opts, text='Qué respaldar', style='Muted.TLabel').grid(row=0, column=0, sticky='w')
        modes = ttk.Frame(opts, style='Card.TFrame')
        modes.grid(row=1, column=0, sticky='w', pady=(6, 10))
        for val, label in [('todo', 'Todo'), ('video', 'Solo vídeo'), ('audio_img', 'Audio + imágenes'), ('otros', 'Otros')]:
            ttk.Radiobutton(modes, text=label, variable=self.mode_var, value=val, command=self._on_mode_change).pack(side='left', padx=(0, 12))
        self.transcode_check = ttk.Checkbutton(
            opts,
            text='Convertir vídeo',
            variable=self.transcode_var,
            command=self._on_transcode_change,
        )
        self.transcode_check.grid(row=2, column=0, sticky='w', pady=(2, 4))

        codec_box = ttk.Frame(opts, style='Card.TFrame')
        codec_box.grid(row=3, column=0, sticky='ew', pady=(0, 8))
        codec_box.columnconfigure(0, weight=1)
        codec_box.columnconfigure(1, weight=1)

        video_codec_box = ttk.Frame(codec_box, style='Card.TFrame')
        video_codec_box.grid(row=0, column=0, sticky='nw', padx=(0, 18))
        ttk.Label(video_codec_box, text='Códec de backup', style='Muted.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 4))
        for row, preset in enumerate((CODEC_AV1_HW, CODEC_HEVC_HW, CODEC_HEVC_SW), start=1):
            rb = ttk.Radiobutton(
                video_codec_box,
                text=CODEC_PRESET_LABELS[preset],
                variable=self.codec_preset_var,
                value=preset,
                command=self._on_codec_preset_change,
            )
            rb.grid(row=row, column=0, sticky='w', pady=1)
            rb.config(state='disabled')
            self.codec_radio_buttons[preset] = rb
        self.codec_status_label = ttk.Label(video_codec_box, text='Detectando códecs...', style='Muted.TLabel', wraplength=280, justify='left')
        self.codec_status_label.grid(row=4, column=0, sticky='w', pady=(6, 0))

        audio_codec_box = ttk.Frame(codec_box, style='Card.TFrame')
        audio_codec_box.grid(row=0, column=1, sticky='nw')
        ttk.Label(audio_codec_box, text='Audio', style='Muted.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 4))
        for row, preset in enumerate((AUDIO_NO_TRANSCODE, AUDIO_WAV_PCM, AUDIO_AAC_M4A, AUDIO_OPUS_MP4), start=1):
            rb = ttk.Radiobutton(
                audio_codec_box,
                text=AUDIO_PRESET_LABELS[preset],
                variable=self.audio_preset_var,
                value=preset,
                command=self._on_audio_preset_change,
            )
            rb.grid(row=row, column=0, sticky='w', pady=1)
            self.audio_radio_buttons[preset] = rb

        ttk.Checkbutton(
            opts,
            text='Incluir originales BRAW en el backup (muy pesado)',
            variable=self.backup_braw_originals_var,
            command=self._persist_config,
        ).grid(row=4, column=0, sticky='w', pady=(0, 4))
        self._make_toggle(opts, 'Modo live', self.backup_live_var, self._toggle_backup_live).grid(row=5, column=0, sticky='ew', pady=(4, 8))

        shutdown = ttk.Frame(opts, style='Card.TFrame')
        shutdown.grid(row=6, column=0, sticky='w', pady=(4, 0))
        ttk.Checkbutton(shutdown, text='Apagar al terminar', variable=self.shutdown_var).pack(side='left')
        ttk.Label(shutdown, text='minutos:', style='Body.TLabel').pack(side='left', padx=(12, 4))
        ttk.Entry(shutdown, textvariable=self.shutdown_min_var, width=5).pack(side='left')

        system_box = ttk.Frame(parent, style='Subtle.TFrame', padding=12)
        self._subtle_frames.append(system_box)
        system_box.grid(row=3, column=0, sticky='ew', pady=(10, 8))
        ttk.Label(system_box, text='Estado del sistema', style='Status.TLabel').pack(anchor='w')
        self.info_label = ttk.Label(system_box, text='Detectando...', style='Status.TLabel', wraplength=620, justify='left')
        self.info_label.pack(anchor='w', pady=(6, 0))

        log_frame = ttk.Frame(parent, style='Card.TFrame')
        log_frame.grid(row=4, column=0, sticky='nsew')
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        top_log = ttk.Frame(log_frame, style='Card.TFrame')
        top_log.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        top_log.columnconfigure(0, weight=1)
        ttk.Label(top_log, text='Actividad', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        self.progress_label = ttk.Label(top_log, text='', style='Muted.TLabel')
        self.progress_label.grid(row=0, column=1, sticky='e')
        self.progress_bar = ttk.Progressbar(log_frame, style='Modern.Horizontal.TProgressbar', mode='determinate')
        self.progress_bar.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state='disabled')
        self.log_text.grid(row=2, column=0, sticky='nsew')

        buttons = ttk.Frame(parent, style='Card.TFrame')
        buttons.grid(row=5, column=0, sticky='ew', pady=(10, 0))
        buttons.columnconfigure(2, weight=1)
        self.btn_start = self._make_button(buttons, 'Iniciar backup', self._start, kind='primary')
        self.btn_start.grid(row=0, column=0, sticky='w')
        self.btn_cancel = self._make_button(buttons, 'Cancelar', self._cancel, kind='danger')
        self.btn_cancel.config(state='disabled')
        self.btn_cancel.grid(row=0, column=1, sticky='w', padx=(8, 0))
        self._make_button(buttons, 'Salir', self.root.quit).grid(row=0, column=3, sticky='e')

    def _iter_proxy_candidates(self):
        root_dir = self.watch_folder_var.get().strip() or SCRIPT_DIR
        if not os.path.isdir(root_dir):
            return
        skip_dirs = {'Proxy', '_orphan', 'portable', 'tools', '__pycache__', '.git', '.agents', '.codex'}
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            if 'Proxy' in Path(dirpath).parts:
                continue
            for filename in filenames:
                if PARTIAL_MARKER in filename:
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in {'.braw', '.mov', '.mxf'}:
                    continue
                source_path = os.path.join(dirpath, filename)
                if not is_source_ready(source_path):
                    continue
                if ext == '.braw' or self._is_prores_source(source_path):
                    base = os.path.splitext(filename)[0]
                    proxy_path = os.path.join(dirpath, 'Proxy', base + proxy_extension_for(source_path))
                    yield source_path, proxy_path

    def _is_prores_source(self, source_path):
        try:
            result = subprocess.run(
                [FFPROBE_BIN, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', source_path],
                capture_output=True,
                text=True,
                check=False,
            )
            return 'prores' in result.stdout.lower()
        except Exception:
            return False

    def _find_pending_proxy_jobs(self):
        jobs = []
        for source_path, proxy_path in self._iter_proxy_candidates() or []:
            if not os.path.exists(proxy_path):
                jobs.append((source_path, proxy_path))
        return jobs

    def _set_proxy_running(self, running):
        self.proxy_running = running
        state = 'disabled' if running else 'normal'
        self.proxy_button.config(state=state)
        self.btn_start.config(state=state if running else 'normal')

    def _import_braw_sdk(self):
        zip_path = filedialog.askopenfilename(
            title='Selecciona el zip del Blackmagic RAW SDK',
            filetypes=[('Zip', '*.zip'), ('Todos los ficheros', '*.*')],
        )
        if not zip_path:
            return
        self.proxy_status_var.set('Importando el SDK BRAW (puede tardar unos segundos)...')
        self.root.update_idletasks()
        try:
            result = braw_proxy.import_braw_sdk(zip_path)
        except Exception as exc:
            self.proxy_status_var.set('No se pudo importar el SDK BRAW.')
            messagebox.showerror(APP_NAME, f'No se pudo importar el SDK BRAW:\n{exc}')
            return

        lines = [f'Copiado: {os.path.basename(path)}' for path in result['copied']]
        if result['missing']:
            lines.append('No se encontró en el zip: ' + ', '.join(result['missing']))
        if not result['decoder']:
            lines.append('Falta el decodificador braw_decode.exe en portable/bin/. No forma parte del SDK:\n'
                         'lo incluye Proxynas, así que descarga de nuevo la última versión.')
        message = '\n'.join(lines)
        self._log(message)
        if result['missing'] or not result['decoder']:
            self.proxy_status_var.set('El SDK BRAW quedó incompleto. Revisa el aviso.')
            messagebox.showwarning(APP_NAME, message)
        else:
            self.proxy_status_var.set('SDK BRAW listo. Ya puedes crear proxies de .braw.')
            messagebox.showinfo(APP_NAME, 'SDK BRAW importado correctamente.')

    def _offer_braw_sdk(self, missing=None):
        """Guía para instalar el SDK, que no se puede redistribuir con la app."""
        detail = f'Para trabajar con BRAW, falta lo siguiente:\n{missing}\n\n' if missing else ''
        if messagebox.askyesno(
            APP_NAME,
            detail + BRAW_SDK_HELP
            + '\n\n¿Quieres abrir la página de descarga del SDK en el navegador?',
        ):
            webbrowser.open(BRAW_SDK_URL)
        if messagebox.askyesno(
            APP_NAME,
            'Si ya tienes el zip del SDK descargado, Proxynas puede copiar por ti los\n'
            'ficheros necesarios.\n\n¿Quieres importarlo ahora?',
        ):
            self._import_braw_sdk()

    def _check_braw_sdk_for_folder(self, folder):
        """Avisa solo si la carpeta elegida trae .braw y falta el SDK."""
        if not contains_files(folder, BRAW_EXTENSIONS, max_depth=BRAW_SCAN_DEPTH):
            return
        missing = [
            os.path.basename(path)
            for path in (braw_proxy.BRAW_DECODE, os.path.join(braw_proxy.SDK_DIR, 'BlackmagicRawAPI.dll'))
            if not os.path.isfile(path)
        ]
        if missing:
            self.root.after(0, lambda: self._offer_braw_sdk(', '.join(missing)))

    def _start_proxy_creation(self):
        if self.proxy_running or self.running:
            return
        root_dir = self.watch_folder_var.get().strip()
        if not root_dir or not os.path.isdir(root_dir):
            messagebox.showerror('Error', 'Selecciona una carpeta vigilada válida.')
            return
        ff_ok, ff_missing = check_ffmpeg()
        if not ff_ok:
            messagebox.showerror(APP_NAME, f'No se encuentra {ff_missing}.\n\n{FFMPEG_HELP}')
            return
        if contains_files(root_dir, BRAW_EXTENSIONS):
            ok, missing = check_braw_tools()
            if not ok:
                self._offer_braw_sdk(missing)
                return
        codec = self.proxy_codec_var.get()
        accel = self.proxy_accel_var.get()
        proxy_caps = (self.encoder_capabilities or {}).get('proxy') or {}
        chosen = (proxy_caps.get(codec) or {}).get(accel) or {}
        # Solo se comprueba si la deteccion ya termino: asi no se bloquea la
        # interfaz, y si aun no hay datos el error lo da el propio trabajo.
        if proxy_caps and not chosen.get('available'):
            label = braw_proxy.PROXY_CODEC_LABELS.get(codec, codec)
            messagebox.showerror(
                APP_NAME,
                f"No hay ningún encoder {label} en {ACCEL_LABELS.get(accel, accel)} para los proxies.\n\n"
                f"{chosen.get('reason') or 'Prueba con otro códec o con CPU.'}",
            )
            return
        self._set_proxy_running(True)
        self.proxy_status_var.set('Buscando material sin proxy...')
        threading.Thread(target=self._run_proxy_creation_for_watch_folder, daemon=True).start()

    def _run_proxy_creation_for_watch_folder(self):
        try:
            try:
                summary = self.registry.reconcile(
                    self.watch_folder_var.get().strip(),
                    proxy_ext_fn=proxy_extension_for,
                )
                if summary.get('moves') or summary.get('orphans') or summary.get('news'):
                    self._log(
                        f"Reconciliado: {summary['moves']} movidos, "
                        f"{summary['orphans']} huérfanos, "
                        f"{summary['news']} nuevos."
                    )
            except Exception as exc:
                self._log(f'Error en reconcile de proxies: {exc}')

            codec = self.proxy_codec_var.get()
            accel = self.proxy_accel_var.get()
            encoder_result = braw_proxy.detect_proxy_encoder(codec, accel)
            if not encoder_result.get('available'):
                label = braw_proxy.PROXY_CODEC_LABELS.get(codec, codec)
                raise RuntimeError(f"Sin encoder {label} para proxies: {encoder_result.get('reason')}")
            self._log(f"Encoder de proxy: {encoder_result['encoder']}")
            jobs = self._find_pending_proxy_jobs()
            if not jobs:
                self.root.after(0, lambda: self.proxy_status_var.set('Todo actualizado. No hay proxies pendientes.'))
                self._log('Proxies: todo actualizado.')
                return
            self._log(f'Proxies pendientes: {len(jobs)}')
            for index, (source_path, proxy_path) in enumerate(jobs, start=1):
                self.root.after(0, lambda i=index, n=len(jobs): self.proxy_status_var.set(f'Creando proxy {i}/{n}...'))
                self._log(f'Proxy {index}/{len(jobs)}: {basename(source_path)}')
                Path(os.path.dirname(proxy_path)).mkdir(parents=True, exist_ok=True)
                if source_path.lower().endswith('.braw'):
                    braw_proxy.create_braw_proxy(source_path, proxy_path, codec, accel)
                else:
                    braw_proxy.create_standard_proxy(source_path, proxy_path, codec, accel)
            self.root.after(0, lambda: self.proxy_status_var.set('Proxies creados.'))
            self._log('Proxies finalizados.')
        except Exception as exc:
            self.root.after(0, lambda: self.proxy_status_var.set(f'Error: {exc}'))
            self._log(f'Error creando proxies: {exc}')
        finally:
            self.root.after(0, lambda: self._set_proxy_running(False))

    def _toggle_proxy_live(self):
        if self.proxy_live_var.get():
            self.proxy_status_var.set('Modo live activo. Vigilando material nuevo...')
            if not self.proxy_live_thread or not self.proxy_live_thread.is_alive():
                self.proxy_live_thread = threading.Thread(target=self._proxy_live_loop, daemon=True)
                self.proxy_live_thread.start()
        else:
            self.proxy_status_var.set('Modo live desactivado.')

    def _proxy_live_loop(self):
        while self.proxy_live_var.get():
            if not self.proxy_running and not self.running:
                self.root.after(0, self._start_proxy_creation)
            for _ in range(15):
                if not self.proxy_live_var.get():
                    break
                time.sleep(1)

    def _toggle_backup_live(self):
        if self.backup_live_var.get():
            self._log('Backup live activo. Vigilando carpeta seleccionada...')
            if not self.backup_live_thread or not self.backup_live_thread.is_alive():
                self.backup_live_thread = threading.Thread(target=self._backup_live_loop, daemon=True)
                self.backup_live_thread.start()
        else:
            self._log('Backup live desactivado.')

    def _backup_live_loop(self):
        while self.backup_live_var.get():
            if not self.running and not self.proxy_running and self.dst_var.get().strip():
                self.root.after(0, self._start)
            for _ in range(30):
                if not self.backup_live_var.get():
                    break
                time.sleep(1)

    def _minimize_to_tray(self):
        try:
            import pystray
            from PIL import Image
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.root.withdraw()
                return

            def show_window(_icon=None, _item=None):
                self.root.after(0, self.root.deiconify)

            def quit_app(icon=None, _item=None):
                if icon:
                    icon.stop()
                self.root.after(0, self.root.quit)

            image = Image.open(ICON_PATH) if os.path.isfile(ICON_PATH) else Image.new('RGBA', (64, 64), (31, 111, 235, 255))
            menu = pystray.Menu(pystray.MenuItem('Mostrar Proxynas', show_window), pystray.MenuItem('Salir', quit_app))
            self.tray_icon = pystray.Icon('Proxynas', image, APP_NAME, menu)
            self.tray_icon.run_detached()
            self.root.withdraw()
        except Exception:
            self._log('Bandeja del sistema no disponible en este entorno; minimizando a la barra de tareas.')
            self.root.iconify()

    def _detect_defaults(self):
        """Detecta GPU y Google Drive en segundo plano."""
        def detect():
            lines = []
            lines.append(f"OS: {platform.system()} {platform.release()}")

            # GPU
            caps = detect_encoder_capabilities(force=True)
            # H.265/H.264 de proxy son otra familia que los presets de backup,
            # asi que se validan aparte probando encoders de verdad.
            caps['proxy'] = {}
            for codec in braw_proxy.PROXY_CODECS:
                caps['proxy'][codec] = {}
                for accel in (ACCEL_GPU, ACCEL_CPU):
                    caps['proxy'][codec][accel] = braw_proxy.detect_proxy_encoder(codec, accel)
            self.encoder_capabilities = caps
            gpu = caps.get('gpu', '')
            lines.append(f"GPU: {gpu or 'No detectada'}")
            for preset in (CODEC_AV1_HW, CODEC_HEVC_HW, CODEC_HEVC_SW):
                data = caps.get('presets', {}).get(preset, {})
                if data.get('available'):
                    lines.append(f"{CODEC_PRESET_LABELS[preset]}: {data.get('encoder')}")
                else:
                    lines.append(f"{CODEC_PRESET_LABELS[preset]}: no disponible")

            # ffmpeg
            ff_ok, ff_missing = check_ffmpeg()
            if not ff_ok:
                lines.append(f"⚠ {ff_missing} no encontrado en PATH")
            else:
                lines.append("ffmpeg/ffprobe: ✓")

            # magick
            if check_magick():
                lines.append("ImageMagick: ✓")
            else:
                lines.append("⚠ ImageMagick (magick) no encontrado en PATH")

            braw_ok, braw_missing = check_braw_tools()
            if braw_ok:
                lines.append("Blackmagic RAW SDK portable: OK")
            else:
                lines.append(f"BRAW portable no disponible: {braw_missing}")
            proxy_caps = caps.get('proxy') or {}
            for codec in braw_proxy.PROXY_CODECS:
                for accel in (ACCEL_GPU, ACCEL_CPU):
                    data = (proxy_caps.get(codec) or {}).get(accel) or {}
                    nombre = f"{braw_proxy.PROXY_CODEC_LABELS[codec]} {ACCEL_LABELS[accel]}"
                    lines.append(f"Proxies {nombre}: {data.get('encoder') if data.get('available') else 'no disponible'}")

            # Google Drive (Windows)
            gd = find_google_drive_path()
            if gd:
                if not self.dst_var.get():
                    self.dst_var.set(os.path.join(gd, 'Mi unidad', 'BACKUP'))

            self.root.after(0, lambda: self._apply_encoder_capabilities(caps, "\n".join(lines)))

        threading.Thread(target=detect, daemon=True).start()

    def _apply_encoder_capabilities(self, caps, status_text=None):
        self.encoder_capabilities = caps
        available_presets = [
            preset for preset in (CODEC_AV1_HW, CODEC_HEVC_HW, CODEC_HEVC_SW)
            if caps.get('presets', {}).get(preset, {}).get('available')
        ]

        for preset, rb in self.codec_radio_buttons.items():
            data = caps.get('presets', {}).get(preset, {})
            label = CODEC_PRESET_LABELS[preset]
            if data.get('available'):
                rb.config(text=f"{label} ({data.get('encoder')})", state='normal')
            else:
                reason = data.get('reason') or 'no disponible'
                rb.config(text=f"{label} - no disponible", state='disabled')

        if self.codec_preset_var.get() not in available_presets and available_presets:
            self.codec_preset_var.set(available_presets[0])

        selected = self.codec_preset_var.get()
        selected_data = caps.get('presets', {}).get(selected, {})
        if available_presets:
            self.codec_status_label.config(
                text=f"Seleccionado: {CODEC_PRESET_LABELS.get(selected, selected)} ({selected_data.get('encoder')})"
            )
        else:
            self.codec_status_label.config(text='No hay códecs de conversión disponibles; se copiará el vídeo original.')

        self._apply_proxy_capabilities(caps.get('proxy') or {})

        if status_text:
            self.info_label.config(text=status_text)
        self._on_mode_change()
        self._persist_config()

    def _on_transcode_change(self):
        self._persist_config()
        self._on_mode_change()

    def _on_codec_preset_change(self):
        self._persist_config()
        if self.encoder_capabilities:
            self._apply_encoder_capabilities(self.encoder_capabilities)

    def _apply_proxy_capabilities(self, proxy_caps):
        """Habilita GPU/CPU segun lo que este equipo tenga validado de verdad."""
        # Sin datos de proxy (deteccion a medias por otra via) se deja la UI
        # como esta: deshabilitar los radios por falta de datos seria mentir.
        if not proxy_caps:
            return
        codec = self.proxy_codec_var.get()
        data = proxy_caps.get(codec) or {}
        for accel, radio in self.proxy_accel_radio_buttons.items():
            available = (data.get(accel) or {}).get('available')
            radio.config(state='normal' if available else 'disabled')
        if not (data.get(ACCEL_GPU) or {}).get('available') and self.proxy_accel_var.get() == ACCEL_GPU:
            self.proxy_accel_var.set(ACCEL_CPU)
        chosen = data.get(self.proxy_accel_var.get()) or {}
        label = braw_proxy.PROXY_CODEC_LABELS.get(codec, codec)
        if chosen.get('available'):
            self.proxy_codec_status_label.config(text=f"Seleccionado: {label} ({chosen.get('encoder')})")
        else:
            reason = chosen.get('reason') or 'sin encoder compatible en este ffmpeg'
            self.proxy_codec_status_label.config(text=f"{label}: no disponible ({reason})")

    def _on_proxy_codec_change(self):
        self._persist_config()
        if self.encoder_capabilities:
            self._apply_encoder_capabilities(self.encoder_capabilities)

    def _on_audio_preset_change(self):
        self._persist_config()

    def _on_mode_change(self):
        mode = self.mode_var.get()
        codec_state = 'normal' if mode in ('video', 'todo') and self.transcode_var.get() else 'disabled'
        audio_state = 'normal' if mode in ('audio_img', 'todo') else 'disabled'
        if mode in ('video', 'todo'):
            self.transcode_check.config(state='normal')
        else:
            self.transcode_check.config(state='disabled')
        for rb in self.audio_radio_buttons.values():
            rb.config(state=audio_state)
        for preset, rb in self.codec_radio_buttons.items():
            if codec_state == 'disabled':
                rb.config(state='disabled')
            elif self.encoder_capabilities:
                data = self.encoder_capabilities.get('presets', {}).get(preset, {})
                rb.config(state='normal' if data.get('available') else 'disabled')
        if hasattr(self, 'codec_status_label'):
            if codec_state == 'disabled':
                self.codec_status_label.config(text='Conversión de vídeo desactivada para este modo.')
            elif self.encoder_capabilities:
                selected = self.codec_preset_var.get()
                data = self.encoder_capabilities.get('presets', {}).get(selected, {})
                if data.get('available'):
                    self.codec_status_label.config(text=f"Seleccionado: {CODEC_PRESET_LABELS.get(selected, selected)} ({data.get('encoder')})")

    def _browse_src(self):
        d = filedialog.askdirectory(title="Seleccionar directorio de origen")
        if d:
            self.src_var.set(d)
            # Auto-rellenar destino si vacío
            if not self.dst_var.get():
                return
            # Si hay destino, sugerir subdirectorio
            dirname = basename(d)
            try:
                year = dirname[:4]
                if not year.isdigit():
                    year = str(time.localtime().tm_year)
            except Exception:
                year = str(time.localtime().tm_year)
            current_dst = self.dst_var.get()
            # Solo sugerir si el destino parece ser la raíz de BACKUP
            if current_dst.rstrip('/\\').endswith('BACKUP'):
                self.dst_var.set(os.path.join(current_dst, year, dirname))
                self._persist_config()

    def _browse_dst(self):
        d = filedialog.askdirectory(title="Seleccionar directorio de destino")
        if d:
            self.dst_var.set(d)

    def _log(self, msg):
        """Escribe en el log de forma thread-safe."""
        def _write():
            self.log_text.config(state='normal')
            self.log_text.insert('end', msg + '\n')
            self.log_text.see('end')
            self.log_text.config(state='disabled')
        self.root.after(0, _write)

    def _update_progress(self):
        """Actualiza la barra de progreso."""
        self.processed_files += 1

        def _update():
            if self.total_files > 0:
                pct = (self.processed_files / self.total_files) * 100
                self.progress_bar['value'] = pct
                self.progress_label.config(
                    text=f"{self.processed_files}/{self.total_files} archivos ({pct:.0f}%)"
                )
        self.root.after(0, _update)

    def _update_file_progress(self, filename, percent, speed):
        def _update():
            speed_text = f' · {speed}' if speed and speed != 'N/A' else ''
            if self.total_files:
                self.progress_bar['value'] = ((self.processed_files + percent / 100) / self.total_files) * 100
            self.progress_label.config(
                text=f"{self.processed_files}/{self.total_files} archivos · {filename}: {percent:.0f}%{speed_text}"
            )
        self.root.after(0, _update)

    def _start(self):
        self.src_var.set(self.watch_folder_var.get().strip())
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()

        if not src or not os.path.isdir(src):
            messagebox.showerror("Error", "El directorio de origen no existe.")
            return
        if not dst:
            messagebox.showerror("Error", "Selecciona un directorio de destino.")
            return

        # Verificar herramientas necesarias
        mode = self.mode_var.get()
        needs_video_ffmpeg = mode in ('todo', 'video') and self.transcode_var.get()
        needs_audio_ffmpeg = mode in ('todo', 'audio_img') and self.audio_preset_var.get() != AUDIO_NO_TRANSCODE
        needs_ffmpeg = needs_video_ffmpeg or needs_audio_ffmpeg
        needs_magick = mode in ('todo', 'audio_img')

        if needs_ffmpeg:
            ff_ok, ff_missing = check_ffmpeg()
            if not ff_ok:
                messagebox.showerror("Error", f'No se encuentra {ff_missing}.\n\n{FFMPEG_HELP}')
                return

        if self.transcode_var.get() and mode in ('todo', 'video'):
            caps = self.encoder_capabilities or detect_encoder_capabilities()
            self.encoder_capabilities = caps
            preset = self.codec_preset_var.get()
            if not select_encoder_for_preset(preset, caps):
                data = caps.get('presets', {}).get(preset, {})
                reason = data.get('reason') or 'no disponible'
                messagebox.showerror("Error", f"{CODEC_PRESET_LABELS.get(preset, preset)} no disponible: {reason}")
                self._apply_encoder_capabilities(caps)
                return

        if needs_magick and not check_magick():
            messagebox.showerror("Error", "No se encuentra ImageMagick (magick). Instálalo y añádelo al PATH.")
            return

        if self.transcode_var.get() and mode in ('todo', 'video') and contains_files(src, BRAW_EXTENSIONS):
            braw_ok, braw_missing = check_braw_tools()
            if not braw_ok:
                self._offer_braw_sdk(braw_missing)
                return

        self.running = True
        self.btn_start.config(state='disabled')
        self.btn_cancel.config(state='normal')
        self.processed_files = 0
        self.progress_bar['value'] = 0

        # Limpiar log
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.config(state='disabled')

        threading.Thread(target=self._run_backup, args=(src, dst), daemon=True).start()

    def _run_backup(self, src, dst):
        mode = self.mode_var.get()
        transcode = self.transcode_var.get()

        src_basename = os.path.basename(src.rstrip(os.sep))
        dst_last = os.path.basename(dst.rstrip(os.sep))
        if src_basename and dst_last.lower() != src_basename.lower():
            effective_dst = os.path.join(dst, src_basename)
        else:
            effective_dst = dst

        self.processor = BackupProcessor(
            src, effective_dst,
            log_callback=self._log,
            progress_callback=self._update_progress,
            detail_callback=self._update_file_progress,
            backup_braw_originals=self.backup_braw_originals_var.get(),
            codec_preset=self.codec_preset_var.get(),
            encoder_capabilities=self.encoder_capabilities,
            audio_preset=self.audio_preset_var.get(),
        )
        p = self.processor

        self._log("=" * 50)
        self._log("Iniciando backup")
        self._log(f"Origen:  {src}")
        self._log(f"Destino: {effective_dst}")
        preset = self.codec_preset_var.get()
        encoder = select_encoder_for_preset(preset, self.encoder_capabilities) if transcode else None
        self._log(f"Modo: {mode} | Transcodificar: {'Sí' if transcode else 'No'}")
        if transcode and mode in ('todo', 'video'):
            self._log(f"Códec de backup: {CODEC_PRESET_LABELS.get(preset, preset)} ({encoder})")
        if mode in ('todo', 'audio_img'):
            audio_preset = self.audio_preset_var.get()
            self._log(f"Audio: {AUDIO_PRESET_LABELS.get(audio_preset, audio_preset)}")
        self._log("=" * 50)

        # Contar archivos para la barra de progreso
        self.total_files = 0
        if mode in ('todo', 'audio_img'):
            self.total_files += p.count_files(AUDIO_EXTENSIONS)
            self.total_files += p.count_files(IMAGE_EXTENSIONS)
        if mode in ('todo', 'video'):
            self.total_files += p.count_files(VIDEO_EXTENSIONS)
        if mode in ('todo', 'otros'):
            self.total_files += p.count_remaining_files()

        self._log(f"Archivos a procesar: ~{self.total_files}")
        self._log("")

        try:
            Path(effective_dst).mkdir(parents=True, exist_ok=True)

            if mode in ('todo', 'audio_img'):
                self._log("── Audio ──")
                p.process_files(AUDIO_EXTENSIONS, p.process_audio)
                self._log("── Imágenes ──")
                p.process_files(IMAGE_EXTENSIONS, p.process_images)

            if mode in ('todo', 'video'):
                self._log("── Vídeo ──")
                if transcode:
                    p.process_files(VIDEO_EXTENSIONS, p.process_videos)
                else:
                    p.process_files(VIDEO_EXTENSIONS, p.process_videos_copy)

            if mode in ('todo', 'otros'):
                self._log("── Otros archivos ──")
                p.copy_remaining_files()

        except Exception as e:
            self._log(f"\n✗ Error fatal: {e}")

        # Resumen
        s = p.stats
        self._log("")
        self._log("=" * 50)
        if p.cancelled:
            self._log("⚠ Backup cancelado por el usuario.")
        else:
            self._log("✓ Backup finalizado.")
        self._log(f"  Vídeos: {s['videos']}  |  Audio: {s['audio']}  |  Imágenes: {s['images']}")
        self._log(f"  Copiados: {s['copied']}  |  Saltados: {s['skipped']}  |  Errores: {s['errors']}")
        self._log("=" * 50)

        # Apagar si está activado
        if not p.cancelled and self.shutdown_var.get():
            try:
                mins = int(self.shutdown_min_var.get())
                if mins > 0:
                    self._log(f"\nEl equipo se apagará en {mins} minuto{'s' if mins > 1 else ''}…")
                    time.sleep(mins * 60)
                    if IS_WINDOWS:
                        os.system('shutdown /s /t 0')
                    else:
                        os.system('systemctl poweroff')
            except ValueError:
                pass

        self._finish(cancelled=p.cancelled)

    def _cancel(self):
        if self.processor:
            self.processor.cancel()
            self._log("\n⚠ Cancelado. Deteniendo el archivo actual…")

    def _finish(self, cancelled=False):
        def _done():
            self.running = False
            self.btn_start.config(state='normal')
            self.btn_cancel.config(state='disabled')
            if cancelled:
                self.progress_bar['value'] = 0
                self.progress_label.config(text='')
        self.root.after(0, _done)


# ─────────────────────────────────────────────
# CLI fallback (para uso sin GUI)
# ─────────────────────────────────────────────

def run_cli():
    """Modo CLI compatible con el script original."""
    if len(sys.argv) < 3:
        print("Uso: Proxynas.py --cli <directorio_origen> <directorio_destino> [--no-transcode]")
        print("     Proxynas.py                    (interfaz gráfica)")
        sys.exit(1)

    args = sys.argv[1:]
    args.remove('--cli')
    no_transcode = '--no-transcode' in args
    if no_transcode:
        args.remove('--no-transcode')

    src_dir = args[0]
    dst_dir = args[1] if len(args) > 1 else None

    if not os.path.isdir(src_dir):
        print(f"Error: '{src_dir}' no existe.")
        sys.exit(1)

    if not dst_dir:
        print("Error: debes especificar un directorio de destino.")
        sys.exit(1)

    ff_ok, ff_missing = check_ffmpeg()
    if not ff_ok:
        print(f"Error: no se encuentra {ff_missing} en PATH.")
        sys.exit(1)

    p = BackupProcessor(src_dir, dst_dir, backup_braw_originals='--include-braw-originals' in sys.argv)

    print(f"\nOrigen:  {src_dir}")
    print(f"Destino: {dst_dir}")
    print(f"Transcodificar: {'No' if no_transcode else 'Sí'}\n")

    p.process_files(AUDIO_EXTENSIONS, p.process_audio)
    p.process_files(IMAGE_EXTENSIONS, p.process_images)
    if no_transcode:
        p.process_files(VIDEO_EXTENSIONS, p.process_videos_copy)
    else:
        p.process_files(VIDEO_EXTENSIONS, p.process_videos)
    p.copy_remaining_files()

    s = p.stats
    print(f"\nVídeos: {s['videos']} | Audio: {s['audio']} | Imágenes: {s['images']}")
    print(f"Copiados: {s['copied']} | Saltados: {s['skipped']} | Errores: {s['errors']}")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def create_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


if __name__ == '__main__':
    enable_high_dpi()
    if not ensure_ffmpeg():
        message = 'No se pudieron descargar ffmpeg/ffprobe. Comprueba la conexión a Internet.'
        if '--cli' in sys.argv:
            print(message, file=sys.stderr)
            raise SystemExit(1)
        root = create_root()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
        raise SystemExit(1)
    if '--cli' in sys.argv:
        run_cli()
    else:
        root = create_root()
        app = BackupApp(root)
        root.mainloop()


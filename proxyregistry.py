"""Registro persistente para seguimiento de movimientos de source y sus proxies."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path


PROXY_SUBDIR = 'Proxy'
ORPHAN_SUBDIR = '_orphan'
PARTIAL_MARKER = '.partial'
ORPHAN_THRESHOLD_SCANS = 10
SPARSE_SCAN_RATIO = 0.5
FFPROBE_TIMEOUT = 5
BRAW_INFO_TIMEOUT = 10

PROXY_CANDIDATE_EXTENSIONS = {'.braw', '.mov', '.mxf'}
SKIP_DIRS = {'Proxy', '_orphan', 'portable', 'tools', '__pycache__', '.git', '.agents', '.codex'}


def _atomic_write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _probe_duration_ffprobe(ffprobe_bin, filepath):
    try:
        result = subprocess.run(
            [ffprobe_bin, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=FFPROBE_TIMEOUT, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _probe_duration_braw(braw_decode_bin, sdk_dir, filepath):
    try:
        result = subprocess.run(
            [braw_decode_bin, '--info', '--sdk', sdk_dir, '--scale', '8', filepath],
            capture_output=True, text=True, timeout=BRAW_INFO_TIMEOUT, check=True,
        )
        info = json.loads(result.stdout)
        frame_count = info.get('frame_count')
        frame_rate = info.get('frame_rate')
        if frame_count and frame_rate:
            return float(frame_count) / float(frame_rate)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError,
            ValueError, ZeroDivisionError, subprocess.CalledProcessError):
        pass
    return None


class ProxyRegistry:
    """Mantiene un registro persistente de archivos de vídeo vistos y reconcilia movimientos."""

    def __init__(self, registry_path, ffprobe_bin, braw_decode_bin=None,
                 sdk_dir=None, log_callback=None):
        self.path = registry_path
        self.ffprobe_bin = ffprobe_bin
        self.braw_decode_bin = braw_decode_bin
        self.sdk_dir = sdk_dir
        self.log = log_callback or (lambda msg: None)
        self.data = {'version': 1, 'by_watch_folder': {}}
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and 'by_watch_folder' in loaded:
                self.data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    def save(self):
        try:
            _atomic_write_json(self.path, self.data)
        except OSError as exc:
            self.log(f'No se pudo guardar el registro de proxies: {exc}')

    def reconcile(self, watch_folder, proxy_ext_fn=None):
        """Compara el estado actual con el registro. Devuelve un resumen dict."""
        watch_folder = os.path.abspath(watch_folder)
        summary = {'moves': 0, 'orphans': 0, 'news': 0, 'skipped': None}

        if not os.path.isdir(watch_folder):
            summary['skipped'] = 'no_dir'
            return summary

        entries = self.data['by_watch_folder'].setdefault(watch_folder, {})
        previous_paths = set(entries.keys())

        current = self._scan_current(watch_folder)
        current_paths = set(current.keys())

        known_count = len(previous_paths)
        if known_count > 0:
            if len(current_paths) == 0:
                self.log('Escaneo vacío: no se procesan huérfanos (¿unidad desconectada?).')
                summary['skipped'] = 'empty_scan'
                return summary
            if len(current_paths) < known_count * SPARSE_SCAN_RATIO:
                self.log(
                    f'Escaneo precavido: {len(current_paths)}/{known_count} archivos. '
                    f'No se procesan huérfanos.'
                )
                summary['skipped'] = 'sparse_scan'
                now = int(time.time())
                for path in current_paths:
                    if path in entries:
                        entries[path]['last_seen'] = now
                        entries[path]['missing_count'] = 0
                self.save()
                return summary

        now = int(time.time())
        appeared = current_paths - previous_paths
        disappeared = previous_paths - current_paths

        for path in appeared:
            current[path]['duration'] = self._probe_duration(path)

        consumed_disappeared = set()
        consumed_appeared = set()
        for new_path in sorted(appeared):
            new_meta = current[new_path]
            match = self._find_match(entries, disappeared - consumed_disappeared, new_meta)
            if match is None:
                continue
            old_entry = entries[match]
            result = self._attempt_proxy_move(match, new_path, old_entry, proxy_ext_fn)
            if result == 'moved':
                summary['moves'] += 1
                self.log(
                    f'Proxy movido: {os.path.basename(new_path)} '
                    f'({os.path.basename(os.path.dirname(match))} -> '
                    f'{os.path.basename(os.path.dirname(new_path))})'
                )
            elif result == 'orphaned':
                summary['orphans'] += 1
                self.log(
                    f'Proxy a _orphan/ (colision): {os.path.basename(old_entry.get("proxy_path", ""))}'
                )
            consumed_disappeared.add(match)
            consumed_appeared.add(new_path)

        for path in disappeared - consumed_disappeared:
            entry = entries[path]
            entry['missing_count'] = entry.get('missing_count', 0) + 1
            if entry['missing_count'] >= ORPHAN_THRESHOLD_SCANS:
                if self._quarantine_proxy(entry):
                    summary['orphans'] += 1
                    self.log(
                        f'Proxy huérfano: {os.path.basename(entry.get("proxy_path", ""))} '
                        f'-> _orphan/ (sin source tras {ORPHAN_THRESHOLD_SCANS} escaneos)'
                    )
                entries.pop(path, None)

        for path in current_paths:
            meta = current[path]
            if path in entries:
                entries[path]['last_seen'] = now
                entries[path]['missing_count'] = 0
                if entries[path].get('size') != meta['size']:
                    entries[path]['size'] = meta['size']
            else:
                proxy_path = self._compute_proxy_path(path, proxy_ext_fn)
                entries[path] = {
                    'basename': meta['basename'],
                    'size': meta['size'],
                    'duration': meta.get('duration'),
                    'last_seen': now,
                    'missing_count': 0,
                    'proxy_path': proxy_path,
                }

        for path in consumed_disappeared:
            entries.pop(path, None)

        summary['news'] = len(appeared - consumed_appeared)

        self.save()
        return summary

    def _scan_current(self, watch_folder):
        current = {}
        for dirpath, dirnames, filenames in os.walk(watch_folder):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            parts = Path(dirpath).parts
            if PROXY_SUBDIR in parts or ORPHAN_SUBDIR in parts:
                continue
            for filename in filenames:
                if PARTIAL_MARKER in filename:
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in PROXY_CANDIDATE_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if size == 0:
                    continue
                current[full] = {
                    'basename': os.path.splitext(filename)[0],
                    'size': size,
                    'ext': ext,
                }
        return current

    def _probe_duration(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()
        if (ext == '.braw' and self.braw_decode_bin and self.sdk_dir
                and os.path.isfile(self.braw_decode_bin)):
            d = _probe_duration_braw(self.braw_decode_bin, self.sdk_dir, filepath)
            if d is not None:
                return d
        if os.path.isfile(self.ffprobe_bin):
            return _probe_duration_ffprobe(self.ffprobe_bin, filepath)
        return None

    def _find_match(self, entries, candidates, new_meta):
        basename = new_meta['basename']
        size = new_meta['size']
        duration = new_meta.get('duration')

        if duration is None:
            return None

        matches = []
        for path in candidates:
            entry = entries[path]
            if entry.get('basename') != basename:
                continue
            if entry.get('size') != size:
                continue
            entry_duration = entry.get('duration')
            if entry_duration is None:
                continue
            if abs(entry_duration - duration) > 0.01:
                continue
            matches.append(path)

        if not matches:
            return None

        matches.sort(key=lambda p: entries[p].get('last_seen', 0), reverse=True)
        return matches[0]

    def _compute_proxy_path(self, source_path, proxy_ext_fn=None):
        directory = os.path.dirname(source_path)
        basename = os.path.splitext(os.path.basename(source_path))[0]
        ext = proxy_ext_fn(source_path) if proxy_ext_fn else '.mov'
        return os.path.join(directory, PROXY_SUBDIR, basename + ext)

    def _attempt_proxy_move(self, old_path, new_path, old_entry, proxy_ext_fn):
        old_proxy = old_entry.get('proxy_path')
        if not old_proxy or not os.path.exists(old_proxy):
            return 'no_source_proxy'

        new_proxy = self._compute_proxy_path(new_path, proxy_ext_fn)
        if os.path.exists(new_proxy):
            if self._quarantine_proxy(old_entry):
                return 'orphaned'
            return 'failed'

        new_proxy_dir = os.path.dirname(new_proxy)
        try:
            os.makedirs(new_proxy_dir, exist_ok=True)
            if Path(old_proxy).anchor == Path(new_proxy).anchor:
                os.rename(old_proxy, new_proxy)
            else:
                shutil.copy2(old_proxy, new_proxy)
                os.remove(old_proxy)
            return 'moved'
        except OSError as exc:
            self.log(f'Error moviendo proxy {old_proxy} -> {new_proxy}: {exc}')
            return 'failed'

    def _quarantine_proxy(self, entry):
        proxy_path = entry.get('proxy_path')
        if not proxy_path or not os.path.exists(proxy_path):
            return False
        if ORPHAN_SUBDIR in Path(proxy_path).parts:
            return False
        proxy_dir = os.path.dirname(proxy_path)
        orphan_dir = os.path.join(proxy_dir, ORPHAN_SUBDIR)
        try:
            os.makedirs(orphan_dir, exist_ok=True)
            target = os.path.join(orphan_dir, os.path.basename(proxy_path))
            if os.path.exists(target):
                stem, ext = os.path.splitext(os.path.basename(proxy_path))
                target = os.path.join(orphan_dir, f'{stem}.{int(time.time())}{ext}')
            os.rename(proxy_path, target)
            entry['proxy_path'] = target
            return True
        except OSError as exc:
            self.log(f'Error cuarentenando proxy {proxy_path}: {exc}')
            return False

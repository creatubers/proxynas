"""Run with: python test_localization.py"""

import contextlib
import io
import os
import sys
import tkinter as tk
from unittest.mock import patch

import backup_gui
import localization
from localization import translate


assert translate('Iniciar backup', 'es') == 'Iniciar backup'
assert translate('Iniciar backup', 'en') == 'Start backup'
assert translate('Vídeos: 2 | Audio: 1 | Imágenes: 3', 'en') == 'Videos: 2 | Audio: 1 | Images: 3'

with patch.object(localization.os, 'name', 'posix'):
    with patch.dict(os.environ, {'LANGUAGE': 'es_ES:en_US'}):
        assert localization.system_language() == 'es'
    with patch.dict(os.environ, {'LANGUAGE': 'en_US'}):
        assert localization.system_language() == 'en'
with patch.object(backup_gui, 'IS_WINDOWS', False), patch.object(backup_gui, 'IS_LINUX', True):
    with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME', 'GTK_THEME': 'Adwaita:dark'}):
        assert backup_gui.system_dark_mode()
    with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME', 'GTK_THEME': 'Adwaita'}):
        assert not backup_gui.system_dark_mode()

original_argv = sys.argv
original_load = backup_gui.load_config
try:
    sys.argv = ['Proxynas.py', '--cli', '--lang', 'en', 'missing-source', 'destination']
    backup_gui.load_config = lambda: {}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            backup_gui.run_cli()
        except SystemExit as exc:
            assert exc.code == 1
    assert 'does not exist' in output.getvalue(), output.getvalue()
finally:
    sys.argv = original_argv
    backup_gui.load_config = original_load

try:
    root = tk.Tk()
except tk.TclError:
    root = None  # Headless CI still checks CLI and translations above.
if root:
    original_detect = backup_gui.BackupApp._detect_defaults
    original_drop = backup_gui.BackupApp._enable_drag_and_drop
    original_save = backup_gui.save_config
    original_system_language = backup_gui.system_language
    original_system_dark_mode = backup_gui.system_dark_mode
    other_root = None
    try:
        root.withdraw()
        saved = []
        backup_gui.load_config = lambda: {}
        backup_gui.save_config = lambda config: saved.append(config.copy())
        backup_gui.system_language = lambda: 'en'
        backup_gui.system_dark_mode = lambda: True
        backup_gui.BackupApp._detect_defaults = lambda self: None
        backup_gui.BackupApp._enable_drag_and_drop = lambda self: None
        app = backup_gui.BackupApp(root)
        assert app.language_var.get() == 'en'
        assert app.dark_mode_var.get()
        assert app.btn_start.text == 'Start backup'
        assert app.proxy_status_text.get('1.0', 'end').strip() == 'Choose a folder and create pending proxies.'
        app._persist_config()
        assert 'language' not in saved[-1] and 'dark_mode' not in saved[-1]
        app.language_var.set('es')
        app._change_language()
        assert app.btn_start.text == 'Iniciar backup'
        assert saved[-1]['language'] == 'es'
        app.dark_mode_var.set(False)
        app._toggle_dark_mode()
        assert saved[-1]['dark_mode'] is False

        backup_gui.load_config = lambda: {'language': 'es', 'dark_mode': False}
        backup_gui.system_language = lambda: 1 / 0
        backup_gui.system_dark_mode = lambda: 1 / 0
        other_root = tk.Tk()
        other_root.withdraw()
        other = backup_gui.BackupApp(other_root)
        assert other.language_var.get() == 'es' and not other.dark_mode_var.get()
    finally:
        if other_root:
            other_root.destroy()
        root.destroy()
        backup_gui.load_config = original_load
        backup_gui.save_config = original_save
        backup_gui.BackupApp._detect_defaults = original_detect
        backup_gui.BackupApp._enable_drag_and_drop = original_drop
        backup_gui.system_language = original_system_language
        backup_gui.system_dark_mode = original_system_dark_mode

print('test_localization: OK')

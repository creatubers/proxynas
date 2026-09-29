#!/usr/bin/env python3
import sys
import tkinter as tk

from backup_gui import BackupApp, enable_high_dpi, ensure_ffmpeg, load_config, run_cli
from localization import system_language, translate


def create_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


if __name__ == "__main__":
    enable_high_dpi()
    if "--cli" in sys.argv:
        # Descargar ffmpeg aqui, en la unica entrada del programa, es lo que
        # hace que la descarga ocurra en el .exe y no solo al ejecutar el
        # modulo suelto.
        if not ensure_ffmpeg():
            language = sys.argv[sys.argv.index('--lang') + 1] if '--lang' in sys.argv and sys.argv.index('--lang') + 1 < len(sys.argv) else load_config().get('language', system_language())
            print(translate('No se pudo descargar FFmpeg. Comprueba la conexión a Internet.', language), file=sys.stderr)
            raise SystemExit(1)
        run_cli()
    else:
        root = create_root()
        app = BackupApp(root)
        app.download_ffmpeg_if_needed()
        root.mainloop()

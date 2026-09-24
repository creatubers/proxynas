#!/usr/bin/env python3
import sys
import tkinter as tk

from backup_gui import BackupApp, enable_high_dpi, run_cli


def create_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


if __name__ == "__main__":
    enable_high_dpi()
    if "--cli" in sys.argv:
        run_cli()
    else:
        root = create_root()
        app = BackupApp(root)
        root.mainloop()

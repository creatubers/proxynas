# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
root = Path.cwd()

# 'portable' and 'vendor' are local-only (see .gitignore); bundle them if present.
bundled = [name for name in ('portable', 'vendor') if (root / name).is_dir()]

a = Analysis(
    ['Proxynas.py'],
    pathex=[str(root)] + [str(root / name) for name in bundled],
    binaries=[],
    datas=[('proxynas.png', '.'), ('proxynas.ico', '.'),
           # El decodificador es nuestro (no es del SDK) y la app lo busca en
           # <app>/portable/bin, asi que lo pone el propio bundle.
           ('tools/braw_decode/braw_decode.exe', 'portable/bin')]
    + [(name, name) for name in bundled],
    hiddenimports=[
        'pystray',
        'PIL',
        'PIL.Image',
        'tkinterdnd2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Proxynas',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX empaqueta el .exe y dispara heuristicas de antivirus, y aqui no
    # compensa: la app carga rapido igual.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Un .exe sin recurso de version suma puntos en las heuristicas de
    # Defender/SmartScreen de los builds sin firmar.
    version='version_info.txt',
    icon='proxynas.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Proxynas',
)


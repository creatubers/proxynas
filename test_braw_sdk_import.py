"""Comprobacion del importador de zip del SDK BRAW.

Ejecutar con:  python test_braw_sdk_import.py
"""

import os
import struct
import tempfile
import types
import zipfile

import proxygenerator

SDK_MEMBERS = {
    'Blackmagic_RAW_SDK/Include/BlackmagicRawAPI.h': b'header',
    'Blackmagic_RAW_SDK/Win/x64/BlackmagicRawAPI.dll': b'dll-x64',
    'Blackmagic_RAW_SDK/Win/x86/BlackmagicRawAPI.dll': b'dll-x86',
    'Blackmagic_RAW_SDK/Win/x64/DecoderCUDA.dll': b'cuda',
    'Blackmagic_RAW_SDK/Win/x64/DecoderOpenCL.dll': b'opencl',
    'Blackmagic_RAW_SDK/Win/x64/InstructionSetServicesAVX.dll': b'avx',
    'Blackmagic_RAW_SDK/Win/x64/InstructionSetServicesAVX2.dll': b'avx2',
    'Blackmagic_RAW_SDK/Win/x64/BlackmagicRawAPI.lib': b'lib',
    'Blackmagic_RAW_SDK/Tools/braw_decode.exe': b'decoder',
}


def write_zip(path, members):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)



def check_folder_warning():
    """Solo avisa si la carpeta elegida trae .braw y falta el SDK."""
    import backup_gui

    class Stub:
        def __init__(self):
            self.offered = []
            self.root = types.SimpleNamespace(after=lambda _ms, fn: fn())

        def _offer_braw_sdk(self, missing=None):
            self.offered.append(missing)

    real_decode = backup_gui.braw_proxy.BRAW_DECODE
    real_sdk = backup_gui.braw_proxy.SDK_DIR
    stub = Stub()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = os.path.join(tmp, 'sin_braw')
            braw_dir = os.path.join(tmp, 'con_braw')
            os.makedirs(empty_dir)
            os.makedirs(braw_dir)
            open(os.path.join(braw_dir, 'clip.braw'), 'wb').close()

            backup_gui.braw_proxy.BRAW_DECODE = os.path.join(tmp, 'nope.exe')
            backup_gui.braw_proxy.SDK_DIR = tmp

            backup_gui.BackupApp._check_braw_sdk_for_folder(stub, empty_dir)
            assert stub.offered == [], 'sin .braw no debe avisar'

            backup_gui.BackupApp._check_braw_sdk_for_folder(stub, braw_dir)
            assert len(stub.offered) == 1, stub.offered
            assert 'nope.exe' in stub.offered[0], stub.offered

            present = os.path.join(tmp, 'braw_decode.exe')
            open(present, 'wb').close()
            open(os.path.join(tmp, 'BlackmagicRawAPI.dll'), 'wb').close()
            backup_gui.braw_proxy.BRAW_DECODE = present
            backup_gui.BackupApp._check_braw_sdk_for_folder(stub, braw_dir)
            assert len(stub.offered) == 1, 'con SDK no debe avisar'
    finally:
        backup_gui.braw_proxy.BRAW_DECODE = real_decode
        backup_gui.braw_proxy.SDK_DIR = real_sdk



def check_scan_depth():
    """El aviso limita la profundidad; los gates de proxy/backup no."""
    import backup_gui

    with tempfile.TemporaryDirectory() as tmp:
        shallow = os.path.join(tmp, 'DCIM', '100MEDIA', 'clip.braw')
        deep = os.path.join(tmp, 'a', 'b', 'c', 'd', 'e', 'hondo.braw')
        for path in (shallow, deep):
            os.makedirs(os.path.dirname(path))
            open(path, 'wb').close()

        assert backup_gui.contains_files(tmp, backup_gui.BRAW_EXTENSIONS, max_depth=backup_gui.BRAW_SCAN_DEPTH)
        assert backup_gui.contains_files(tmp, backup_gui.BRAW_EXTENSIONS)

        os.remove(shallow)
        assert not backup_gui.contains_files(tmp, backup_gui.BRAW_EXTENSIONS, max_depth=backup_gui.BRAW_SCAN_DEPTH), \
            'no debería bajar hasta el fichero hondo'
        assert backup_gui.contains_files(tmp, backup_gui.BRAW_EXTENSIONS), \
            'el escaneo completo si debe encontrarlo'



def fake_pe(machine):
    """PE mínimo con la arquitectura pedida (0x8664 = x64, 0xAA64 = ARM64)."""
    data = bytearray(0x100)
    struct.pack_into("<I", data, 0x3C, 0x80)
    struct.pack_into("<H", data, 0x84, machine)
    return bytes(data)


def check_sdk_tree_picker():
    """Del arbol extraido del instalador se elige el x64, nunca el ARM."""
    import backup_gui  # noqa: F401  (no tocar la config real)
    import proxygenerator as pg

    with tempfile.TemporaryDirectory() as tmp:
        def put(rel, machine):
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(fake_pe(machine))

        put("Blackmagic RAW SDK/Win/Libraries/BlackmagicRawAPI.dll", 0x8664)
        put("Blackmagic RAW SDK/Win/Libraries/ARM64/BlackmagicRawAPI.dll", 0xAA64)
        put("Blackmagic RAW SDK/Win/Libraries/ARM64EC/BlackmagicRawAPI.dll", 0x8664)
        put("Blackmagic RAW Player/BlackmagicRawAPI/BlackmagicRawAPI.dll", 0x8664)

        chosen = pg.sdk_folder_in_tree(tmp)
        assert chosen, "debería encontrar la carpeta con el DLL x64"
        assert "arm" not in chosen.lower(), chosen
        assert chosen.endswith(os.path.join("Win", "Libraries")), chosen

        solo_arm = os.path.join(tmp, "solo_arm")
        arm_path = os.path.join(solo_arm, "ARM64", "BlackmagicRawAPI.dll")
        os.makedirs(os.path.dirname(arm_path))
        with open(arm_path, "wb") as handle:
            handle.write(fake_pe(0xAA64))
        assert pg.sdk_folder_in_tree(solo_arm) is None, "con solo ARM no hay carpeta válida"


def check_braw_gate():
    """El aviso de BRAW no debe hablar de FFmpeg, y tampoco ofrecer el SDK."""
    import backup_gui

    with tempfile.TemporaryDirectory() as tmp:
        sdk_dir = os.path.join(tmp, "sdk")
        bin_dir = os.path.join(tmp, "bin")
        os.makedirs(sdk_dir)
        os.makedirs(bin_dir)

        names = ("BIN_DIR", "SDK_DIR", "BRAW_DECODE", "FFMPEG", "FFPROBE")
        real = {name: getattr(proxygenerator, name) for name in names}
        try:
            proxygenerator.BIN_DIR = bin_dir
            proxygenerator.SDK_DIR = sdk_dir
            proxygenerator.BRAW_DECODE = os.path.join(bin_dir, "braw_decode.exe")
            proxygenerator.FFMPEG = os.path.join(bin_dir, "ffmpeg.exe")
            proxygenerator.FFPROBE = os.path.join(bin_dir, "ffprobe.exe")

            ok, missing = backup_gui.check_braw_tools()
            assert not ok
            assert "FFmpeg" not in missing and "FFprobe" not in missing, missing
            assert "Decodificador BRAW portable" in missing, missing

            with open(proxygenerator.BRAW_DECODE, "wb") as handle:
                handle.write(b"decoder")
            ok, missing = backup_gui.check_braw_tools()
            assert not ok and "BlackmagicRawAPI.dll" in missing, missing

            with open(os.path.join(sdk_dir, "BlackmagicRawAPI.dll"), "wb") as handle:
                handle.write(b"dll")
            assert backup_gui.check_braw_tools() == (True, None)
        finally:
            for name, value in real.items():
                setattr(proxygenerator, name, value)

    captured = []
    real_ask = backup_gui.messagebox.askyesno
    real_open = backup_gui.webbrowser.open
    try:
        backup_gui.messagebox.askyesno = lambda title, message, **kw: captured.append(message) or False
        backup_gui.webbrowser.open = lambda url: None
        stub = types.SimpleNamespace(_import_braw_sdk=lambda: None)
        backup_gui.BackupApp._offer_braw_sdk(stub, "No se encuentra el SDK BRAW portable: X")
        assert captured, "deberia pedir algo al usuario"
        message = captured[0]
        assert "FFmpeg" not in message, message
        assert "No se encuentra el SDK BRAW portable" in message, message
        assert "blackmagicdesign.com" in message, message
        assert "importar" in captured[1].lower(), captured[1]
    finally:
        backup_gui.messagebox.askyesno = real_ask
        backup_gui.webbrowser.open = real_open


def main():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, 'sdk.zip')
        write_zip(zip_path, SDK_MEMBERS)

        with zipfile.ZipFile(zip_path) as archive:
            picked = proxygenerator.braw_sdk_entries(archive.namelist())

        assert picked['blackmagicrawapi.dll'].endswith('x64/BlackmagicRawAPI.dll'), picked
        assert len([key for key in picked if key.endswith('.dll')]) == 5, picked
        assert 'blackmagicrawapi.h' not in picked, 'no debe copiar cabeceras'
        assert 'blackmagicrawapi.lib' not in picked, 'no debe copiar libs'

        sdk_dir = os.path.join(tmp, 'sdk')
        bin_dir = os.path.join(tmp, 'bin')
        proxygenerator.SDK_DIR = sdk_dir
        proxygenerator.BIN_DIR = bin_dir
        proxygenerator.BRAW_DECODE = os.path.join(bin_dir, 'braw_decode.exe')

        result = proxygenerator.import_braw_sdk(zip_path)

        assert os.path.isfile(os.path.join(sdk_dir, 'BlackmagicRawAPI.dll'))
        assert os.path.isfile(os.path.join(sdk_dir, 'InstructionSetServicesAVX2.dll'))
        assert not os.path.exists(os.path.join(sdk_dir, 'BlackmagicRawAPI.h'))
        assert os.path.isfile(os.path.join(bin_dir, 'braw_decode.exe'))
        assert result['missing'] == [], result
        assert result['decoder'] is True, result

        empty_zip = os.path.join(tmp, 'vacio.zip')
        write_zip(empty_zip, {'leeme.txt': b'nada'})
        try:
            proxygenerator.import_braw_sdk(empty_zip)
        except ValueError:
            pass
        else:
            raise AssertionError('un zip sin DLL del SDK debería dar ValueError')

    check_folder_warning()
    check_scan_depth()
    check_sdk_tree_picker()
    check_braw_gate()
    print('test_braw_sdk_import: OK')


if __name__ == '__main__':
    main()

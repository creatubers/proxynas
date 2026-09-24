"""Comprobacion del importador de zip del SDK BRAW.

Ejecutar con:  python test_braw_sdk_import.py
"""

import os
import tempfile
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



def check_startup_warning():
    """El aviso de arranque solo aparece si falta el decodificador o el SDK."""
    import backup_gui

    class Stub:
        def __init__(self):
            self.offered = []

        def _offer_braw_sdk(self, missing=None):
            self.offered.append(missing)

    real_decode = backup_gui.braw_proxy.BRAW_DECODE
    real_sdk = backup_gui.braw_proxy.SDK_DIR
    stub = Stub()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            backup_gui.braw_proxy.BRAW_DECODE = os.path.join(tmp, 'nope.exe')
            backup_gui.braw_proxy.SDK_DIR = tmp
            backup_gui.BackupApp._warn_if_braw_sdk_missing(stub)
            assert len(stub.offered) == 1, stub.offered
            assert 'nope.exe' in stub.offered[0], stub.offered

            present = os.path.join(tmp, 'braw_decode.exe')
            open(present, 'wb').close()
            open(os.path.join(tmp, 'BlackmagicRawAPI.dll'), 'wb').close()
            backup_gui.braw_proxy.BRAW_DECODE = present
            backup_gui.BackupApp._warn_if_braw_sdk_missing(stub)
            assert len(stub.offered) == 1, 'no deberia avisar si todo esta presente'
    finally:
        backup_gui.braw_proxy.BRAW_DECODE = real_decode
        backup_gui.braw_proxy.SDK_DIR = real_sdk


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
            raise AssertionError('un zip sin DLL del SDK deberia dar ValueError')

    check_startup_warning()
    print('test_braw_sdk_import: OK')


if __name__ == '__main__':
    main()

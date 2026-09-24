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

    print('test_braw_sdk_import: OK')


if __name__ == '__main__':
    main()

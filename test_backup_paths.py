"""Comprobación rápida de rutas de backup."""

import os
import tempfile

from backup_gui import BackupProcessor, validate_backup_destination


with tempfile.TemporaryDirectory() as root:
    source = os.path.join(root, 'source')
    os.mkdir(source)
    validate_backup_destination(source, os.path.join(root, 'backup'))
    for destination in (source, os.path.join(source, 'backup')):
        try:
            BackupProcessor(source, destination, encoder_capabilities={'presets': {}})
        except ValueError:
            pass
        else:
            raise AssertionError(f'Destino dentro del origen aceptado: {destination}')

print('test_backup_paths: OK')

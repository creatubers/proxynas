"""Run with: python test_image_backup.py"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backup_gui import BackupProcessor, IMAGE_EXTENSIONS


with TemporaryDirectory() as root:
    source, destination = Path(root) / 'source', Path(root) / 'backup'
    source.mkdir()
    originals = {}
    for extension in IMAGE_EXTENSIONS:
        data = b'unchanged\x00image\xff' + extension.encode()
        (source / f'still{extension}').write_bytes(data)
        originals[extension] = data
    processor = BackupProcessor(source, destination, encoder_capabilities={'presets': {}}, log_callback=lambda _: None)
    with patch('backup_gui.is_source_ready', return_value=True), patch('backup_gui.subprocess.Popen', side_effect=AssertionError('External image tool launched')):
        processor.process_files(IMAGE_EXTENSIONS, processor.process_images)
    for extension, data in originals.items():
        assert (destination / f'still{extension}').read_bytes() == data
    assert processor.stats['images'] == len(originals)

print('test_image_backup: OK')

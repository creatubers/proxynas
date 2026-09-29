import os
import shutil
import tempfile
from pathlib import Path

from proxyregistry import ProxyRegistry


def test_move_without_duration():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / 'clip.braw'
        source.write_bytes(b'clip')
        registry = ProxyRegistry(str(root / 'registry.json'), ffprobe_bin='missing')
        registry.reconcile(folder)
        old_proxy = root / 'Proxy' / 'clip.mov'
        old_proxy.parent.mkdir()
        old_proxy.write_bytes(b'proxy')

        destination = root / 'scene' / 'clip.braw'
        destination.parent.mkdir()
        os.rename(source, destination)
        result = registry.reconcile(folder)

        assert result['moves'] == 1
        assert not old_proxy.exists()
        assert (root / 'scene' / 'Proxy' / 'clip.mov').read_bytes() == b'proxy'

        candidates = {
            str(root / 'a' / 'clip.braw'): {'basename': 'clip', 'size': 4, 'duration': None},
            str(root / 'b' / 'clip.braw'): {'basename': 'clip', 'size': 4, 'duration': None},
        }
        assert registry._find_match(candidates, set(candidates), {
            'basename': 'clip', 'size': 4, 'ext': '.braw', 'duration': None,
        }) is None


def test_copy_then_delete_between_scans():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / 'clip.braw'
        source.write_bytes(b'clip')
        registry = ProxyRegistry(str(root / 'registry.json'), ffprobe_bin='missing')
        registry.reconcile(folder)
        old_proxy = root / 'Proxy' / 'clip.mov'
        old_proxy.parent.mkdir()
        old_proxy.write_bytes(b'proxy')

        destination = root / 'scene' / 'clip.braw'
        destination.parent.mkdir()
        shutil.copy2(source, destination)
        copied = registry.reconcile(folder)
        assert copied['deferred'] == {str(destination)}
        assert not (destination.parent / 'Proxy' / 'clip.mov').exists()

        source.unlink()
        moved = registry.reconcile(folder)
        assert moved['moves'] == 1
        assert not moved['deferred']
        assert not old_proxy.exists()
        assert (destination.parent / 'Proxy' / 'clip.mov').read_bytes() == b'proxy'


def test_copy_kept_gets_own_proxy_job():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / 'clip.braw'
        source.write_bytes(b'clip')
        registry = ProxyRegistry(str(root / 'registry.json'), ffprobe_bin='missing')
        registry.reconcile(folder)
        old_proxy = root / 'Proxy' / 'clip.mov'
        old_proxy.parent.mkdir()
        old_proxy.write_bytes(b'proxy')

        destination = root / 'scene' / 'clip.braw'
        destination.parent.mkdir()
        shutil.copy2(source, destination)
        registry.reconcile(folder)
        entries = registry.data['by_watch_folder'][os.path.abspath(folder)]
        entries[str(destination)]['copy_seen_at'] -= 61
        assert not registry.reconcile(folder)['deferred']


if __name__ == '__main__':
    test_move_without_duration()
    test_copy_then_delete_between_scans()
    test_copy_kept_gets_own_proxy_job()

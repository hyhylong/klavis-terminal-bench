"""A trial snapshot excludes runtime debris and rejects concurrent source edits."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('freeze_candidate', Path(__file__).resolve().parents[1] / 'evaluation/freeze_task.py')
FREEZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FREEZER)


class FreezeTaskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.task = self.root / 'tasks/example'
        self.task.mkdir(parents=True)
        self.source = self.task / 'source.py'
        self.source.write_text('value = 1\n')
        (self.task / 'task.toml').write_text('schema_version = "1.0"\n')
        (self.task / 'instruction.md').write_text('Implement the described task.\n')
        (self.root / '.gitignore').write_text('__pycache__/\nartifacts/\n')
        cache = self.task / '__pycache__'
        cache.mkdir()
        (cache / 'source.pyc').write_bytes(b'ignored bytecode')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        self.root_patch = patch.object(FREEZER, 'ROOT', self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def test_runtime_caches_are_excluded_and_captured_sources_are_independent(self):
        destination = FREEZER.freeze(self.task)
        manifest = json.loads((destination.parent / 'source-manifest.json').read_text())
        self.assertEqual({entry['path'] for entry in manifest['files']}, {'task.toml', 'instruction.md', 'source.py'})
        self.assertFalse((destination / '__pycache__').exists())
        self.source.write_text('value = 2\n')
        self.assertEqual((destination / 'source.py').read_text(), 'value = 1\n')

    def test_source_change_during_capture_produces_no_trial_directory(self):
        original = Path.read_bytes
        changed = False
        def reading(path):
            nonlocal changed
            value = original(path)
            if path == self.source and not changed:
                changed = True
                path.write_text('value = 99\n')
            return value
        with patch.object(Path, 'read_bytes', reading):
            with self.assertRaisesRegex(RuntimeError, 'sources changed'):
                FREEZER.freeze(self.task)
        self.assertFalse((self.root / 'artifacts').exists())


if __name__ == '__main__':
    unittest.main()

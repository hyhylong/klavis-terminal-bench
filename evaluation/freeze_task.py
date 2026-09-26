"""Create an immutable source-only task snapshot for reproducible evaluations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def freeze(source):
    source = Path(source).resolve()
    relative = source.relative_to(ROOT / 'tasks')
    if len(relative.parts) != 1 or not (source / 'task.toml').is_file():
        raise ValueError('Choose an existing immediate child of tasks/')
    prefix = source.relative_to(ROOT).as_posix()
    def revision():
        return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    def inventory():
        listing = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z',
                                           '--cached', '--others', '--exclude-standard', '--', prefix])
        return sorted(set(item.decode('utf-8') for item in listing.split(b'\0') if item))
    commit = revision()
    paths = inventory()
    captured = []
    for entry in paths:
        origin = ROOT / entry
        if origin.is_symlink() or not origin.is_file():
            raise ValueError(f'Source must contain only regular files: {entry}')
        captured.append((origin, origin.read_bytes()))
    # Refuse a candidate assembled while another agent changed its sources.
    # Write from these captured bytes, never re-read sources during the copy.
    if (revision() != commit or inventory() != paths
            or any(origin.is_symlink() or not origin.is_file() or origin.read_bytes() != data
                   for origin, data in captured)):
        raise RuntimeError('Task sources changed while freezing; retry after edits finish')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    container = ROOT / 'artifacts/local/frozen' / f'{source.name}-{stamp}'
    destination = container / source.name
    destination.mkdir(parents=True, exist_ok=False)
    files = []
    tree = hashlib.sha256()
    for origin, data in captured:
        relpath = origin.relative_to(source)
        target = destination / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        checksum = hashlib.sha256(data).hexdigest()
        files.append({'path': relpath.as_posix(), 'bytes': len(data), 'sha256': checksum})
        tree.update(relpath.as_posix().encode() + b'\0' + data + b'\0')
    manifest = {'source': prefix, 'created_utc': stamp,
                'source_commit': commit,
                'includes_uncommitted_source': True,
                'snapshot_tree_sha256': tree.hexdigest(),
                'hash_definition': 'SHA256 of sorted relative-path NUL raw-file-bytes NUL; not Harbor Task.checksum',
                'selection': 'git ls-files --cached --others --exclude-standard; ignored runtime caches excluded',
                'files': files}
    (container / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    print(freeze(parser.parse_args().task))

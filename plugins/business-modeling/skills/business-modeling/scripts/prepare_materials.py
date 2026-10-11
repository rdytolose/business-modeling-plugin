#!/usr/bin/env python3
"""Restore the unchanged supplied book into a writable working directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def restore(destination):
    root = Path(__file__).resolve().parent.parent / 'references/methodology'
    manifest = json.loads((root / 'sources/book-parts.json').read_text(encoding='utf-8'))
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / manifest['file_name']
    if target.exists():
        if target.stat().st_size == manifest['size_bytes'] and sha256(target) == manifest['sha256']:
            return target
        raise ValueError(f'Existing file differs; it was not overwritten: {target}')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination, prefix='.book-', delete=False) as output:
            temporary = Path(output.name)
            whole = hashlib.sha256()
            total = 0
            for item in manifest['parts']:
                part = (root / item['path']).resolve()
                if not part.is_relative_to(root.resolve()):
                    raise ValueError('Part path leaves the materials directory')
                actual = hashlib.sha256()
                size = 0
                with part.open('rb') as source:
                    while chunk := source.read(1024 * 1024):
                        actual.update(chunk)
                        whole.update(chunk)
                        size += len(chunk)
                        output.write(chunk)
                if size != item['size_bytes'] or actual.hexdigest() != item['sha256']:
                    raise ValueError(f'Missing or damaged book part: {part.name}')
                total += size
            if total != manifest['size_bytes'] or whole.hexdigest() != manifest['sha256']:
                raise ValueError('Book checksum mismatch')
        # Another process may have completed the same preparation meanwhile.
        if target.exists():
            if sha256(target) != manifest['sha256']:
                raise ValueError(f'Existing file differs: {target}')
        else:
            os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(restore(args.destination))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Verify every distributed file using the release manifest."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / 'MANIFEST.sha256.json').read_text(encoding='utf-8'))
    failures = []
    for item in manifest['files']:
        path = (root / item['path']).resolve()
        if not path.is_relative_to(root):
            failures.append(f'Invalid manifest path: {item["path"]}')
            continue
        if not path.is_file() or path.stat().st_size != item['size_bytes']:
            failures.append(f'Missing/changed size: {item["path"]}')
            continue
        with path.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if checksum != item['sha256']:
            failures.append(f'SHA-256 mismatch: {item["path"]}')
    print(json.dumps({'valid': not failures, 'files_checked': len(manifest['files']),
                      'errors': failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())

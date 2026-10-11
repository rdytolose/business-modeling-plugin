#!/usr/bin/env python3
"""Check RSF ZIP integrity; this is not a test of opening a model in Ramus."""
import argparse
import json
from pathlib import Path
import zipfile


def check(path):
    path = Path(path)
    if path.suffix.lower() != '.rsf' or not path.is_file() or not path.stat().st_size:
        raise ValueError('Expected a nonempty .rsf file')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names:
            raise ValueError('Empty ZIP container')
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP member names')
        if not any(name.startswith('data/') and name.endswith('.xml') for name in names):
            raise ValueError('ZIP lacks the expected Ramus data XML files')
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP CRC error: {bad}')
    return {'container_valid': True, 'size_bytes': path.stat().st_size,
            'members': len(names), 'opened_in_ramus': False,
            'note': 'ZIP/CRC checked; semantic, visual and Ramus application checks are separate.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    try:
        result = check(args.file)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(json.dumps({'container_valid': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

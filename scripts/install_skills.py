#!/usr/bin/env python3
"""Install the eight skills when plugin installation is unavailable."""
import argparse
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True,
                        help='User skill directory, for example ~/.codex/skills')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent / 'plugins/business-modeling/skills'
    folders = sorted(p for p in source.iterdir() if (p / 'SKILL.md').is_file())
    target = args.destination.expanduser().resolve()
    conflicts = [p.name for p in folders if (target / p.name).exists()]
    if conflicts:
        parser.exit(1, 'Nothing copied: existing skills would be overwritten: ' + ', '.join(conflicts) + '\n')
    target.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        shutil.copytree(folder, target / folder.name)
    print(f'Installed {len(folders)} skills into {target}. Restart Codex and open a new chat.')


if __name__ == '__main__':
    sys.exit(main())

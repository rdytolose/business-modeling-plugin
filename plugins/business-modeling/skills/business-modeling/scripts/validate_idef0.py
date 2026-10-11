#!/usr/bin/env python3
"""Check the user's recursive IDEF0 JSON contract; no third-party dependencies."""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

SIDES = ('inputs', 'controls', 'outputs', 'mechanisms')


def load_model(text):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Повторяющийся ключ JSON: {key}')
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f'Недопустимая константа JSON: {value}')

    return json.loads(text, object_pairs_hook=unique_keys,
                      parse_constant=reject_constant)


def normalized(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold()
                  .replace('ё', 'е').replace('–', '-').replace('—', '-')).strip()


def validate(model):
    errors, warnings, names, labels = [], [], {}, set()
    count = 0

    def error(path, message):
        errors.append(f'{path}: {message}')

    def warning(path, message):
        warnings.append(f'{path}: {message}')

    def check_string(value, path):
        if not isinstance(value, str) or not value.strip():
            error(path, 'ожидается непустая строка')
            return False
        if value != value.strip():
            error(path, 'пробелы по краям названия')
        if any(unicodedata.category(c) in ('Cc', 'Cf') for c in value):
            error(path, 'управляющие или невидимые символы в названии')
        return True

    def visit(node, path):
        nonlocal count
        if not isinstance(node, dict):
            error(path, 'работа должна быть объектом')
            return False
        count += 1
        required = {'name', *SIDES}
        missing = required - node.keys()
        extra = node.keys() - (required | {'children'})
        if missing:
            error(path, f'отсутствуют поля: {sorted(missing)}')
        if extra:
            error(path, f'лишние поля: {sorted(extra)}')
        name = node.get('name')
        if check_string(name, path + '.name'):
            key = normalized(name)
            if key in names:
                error(path, f'повтор имени работы {name!r}, уже есть в {names[key]}')
            names[key] = path
        arrays_ok = True
        for side in SIDES:
            values = node.get(side)
            if not isinstance(values, list):
                error(path + '.' + side, 'ожидается массив строк')
                arrays_ok = False
                continue
            if len(values) > 6:
                error(path + '.' + side, 'больше 6 стрелок')
            if side in ('controls', 'outputs') and not values:
                error(path + '.' + side, 'обязательна хотя бы одна стрелка')
            seen = set()
            for i, value in enumerate(values):
                if not check_string(value, f'{path}.{side}[{i}]'):
                    arrays_ok = False
                    continue
                if value in seen:
                    error(path + '.' + side, f'повтор стрелки {value!r}')
                seen.add(value)
                labels.add(value)
        if arrays_ok:
            overlap = set(node['inputs']) & set(node['controls'])
            if overlap:
                error(path, f'одновременно во входах и управлениях: {sorted(overlap)}')
            norm_overlap = ({normalized(s) for s in node['inputs']} &
                            {normalized(s) for s in node['controls']})
            if norm_overlap and not overlap:
                warning(path, 'вход и управление различаются лишь написанием; проверить дублирование')
        if 'children' not in node:
            return arrays_ok and not missing
        children = node['children']
        if not isinstance(children, list):
            error(path + '.children', 'ожидается массив из 3–6 работ')
            return False
        if not 3 <= len(children) <= 6:
            error(path + '.children', 'декомпозиция должна содержать 3–6 работ; у листа поле отсутствует')
        child_valid = [visit(child, f'{path}.children[{i}]')
                       for i, child in enumerate(children)]
        if not arrays_ok or missing or not all(child_valid):
            return False
        for side in SIDES:
            used = {value for child in children for value in child[side]}
            for value in node[side]:
                if value not in used:
                    error(path, f'{side}: стрелку родителя {value!r} не использует ни один ребенок на этой стороне')
        parent_labels = {v for side in SIDES for v in node[side]}
        for i, child in enumerate(children):
            other_outputs = {v for j, sibling in enumerate(children) if j != i
                             for v in sibling['outputs']}
            for side in ('inputs', 'controls', 'mechanisms'):
                for value in child[side]:
                    if value not in node[side] and value not in other_outputs:
                        if value in parent_labels:
                            warning(path, f'ребенок {i + 1}: {value!r} перемещена на {side}; проверить совместимость сайта')
                        else:
                            warning(path, f'ребенок {i + 1}: {side} {value!r} — дополнительная граница/туннель; обосновать источник')
            other_consumed = {v for j, sibling in enumerate(children) if j != i
                              for side in ('inputs', 'controls', 'mechanisms')
                              for v in sibling[side]}
            for value in child['outputs']:
                if value not in node['outputs'] and value not in other_consumed:
                    warning(path, f'ребенок {i + 1}: выход {value!r} не востребован соседями и не выведен родителем; проверить туннель')
        producers = {}
        for i, child in enumerate(children):
            for value in child['outputs']:
                producers.setdefault(value, []).append(i + 1)
        for value, indexes in producers.items():
            if len(indexes) > 1:
                warning(path, f'выход {value!r} производят работы {indexes}; проверить отсутствие ложных связей')
        return True

    if not isinstance(model, dict):
        return {'valid': False, 'activity_count': 0,
                'errors': ['$: ожидается один JSON-объект'], 'warnings': []}
    if set(model) != {'model', 'author', 'activity'}:
        error('$', 'корень должен содержать только model, author, activity')
    for field in ('model', 'author'):
        check_string(model.get(field), '$.' + field)
    root = model.get('activity')
    visit(root, '$.activity')
    if isinstance(root, dict) and 'children' not in root:
        error('$.activity', 'контекстная работа должна быть декомпозирована в A0')
    buckets = {}
    for label in sorted(labels):
        buckets.setdefault(normalized(label), []).append(label)
    for variants in buckets.values():
        if len(variants) > 1:
            warning('$', f'разные строки для возможной общей стрелки: {variants}')
    ordered = sorted(labels)
    for i, first in enumerate(ordered):
        for second in ordered[i + 1:]:
            a, b = normalized(first), normalized(second)
            if a != b and min(len(a), len(b)) >= 8 and difflib.SequenceMatcher(None, a, b).ratio() >= .93:
                warning('$', f'похожие названия стрелок, проверить словарь: {first!r}, {second!r}')
    return {'valid': not errors, 'activity_count': count,
            'errors': errors, 'warnings': warnings,
            'manual_review': ['Семантика ICOM и названий', 'Полнота и единый смысл сущностей',
                              'Границы процесса и обоснование туннелей', 'Реальная отрисовка сайта']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', help='UTF-8 JSON file, or - for stdin')
    parser.add_argument('--strict', action='store_true', help='fail on warnings too')
    args = parser.parse_args()
    try:
        text = sys.stdin.read() if args.file == '-' else Path(args.file).read_text(encoding='utf-8-sig')
        result = validate(load_model(text))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        print(json.dumps({'valid': False, 'errors': [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['valid'] and (not args.strict or not result['warnings']) else 1


if __name__ == '__main__':
    sys.exit(main())

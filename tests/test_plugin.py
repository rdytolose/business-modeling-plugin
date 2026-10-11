import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'plugins/business-modeling/skills/business-modeling'


def module(name):
    spec = importlib.util.spec_from_file_location(name, CORE / 'scripts' / f'{name}.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


VALIDATOR = module('validate_idef0')
RSF = module('check_rsf')


def example():
    control, mechanism = ['Регламент обработки заявки'], ['Специалист']
    def work(name, inputs, outputs):
        return {'name': name, 'inputs': inputs, 'controls': list(control),
                'outputs': outputs, 'mechanisms': list(mechanism)}
    root = work('Обработать заявку', ['Заявка'], ['Результат обработки'])
    root['children'] = [
        work('Зарегистрировать заявку', ['Заявка'], ['Зарегистрированная заявка']),
        work('Проверить заявку', ['Зарегистрированная заявка'], ['Проверенная заявка']),
        work('Оформить результат', ['Проверенная заявка'], ['Результат обработки'])]
    return {'model': 'Учебный пример: обработка заявки',
            'author': 'Учебный пример', 'activity': root}


class ContractTests(unittest.TestCase):
    def test_complete_balanced_chain(self):
        result = VALIDATOR.validate(example())
        self.assertTrue(result['valid'])
        self.assertEqual(result['activity_count'], 4)
        self.assertEqual(result['warnings'], [])

    def test_parent_boundary_cannot_disappear(self):
        value = example()
        value['activity']['controls'] = ['Регламент обработки заявки', 'Только у родителя']
        self.assertFalse(VALIDATOR.validate(value)['valid'])

    def test_input_control_overlap_is_rejected(self):
        value = example()
        value['activity']['controls'] = ['Заявка']
        self.assertFalse(VALIDATOR.validate(value)['valid'])

    def test_no_extra_json_fields(self):
        value = example()
        value['notation'] = 'BPMN'
        self.assertFalse(VALIDATOR.validate(value)['valid'])

    def test_name_variants_do_not_silently_join(self):
        value = example()
        value['activity']['children'][1]['inputs'] = ['Зарегистрированная  заявка']
        self.assertTrue(VALIDATOR.validate(value)['warnings'])

    def test_context_requires_decomposition(self):
        value = example()
        del value['activity']['children']
        self.assertFalse(VALIDATOR.validate(value)['valid'])


class FileTests(unittest.TestCase):
    def test_json_renamed_to_rsf_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fake.rsf'
            path.write_text(json.dumps(example()))
            with self.assertRaises(zipfile.BadZipFile):
                RSF.check(path)

    def test_unrelated_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'unrelated.rsf'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('readme.txt', 'not a model')
            with self.assertRaises(ValueError):
                RSF.check(path)

    def test_restoration_verifies_parts_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'skill/scripts/prepare_materials.py'
            script.parent.mkdir(parents=True)
            shutil.copy2(CORE / 'scripts/prepare_materials.py', script)
            material = root / 'skill/references/methodology'
            part = material / 'sources/part'
            part.parent.mkdir(parents=True)
            original = b'%PDF-training-fixture\n'
            part.write_bytes(original)
            checksum = hashlib.sha256(original).hexdigest()
            manifest = {'file_name': 'fixture.pdf', 'size_bytes': len(original), 'sha256': checksum,
                        'parts': [{'path': 'sources/part', 'size_bytes': len(original), 'sha256': checksum}]}
            (material / 'sources/book-parts.json').write_text(json.dumps(manifest))
            destination = root / 'workspace'
            command = [sys.executable, str(script), '--destination', str(destination)]
            run = lambda: subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            self.assertEqual((destination / 'fixture.pdf').read_bytes(), original)
            self.assertEqual(run().returncode, 0)
            (destination / 'fixture.pdf').write_bytes(b'User file')
            self.assertNotEqual(run().returncode, 0)
            self.assertEqual((destination / 'fixture.pdf').read_bytes(), b'User file')
            (destination / 'fixture.pdf').unlink()
            part.write_bytes(b'corrupted')
            self.assertNotEqual(run().returncode, 0)
            self.assertFalse((destination / 'fixture.pdf').exists())
            self.assertEqual(list(destination.glob('.book-*')), [])

    def test_skill_installer_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            existing = target / 'business-modeling'
            existing.mkdir()
            marker = existing / 'SKILL.md'
            marker.write_text('User skill')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install_skills.py'),
                                     '--destination', str(target)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), 'User skill')
            self.assertEqual(len(list(target.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()

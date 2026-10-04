"""Meaningful count, provenance and timing checks for the worked example."""
import copy
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'examples' / 'simpson' / 'render_demo.py'
spec = importlib.util.spec_from_file_location('synthetic_demo', ENTRY)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class DemoTests(unittest.TestCase):
    def test_reversal_and_common_weights_from_counts(self):
        data = demo.load_data()
        got = demo.calculate(data)
        for group in data['groups']:
            self.assertGreater(Fraction(**{'numerator': group['B']['successes'], 'denominator': group['B']['trials']}), Fraction(group['A']['successes'], group['A']['trials']))
        self.assertAlmostEqual(got['pooled']['A'], float(Fraction(91, 110)))
        self.assertAlmostEqual(got['pooled']['B'], float(Fraction(39, 120)))
        self.assertGreater(got['pooled']['A'], got['pooled']['B'])
        self.assertAlmostEqual(got['standardized']['A'], .5)
        self.assertAlmostEqual(got['standardized']['B'], .575)
        self.assertGreater(got['standardized']['B'], got['standardized']['A'])

    def test_bad_denominators_and_unlabelled_data_rejected(self):
        for field, value in [('trials', 0), ('trials', True), ('successes', 101)]:
            data = demo.load_data()
            data['groups'][0]['A'][field] = value
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'data.json'
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    demo.load_data(path)
        data = demo.load_data()
        data['provenance']['synthetic'] = False
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'data.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                demo.load_data(path)

    def test_changed_data_cannot_keep_old_explanation(self):
        data = copy.deepcopy(demo.load_data())
        data['groups'][0]['A']['successes'] = 80
        with self.assertRaises(ValueError):
            demo.verify_inputs(data, demo.calculate(data), demo.parse_srt())

    def test_actual_source_quotes_and_authored_timing(self):
        data = demo.load_data()
        captions = demo.parse_srt()
        demo.verify_inputs(data, demo.calculate(data), captions)
        self.assertEqual(sum(c['end'] - c['start'] for c in captions), 48)
        mapping = json.loads((ENTRY.parent / 'evidence_map.json').read_text(encoding='utf-8'))
        self.assertFalse(mapping['timing']['audio_aligned'])
        self.assertEqual(mapping['timing']['basis'], 'authored_visual_schedule')


if __name__ == '__main__':
    unittest.main()

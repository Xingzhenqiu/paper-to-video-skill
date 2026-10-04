"""Synthetic contract tests, not real-paper generalization evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ENTRY = Path(__file__).resolve().parents[1] / 'skills/paper-to-video/scripts/project.py'
spec = importlib.util.spec_from_file_location('portable_project', ENTRY)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PortableProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'source.txt'
        self.source.write_text('Synthetic example, not a research result.\n这是测试文本，没有图或DOI。', encoding='utf-8')

    def project(self, kind='opinion', coverage='full'):
        return module.create_project(self.source, 'text', kind, coverage, 'zh-CN', 300)

    def reviewed(self):
        project = self.project()
        project['claims'] = [{'id': 'c1', 'text': '测试材料没有图。', 'review_status': 'verified',
                              'evidence': [{'unit_id': 'line_2', 'quote': '没有图或DOI'}]}]
        project['scenes'] = [{'id': 's1', 'display_text': '测试材料', 'spoken_text': '测试材料',
                             'claim_ids': ['c1'], 'visual_intent': 'text emphasis'}]
        project['acceptance'].update(source_review='verified', scientific_review='verified')
        return project

    def test_routes_and_no_old_paper_content(self):
        for kind in module.TYPES:
            with self.subTest(kind=kind):
                project = self.project(kind)
                self.assertTrue(module.validate(project)['contract_valid'])
                self.assertFalse(module.validate(project)['evidence_ready'])
                self.assertEqual(project['project']['pronunciations'], {})
                self.assertEqual(project['claims'], [])
        self.assertNotEqual(self.project('theoretical')['route'], self.project('clinical')['route'])

    def test_no_doi_no_figures_is_valid(self):
        result = module.validate(self.reviewed())
        self.assertTrue(result['evidence_ready'])
        self.assertFalse(result['video_ready'])

    def test_content_led_duration_is_valid(self):
        project=module.create_project(self.source,'text','opinion','full','zh-CN',None)
        self.assertIsNone(project['project']['target_seconds'])
        self.assertTrue(module.validate(project)['contract_valid'])

    def test_partial_cannot_pass_full_paper_gate(self):
        for coverage in ('abstract', 'partial', 'unknown'):
            project = self.reviewed()
            project['source']['coverage'] = coverage
            self.assertFalse(module.validate(project)['evidence_ready'])

    def test_broken_anchor_and_invented_quote_fail(self):
        for key, value in [('unit_id', 'missing'), ('quote', 'imagined result')]:
            project = self.reviewed()
            project['claims'][0]['evidence'][0][key] = value
            self.assertFalse(module.validate(project)['contract_valid'])

    def test_scene_reference_and_duplicates_fail(self):
        project = self.reviewed()
        project['scenes'][0]['claim_ids'] = ['unknown']
        self.assertFalse(module.validate(project)['contract_valid'])
        project = self.reviewed()
        project['claims'].append(copy.deepcopy(project['claims'][0]))
        self.assertFalse(module.validate(project)['contract_valid'])

    def test_blank_and_invalid_duration_rejected(self):
        for seconds in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                module.create_project(self.source, 'text', 'review', 'full', 'en', seconds)
        self.source.write_text('  \n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.project()

    def test_bad_shapes_fail_without_crash(self):
        for value in (None, [], {}, {'schema_version': 1, 'project': None}):
            self.assertFalse(module.validate(value)['contract_valid'])

    def test_invalid_locator_cannot_pass_review(self):
        for locator in ({'kind': 'text', 'line': 0}, {'kind': 'pdf', 'page_index': 0, 'bbox': [5, 5, 1, 1]}, {'kind': 'invented'}):
            project = self.reviewed()
            project['source']['units'][0]['locator'] = locator
            self.assertFalse(module.validate(project)['contract_valid'])

    def test_reader_adapter_preserves_locations_without_paths(self):
        card = {'meta': {'title': 'Synthetic card', 'source_pdf': '/private/paper.pdf'},
                'paragraphs': [{'id': 'p1', 'page': 2, 'bbox': [1, 2, 20, 30], 'text': 'Synthetic evidence.'}],
                'figures': [{'id': 'fig_1', 'page': 2, 'image': '/private/figure.png', 'caption': 'Test'}]}
        path = Path(self.tmp.name) / 'card.json'
        path.write_text(json.dumps(card), encoding='utf-8')
        project = module.create_project(path, 'reader-card', 'review', 'full', 'en', 120)
        self.assertEqual(project['source']['units'][0]['locator']['page_index'], 2)
        self.assertNotIn('/private/', json.dumps(project))
        self.assertTrue(module.validate(project)['contract_valid'])
        card['paragraphs'].append(copy.deepcopy(card['paragraphs'][0]))
        path.write_text(json.dumps(card), encoding='utf-8')
        with self.assertRaises(ValueError):
            module.create_project(path, 'reader-card', 'review', 'full', 'en', 120)

    def test_never_overwrites_existing_output(self):
        output = Path(self.tmp.name) / 'project.json'
        module.write_new(output, {'original': True})
        with self.assertRaises(FileExistsError):
            module.write_new(output, {'original': False})
        self.assertEqual(module.read_json(output), {'original': True})

    def test_upstream_issues_block_even_with_review_flags(self):
        project=self.reviewed()
        project['source']['upstream_issues']=['fig_2_cross_page_review_required']
        self.assertFalse(module.validate(project)['evidence_ready'])
        project['source']['issue_reviews']=[{'code':'fig_2_cross_page_review_required','status':'verified','reason':'Checked both original pages against the crop.'}]
        self.assertTrue(module.validate(project)['evidence_ready'])

    def test_adapter_preserves_upstream_issues(self):
        card={'paragraphs':[{'id':'p1','page':0,'bbox':[1,2,30,40],'text':'Test source'}],
              'quality':{'issues':['figure_extraction_failed']}}
        path=Path(self.tmp.name)/'card.json'
        path.write_text(json.dumps(card),encoding='utf-8')
        project=module.create_project(path,'reader-card','experimental','full','en',100)
        self.assertEqual(project['source']['upstream_issues'],['figure_extraction_failed'])
        self.assertIn('upstream extraction issue: figure_extraction_failed',module.validate(project)['pending'])


if __name__ == '__main__':
    unittest.main()

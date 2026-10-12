"""Meaningful pipeline contract/cache tests with explicitly mocked media providers.

These tests prove deterministic routing and invalidation, not voice quality or
real rendering. The public example and independent build cover actual media.
"""
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from p2v import pipeline

spec = importlib.util.spec_from_file_location('pipeline_test_contract', ROOT / 'skills/paper-to-video/scripts/project.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def write_wave(path, samples=12000, rate=12000, value=200):
    import wave
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(value.to_bytes(2, 'little', signed=True) * samples)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / 'project'
        self.base.mkdir()
        self.source = self.base / 'source.txt'
        self.source.write_text('Synthetic example.\nObservation A is supported.\nObservation B is supported.\n', encoding='utf-8')
        self.project_path = self.base / 'project.json'
        self.output = self.base / 'output'
        self.audio_calls, self.render_calls = [], []
        write_wave(self.base / 'audio/a.wav')
        write_wave(self.base / 'audio/b.wav', value=400)
        self.project = contract.create_project(self.source, 'text', 'experimental', 'full', 'en', None)
        self.project['claims'] = [
            {'id': 'c_a', 'text': 'A observation', 'evidence': [{'unit_id': 'line_2', 'quote': 'Observation A is supported.'}], 'review_status': 'pending'},
            {'id': 'c_b', 'text': 'B observation', 'evidence': [{'unit_id': 'line_3', 'quote': 'Observation B is supported.'}], 'review_status': 'pending'},
        ]
        self.project['scenes'] = [
            {'id': 's_a', 'display_text': 'Observation A.', 'spoken_text': 'Observation A is supported.',
             'claim_ids': ['c_a'], 'visual_intent': 'One supported observation', 'visual': {'kind': 'title', 'title': 'A'}},
            {'id': 's_b', 'display_text': 'Observation B.', 'spoken_text': 'Observation B is supported.',
             'claim_ids': ['c_b'], 'visual_intent': 'Next supported observation', 'visual': {'kind': 'title', 'title': 'B'}},
        ]
        self.project['render'] = {'schema_version': 1, 'width': 640, 'fps': 12, 'pause_seconds': 0.35,
                                             'audio': {'engine': 'import', 'clips': {'s_a': 'audio/a.wav', 's_b': 'audio/b.wav'}}}
        self.save()

    def save(self):
        self.project_path.write_text(json.dumps(self.project, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def visual_validator(project, scene):
        if scene['visual']['kind'] not in ('title', 'figure'):
            raise ValueError('unsupported test visual kind')
        if scene['visual']['kind'] == 'figure':
            if scene['visual']['asset'] not in project['render'].get('assets', {}):
                raise ValueError('missing figure asset')
        return {'kind': scene['visual']['kind']}

    def audio(self, text, output_wav, config):
        self.audio_calls.append(text)
        # Mock only: measured duration follows the authored text, rather than a
        # project target_seconds or guessed reading-speed estimate.
        samples = 7200 + len(text) * 120
        write_wave(output_wav, samples=samples)
        return {'mock': True}

    def renderer(self, project, scene, output_mp4, duration, width, fps):
        self.render_calls.append(scene['id'])
        frames = round(duration * fps)
        output_mp4.write_bytes(json.dumps({'visual': scene['visual'], 'display_text': scene['display_text'],
                                          'duration': duration, 'width': width, 'fps': fps}, sort_keys=True).encode('utf-8'))
        return {'frames': frames}

    @staticmethod
    def assembler(clips, wavs, timeline, output, fps):
        output.joinpath('video.mp4').write_bytes(b'MOCK-MEDIA\n' + b'\n'.join(path.read_bytes() for path in clips))
        return {'decoded': True, 'audio_decode': True, 'decoded_frames': sum(cue['frames'] for cue in timeline), 'mock': True}

    def build(self, **kwargs):
        return pipeline.build(self.project_path, self.output, audio_fn=self.audio, render_fn=self.renderer,
                              assemble_fn=self.assembler, visual_validator=self.visual_validator, **kwargs)

    def validate(self):
        return pipeline.validate_project(self.project_path, visual_validator=self.visual_validator)

    def test_relative_inputs_resolve_outside_current_directory(self):
        other = Path(self.tmp.name) / 'unrelated'
        other.mkdir()
        before = Path.cwd()
        try:
            os.chdir(other)
            self.assertTrue(self.validate()['build_ready'])
            report = self.build()
        finally:
            os.chdir(before)
        self.assertTrue(report['automated_passed'])
        self.assertNotIn(str(self.base), json.dumps(report))

    def test_silent_preview_uses_authored_timing_and_invalidates_one_scene(self):
        self.project['render']['audio'] = {'engine': 'silence', 'durations': {'s_a': 1.1, 's_b': 2.2}}
        self.save()
        options = {'render_fn': self.renderer, 'assemble_fn': self.assembler,
                   'visual_validator': self.visual_validator}
        first = pipeline.build(self.project_path, self.output, **options)
        self.assertEqual(first['timing_basis'], 'authored_silent_preview')
        self.assertFalse(first['narration_present'])
        self.assertGreaterEqual(first['scenes'][0]['audio_duration_seconds'], 1.1)
        self.assertLessEqual(first['scenes'][0]['audio_duration_seconds'], 1.1 + 1 / 24000 + 1e-12)
        resumed = pipeline.build(self.project_path, self.output, resume=True, **options)
        self.assertEqual(resumed['cache']['audio_reused'], 2)
        self.assertEqual(resumed['cache']['clips_reused'], 2)
        self.project['render']['audio']['durations']['s_b'] = 3.3
        self.save()
        revised = pipeline.build(self.project_path, self.output, resume=True, **options)
        self.assertEqual(revised['cache']['audio_built'], 1)
        self.assertEqual(revised['cache']['clips_built'], 1)
        self.assertEqual(revised['scenes'][0]['audio_sha256'], first['scenes'][0]['audio_sha256'])

    def test_missing_or_invalid_silent_duration_blocks_before_build(self):
        for durations in ({'s_a': 1}, {'s_a': 1, 's_b': 0}, {'s_a': 1, 's_b': True}):
            with self.subTest(durations=durations):
                self.project['render']['audio'] = {'engine': 'silence', 'durations': durations}
                self.save()
                self.assertFalse(self.validate()['build_ready'])
                with self.assertRaises(ValueError):
                    self.build()
                self.assertEqual(self.audio_calls, [])
                self.assertFalse(self.output.exists())

    def test_changed_source_bytes_block_before_audio(self):
        self.source.write_text('Changed actual evidence.\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source SHA256 mismatch'):
            self.build()
        self.assertEqual(self.audio_calls, [])
        self.assertFalse(self.output.exists())

    def test_modified_embedded_quote_cannot_bypass_actual_source(self):
        self.project['source']['units'][1]['text'] = 'Invented new A result.'
        self.project['claims'][0]['evidence'][0]['quote'] = 'Invented new A result.'
        self.save()
        self.assertTrue(contract.validate(self.project)['contract_valid'])
        self.assertIn('differs from actual file', self.validate()['errors'][0])
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(self.audio_calls, [])

    def test_pending_human_review_stays_pending_in_successful_draft(self):
        snapshot = copy.deepcopy(self.project['acceptance'])
        report = self.build()
        self.assertEqual(report['human_review'], snapshot)
        self.assertEqual(json.loads(self.project_path.read_text(encoding='utf-8'))['acceptance'], snapshot)
        self.assertTrue(report['automated_passed'])
        self.assertFalse(report['scientific_guarantee'])
        self.assertFalse(self.validate()['evidence_ready'])

    def test_partial_source_requires_explicit_scoped_excerpt(self):
        self.project['source']['coverage'] = 'partial'
        self.save()
        self.assertFalse(self.validate()['build_ready'])
        self.project['project'].update(scope='focused_excerpt', selected_coverage='Only the selected A and B observations.')
        self.save()
        self.assertTrue(self.validate()['build_ready'])
        self.project['project']['selected_coverage'] = ''
        self.save()
        self.assertFalse(self.validate()['build_ready'])

    def test_unsupported_visual_fails_before_audio(self):
        self.project['scenes'][0]['visual']['kind'] = 'imaginary_structure'
        self.save()
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            self.build()
        self.assertEqual(self.audio_calls, [])

    def test_resume_reuses_hash_verified_audio_and_clips(self):
        first = self.build()
        second = self.build(resume=True)
        self.assertEqual(len(self.audio_calls), 2)
        self.assertEqual(len(self.render_calls), 2)
        self.assertEqual(second['cache'], {'audio_reused': 2, 'clips_reused': 2, 'audio_built': 0, 'clips_built': 0})
        self.assertEqual([cue['clip_sha256'] for cue in first['scenes']], [cue['clip_sha256'] for cue in second['scenes']])

    def test_local_sentence_change_rebuilds_only_affected_stages(self):
        first = self.build()
        self.project['scenes'][0].update(spoken_text='Observation A is supported, with a longer explanation.',
                                          display_text='A supported observation, explained.')
        self.save()
        second = self.build(resume=True)
        self.assertEqual(second['cache'], {'audio_reused': 1, 'clips_reused': 1, 'audio_built': 1, 'clips_built': 1})
        self.assertEqual(first['scenes'][1]['clip_sha256'], second['scenes'][1]['clip_sha256'])
        self.assertGreater(second['scenes'][1]['start_seconds'], first['scenes'][1]['start_seconds'])

    def test_display_change_reuses_audio(self):
        self.build()
        self.project['scenes'][0]['display_text'] = 'Updated display wording.'
        self.save()
        report = self.build(resume=True)
        self.assertEqual(report['cache']['audio_reused'], 2)
        self.assertEqual(report['cache']['clips_reused'], 1)

    def test_audio_input_bytes_change_invalidates_selected_audio(self):
        self.build()
        write_wave(self.base / 'audio/a.wav', value=800)
        report = self.build(resume=True)
        self.assertEqual(report['cache']['audio_built'], 1)
        self.assertEqual(report['cache']['audio_reused'], 1)

    def test_scene_order_updates_timeline_without_rebuilding_clips(self):
        self.build()
        self.project['scenes'].reverse()
        self.save()
        report = self.build(resume=True)
        self.assertEqual(report['cache']['clips_reused'], 2)
        self.assertEqual(report['scenes'][0]['id'], 's_b')
        self.assertEqual(report['scenes'][0]['start_seconds'], 0)
        self.assertAlmostEqual(report['scenes'][1]['start_seconds'], report['scenes'][0]['end_seconds'])
        self.assertLess((self.output / 'subtitles.srt').read_text().index('Observation B.'),
                        (self.output / 'subtitles.srt').read_text().index('Observation A.'))

    def test_corrupted_cached_clip_is_rebuilt_without_audio(self):
        self.build()
        cache_dir = self.output / '.p2v-cache' / hashlib.sha256(b's_a').hexdigest()[:24]
        (cache_dir / 'clip.mp4').write_bytes(b'bad cache bytes')
        report = self.build(resume=True)
        self.assertEqual(report['cache']['clips_built'], 1)
        self.assertEqual(report['cache']['audio_reused'], 2)

    def test_corrupted_cached_wav_is_rebuilt(self):
        self.build()
        cache_dir = self.output / '.p2v-cache' / hashlib.sha256(b's_a').hexdigest()[:24]
        (cache_dir / 'narration.wav').write_bytes(b'bad cache bytes')
        report = self.build(resume=True)
        self.assertEqual(report['cache']['audio_built'], 1)

    def test_asset_change_must_be_repinned_and_rebuilds_only_its_scene(self):
        asset = self.base / 'assets/figure.png'
        asset.parent.mkdir()
        asset.write_bytes(b'figure-version-one')
        self.project['render']['assets'] = {
            'fig1': {'path': 'assets/figure.png', 'sha256': pipeline._hash(asset),
                     'rights': 'Original test asset', 'attribution': 'Synthetic test fixture'}
        }
        self.project['scenes'][0]['visual'] = {'kind': 'figure', 'asset': 'fig1'}
        self.save()
        first = self.build()
        asset.write_bytes(b'figure-version-two')
        with self.assertRaisesRegex(ValueError, 'asset SHA256 mismatch'):
            self.build(resume=True)
        self.project['render']['assets']['fig1']['sha256'] = pipeline._hash(asset)
        self.save()
        second = self.build(resume=True)
        self.assertEqual(second['cache']['audio_reused'], 2)
        self.assertEqual(second['cache']['clips_reused'], 1)
        self.assertEqual(first['scenes'][1]['clip_sha256'], second['scenes'][1]['clip_sha256'])

    def test_width_and_pause_changes_keep_audio_but_rebuild_visuals(self):
        self.build()
        report = self.build(resume=True, width=960)
        self.assertEqual(report['cache']['audio_reused'], 2)
        self.assertEqual(report['cache']['clips_reused'], 0)
        self.project['render']['pause_seconds'] = 0.8
        self.save()
        report = self.build(resume=True, width=960)
        self.assertEqual(report['cache']['audio_reused'], 2)
        self.assertEqual(report['cache']['clips_reused'], 0)

    def test_caption_times_follow_measured_speech_and_keep_pause(self):
        report = self.build()
        first = report['scenes'][0]
        self.assertGreaterEqual(first['pause_duration_seconds'], 0.35 - 1e-8)
        self.assertAlmostEqual(first['end_seconds'], first['frames'] / 12)
        expected_end = pipeline._timestamp(first['audio_duration_seconds'])
        self.assertIn('00:00:00,000 --> ' + expected_end, (self.output / 'subtitles.srt').read_text())
        self.assertNotEqual(first['end_seconds'], first['audio_duration_seconds'])

    def test_unsafe_or_unowned_output_does_not_overwrite_files(self):
        (self.base / 'keep.txt').write_text('Preserve me.')
        with self.assertRaisesRegex(ValueError, 'contain or overwrite'):
            pipeline.build(self.project_path, self.base, audio_fn=self.audio, render_fn=self.renderer,
                           assemble_fn=self.assembler, visual_validator=self.visual_validator)
        self.output.mkdir()
        self.output.joinpath('keep.txt').write_text('Preserve me too.')
        with self.assertRaisesRegex(ValueError, 'not owned'):
            self.build()
        self.assertEqual(self.output.joinpath('keep.txt').read_text(), 'Preserve me too.')
        self.assertEqual(self.audio_calls, [])

    def test_audio_override_import_paths_resolve_from_override_file(self):
        config_dir = Path(self.tmp.name) / 'audio_override'
        config_dir.mkdir()
        write_wave(config_dir / 'replacement.wav', value=1000)
        override = config_dir / 'config.json'
        override.write_text(json.dumps({'engine': 'import', 'clips': {'s_a': 'replacement.wav', 's_b': 'replacement.wav'}}))
        report = self.build(audio_config_path=override)
        self.assertTrue(report['automated_passed'])
        self.assertNotIn(str(config_dir), json.dumps(report))
        self.assertEqual(json.loads(self.project_path.read_text())['render']['audio']['clips']['s_a'], 'audio/a.wav')

    def test_unified_init_rebases_relative_source_and_preserves_existing_output(self):
        new_path = self.base / 'nested/project.json'
        capture = io.StringIO()
        arguments = ['init', str(self.source), str(new_path), '--format', 'text', '--article-type', 'experimental', '--coverage', 'full', '--language', 'en']
        with redirect_stdout(capture):
            self.assertEqual(pipeline.main(arguments), 0)
        initialized = json.loads(new_path.read_text())
        self.assertEqual(initialized['source']['path'], '../source.txt')
        before = new_path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline.main(arguments), 1)
        self.assertEqual(before, new_path.read_bytes())

    def test_doctor_import_route_requires_renderer_and_encoder_not_numpy(self):
        def check(pillow=True, encoder=True, ffmpeg=True):
            def import_dependency(name):
                if name == 'PIL' and pillow or name == 'imageio_ffmpeg' and encoder:
                    return SimpleNamespace(__version__='test-version')
                if name == 'p2v.audio':
                    return SimpleNamespace(doctor=lambda: {'engines': {'import': True, 'kokoro_onnx': False},
                                                           'dependencies': {'numpy': {'installed': False}}})
                raise ImportError('absent in this first-use environment: ' + name)
            process = SimpleNamespace(returncode=0 if ffmpeg else 1,
                                      stdout=b'ffmpeg test-version\n' if ffmpeg else b'', stderr=b'')
            with patch.object(pipeline.importlib, 'import_module', side_effect=import_dependency), \
                 patch.object(pipeline, '_ffmpeg', return_value='test-encoder'), \
                 patch.object(pipeline.subprocess, 'run', return_value=process):
                return pipeline.doctor()
        result = check()
        self.assertTrue(result['ok'])
        self.assertFalse(result['checks']['audio']['dependencies']['numpy']['installed'])
        for missing in ({'pillow': False}, {'encoder': False}, {'ffmpeg': False}):
            with self.subTest(missing=missing):
                self.assertFalse(check(**missing)['ok'])

    def test_output_alias_is_explicit_and_preserves_canonical_destination(self):
        fake_report = {'duration_seconds': 1, 'cache': {}, 'human_review': {}, 'automated_passed': True}
        for flag in ('--output-dir', '--output'):
            with self.subTest(flag=flag), patch.object(pipeline, 'build', return_value=fake_report) as make, redirect_stdout(io.StringIO()):
                self.assertEqual(pipeline.main(['build', str(self.project_path), flag, str(self.output)]), 0)
                self.assertEqual(make.call_args.args[1], self.output)


if __name__ == '__main__':
    unittest.main()

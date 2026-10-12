"""The public package excludes standalone audio, including declared presets."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import wave

SPEC = importlib.util.spec_from_file_location('verify_package', Path(__file__).resolve().parents[1] / 'scripts/verify_package.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture(root):
    case = root / 'examples/antigen_escape'
    (case / 'audio').mkdir(parents=True)
    clip = case / 'audio/s01.wav'
    with wave.open(str(clip), 'wb') as out:
        out.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        out.writeframes(b'\x01\x00' * 240)
    (case / 'project.json').write_text(json.dumps({'scenes': [{'id': 's01', 'spoken_text': 'Example.'}]}), encoding='utf-8')
    record = {'voice': 'am_michael', 'model_license': 'Apache-2.0', 'scenes': [{'scene_id': 's01', 'path': 'audio/s01.wav', 'sha256': hashlib.sha256(clip.read_bytes()).hexdigest(), 'text_sha256': hashlib.sha256(b'Example.').hexdigest(), 'frames': 240}]}
    (case / 'audio/provenance.json').write_text(json.dumps(record), encoding='utf-8')
    return case


class PackageTests(unittest.TestCase):
    def test_declared_public_preset_clip_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            result = module.verify(root)
            self.assertFalse(result['passed'])
            self.assertIn('unexpected private/cache/output file: examples/antigen_escape/audio/s01.wav', result['errors'])

    def test_standalone_audio_formats_rejected_without_decoding(self):
        filenames = (
            'recording.wav', 'music.mp3', 'lossless.flac', 'clip.ogg',
            'voice.m4a', 'voice.aac', 'speech.opus', 'recording.aiff',
            'recording.WAV', 'voice.M4A',
        )
        for filename in filenames:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'assets').mkdir()
                path = root / 'assets' / filename
                path.write_bytes(b'not decodable audio')
                result = module.verify(root)
                self.assertFalse(result['passed'])
                self.assertIn('unexpected private/cache/output file: ' + path.relative_to(root).as_posix(), result['errors'])

    def test_source_and_metadata_without_audio_still_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case = fixture(root)
            (case / 'audio/s01.wav').unlink()
            result = module.verify(root)
            self.assertTrue(result['passed'], result['errors'])

    def test_manifest_rejects_added_and_tampered_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'article.txt'
            path.write_text('Source', encoding='utf-8')
            entry = {'path': 'article.txt', 'size': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            (root / 'RELEASE_MANIFEST.json').write_text(json.dumps({'files': [entry]}), encoding='utf-8')
            self.assertTrue(module.verify(root)['passed'])
            path.write_text('Tampered', encoding='utf-8')
            self.assertFalse(module.verify(root)['passed'])
            (root / 'extra.txt').write_text('New', encoding='utf-8')
            self.assertTrue(any('file set' in error for error in module.verify(root)['errors']))


if __name__ == '__main__':
    unittest.main()

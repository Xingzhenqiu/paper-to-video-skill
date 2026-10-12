"""Audio trust-boundary checks run without a model or optional dependencies."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p2v_audio_test", ROOT / "scripts" / "p2v" / "audio.py")
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


def wav(path, frames=2400, width=2):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(width)
        stream.setframerate(24000)
        stream.writeframes(struct.pack("<h", 500) * frames if width == 2 else b"\x80" * frames)


class AudioTests(unittest.TestCase):
    def test_silent_preview_has_authored_duration_and_only_zero_pcm_without_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "preview.wav"
            with mock.patch.object(audio, "_load_model", side_effect=AssertionError("must not load")), \
                    mock.patch.object(audio, "_local_file", side_effect=AssertionError("must not read a provider asset")):
                result = audio.synthesize("", output, {"engine": "silence", "duration_seconds": 0.10001})
            self.assertEqual(result["engine"], "silence")
            self.assertEqual(result["duration_basis"], "authored_silent_preview")
            self.assertEqual(result["declared_duration_seconds"], 0.10001)
            self.assertGreaterEqual(result["duration"], 0.10001)
            self.assertLess(result["duration"] - 0.10001, 1 / 24000)
            with wave.open(str(output), "rb") as stream:
                self.assertEqual((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()),
                                 (1, 2, 24000, "NONE"))
                self.assertGreater(stream.getnframes(), 0)
                self.assertEqual(stream.readframes(stream.getnframes()), b"\0" * (stream.getnframes() * 2))
            self.assertNotIn("voice", result)
            self.assertNotIn("model_sha256", result)

    def test_silent_duration_errors_preserve_previous_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "preview.wav"
            output.write_bytes(b"keep")
            for duration in (None, True, "1", 0, -1, float("nan"), float("inf"), 3601):
                with self.subTest(duration=duration), self.assertRaisesRegex(audio.AudioError, "duration_seconds"):
                    audio.synthesize("", output, {"engine": "silence", "duration_seconds": duration})
                self.assertEqual(output.read_bytes(), b"keep")
            self.assertEqual(list(Path(folder).glob(".p2v-audio-*")), [])

    def test_silent_doctor_succeeds_without_optional_dependencies_or_model(self):
        with mock.patch.object(audio.importlib.util, "find_spec", return_value=None), \
                mock.patch.object(audio, "_load_model", side_effect=AssertionError("must not load")):
            report = audio.doctor()
        self.assertTrue(report["engines"]["silence"])
        self.assertFalse(report["engines"]["kokoro_onnx"])
        self.assertTrue(all(not dependency["installed"] for dependency in report["dependencies"].values()))

    def test_import_uses_actual_sample_duration_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "source.wav", Path(folder) / "out.wav"
            wav(source, frames=3960)
            result = audio.synthesize("Reviewed narration.", output, {"engine": "import", "path": str(source)})
            self.assertAlmostEqual(result["duration"], 0.165)
            self.assertEqual(result["frames"], 3960)
            self.assertEqual(result["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(source.read_bytes(), output.read_bytes())

    def test_bad_wav_rejected_before_replacing_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "bad.wav", Path(folder) / "out.wav"
            wav(source, width=1)
            output.write_bytes(b"keep")
            with self.assertRaises(audio.AudioError):
                audio.synthesize("Reviewed narration.", output, {"engine": "import", "path": str(source)})
            self.assertEqual(output.read_bytes(), b"keep")

    def test_truncated_wav_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.wav"
            wav(source)
            source.write_bytes(source.read_bytes()[:-20])
            with self.assertRaisesRegex(audio.AudioError, "truncated"):
                audio.validate_config({"engine": "import", "path": str(source)})

    def test_remote_assets_and_unknown_engines_rejected(self):
        with self.assertRaises(audio.AudioError):
            audio.validate_config({"engine": "private_clone"})
        with self.assertRaisesRegex(audio.AudioError, "local paths"):
            audio.validate_config({"engine": "kokoro_onnx", "model_path": "https://example.com/model.onnx"})

    def test_wrong_digest_language_voice_and_nonfinite_speed_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            model, voices = Path(folder) / "model.onnx", Path(folder) / "voices.bin"
            model.write_bytes(b"model")
            voices.write_bytes(b"voices")
            config = {"engine": "kokoro_onnx", "model_path": str(model), "voices_path": str(voices)}
            for extra in ({"model_sha256": "0" * 64}, {"language": "zh"}, {"voice": "private_voice"},
                          {"speed": float("nan")}, {"speed": True}, {"speed": 0.1}):
                with self.subTest(extra=extra), self.assertRaises(audio.AudioError):
                    audio.validate_config({**config, **extra})
            normalized = audio.validate_config(config)
            self.assertEqual(normalized["voice"], "am_michael")
            self.assertEqual(normalized["speed"], 1.0)

    def test_model_failure_is_actionable_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as folder:
            model, voices, output = (Path(folder) / name for name in ("model.onnx", "voices.bin", "out.wav"))
            model.write_bytes(b"model")
            voices.write_bytes(b"voices")
            output.write_bytes(b"keep")
            config = {"engine": "kokoro_onnx", "model_path": str(model), "voices_path": str(voices)}
            with mock.patch.object(audio, "_load_model", side_effect=audio.AudioError("Model unavailable")):
                with self.assertRaisesRegex(audio.AudioError, "Model unavailable"):
                    audio.synthesize("Reviewed narration.", output, config)
            self.assertEqual(output.read_bytes(), b"keep")
            self.assertEqual(list(Path(folder).glob(".p2v-audio-*")), [])

    def test_doctor_never_loads_or_downloads_a_model(self):
        with mock.patch.object(audio, "_load_model", side_effect=AssertionError("must not load")):
            report = audio.doctor()
        self.assertTrue(report["engines"]["import"])
        self.assertIn("kokoro-onnx", report["dependencies"])


if __name__ == "__main__":
    unittest.main()

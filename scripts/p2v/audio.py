"""Explicit silent previews, local public-model synthesis and PCM WAV import.

No model, credential, reference recording or network download is implicit.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib.metadata
import importlib.util
import math
import os
from pathlib import Path
import shutil
import tempfile
import wave


PUBLIC_VOICES = {
    "en-us": ("am_michael", "am_puck", "am_fenrir", "am_adam"),
    "en-gb": ("bm_george", "bm_fable", "bm_daniel", "bm_lewis"),
}
_ESPEAK_TEMP = None


class AudioError(ValueError):
    """Actionable audio configuration or data error."""


def doctor() -> dict:
    """Report optional dependencies without loading a model or contacting a service."""
    modules = {
        "kokoro_onnx": "kokoro-onnx", "numpy": "numpy",
        "onnxruntime": "onnxruntime", "phonemizer": "phonemizer",
        "espeakng_loader": "espeakng-loader",
    }
    dependencies = {}
    for module, distribution in modules.items():
        try:
            installed = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            installed = False
        try:
            version = importlib.metadata.version(distribution) if installed else None
        except importlib.metadata.PackageNotFoundError:
            version = None
        dependencies[distribution] = {"installed": installed, "version": version}
    return {
        "engines": {"silence": True, "import": True, "kokoro_onnx": all(item["installed"] for item in dependencies.values())},
        "dependencies": dependencies,
        "model_downloaded": "not checked; supply explicit model_path and voices_path",
        "languages": list(PUBLIC_VOICES),
        "setup": "Silent previews need no model. For speech, install requirements-voice.txt and follow docs/AUDIO.md; or import reviewed PCM16 WAV clips.",
    }


def _local_file(value, field: str) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise AudioError(f"{field} must be an explicit local file path.")
    if "://" in str(value):
        raise AudioError(f"{field} accepts local paths only; no implicit downloads.")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise AudioError(f"{field} file is missing; follow docs/AUDIO.md.")
    return path


def _number(value, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudioError(f"{field} must be a finite number from {minimum} to {maximum}.")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise AudioError(f"{field} must be a finite number from {minimum} to {maximum}.")
    return number


@lru_cache(maxsize=16)
def _digest(path: str, size: int, mtime_ns: int) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _sha256(path: Path) -> str:
    info = path.stat()
    return _digest(str(path), info.st_size, info.st_mtime_ns)


def _verify_digest(path: Path, expected, field: str):
    if expected is None:
        return
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise AudioError(f"{field} must be a lowercase SHA256 hex digest.")
    if _sha256(path) != expected:
        raise AudioError(f"{field} does not match the supplied asset.")


def validate_config(config: dict) -> dict:
    """Validate without importing optional synthesis dependencies. Return normalized config."""
    if not isinstance(config, dict):
        raise AudioError("Audio config must be an object.")
    normalized = dict(config)
    engine = config.get("engine")
    if engine == "silence":
        normalized["duration_seconds"] = _number(config.get("duration_seconds"), "duration_seconds", 1 / 24000, 3600)
        return normalized
    if engine == "import":
        path = _local_file(config.get("path"), "path")
        _pcm_info(path)
        normalized["path"] = str(path)
        return normalized
    if engine != "kokoro_onnx":
        raise AudioError("Supported audio engines are 'silence', 'kokoro_onnx' and 'import'.")
    language = config.get("language", "en-us")
    if language not in PUBLIC_VOICES:
        raise AudioError("This adapter supports en-us and en-gb; other languages need reviewed imported audio.")
    voice = config.get("voice", "am_michael" if language == "en-us" else "bm_george")
    if voice not in PUBLIC_VOICES[language]:
        raise AudioError(f"Choose a public {language} voice: {', '.join(PUBLIC_VOICES[language])}.")
    normalized.update({
        "language": language,
        "voice": voice,
        "speed": _number(config.get("speed", 1.0), "speed", 0.5, 2.0),
    })
    for field in ("model_path", "voices_path"):
        path = _local_file(config.get(field), field)
        _verify_digest(path, config.get(field.replace("_path", "_sha256")), field.replace("_path", "_sha256"))
        normalized[field] = str(path)
    return normalized


def _pcm_info(path: Path) -> dict:
    try:
        with wave.open(str(path), "rb") as stream:
            channels = stream.getnchannels()
            sample_rate = stream.getframerate()
            frames = stream.getnframes()
            if stream.getcomptype() != "NONE" or stream.getsampwidth() != 2:
                raise AudioError("Audio must be uncompressed PCM16 WAV.")
            if channels not in (1, 2) or not 8000 <= sample_rate <= 96000 or frames <= 0:
                raise AudioError("Audio must contain mono/stereo PCM16 samples at 8–96 kHz.")
            byte_count = 0
            while block := stream.readframes(65536):
                byte_count += len(block)
            if byte_count != frames * channels * 2:
                raise AudioError("WAV data is truncated.")
    except (wave.Error, EOFError, OSError) as error:
        raise AudioError("Unable to read a complete PCM16 WAV file.") from error
    return {"sample_rate": sample_rate, "channels": channels, "frames": frames,
            "sample_width": 2, "duration": frames / sample_rate}


@lru_cache(maxsize=2)
def _load_model(model_path: str, model_size: int, model_mtime: int,
                voices_path: str, voices_size: int, voices_mtime: int):
    try:
        from kokoro_onnx import Kokoro
    except ImportError as error:
        raise AudioError("Kokoro dependencies are missing; install requirements-voice.txt or use imported clips.") from error
    try:
        return Kokoro(model_path, voices_path, espeak_config=_espeak_config())
    except Exception as error:
        raise AudioError("Kokoro model initialization failed; verify assets and run doctor.") from error


def _espeak_config():
    """Avoid the Windows C backend's failure to open Unicode data paths."""
    global _ESPEAK_TEMP
    import espeakng_loader
    from kokoro_onnx.config import EspeakConfig
    data_path = Path(espeakng_loader.get_data_path())
    if os.name == "nt" and not str(data_path).isascii():
        if _ESPEAK_TEMP is None:
            _ESPEAK_TEMP = tempfile.TemporaryDirectory(prefix="p2v-espeak-")
            if not _ESPEAK_TEMP.name.isascii():
                _ESPEAK_TEMP.cleanup()
                _ESPEAK_TEMP = None
                raise AudioError("Windows synthesis needs an ASCII temporary path; set TMP to an ASCII directory or import clips.")
            shutil.copytree(data_path, Path(_ESPEAK_TEMP.name) / "espeak-ng-data")
        data_path = Path(_ESPEAK_TEMP.name) / "espeak-ng-data"
    return EspeakConfig(lib_path=espeakng_loader.get_library_path(), data_path=str(data_path))


def synthesize(text: str, output_wav, config: dict) -> dict:
    """Write a complete PCM16 WAV atomically and report actual duration and provenance."""
    normalized = validate_config(config)
    if not isinstance(text, str) or len(text) > 10000 or (normalized["engine"] != "silence" and not text.strip()):
        raise AudioError("Narration must contain 1–10,000 characters; split longer narration into scenes.")
    output = Path(output_wav).resolve()
    if output.suffix.lower() != ".wav":
        raise AudioError("output_wav must end in .wav.")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".p2v-audio-", suffix=".wav", dir=output.parent)
    os.close(descriptor)
    temp_path = Path(temporary)
    metadata = {"engine": normalized["engine"], "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    try:
        if normalized["engine"] == "silence":
            frames = math.ceil(normalized["duration_seconds"] * 24000)
            with wave.open(str(temp_path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(24000)
                remaining = frames
                while remaining:
                    block_frames = min(remaining, 65536)
                    stream.writeframesraw(b"\0" * (block_frames * 2))
                    remaining -= block_frames
            metadata.update({"duration_basis": "authored_silent_preview",
                             "declared_duration_seconds": normalized["duration_seconds"]})
        elif normalized["engine"] == "import":
            source = Path(normalized["path"])
            if source == output:
                raise AudioError("Imported source and output must be different files.")
            shutil.copyfile(source, temp_path)
            metadata["source_sha256"] = _sha256(source)
        else:
            model, voices = Path(normalized["model_path"]), Path(normalized["voices_path"])
            model_info, voices_info = model.stat(), voices.stat()
            engine = _load_model(str(model), model_info.st_size, model_info.st_mtime_ns,
                                 str(voices), voices_info.st_size, voices_info.st_mtime_ns)
            try:
                import numpy as np
                samples, sample_rate = engine.create(text.strip(), voice=normalized["voice"],
                                                     speed=normalized["speed"], lang=normalized["language"])
                samples = np.asarray(samples, dtype=np.float64)
                if samples.ndim != 1 or not len(samples) or not np.all(np.isfinite(samples)):
                    raise AudioError("Synthesis returned empty, non-finite or non-mono samples.")
                peak = float(np.max(np.abs(samples)))
                if peak == 0:
                    raise AudioError("Synthesis returned silence only.")
                samples = samples / max(1.0, peak)
                pcm = np.rint(np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
                if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 96000:
                    raise AudioError("Synthesis returned an invalid sample rate.")
                with wave.open(str(temp_path), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(sample_rate)
                    stream.writeframes(pcm.tobytes())
            except AudioError:
                raise
            except Exception as error:
                raise AudioError("Kokoro synthesis failed; check voice, model and language compatibility.") from error
            metadata.update({"voice": normalized["voice"], "language": normalized["language"],
                             "speed": normalized["speed"], "model_sha256": _sha256(model),
                             "voices_sha256": _sha256(voices), "peak_before_normalization": peak})
        metadata.update(_pcm_info(temp_path))
        metadata["sha256"] = _sha256(temp_path)
        temp_path.replace(output)
        metadata["path"] = str(output)
        return metadata
    finally:
        temp_path.unlink(missing_ok=True)

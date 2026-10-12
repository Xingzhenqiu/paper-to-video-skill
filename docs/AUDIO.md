# Silent preview and optional local narration

The public example is silent and includes no recordings or synthetic speech. Its render.audio uses engine="silence" and a durations map keyed by scene ID. The runner creates temporary zero-valued PCM from these authored reading durations; it does not measure or synthesize speech. This default route needs no model, voice pack or account.

For local narrated work, use an explicit import or synthesis override. Imported recordings need the necessary speaker and distribution permissions. Speech outputs are not included in this public release.

## Optional CPU synthesis

Use Python 3.12 and install the optional dependencies in your environment:

```sh
python -m pip install -r requirements-voice.txt
```

The tested adapter uses `kokoro-onnx==0.6.1`. It runs with ONNX Runtime on CPU and does not install PyTorch. Dependencies include eSpeak NG through `espeakng-loader`; retain the license notices supplied with your installed dependencies. Python 3.12 on Windows is the locally tested platform. Other operating systems still need an actual first-use test.

On Windows, eSpeak's native backend may fail if the installed data directory contains non-ASCII characters. The adapter copies that dependency's phoneme data to a temporary ASCII directory for the current process and cleans it up on exit. If your system temporary directory also contains non-ASCII characters, use an ASCII `TMP` directory or a local import route. Model weights and narration are never copied into this workaround directory.

Explicitly download these two fixed assets from the upstream model release and keep them outside the repository. The full model is about 326 MB and the voice pack about 28 MB. The application never downloads models automatically.

| Asset | Fixed download | SHA256 |
|---|---|---|
| `kokoro-v1.0.onnx` | [Upstream release asset](https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx) | `beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a` |
| `voices-v1.0.bin` | [Upstream release asset](https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin) | `bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d` |

These SHA256 values come from the [upstream v1.1 release asset metadata](https://api.github.com/repos/thewh1teagle/kokoro-onnx/releases/tags/model-files-v1.1). The asset names use v1.0; the hosting release tag is v1.1.

Supply explicit local paths when selecting the synthesis engine:

```json
{
  "engine": "kokoro_onnx",
  "model_path": "/your/model-cache/kokoro-v1.0.onnx",
  "voices_path": "/your/model-cache/voices-v1.0.bin",
  "model_sha256": "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
  "voices_sha256": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
  "voice": "am_michael",
  "language": "en-us",
  "speed": 1.0
}
```

Keep machine-specific paths in a local project copy. Do not publish credentials or private recordings. `am_puck` and `am_fenrir` are additional supported American male presets; British presets include `bm_george` and `bm_fable` with `language: en-gb`. The canonical [voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) documents these presets. This version's adapter is limited to English; use reviewed imported clips for other languages.

The public-model route writes 24 kHz mono PCM16 WAV, measures its real duration, records the model/voice-pack hashes, and uses one consistent preset and speed. Each scene is a complete sentence or short paragraph. Do not force speech into a target duration. Natural sentence pauses remain inside the clip; the scene plan can add a short pause after it. Subtitles follow scene audio boundaries, not word-level forced alignment. Listen to terminology before accepting a new narration.

## Import route

The unified project runner resolves an import config's `clips` map from scene IDs to project-relative WAV paths. It passes one explicit local path to the audio adapter per scene:

```json
{"engine": "import", "path": "/your/reviewed/s01.wav"}
```

Import preserves the bytes of a complete uncompressed PCM16 mono/stereo WAV at 8–96 kHz. Truncated, empty and unsupported files fail before replacing a previous valid output. There is no automatic transcript checking: your clip must actually say the reviewed spoken text. Imported-audio hashes enter the runner's cache so changing a clip rebuilds the affected scene.

## Rights and verification

The upstream [kokoro-onnx project](https://github.com/thewh1teagle/kokoro-onnx) declares MIT for its code and Apache 2.0 for the Kokoro model. The canonical [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M) labels its weights Apache 2.0 and describes training sources and attribution. No model weights, voice pack, dependency code or private reference voice are bundled with this repository. Those upstream terms do not determine this repository's own software license.

The setup uses official asset hashes and locally measured PCM durations. Unit tests verify import integrity, truncated-file rejection, configuration failures and preservation of existing output on failure. They do not prove subjective vocal quality, scientific pronunciation or rights of audio imported by another user. The public example instead records authored silent-preview timing; it does not provide listening or pronunciation validation.

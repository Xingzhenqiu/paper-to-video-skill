# Reproduction record: v0.2-alpha silent preview

The public package contains code and silent demonstrations. Its default real-paper example uses authored scene durations for visual inspection. It requires a reviewed project plan and does not infer a finished explanation from arbitrary PDF bytes.

## Current validation status

The revised silent default passed its current unit suite and the local checks below on 2026-10-12. Media and cache results here come from the current explicit-silence plan, rather than the earlier voiced example. Automated checks do not establish human scientific or visual approval.

| Check | Current result |
|---|---|
| Current unit suite | 59 tests passed after the explicit-silence change, including silent audio generation, pipeline timing, and public-package audio exclusion. |
| Default case doctor and source validation | Passed in the independent Windows Agent run: environment check and reviewed source/quote/figure validation completed. |
| Silent build and full video decode | Passed at 1920×1080 / 24 fps: 41.625 seconds, 999 decoded frames. The independent 640×360 / 12 fps run decoded all 503 frames over 41.9166667 seconds. |
| Silence audit | Passed on both builds. The exact release gate accepted the 1080p film; the independent 640px run decoded its AAC stream with all samples zero, including peak amplitude zero. No standalone audio files are included. |
| Unchanged resume | Passed in the independent 640px run: all 7 generated-silence caches and 7 visual clips reused; all 14 payload SHA256 values and modification times, scene hashes, and the final video SHA256 stayed unchanged. |
| One-title revision and resume | Passed at 1080p / 24 fps: exactly `s04`'s visual clip rebuilt, 6 visual clips and all 7 generated-silence caches reused with matching unchanged payload hashes. Both films remain 41.625 seconds / 999 decoded frames and pass the silence gate; scene timing, captions and evidence hashes stay unchanged. See [INCREMENTAL.md](INCREMENTAL.md). |
| Independent Agent reproduction | Passed on Windows x64 / Python 3.12.0 in an existing isolated virtual environment with Pillow 12.3.0 and imageio-ffmpeg 0.6.0. No private voice/model or paid API was used. No new environment or package installation was performed in this run; this is not a human user trial. |
| Captions and evidence | Passed in the independent run: all 7 subtitle cues match scene timing and display text without overlap; 4 evidence claims retain matching source quotes/locators, working relative assets and attribution. |
| Release file and archive checks | Pending final manifest, CRC, per-member hashes and silence audit. |

## Reproduce the current default

Use Python 3.12 and the full repository:

```bash
python -m pip install -r requirements-demo.txt
python -B -m unittest discover -s tests -v
python scripts/pipeline.py doctor
python scripts/pipeline.py validate examples/antigen_escape/project.json
python scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/silent-check --width 640 --fps 12
python scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/silent-check --width 640 --fps 12 --resume
python -B scripts/verify_package.py
```

Inspect `video.mp4`, captions, `evidence.html` and `build_report.json` in the output directory. A completed command alone does not verify encoded media or the claims shown on screen. The [workflow](../.github/workflows/checks.yml) requires unit/source/package checks and a Linux build/resume before its release job; packaging then verifies every public video for full decoding and silence. See [GitHub Actions](https://github.com/Xingzhenqiu/paper-to-video-skill/actions) for actual remote results; a configured workflow is not a passing run.

## Timing and package integrity

The public plan selects `render.audio.engine: "silence"` and sets each scene's duration in `render.audio.durations`. These durations provide planned reading and viewing time; they do not measure speech rate or certify narration alignment. Silent build records use `timing_basis: "authored_silent_preview"` and `narration_present: false`. Captions use reviewed display text and follow scene timing. The plan adds a 0.35-second scene pause, with frame-grid rounding that can make output durations differ slightly between frame rates.

Fonts, Pillow and encoder versions can change pixels or MP4 bytes. Compare content, source links, scene timing and cache reuse instead of assuming one universal video hash. Local and CI ZIP metadata can also differ; compare member paths, actual payload bytes and per-member SHA256. Each download includes LICENSE and a manifest for its own contents.

Optional local audio import and synthesis remain separate code paths; speech files and voiced videos are excluded from this public release. See [AUDIO.md](AUDIO.md) for local configuration.

## Human review and unverified scope

- Watch the full silent film, check terminology and scientific structures against the source, and obtain specialist sign-off when appropriate.
- Broader cross-platform and multilingual testing remain incomplete. Count each environment as tested only after its current run passes.
- Arbitrary-paper automatic interpretation, unsupported scientific components and automatic PDF/OCR extraction are outside the verified path.
- Same-paper comparisons with other projects and five-person first-use trials have not been performed.

Existing `verified` source flags are input records. A successful build does not turn pending human review into approval. Published v0.1 is preserved separately.

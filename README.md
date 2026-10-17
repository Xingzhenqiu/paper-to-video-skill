# Paper to Video Skill

English · [简体中文](README.zh-CN.md)

[![Package checks](https://github.com/Xingzhenqiu/paper-to-video-skill/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/Xingzhenqiu/paper-to-video-skill/actions/workflows/checks.yml)

**Make a paper's key experiment or mechanism understandable.** An Agent plans a source-backed explanation; a local runner builds a silent visual preview, captions and an evidence page.

**v0.2.1-alpha:** reviewed plans, a silent real-paper excerpt, scene reuse and first-run portability checks. Scientific and visual review remain human responsibilities.

[![Watch the antigen escape walkthrough](docs/media/antigen_escape.poster.png)](docs/media/antigen_escape.mp4)

[Watch the silent example](docs/media/antigen_escape.mp4) · [Local preview](docs/demo.html) · [Source and attribution](examples/antigen_escape/README.md)

The example explains **antigen escape** using Figure 1A and selected passages from [Sterner & Sterner's 2021 review](https://www.nature.com/articles/s41408-021-00459-7), licensed CC BY 4.0. It combines an adapted source figure and qualitative animation. It is a focused excerpt, not a full review or measured efficacy comparison. Public downloads contain code and silent demonstrations. The default preview requires no voice recording, speech model or API key.

## Try it locally

Download and extract the full repository. Use **64-bit Python 3.12** and open a terminal in the repository root. The first install downloads two pinned dependencies; the default example needs no API key.

Windows (no environment activation required):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.venv\Scripts\python.exe scripts/pipeline.py doctor
.venv\Scripts\python.exe scripts/pipeline.py validate examples/antigen_escape/project.json
.venv\Scripts\python.exe scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/antigen-escape
```

macOS / Linux (install Python 3.12 first):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-demo.txt
.venv/bin/python scripts/pipeline.py doctor
.venv/bin/python scripts/pipeline.py validate examples/antigen_escape/project.json
.venv/bin/python scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/antigen-escape
```

In subsequent commands, `python` means the interpreter in this environment. If `py` or `python3.12` is missing, install the matching Python version first. Run these commands in a terminal, not the Python `>>>` prompt.

Open `outputs/antigen-escape/video.mp4`. The same folder contains SRT/VTT captions, `evidence.html` and `build_report.json`. The silent preview uses authored scene durations for visual inspection, without a fixed five-minute template. These durations are planned viewing time, not measured speech or word alignment. The checked default output is 1920×1080 at 24 fps: 41.625 seconds and 999 decoded frames. For a smaller first run, add `--width 640 --fps 12`; frame rounding changes the duration slightly.

Add `--resume` to reuse hash-verified unchanged work. Edit only scene `s04`'s `visual.title`, then resume and inspect which visual clips were reused in the build report. Preserve a copy first if you want both videos. See [the revision procedure](docs/INCREMENTAL.md) for the expected behavior and current verification status.

Installation can download packages; the silent default renders locally without a speech service. Time depends on your machine. Optional audio import and English TTS remain code capabilities for separately configured local use; speech files and voiced videos are excluded from public downloads. See [AUDIO.md](docs/AUDIO.md).

## Install the Agent skill

Copy the complete [skill folder](skills/paper-to-video/SKILL.md) into your host's supported skill directory. In Codex, use `<your-project>/.agents/skills/paper-to-video` or `~/.agents/skills/paper-to-video`; reload if needed. You can ask the skill installer to install `skills/paper-to-video` from [this repository](https://github.com/Xingzhenqiu/paper-to-video-skill).

The skill folder supplies instructions and a lightweight source adapter. **The runnable renderer and examples require the full repository.** Model weights, credentials and PDF extraction services are not bundled.

Try this request:

> Use paper-to-video to explain this paper for my audience. Check the source, link claims to evidence, and preview the hardest visual first. Let the content determine the length. Keep source locators backstage, use one central idea per scene, and identify what still needs scientific or visual review.

## What runs, and what the Agent does

| Step | Current implementation |
|---|---|
| Input | UTF-8 article text or a reviewed Reader card; raw PDF/OCR needs an upstream extractor. |
| Explanation | Agent authors claims, narration and visual plans. Initialization does not invent or verify them. |
| Source checks | Reopens the actual source; checks its hash, units, quotes and referenced figure assets. |
| Visuals | Titles, aspect-preserving figures, authored node animations and simple bar charts; unsupported components fail explicitly. |
| Audio | The public example uses explicit silence. Optional reviewed PCM WAV import and English Kokoro synthesis are separately configured local code paths. |
| Timing | Public preview captions and animation use authored scene durations. A separately configured local speech run uses measured clip duration; neither route supplies word-level forced alignment. |
| Revision | Changed sentences/assets rebuild dependent scenes; unchanged clips are verified and reused. |
| Review | Automated decode and integrity results stay separate from human scientific and visual approval. Local speech use also requires listening review. |

Initialize another article:

```bash
python scripts/pipeline.py init article.txt outputs/my-paper/project.json --format text --article-type experimental
```

Then author and review the project record; see [execution](skills/paper-to-video/references/execution.md) and the [input contract](skills/paper-to-video/references/project-interface.md). Full-paper plans require full source coverage. Excerpts must declare their scope. A newly initialized record is not yet buildable.

## Checks and limits

```bash
python -B -m unittest discover -s tests -v
python -B scripts/verify_package.py
python scripts/smoke_check.py --output-dir outputs/first-run-check
```

The last command actually builds a small silent video, checks full decoding, captions, evidence and cache reuse, then changes one title in its working copy to verify selective rebuilding. It preserves the original example and refuses an existing nonempty directory; use a new directory for another run. Results are written to `smoke_report.json` there.

**Configure a font before making CJK content.** Place a suitably licensed Chinese/Japanese/Korean `.ttf` or `.otf` in your project, for example `assets/NotoSansSC-Regular.ttf`, and set `"font": "assets/NotoSansSC-Regular.ttf"` in the root-level `render` object. The default font is for Western text; CJK scenes without an explicit font fail validation. A font path does not prove glyph coverage: inspect the rendered preview. Check redistribution terms before adding a font to a public repository.

Repository `.gitattributes` disables automatic line-ending conversion to preserve the exact bytes bound by evidence and retained-report hashes. Do not rewrite a source hash to bypass a failure. If an older checkout has converted line endings, preserve your own work and download the latest full repository into a new folder.

[Reproduction notes](docs/REPRODUCIBILITY.md) distinguish the retained v0.2.0 measurements from v0.2.1's 66 passing tests and actual smoke check in a newly created Windows / Python 3.12 environment. All 14 cached payloads were reused unchanged; a title revision rebuilt only `s04`'s clip. The workflow runs the same checks on Windows, Linux and macOS; the badge links to actual results. These are technical Agent/CI checks, not human trials or scientific approval. Compare structures with the source and watch the encoded result before publication. Separately configured local speech needs listening review.

This version does not promise arbitrary-PDF automatic production, independently audited accuracy, or superior performance. No same-paper comparison, cross-platform end-to-end benchmark or five-person study has been conducted. The earlier [synthetic Simpson's paradox example](examples/simpson/render_demo.py) remains available separately.

## Contribute and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for small, concrete tasks and [Community](docs/COMMUNITY.md) for privacy-friendly feedback, voluntary case sharing and collaboration scope. [Open a feedback form](https://github.com/Xingzhenqiu/paper-to-video-skill/issues/new/choose); unpublished papers and private voice recordings are not required. Cases enter the showcase only with explicit consent.

Optional credit you can copy:

> Created with Paper to Video Skill: https://github.com/Xingzhenqiu/paper-to-video-skill

Visible credit, a star or a watermark is not a condition of use. The software and skill use the [MIT License](LICENSE), including its notice requirement. Paper assets and upstream terms remain separate; see [RIGHTS.md](RIGHTS.md).

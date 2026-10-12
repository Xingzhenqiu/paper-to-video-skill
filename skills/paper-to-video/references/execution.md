# Executable project plans

Use this reference when the full repository's `scripts/pipeline.py` is available. Installing only this skill's instruction folder does not install the repository renderer, its examples, fonts or optional voice model. If the helper is absent, use the host's actual tools and report that distinction.

## First successful run

From the downloaded repository, install `requirements-demo.txt`, run `python scripts/pipeline.py doctor`, then build the supplied plan:

```bash
python scripts/pipeline.py validate examples/antigen_escape/project.json
python scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/antigen-escape
```

This path uses the `silence` engine with explicitly authored reading durations; it creates zero PCM locally and requires no voice files, model or paid API. The public download contains code and silent previews only. Optional local narration uses imported audio or TTS with separate dependencies/model files. Supported drawing components are deliberately bounded; an unknown visual must fail or be replaced with a reviewed source figure, never silently invented.

## Preparing another article

Import readable UTF-8 text or a reviewed Reader card through the input adapter. The Agent must author source-backed claims, short display/spoken sentences and a supported visual plan. Initialization does not perform scientific review or produce a finished storyboard automatically. Keep all source, image and audio references relative to the project record where practical.

A full-paper plan requires full source coverage. A focused excerpt must explicitly state `project.scope=focused_excerpt` and `project.selected_coverage`; that does not imply that the whole paper was read or explained. Preserve unresolved extraction and scientific questions.

The render extension includes `render.assets`, output dimensions/fps, an audio provider and a short pause. A scene's `visual` describes a title, reviewed figure, qualitative diagram or supported chart. Display text and spoken text are separate: one short sentence appears for the measured speech duration, or the explicitly authored reading duration in a silent preview. Do not estimate whole-film timing from character count or force a default duration.

Execution settings are at the record's root `render` field. Source assets declare project-relative paths, SHA256, rights and attribution. Diagram `x` and `y` are normalized within the safe content area; `size` is relative to content height, not the whole screen. Event `start` and `end` are fractions of the current scene duration. Preserve the visual meaning when changing a node's location or an arrow.

The bundled scalable font is used for the English example. Other writing systems or scientific glyphs may require an explicitly supplied licensed font via `render.font`, relative to the project. Inspect actual rendered text for missing glyphs before the full build. Imported speech allows other languages; the optional synthesis adapter currently supports English only.

## Revision and reporting

Change the smallest relevant plan or asset. Resume against the same run directory to reuse verified cached audio and visuals; check the report rather than assuming a file was reused. Changes in voice, speed or sentence length affect real durations and the dependent timeline. Preserve a first output copy when both versions are needed.

Treat `build_report.json` as technical evidence, not domain approval. Review quotes/figures against the source, inspect the encoded picture, and listen to the actual sound when narration is present. A silent preview verifies authored timing and zero audio; it does not demonstrate speech quality. Do not automatically turn pending human checks into verified flags. Backstage evidence belongs in the review page; keep the video visually concise.

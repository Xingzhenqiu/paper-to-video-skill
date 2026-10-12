# A real-paper excerpt: antigen escape

This case explains Figure 1A and selected sentences from Sterner RC and Sterner RM, **CAR-T cell therapy: current limitations and potential strategies**, *Blood Cancer Journal* 11, 69 (2021), [DOI: 10.1038/s41408-021-00459-7](https://doi.org/10.1038/s41408-021-00459-7).

The article and included figure are **CC BY 4.0**. [Publisher source and license](https://www.nature.com/articles/s41408-021-00459-7) · [License](https://creativecommons.org/licenses/by/4.0/). Figure 1 was rendered from the PDF; panel A was cropped and adapted for a dark background. Neutral text is lightened; the colored scientific illustrations retain their colors. The diagrams are qualitative explanations, not molecular reconstructions or measured efficacy results. Attribution and source locations are recorded in [provenance.json](provenance.json).

This is a focused review excerpt, not an experiment, a complete summary of the article, or clinical advice. The source text, selected coverage, claims, captions, planned narration and visuals are defined in [project.json](project.json). This public example is a silent visual preview: scene durations are authored for reading the captions, followed by a short pause. No voice recording or measured speech is included.

From the repository root:

```bash
python -m pip install -r requirements-demo.txt
python scripts/pipeline.py doctor
python scripts/pipeline.py validate examples/antigen_escape/project.json
python scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/antigen-escape
```

The default silence engine needs no voice files, model or API key. Optional narration code can run locally with an explicit audio override; see [AUDIO.md](../../docs/AUDIO.md). Generated or imported speech is not part of the public download.

The build directory contains `video.mp4`, timed subtitles, an evidence review page and a build report. Structural/source checks and successful decoding do not constitute independent scientific approval or a human judgment of pronunciation and aesthetics. Inspect the report's pending review items.

To demonstrate a local revision, back up the plan and first video, edit only `s04.visual.title` in the same `project.json` to `Target loss breaks single-target recognition`, and repeat the build with the same output directory and `--resume`. The report identifies which clips were rebuilt. A different project file has a separate run identity and needs its own output directory; records moved to another folder must rebase their relative source, asset and audio paths. See [the measured revision](../../docs/INCREMENTAL.md).

中文：这个公开案例用一张真实综述图解释抗原逃逸。原图与摘录采用 CC BY 4.0，并注明作者、出处与改动；示意动画只表达定性机制，不代表治疗效果。公开版本为无声预览，不含配音文件。先按上面的命令运行，再查看证据页与待人工确认项。片长来自分镜阅读时长的编排，不代表配音节奏，也不固定为五分钟。

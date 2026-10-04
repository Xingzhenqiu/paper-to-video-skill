# Paper to Video Skill

English · [简体中文](README.zh-CN.md)

An Agent workflow for turning research papers into clear animated explanations, with claims linked to sources and visuals built around one idea at a time.

**v0.1-alpha:** workflow skill + a reproducible, original demonstration. Installing the skill does not provide an automatic video engine for arbitrary PDFs.

[![Watch the Simpson's paradox demonstration](docs/media/poster.png)](docs/media/demo.mp4)

[Watch the 48-second demo](docs/media/demo.mp4) · After downloading, open [the local preview](docs/demo.html).

The demo explains Simpson's paradox through staged charts on a dark background. Its article and numbers are synthetic teaching material, not experimental results. It renders at 1920×1080, 24 fps, with burned-in English captions. The default is silent; you can add your own authorized audio.

## What you get

| Included | Scope |
|---|---|
| [Agent skill](skills/paper-to-video/SKILL.md) | Source review, claim mapping, narration, visual planning, voice/subtitle timing, and delivery checks. The host Agent performs the work using its available tools. |
| [Project interface](skills/paper-to-video/references/project-interface.md) | Import UTF-8 text or an existing Reader card; check source quotes and scene references. Python standard library only. |
| [Runnable demonstration](examples/simpson/render_demo.py) | Render the supplied teaching example locally, without an API key. It is a dedicated demo renderer, not a general paper renderer. |

## Install the skill

Copy the complete `skills/paper-to-video` folder, including its references and script, into your host's skill directory.

For local Codex use, place it at `<your-project>/.agents/skills/paper-to-video` or `~/.agents/skills/paper-to-video`. Reload or restart if it does not appear. See [official OpenAI skill documentation](https://learn.chatgpt.com/docs/build-skills).

Once a repository is published, you can also ask the Codex skill installer to install `paper-to-video` from that repository's URL, using the path `skills/paper-to-video`. Substitute the actual published URL; this package does not assume a repository owner.

Try this request after installation:

> Use the paper-to-video skill to explain this article for my intended audience. First check the source and available tools, then make a claim map and a short visual preview. Let the content determine the duration. Identify statements and structures that need human review before making the full video.

The skill needs an Agent with file access and suitable execution tools. PDF extraction, fonts, encoders, models, and TTS services are separate environment dependencies; installation does not provide them.

Both READMEs are provided in English and Chinese. The skill's detailed instructions and references are currently mainly in Chinese.

## Run the demo

Use Python 3.10+ and run these commands from the downloaded repository root. No Agent or cloud account is needed for this example.

```bash
python -m pip install -r requirements-demo.txt
python examples/simpson/render_demo.py --output outputs/demo.mp4
```

Dependencies: `Pillow>=10.1,<13` and `imageio-ffmpeg>=0.6,<0.7`. The latter supplies the video encoder. Local dependency installation may download packages; rendering makes no paid API calls. Runtime depends on your machine. Rendering on other operating systems has not yet been independently tested.

Optional: add an authorized 48-second audio track that already matches the example's timing:

```bash
python examples/simpson/render_demo.py --output outputs/demo-with-audio.mp4 --audio YOUR.wav
```

This adds an audio track. It does not synthesize speech or align arbitrary narration to captions. The default captions use the supplied demo timeline; the separate [SRT](examples/simpson/subtitles.en.srt) and [narration](examples/simpson/narration.en.md) let you prepare matching audio.

The example's editable sources are [article.txt](examples/simpson/article.txt), [data.json](examples/simpson/data.json), and [project.json](examples/simpson/project.json). The original data and drawing instructions determine the demo; fonts and encoder versions can change its exact appearance and binary file.

See [REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for the checks actually completed and those not yet performed. To run the source/data checks yourself:

```bash
python -B -m unittest discover -s tests -v
python -B scripts/verify_package.py
```

## Start a paper project

For an existing UTF-8 text file, initialize a new record and validate it:

```bash
python skills/paper-to-video/scripts/project.py init examples/simpson/article.txt outputs/project.json --format text --article-type theoretical
python skills/paper-to-video/scripts/project.py validate outputs/project.json
```

The output must not already exist. Initialization records the source; it does not automatically write verified claims, scenes, or video. Use [the project interface guide](skills/paper-to-video/references/project-interface.md) to add actual source quotes and review states. An existing Reader card is another supported input; a PDF requires an upstream extraction tool.

## Limits and review

The demonstrated capability is the supplied text/data → scripted animation → MP4 example. A host Agent must still implement the production steps for a new paper. There is no unified arbitrary-PDF parser, TTS adapter, automatic alignment service, or general rendering CLI in this package.

`contract_valid` checks basic data and references. `evidence_ready` combines structural checks with recorded human review; it is not an independent scientific audit. The project validator's `video_ready` is currently always `false`, because audio, timing, rendering, and final viewing checks are not connected to that interface. A separately rendered demo does not change this state.

For real papers, review scientific claims and diagram topology against the source, then listen to and watch the encoded result. Set duration from the material and measured narration, rather than forcing every paper into a fixed time. Public distribution of a paper, its figures, or a voice requires its own permission; private reading access is insufficient.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md). Useful contributions include a reproducible installation report, a failing reference-check case, or a small public example from another field. Include the input, expected behavior, environment, and minimal reproduction. Share only material you are authorized to distribute.

## License

**License pending author confirmation.** No open-source license has been granted for this release candidate. See [RIGHTS.md](RIGHTS.md) for the package's current rights status. Dependency licenses and rights in future paper or voice assets are separate.

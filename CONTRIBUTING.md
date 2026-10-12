# Contributing

Useful contributions include independently reproduced examples, extraction fixes, reviewed animation components, and speech/alignment adapters.

## Start small

- Run the included antigen-escape example in a fresh environment and report your operating system, Python version and completed checks.
- Correct one unclear installation or revision step, with the command that worked for you.
- Reduce one source-check or asset failure to a small synthetic example and report the expected and observed result.
- Review one caption or source-to-claim link in a public, rights-cleared example and explain a specific correction.

Use the repository's [issue forms](https://github.com/Xingzhenqiu/paper-to-video-skill/issues/new/choose) for bugs, voluntary cases or collaboration requests. English and Chinese reports are welcome. A short report is useful even when you cannot provide an input file.

## Reports and examples

For a bug report, provide the command, Python and package versions, operating system, and expected and observed output. A public DOI, small shareable excerpt or synthetic reproduction can replace a full paper. Remove private paths and secrets from logs. Do not attach private papers, credentials or cloned voice references.

For an example, include the input and its rights, script, source-to-claim links, actual outputs, reproduction steps, and completed versus unperformed checks. Synthetic examples must be labelled synthetic. A working renderer does not certify scientific accuracy.

Case sharing is voluntary. Posting an issue does not authorize showcase inclusion: the case form defaults to no inclusion and asks separately for explicit consent. See [COMMUNITY.md](docs/COMMUNITY.md) for the scope of that consent and collaboration requests.

## Changes and checks

Keep changes local. Run `python -m unittest discover -s tests -v`, then reproduce the affected example. A new dependency should solve a concrete need and have a documented fallback. Do not add a provider setting unless actual code uses it.

This release is a workflow skill with a deterministic demonstration. Universal PDF rendering and interchangeable TTS providers are not implemented yet.

## Optional acknowledgement

If useful, you may credit the project with:

> Created with Paper to Video Skill: https://github.com/Xingzhenqiu/paper-to-video-skill

Project citation, stars, watermarks, donations and usage reporting are not requirements. Follow the [software license](LICENSE) and [upstream asset terms](RIGHTS.md) when redistributing or publishing.

中文：欢迎从复现示例、修正文档、最小报错案例或字幕核查开始。无需提交私人论文；致谢和案例收录均为自愿，案例收录须另行明确同意。

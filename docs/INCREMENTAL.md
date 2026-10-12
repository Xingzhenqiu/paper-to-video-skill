# One scene changes; the others stay

This worked revision changes only scene `s04`'s `visual.title` in the existing project record:

```diff
- "title": "Target loss can enable escape"
+ "title": "Target loss breaks single-target recognition"
```

No source quote, image, animation or planned timing setting changes. The public case uses explicit silence. The current revision was checked at 1920×1080 / 24 fps against a saved baseline report and the actual cached payloads.

| Check | Expected behavior | Current verification |
|---|---|---|
| Changed scene | Rebuild the visual clip for `s04`. | Passed: exactly one visual clip rebuilt; only `s04`'s clip SHA256 changed. |
| Other scenes | Reuse visual clips only when their recorded hashes remain valid. | Passed: 6 visual clips and all 7 generated-silence caches reused; their payload SHA256 values stayed unchanged and matched the report. |
| Planned timing | Preserve scene durations because the title edit does not change them. | Passed: scene starts, ends and frame counts stayed unchanged; both films are 41.625 seconds and 999 decoded frames. |
| Generated preview integrity | The encoded previews remain silent. | Passed: both films fully decoded and passed the release silence gate; the current cached PCM silence samples were also all zero. |

The measured result is one visual change with the other eligible scenes reused. Subtitle and evidence-page payload hashes also stayed unchanged. Generated-silence cache files remain local build outputs and are excluded from public downloads. Human review states remain separate from cache checks; this result does not certify scientific or visual quality or guarantee performance on another machine.

## Reproduce

1. Run the case from the README, using one dedicated output directory.
2. Save copies of the first film and plan if you need both versions.
3. Edit the title in the **same** `examples/antigen_escape/project.json`.
4. Run the same build command with `--resume` and inspect `build_report.json`.

```bash
python scripts/pipeline.py build examples/antigen_escape/project.json --output-dir outputs/antigen-escape --resume
```

The output marker belongs to the project file's identity. Building a sibling plan into that directory is rejected to avoid mixing projects. Use a new output directory for a different record. Resolution, fps and scene-duration changes can invalidate dependent clips. Cache reuse requires valid hashes, not simply an existing filename.

中文：公开案例采用静音，分镜时长用于视觉检查。本轮只改第四景标题，实际重做该景画面，复用其余 6 景与 7 个本地静音缓存；对应哈希核验通过。两版均为 41.625 秒、999 帧，完整解码及全零音轨检查通过。静音缓存不随公开下载分发。请编辑同一项目文件后恢复运行，另一个项目文件需使用新的输出目录。

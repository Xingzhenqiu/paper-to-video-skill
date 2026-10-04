# Reproducibility / 复现记录

Release candidate: v0.1.0-alpha. Checked on Windows on 2026-10-05, with Python 3.12.0, Pillow 12.3.0 and imageio-ffmpeg 0.6.0. Dependencies were already installed; a fresh network installation has not been tested.

发布候选包 v0.1.0-alpha 于 2026-10-05 在 Windows 实测。依赖版本如上，使用已安装库；尚未测试联网从零安装。

| Check / 检查 | Actual result / 实测结果 |
|---|---|
| Contract and arithmetic checks / 输入契约与算术 | 17 tests passed. Covers source locations, invented quotes, incomplete-source gates, reference integrity, output preservation, invalid counts and independently recomputed rates. / 17 项通过，涵盖来源定位、伪造引文、来源不全、引用完整性、输出保留及数值计算。 |
| First use in an isolated copy / 隔离副本首次使用 | Source initialization and validation succeeded. A separate 1280×720, 12 fps preview rendered and all 576 frames decoded. No private project logic or credentials were used. / 成功导入来源、检查契约并渲染独立预览，576 帧完整解码。 |
| Source and evidence / 来源与证据 | 6 claims, 10 continuous quotes matched the original synthetic article. Group and pooled rates were independently recalculated from counts. / 6 个主张、10 处连续引文与合成原文对应，分组和总体比率由计数独立复算。 |
| Included MP4 / 随包成片 | 48 seconds, 1920×1080, 24 fps, H.264, silent. All 1,152 frames decoded with increasing timestamps. / 全帧解码，时间戳递增。 |
| Encoded visuals / 编码后画面 | 6 main frames and 10 transition frames compared with the renderer; mean absolute RGB error below 1.5/255. Main frames were visually inspected for clipping and overlap. / 重点帧及转场与绘图源比对，检查裁切和遮挡。 |
| Captions / 字幕 | Six authored cues cover 0–48 seconds; rendered caption bounds fit the designated safe area. SRT and VTT are included. / 六段预设字幕覆盖全片，字幕位置在设定区域内。 |
| Readiness / 放行状态 | `contract_valid=true`; human review remains pending, so `evidence_ready=false` and `video_ready=false`. The demo renders separately from this project interface. / 基础契约通过，未把此结果作为科学审核或完整成片放行。 |

Not tested: fresh dependency installation, automatic host skill discovery, macOS/Linux execution, arbitrary PDF/OCR, new-paper full rendering, TTS, optional audio muxing, speech alignment, browser playback from start to finish, independent scientific review, or a GitHub Actions run.

尚未测试：依赖从零安装、宿主自动发现 skill、其他系统、任意 PDF/OCR、新论文全片、TTS、可选音轨混流、语音对齐、浏览器全程播放、独立科学审核及 GitHub 远程 CI。

At 360px width the main figures are readable, but small denominators and provenance labels need zooming. This is a landscape demo, not a validated portrait/mobile layout. Different dependency versions can change fonts or encoded bytes; numerical and source checks are the reproducibility criteria, not byte-identical videos.

360px 宽缩图中主要数字可辨，小字需放大。本例为横屏演示，尚未完成竖屏或手机布局验收。字体和编码字节可能随依赖变化；复现以来源、数值和画面行为一致为准。

The included [render report](media/demo.report.json) records input and video hashes, versions and the authored timing basis. The example is original synthetic teaching material, not a paper-derived experiment. The 48-second schedule applies only to this example; new articles should use content-led duration.

[绘图报告](media/demo.report.json)记录输入及视频哈希、版本和预设时间轴。案例为原创合成教学材料，48 秒仅用于此例，不作为新文章的统一时长。

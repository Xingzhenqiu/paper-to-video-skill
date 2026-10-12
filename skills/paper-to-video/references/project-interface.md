# 可运行的输入与证据接口（v1）

Python 3.10+，仅标准库；不访问网络，不生成配音或视频。从本 skill 目录运行：

```bash
python scripts/project.py init /path/to/card.json /path/to/project.json --format reader-card --article-type review --coverage full
python scripts/project.py init /path/to/article.txt /path/to/project.json --format text --article-type opinion --coverage full
python scripts/project.py validate /path/to/project.json
```

第一条接收既有 Reader 的 card.json；第二条接收 UTF-8 纯文本。output 必须尚不存在，避免覆盖已核对内容。全文是否齐全须由实际检查决定；不确定时省略 coverage，默认 unknown。PDF/OCR/HTML 仍需上游工具，不能将 PDF 直接当 text 传入。文章类型默认 unknown，不根据个别关键词猜测。

## 当前实现的契约

- `schema_version=1`：接口版本。
- `project`：article_type、language、target_seconds、audience、use、pronunciations。类型为 unknown / experimental / review / clinical / engineering / theoretical / opinion。术语词典每篇从空字典开始。

`target_seconds` 默认null，表示由内容决定长度；不预设片长，也不生成虚构逐景秒数。只有用户明确指定目标时长时才传入 `--seconds`。实际配音完成后再生成时间轴，不为满足旧预算加速声音或删掉必要解释。
- `source`：id、format、sha256、coverage、rights、metadata、units、figures。哈希针对本次输入的卡或文本，不冒充原 PDF 哈希。原始材料另行只读保存。
- `units[]`：id、text、locator；Reader 页码保留零基 page_index 和 bbox，纯文本保留一基行号。
- `claims[]`：id、text、evidence、review_status。evidence 每项含 unit_id 和 quote，quote 必须是对应原文片段。`verified` 由实际语义核对后填写，脚本不会自动写入。
- `scenes[]`：id、claim_ids、display_text、spoken_text、visual_intent；显示术语与口播可以不同。
- `acceptance`：source_review、scientific_review、audio_review、visual_review、timing_review 分开记录。

Reader 的 `quality.issues` 会保留在 `source.upstream_issues`。除私人整理中不阻断的 license_not_found_in_pdf 外，未处理问题阻断 evidence_ready；不能只把总审阅状态设为verified就绕过。确经原文复核的问题，在 `source.issue_reviews` 逐项记录 code、status=verified、reason。图注与图像分处不同页时，figures同时保留page_index和caption_page_index；不要用图片页码替代图注页码。

最小主张与分镜示例（ID与引文必须替换为实际来源）：

```json
{
  "claims": [{"id": "c1", "text": "经核对的主张", "evidence": [{"unit_id": "line_1", "quote": "原文中的连续片段"}], "review_status": "pending"}],
  "scenes": [{"id": "s1", "claim_ids": ["c1"], "display_text": "屏幕文字", "spoken_text": "口播文字", "visual_intent": "比较两种方法的已核对差异"}]
}
```

## 检查结果含义

`contract_valid` 仅表示基础数据与引用检查通过；命令退出码0只对应这一项。`evidence_ready` 还要求全文覆盖、明确类型、非空主张和分镜、来源与科学核对状态已填写 verified。它是人工核对状态加结构检查，不是独立科学审计。有限资料仍可导入做私人整理，但不能通过全文制作闸门。

轻量 `project.py` 的 `video_ready` 仍为 false，它不执行渲染。完整仓库的 `scripts/pipeline.py` 另行验证 `build_ready`，连接实际音频、时间轴和渲染并生成技术报告；这仍不自动批准人工听看。缺少 DOI、期刊或图不导致轻量接口失败。

Reader 图片只导入定位和图注，不搬运原始路径和图片。统一工具的 `init` 记录 `source.path`，构建时重新读取来源并核对哈希和原文；可用资产需要补充相对路径、SHA256、许可和署名。旧版辛普森专用绘图器仍是独立案例。导入内容不自动匿名化，也不自动成为公共发布素材。

完整仓库使用根级 `render` 扩展存放画面、音频和资产设置，支持 `--audio-config` 本地覆盖；与轻量科学契约分别验证。具体字段与无声案例见 [执行说明](execution.md)。不要添加未被实际读取的供应商配置。

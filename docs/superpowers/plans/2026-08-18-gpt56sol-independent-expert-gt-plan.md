# GPT-5.6-sol 独立专家 GT 实施计划

设计依据：`docs/superpowers/specs/2026-08-18-gpt56sol-independent-expert-gt-design.md`

## 阶段 1：盲输入与契约

1. 新增 `scripts/independent_gt.py`，提供 `prepare`、`validate`、`seal` 子命令。
2. `prepare` 校验冻结 OCR baseline ID、30 篇论文身份、30 份增强 Markdown 和关联 CSV，计算 SHA-256。
3. 生成 `data/gt/gpt56sol-independent-expert-20260818/blind_input_manifest.json` 和三个稳定的 10 篇 batch manifest。
4. 新增 claim、curve audit、issue 和 annotation audit 的 JSON Schema；拒绝缺 owner、证据、locator 或非法轴的 claim。
5. 添加单元测试，覆盖身份映射、稳定分批、digest、JSONL 解析和禁止 locator-only 证据。

## 阶段 2：独立盲标

1. 启动三个 `fork_turns: "none"`、模型为 `gpt-5.6-sol` 的标注任务。
2. 每个任务只获得一个 batch manifest、允许的 Alpha25 规范路径和独立 GT 输出根目录。
3. 每篇产出 `expert_claims.jsonl`、`expert_gt.json`、`curve_audit.json`、`issues.json` 和 `annotation_audit.jsonl`。
4. 每完成一篇立即运行该篇 contract/schema/evidence 校验；失败只返工该篇。

## 阶段 3：盲态交叉复核

1. A 复核 B、B 复核 C、C 复核 A，不开放业务 GT、v5 或对比报告。
2. 修复必须追加 annotation audit，禁止静默覆盖。
3. 复核完成后运行全量引用、owner、ID、重复和 CSV digest 检查。

## 阶段 4：封存

1. 对所有盲标产物计算 digest。
2. `seal` 只有在 30/30 完整、Schema/contract/evidence 校验全通过时才生成 `blind_seal.json`。
3. seal 中记录模型、批次、输入 manifest digest、产物 digest 和完成时间。

## 阶段 5：三方比较与裁决

1. seal 后才加载业务 GT 和 final v5。
2. 将 sealed expert GT、业务 GT、v5 转换为同一 claim 语义。
3. 计算五轴、unique claim、core tensile、严格 owner/condition 和宽松语义指标。
4. 逐条裁决差异；若专家 GT 错误，写 amendment 并生成 adjudicated 版，sealed 版保持不变。

## 阶段 6：交付

1. 生成 Markdown、JSON 和逐篇逐轴 CSV 报告。
2. 报告明确区分缺漏、unsupported、wrong owner/axis/origin、value/unit/condition conflict 和 OCR/chart error。
3. 打包业务交付 ZIP，排除 `.env`、缓存和无关运行产物。
4. 最终验证 30/30、证据覆盖率、Schema 通过率、seal digest 和压缩包清单。

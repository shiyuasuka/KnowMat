# KnowMat v11 alpha.6 提示词强化与八篇材料回归验证设计

## 1. 背景与目标

KnowMat 当前通过 LangGraph 串联 PDF OCR、论文路由、材料信息抽取、结果评估、聚合、校正、质量判断和最终 schema 转换。现有抽取提示词与运行时模型仍以旧版 `compositions` 数据结构为主，无法稳定生成 `material-extracor-v11.0.0-alpha.6` 示例包中的 `material_extraction_v11.3.0` 四轴结果。

本次工作的目标是：在保留 KnowMat LangGraph 架构、PaddleOCR API 和现有 LLM API 调用方式的前提下，将 alpha.6 修复后的抽取约束融入 KnowMat 的动态 system prompt 和 user prompt，并同步调整 LangGraph 节点的数据契约，使最终结果与八篇示例的 `final.json` 格式和核心语义一致。

本次回归验证必须从示例 PDF 重新执行 OCR，不复用示例包中的 `ocr.md`。八个 PDF 按 manifest 中的论文标题复制并安全重命名到 `data/raw/`，示例包原件保持不变。

## 2. 范围

### 2.1 包含范围

- 将 alpha.6 Step 3 强制候选合约、证据边界、四轴抽取纪律和 item 粒度规则融入 KnowMat 抽取提示词。
- 根据论文路由动态拼装 base material、application、research paradigm 和 domain overlay。
- 让抽取、评估、重抽、聚合、校正和最终质量节点处理 v11 candidate/final 数据。
- 在 LangGraph 内执行 alpha.6 的成分、工艺、结构和拉伸性能确定性标准化与 schema 校验。
- 输出与示例同构的 `material_extraction_v11.3.0` `final.json`。
- 对八篇论文执行重新 OCR、LLM 抽取、标准化、校验和语义回归对比。
- 提供一条可复现的 KnowMat 启动命令和逐篇/汇总验证报告。

### 2.2 不包含范围

- 不修改 PaddleOCR 服务端模型或 OCR API 协议。
- 不把示例 `final.json` 作为抽取事实输入或 few-shot 答案注入提示词。
- 不追求生成 JSON 与示例逐字节相同；作者字符串、OCR 标点、自然语言简化表述和非关键 ID 可以存在等价差异。
- 不回退或覆盖工作区中与本任务无关的既有修改。
- 不修改 alpha.6 冻结规则以迎合单篇论文。

## 3. 设计原则

1. **OCR 是唯一事实源。** 抽取、评估和修订只能依据本轮 PDF OCR 结果，示例 `final.json` 只用于运行结束后的回归比较。
2. **LLM 负责证据候选，代码负责确定性标准化。** LLM 不生成规则摘要、canonical 单位、规则 ID、ruleset digest 或缺失参数占位。
3. **LangGraph 保持工作流主干。** v11 能力作为 KnowMat 节点和状态契约的一部分接入，不建立脱离 KnowMat 的第二套抽取入口。
4. **四轴与 item 边界优先。** Composition、Processing、Structure、Properties 必须对齐到相同材料、样品、状态和测试方向。
5. **省略优先。** 未报道概念不输出；明确提到但无法确定时才保留显式未知。
6. **证据可追溯。** 每条成分、工艺、结构和性能事实必须带可定位的 `source_evidence`。

## 4. LangGraph 架构

完整流水线调整为：

```text
START
  → parse_pdf
  → detect_sub_field
  → extract_data
  → evaluate_data
       ├─ needs_rerun → extract_data
       └─ accepted    → aggregate_runs
  → validate_and_correct
  → normalize_v11
  → validate_v11
  → assess_final_quality
  → finalize_v11
  → END
```

### 4.1 `parse_pdf`

- 继续使用 KnowMat 当前 PaddleOCR API 路径。
- 本次验证使用 `.env` 中已配置的 `PaddleOCR-VL-1.6`。
- `--force-rerun` 必须绕过现有 OCR Markdown；`--skip-cached-ocr` 必须同时绕过本地 OCR 缓存，确保从 PDF 重新提交 OCR。
- OCR Markdown、OCR JSON 和相关中间产物继续放在 `data/raw/<paper-title>/`。

### 4.2 `detect_sub_field`

- 保留三轴路由：`base_material × application × research_paradigm`。
- domain overlay 扩充为：Machining、Coating、Battery、Additive Manufacturing、Titanium Alloy、High Temperature Alloy、High Entropy Alloy。
- 路由结果同时进入状态和最终 `Paper_Routing`。
- 方向补充文本只影响抽取关注点，不能覆盖 OCR 证据。

### 4.3 `extract_data`

- 使用 v11 candidate Pydantic 数据模型进行结构化输出。
- 生成 `Paper_Metadata`、`Paper_Routing` 和非空 `items`。
- 每个 item 包含 `Composition`、`Processing`、`Structure`、`Properties` 四轴 candidate。
- 保留原始值、原始单位、原文片段、数据来源、置信度和条件绑定。
- 不在本节点生成确定性 canonical 字段或规则元数据。

### 4.4 `evaluate_data`

- 对照同一轮 OCR 文本检查 candidate 的遗漏、幻觉、item 过拆/漏拆、状态串线、工艺顺序和条件绑定。
- 评估反馈写成有界的 prompt update，只允许补充本篇论文的抽取注意点，不能改写 v11 核心合约。
- 最多执行配置的 `max_runs` 次抽取。

### 4.5 `aggregate_runs`

- 不再按旧版 composition 字符串合并。
- 使用 item identity 进行合并：材料/样品、制备或后处理状态、方向/位置以及数据性质。
- 轴内记录使用证据签名去重；发生冲突时优先保留证据更完整、评估置信度更高的记录，并把不可安全裁决的冲突交给校正节点。
- 不允许聚合器把多个样品、处理态或方向合并成一个 item。

### 4.6 `validate_and_correct`

- 只修改 candidate，不直接编辑规范化 final。
- 依据 OCR 文本和评估反馈删除幻觉、恢复遗漏、修正 item 边界和证据绑定。
- 校正结果仍需满足 v11 candidate 合约。

### 4.7 `normalize_v11` 与 `validate_v11`

- 在 KnowMat LangGraph 节点中调用 alpha.6 的冻结规则包。
- 按顺序执行 composition、structure、process 和 tensile normalization。
- 由代码写入 `Rule_Metadata`，包括 schema、skill、规则版本、digest 和源码 commit。
- schema 或确定性校验出现 fatal 时不得生成可晋级 `final.json`。
- review 级问题进入质量报告，但允许输出 `passed_with_review` 结果。

### 4.8 `assess_final_quality` 与 `finalize_v11`

- 质量判断使用 v11 校验结果、证据覆盖率、item 边界风险和评估历史。
- 最终输出根字段固定为 `Paper_Metadata`、`Paper_Routing`、`Rule_Metadata`、`items`。
- `final.json` 只来自通过或带复核通过的规范化结果。

## 5. 动态提示词设计

### 5.1 System prompt

System prompt 按以下顺序构造：

1. alpha.6 Step 3 强制候选合约；
2. 事实边界与证据要求；
3. item 粒度、状态隔离和四轴对齐规则；
4. Composition、Processing、Structure、Properties candidate 字段约束；
5. base material supplement；
6. application supplement；
7. research paradigm supplement；
8. 零个或多个 domain overlay；
9. 本轮评估反馈产生的有界修复说明。

系统模板保留明确的动态占位符，不在 Python 代码中复制大段提示词正文。未知占位符、缺失必填段或未替换占位符应在调用 LLM 前失败。

### 5.2 User prompt

User prompt 包含：

- 已确定的三轴路由及 domain overlay；
- 本轮任务是 evidence-first candidate，而非 final normalization；
- 不得使用论文外知识补写标准成分、工艺参数或性能；
- item 枚举、四轴覆盖和证据完整性自检清单；
- 明确分隔的完整 OCR 文本；
- 只输出结构化工具结果，不输出解释性散文。

### 5.3 Prompt 长度与降级

- 优先保留核心合约和命中方向的 overlay，不加载无关方向文件。
- 论文过长时可以剥离非事实性的 VLM prose，但保留正文、表格、图注和可抽取的图表数字化数据。
- 降级路径必须使用同一 v11 candidate schema，不允许回退到旧 `compositions` schema。
- 任一路径返回空 items、空四轴或无证据的大量记录时触发质量门并重试。

## 6. 数据模型与状态契约

- 新增或替换抽取结构化模型，使字段与 v11 candidate schema 对齐。
- `KnowMatState.latest_extracted_data`、`aggregated_data` 和 `final_data` 均使用明确的 candidate/final 类型阶段，不再混用旧 runtime schema。
- 每次 run 的 candidate 持久化到 paper output 目录，避免将大型 JSON 长期驻留在 LangGraph checkpoint。
- 最终输出文件名使用 `<paper-title>/final.json`，并保留 candidate、normalized、validation、issues、audit 和 run metadata 中间产物。

## 7. 八篇 PDF 准备与运行

### 7.1 文件准备

- 从 `8篇材料抽取模板示例_v11.0.0-alpha.6_20260714/manifest.json` 读取八篇标题。
- 将每个 `paper.pdf` 复制到 `data/raw/`，文件名为经过 KnowMat 安全文件名规则处理的文章标题。
- 若目标文件已存在且哈希相同则复用；若同名但哈希不同则停止并报告冲突，不覆盖。
- 示例目录中的 PDF、OCR 和 final 文件保持不变。

### 7.2 启动命令

使用项目虚拟环境和 `.env` 中已有配置，从 PDF 强制重跑 OCR 与 LangGraph 全流程。最终命令将基于实际实现后的 CLI 参数验证，目标形式为：

```bash
venv/bin/python -m knowmat \
  --input-folder data/raw \
  --output-dir data/output/v11-alpha6-validation \
  --paddleocr-api \
  --force-rerun \
  --skip-cached-ocr \
  --full-pipeline \
  --max-runs 3 \
  --only <八篇论文的安全文件名>
```

如果采用 batch 模式，必须为本次验证使用独立 batch DB，并确保强制重跑语义会重置这八篇任务；否则使用上述非 batch 命令，避免旧状态导致跳过。

## 8. 验证设计

### 8.1 硬性验收

每篇结果必须：

- 通过 `material_extraction_v11.3.0` JSON Schema；
- 根字段和 item 四轴结构与示例一致；
- `Rule_Metadata.ruleset_digest` 与 alpha.6 manifest 一致；
- 至少包含一个 item；
- 所有四轴存在且满足各自 required contract；
- 不包含旧版 `compositions`、`properties_of_composition` 或 legacy composition 字段；
- 不存在 fatal validation issue；
- 关键事实记录具备 `source_evidence`。

### 8.2 语义回归

以示例 `final.json` 为 expected，只在运行完成后比较：

- 论文路由；
- item 数量与 Sample_ID/Role/Data_Nature 边界；
- 成分 observation 的材料状态、组分、原始值和单位；
- 工艺节点、顺序、边和参数归属；
- 结构 observation 的类别、状态、实体和定量特征；
- 性能名称、值、单位、测试条件、来源语义和证据；
- 直接拉伸 UTS/YS/EL 的 canonical 语义；
- evidence trace rate、fatal/review issue 数量和显式字段遗漏。

### 8.3 通过标准

- 八篇全部 schema-valid，fatal issue 为 0。
- 八篇根级路由完全一致。
- 工艺 route exact match、关键 item 边界和直接拉伸语义逐篇报告；存在差异时必须回到 OCR 证据解释。
- 汇总报告不得用一个总分掩盖单篇失败；每篇列出匹配项、遗漏、额外项和证据裁决。
- 无法由新 OCR 支持的示例事实不强行复现，记录为基准与本轮 OCR 的证据差异。

## 9. 测试策略

### 9.1 单元测试

- Prompt 组装顺序、必填占位符和未替换占位符检测。
- 动态路由对七类 domain overlay 的加载。
- v11 candidate Pydantic 模型的有效/无效样例。
- item identity、聚合去重和不跨状态合并。
- evaluation prompt update 不得覆盖核心合约。
- alpha.6 rule digest、normalization 和 schema validation。
- fallback 仍输出 v11 candidate，而不是 legacy schema。

### 9.2 集成测试

- 使用小型 OCR 文本夹具跑完整 LangGraph，不调用真实 OCR。
- 模拟两轮 extraction/evaluation，验证重抽和聚合。
- 验证 fatal 结果不会晋级为 `final.json`。
- 验证 `passed_with_review` 会输出 final 和 review 报告。

### 9.3 真实回归

- 八篇 PDF 重新 PaddleOCR API OCR。
- 使用 `.env` 中的 `gpt-5.5` 运行完整 LangGraph。
- 保存逐篇中间产物、最终结果和对比报告。

## 10. 错误处理与恢复

- OCR 提交、轮询或下载失败：保留任务元数据并按现有重试策略处理，不生成伪造文本。
- LLM 工具调用失败或截断：使用同 schema 重试；不得回退到 legacy 输出。
- candidate 不完整：由质量门触发重抽，达到 `max_runs` 后标记失败或需人工复核。
- normalization fatal：保留 normalized、issues 和 audit，但不写可晋级 final。
- API 限流：沿用 KnowMat key pool、并发控制和 batch 恢复机制。
- 单篇失败不阻止其他论文完成；汇总报告明确列出失败阶段。

## 11. 交付物

- 强化后的动态 extraction system/user prompt 和 routing overlays。
- v11 candidate/final 数据模型及 LangGraph 节点适配。
- alpha.6 规则标准化与校验的 KnowMat 内部集成。
- 八篇按标题命名的 `data/raw` PDF。
- 可复现的 OCR + LLM 启动命令。
- 八篇 `final.json`、中间产物、逐篇验证报告和汇总报告。

# GPT-5.6-sol 独立专家 GT 与三方专业评估设计

## 1. 目标与结论口径

本工作为 30 篇材料科学论文建立一套新的、证据驱动的独立专家 GT，随后将其与业务方 GT 和当前 final v5 做三方比较。新 GT 使用用户指定的 `gpt-5.6-sol`，以 Alpha25 经专业人员校对的提示词和 v11 Schema 作为领域与结构规范，以冻结 OCR、完整折线图 CSV 和原始论文元数据作为事实输入。

新 GT 是后续精度评价的主要参照，但不是不可质疑的绝对真理。盲标结果必须先冻结；解封后若发现独立 GT 自身存在缺漏或事实错误，只能通过有原文证据的显式 amendment 修正，不能静默覆盖。最终报告同时展示原始盲标版和证据裁决版，客观说明三方各自的正确、缺漏、误归属和事实性错误。

本阶段不修改 Alpha25 提示词、不修改 production `final.json` 格式、不重新 OCR，也不重新调用现有抽取流水线。`Historical rematerialized baseline` 不是 GT，不作为本次三方比较的一方。

## 2. 已选择方案与被拒绝方案

### 方案 1：独立盲标后解封比较（已选择）

三个全新上下文的 `gpt-5.6-sol` 标注者各负责 10 篇，只读取允许的事实包和 Alpha25 规范。完成交叉复核、Schema 校验、证据审计和结果封存后，才允许读取业务 GT 与 final v5，并开展三方差异裁决。

优点是最大限度降低已有答案对新 GT 的锚定，同时能保留完整证据链。代价是工作量最大，且需要单独管理盲标版、裁决版和审计记录。

### 方案 2：以业务 GT 为底稿补全

从业务 GT 开始，由 GPT-5.6-sol 补漏和纠错。速度更快，但会继承业务 GT 的粒度、遗漏和标签偏差，不能回答“独立专家本来会抽取什么”。不采用。

### 方案 3：以 final v5 为底稿审核

从当前抽取结果开始逐条验真。最省时间，但新 GT 会与待评对象高度相关，容易把系统性错误写回基准，也无法独立评价召回率。不采用。

## 3. 冻结输入与禁止输入

### 3.1 允许输入

每篇论文的盲标事实包只包含以下内容：

1. 冻结 OCR manifest：`data/raw/.knowmat_ocr_baselines/alpha25-fresh-20260810.json`，baseline ID 必须为 `d3b79e0090ec2e436ceb328c6a08c728eb5c2343d061e4724bb14bcce441c347`，记录数必须为 30，状态必须为 frozen。
2. 源运行中的完整 OCR/图表增强 Markdown：`data/output-alpha25-prompt-v5-final30-20260818/<paper>/txt_parse/*_final_output.md`。当前预期为 30 份；实施前为每份计算 SHA-256 并写入独立输入 manifest。
3. 与上述 Markdown 同目录、能够关联到具体图号的 `figure_*_digitized.csv`。当前预期为 95 份；实施前记录文件名、论文、图号、大小和 SHA-256。
4. 原始论文元数据，包括文件名、论文标题、DOI、PDF SHA-256 和 OCR manifest 中已有的身份信息。PDF 正文不是额外事实源；科学事实仍必须回到冻结 Markdown 或关联 CSV。
5. Alpha25 专业规范：
   - `material-extractor-alpha25-20260804/material-extractor/SKILL.md`
   - `references/03-extract-system-prompt.md`
   - `references/03-extract-user-prompt.md`
   - `references/05-review.md`
   - `references/06-revise.md`
   - `references/07-evaluate.md`
   - `references/schema/material_extraction_v11.schema.json`
   - 与论文路由匹配的 base、application、paradigm 和 domain direction 文件。

允许输入在盲标启动前复制到独立的只读清单目录；标注任务只接收该清单中的路径，不接收任何比较结果、历史分数或缺漏提示。外部网页、模型常识中的标准牌号成分和未出现在事实包中的补充材料均不得作为论文事实。

### 3.2 解封前禁止输入

盲标者和盲态复核者不得读取或搜索：

- 业务 GT：`data/gt/papers-native-ids-with-pdf-ocr-images-20260809`；
- 当前 v5：`data/output-alpha25-prompt-v5-final30-quality-gates-final-v5-20260818`；
- 任何包含业务 GT/v5 对比结论、命中数、F1、缺失值清单或逐篇差异的 report；
- 旧版抽取结果、历史 rematerialized 结果和缓存响应。

主协调者已经接触过部分对比信息，因此不参与盲态科学事实标注，只负责构建无答案的输入清单、机械校验、任务调度和封存。标注者使用 `fork_turns: "none"` 创建，显式指定 `gpt-5.6-sol`，避免继承当前会话。该隔离是“清洁上下文 + 允许路径清单 + 操作审计”的程序性隔离，不宣称为操作系统级强制沙箱。

## 4. 专家 GT 的事实模型

### 4.1 五个评价轴

本次“全量五轴”统一指：

1. Composition；
2. Processing；
3. Structure；
4. Characterization；
5. Properties。

Characterization 在 v11 中属于 Structure 的关联对象，但评价时单独成轴。每个事实必须绑定明确的材料 owner、样品或状态、轴、数值语义、单位、条件、来源类型和原文证据。不同材料、配方、热处理状态、区域、方向或批次不得错误合并；相同材料仅测试条件不同不应机械拆成多个材料 owner。

### 4.2 双层产物

这里的“全量”指 Alpha25 合约下可入库、可由证据定位的唯一材料事实，不把纯叙述背景、无归属修辞或曲线绘图产生的密集插值采样行伪装成独立科学事实。

每篇论文同时生成两种互相可追溯的表示：

- `expert_claims.jsonl`：独立评价使用的扁平事实账本。每行是一条去重后的科学 claim，包含稳定 claim ID、五轴类别、owner、状态/区域、原始名称、规范语义、原始值、数值结构、单位、条件、来源类型、证据定位和复制的证据文本。
- `expert_gt.json`：按 `material_extraction_v11.schema.json` 组织的 v11 兼容投影，便于与现有 `final.json` 做结构和语义比较。

扁平账本是事实裁决的主表示，v11 JSON 是结构兼容投影。这样可以避免把 production materializer 的行为直接当作真值，同时仍能复用现有 Schema 检查和比较工具。两者必须通过 claim ID/来源证据互相映射；投影失败的事实不能丢失，须保留在账本并产生 review issue。

### 4.3 每条 claim 的最低证据要求

每条 claim 至少包含：

- `claim_id`：论文内稳定且唯一；
- `axis`：五轴之一；
- `owner`：材料、样品、状态及必要的区域/方向；
- `semantic_key`：性质、工艺、组织或表征语义；
- `value_raw`、结构化数值语义和 `unit_raw`；无数值事实保留原文类别表达；
- `condition`：温度、时间、速率、方向、环境、阶段等原文明示条件；
- `origin`：作者实验、作者计算、文献实验、文献计算、图表数字化或未知；
- `evidence_source`：Markdown 或 CSV；
- `evidence_locator`：Markdown 行号/表号/图号，或 CSV 文件与行范围；
- `source_evidence`：复制的原文句子、表格行或图注；CSV 事实还要记录文件 SHA-256 与列名；
- `confidence` 与 `review_status`。

只有定位符而没有复制证据的 claim 不可进入 sealed GT。范围、不等式、标准差、近似值和 Balance 必须保留原始语义，不能压成等式或单点。作者实验、仿真、机器学习、派生值和文献引用必须隔离。

## 5. 折线图与上下文控制

Markdown 中的 `series:` 摘要只作为图表索引，不能单独充当数值证据。标注者必须打开对应完整 CSV，核对图号、横纵轴、单位、系列标签、样品 owner、测试条件和校准状态。

为避免上下文爆炸和统计权重失真，密集曲线的像素/插值采样行不逐行变成独立 Property claim。处理方式为：

1. 完整原始 CSV 保持不变，记录 digest、列定义和有效行范围；
2. 一条可解释曲线以一个 `curve_series` 审计对象保存完整追溯信息；
3. 只有图中可明确归属的离散 marker、正文/图注明确点名的点、物理意义明确的峰值/阈值，才进入标量 Property claim；
4. F1 中不按 CSV 采样密度重复计数同一条曲线；
5. 整条系列由 `curve_audit.json` 和 claim 账本引用 CSV；v11 投影只写 Schema 能合法表达、且通过证据门的标量事实，不新增自定义曲线字段。无法无损投影的曲线级对象保留在账本并标记 `schema_projection_only`。

以下情况必须隔离，不能进入可信 Properties：轴或单位无法确定、系列 owner 无法唯一绑定、面板映射不明、CSV 校准失败、明显越界/跳变、拉伸应力曲线出现无法由原文解释的显著负值、重复图层或曲线来源冲突。隔离记录保留原 CSV、异常原因、影响范围和 review 标记，不删除证据。

## 6. 盲标、复核与封存流程

### 6.1 预检

协调者生成 `blind_input_manifest.json`，验证 30 篇 Markdown、全部关联 CSV、论文身份和 SHA-256。任何缺失、重复 paper key、manifest 漂移或图表无法归属都会阻止启动对应论文，而不是用 v5/业务 GT 补答案。

### 6.2 三批独立标注

按规范化 paper key 排序后稳定切分为三批，每批 10 篇。三个 `gpt-5.6-sol` 清洁上下文标注者各处理一批。每篇按以下顺序完成：元数据与 owner inventory、全文表格清单、Composition、Processing、Structure、Characterization、Properties、关联 CSV、跨轴 owner/condition 校验、跨 chunk/跨表去重。

标注者不得只提取“代表值”或只围绕核心拉伸。所有源支持的唯一事实都进入账本；同一事实因摘要、正文、表格和图注重复出现时合并为一条 claim，并保留多个 evidence locator。

### 6.3 盲态交叉复核

三批完成后轮换复核：A 复核 B，B 复核 C，C 复核 A。复核者仍只能读取允许事实包、被复核的独立 GT 和审计文件。复核重点包括：

- 全表覆盖和系列覆盖；
- owner、状态、阶段、区域与条件绑定；
- Composition/Processing/Structure/Properties 串轴；
- Characterization 与制备/测试设备串槽；
- Target/Reference 和实验/计算/文献来源；
- 范围、不等式、标准差、单位和温度语义；
- 图表校准、异常曲线隔离和跨来源去重。

复核修改必须写入 `annotation_audit.jsonl`，包括 before、after、原因、证据和 reviewer。不得静默改写。

### 6.4 机械验证与盲态封存

解封前必须通过：

- 30/30 论文产物齐全；
- `expert_gt.json` 100% 通过 v11 JSON Schema；
- `expert_claims.jsonl` 100% 通过专用 claim contract；
- 每条 claim 有非空 owner、来源、locator 和复制证据；
- CSV claim 的文件 digest 与 blind manifest 一致；
- claim ID 唯一，跨证据重复已合并；
- 无悬空 characterization ID、stage ID 或 owner；
- 所有 unresolved 和 quarantine 均有 issue/audit 记录。

随后生成 `blind_seal.json`，记录全部盲标文件的 SHA-256、模型、批次、标注/复核时间和输入 manifest digest。seal 生成后盲标版只读，不再覆盖。

## 7. 解封后的三方比较与专业裁决

seal 完成后才读取：

1. sealed GPT-5.6-sol 独立专家 GT；
2. 用户提供的业务 GT：`data/gt/papers-native-ids-with-pdf-ocr-images-20260809`；
3. 当前 final v5：`data/output-alpha25-prompt-v5-final30-quality-gates-final-v5-20260818`。

比较先将三方转换为同一 claim 语义：paper、owner、轴、semantic key、数值/单位、条件、origin 和证据。匹配不依赖 Item_ID 或字段名完全一致；同时禁止只按数值近似而忽略 owner、状态和测试条件。

以 sealed expert GT 为主要评价基准，分别给出业务 GT 和 v5 的 precision、recall、F1；另给出不预设真值的双向覆盖率和逐条证据裁决，防止把专家 GT 的潜在遗漏误算成另一方错误。指标至少覆盖：

- 五轴逐轴及宏/微平均；
- unique claim 与 raw claim；
- unique core tensile；
- owner/状态/条件严格匹配与宽松语义匹配；
- 每篇论文的 TP、缺漏、误提取和争议数量。

每个三方差异使用以下问题码之一，并附 OCR/CSV 证据与专业理由：

- `business_gt_missing`；
- `gpt_gt_missing`；
- `v5_missing`；
- `unsupported_claim`；
- `wrong_owner`；
- `wrong_axis`；
- `wrong_origin`；
- `value_conflict`；
- `unit_conflict`；
- `condition_conflict`；
- `duplicate_claim`；
- `likely_ocr_error`；
- `likely_chart_error`；
- `schema_projection_only`；
- `unresolved_requires_human_review`。

若解封后确认 sealed GPT GT 有错误，新增 amendment，并生成 `adjudicated_expert_gt`。原始 sealed 文件和 digest 保持不变；最终主指标同时标明使用的是 sealed 版还是 adjudicated 版。业务 GT 或 v5 的某条事实只要比 GPT GT 更符合原始证据，就必须判其正确并修订专家 GT，不能因“GPT 是主基准”而强行维持原判。

## 8. 目录与交付物

独立 GT 根目录：

`data/gt/gpt56sol-independent-expert-20260818/`

目录结构固定为：

```text
blind_input_manifest.json
papers/<paper_key>/expert_claims.jsonl
papers/<paper_key>/expert_gt.json
papers/<paper_key>/curve_audit.json
papers/<paper_key>/issues.json
papers/<paper_key>/annotation_audit.jsonl
blind_seal.json
adjudicated/<paper_key>/expert_claims.jsonl
adjudicated/<paper_key>/expert_gt.json
adjudicated/amendments.jsonl
corpus_summary.json
```

三方报告：

- `reports/gpt56sol_independent_gt_vs_business_vs_v5_20260818.md`；
- `reports/gpt56sol_independent_gt_vs_business_vs_v5_20260818.json`；
- 逐篇逐轴差异表 CSV；
- 面向业务方的压缩包，包含报告、指标表、可核查证据摘录、sealed/adjudicated GT 和审计说明，不包含 `.env`、模型缓存或无关运行产物。

## 9. 验收标准

只有同时满足以下条件才算完成：

1. 30/30 论文完成独立盲标和轮换复核；
2. 五轴均进行全量扫描，不以业务 GT 或 v5 的已有字段作为抽取范围；
3. 盲标前后输入 digest 一致，blind seal 完整；
4. v11 投影 Schema 通过率 100%；
5. 进入 GT 的 claim 证据覆盖率 100%，无 locator-only 证据；
6. 图表 CSV 全部被检查，接受、忽略或隔离均有原因；
7. 密集曲线不按像素采样点虚增事实计数；
8. 三方报告同时给出量化指标和专业逐条裁决，明确谁更准确、谁有缺漏、谁有事实错误；
9. GPT GT 自身的解封后修订全部可追溯，sealed 原版不被覆盖；
10. Alpha25 提示词、现有 production `final.json` 格式、业务 GT 和 final v5 原文件均未被修改。

## 10. 失败处理与边界

- OCR 缺页、表格错位、图轴不可识别或 SI 缺失时，记录 `unresolved_requires_human_review`，不依靠模型常识补值。
- 单篇输出不通过 Schema 或证据检查时，只返工该篇，最多两轮；仍不能解决则保留失败状态，不用另一方答案填充。
- 任一标注者误读禁止目录时，其受影响批次作废并由新的清洁上下文重新标注。
- 模型调用失败或上下文过大时按论文内的表格/图表单元分段处理，但最终必须执行全篇 owner inventory、跨段去重和五轴一致性复核。
- 本设计只建立与评价 GT，不借此修改抽取提示词或生产规则；后续是否基于结论优化 v5，另行设计和审批。

# Alpha25 双高精度/召回收敛设计

日期：2026-08-19  
状态：已获用户批准，待实现  
范围：GLM Alpha25 后处理、owner/condition 归属、tensile 质量和独立专家 GT 评估

## 1. 背景与基线

30 篇正式 v25 输出相对 GPT-5.6-sol 独立专家账本的当前主要指标如下：

| 指标 | v25 |
|---|---:|
| Overall loose precision / recall / F1 | 0.227951 / 0.488846 / 0.310919 |
| Overall strict precision / recall / F1 | 0.108699 / 0.233107 / 0.148262 |
| Core tensile loose precision / recall / F1 | 0.425134 / 0.716216 / 0.533557 |
| Core tensile strict precision / recall / F1 | 0.224599 / 0.378378 / 0.281879 |

相对业务 GT，v25 的 Composition loose F1 更高，但总体 loose F1 与核心 tensile 仍明显落后。残差检查还发现两类问题混在现有评分中：

1. 生产输出问题：跨 item 投影、owner/state 粒度不足、已有 tensile 条件不完整、结构实体占位 canonical name。
2. 评估表示问题：`final.json` 合法的 `Value_Raw`（近似值、误差、科学计数法）被评估器当成 `unknown`，结构实体容器又被额外投影成独立 presence claim。

因此本轮必须把“改善生产事实质量”和“修复评估失真”分开实现、分开报告，不能用评估器改动冒充生产质量提升。

## 2. 目标与不可变约束

### 2.1 目标

- 同时提升 overall loose precision、recall、F1。
- 同时提升 core tensile loose precision、recall、F1。
- 减少 strict owner/condition 冲突，并提升 strict F1。
- 保持 Composition 的现有优势，不以牺牲 Composition recall 换整体分数。
- 不增加 LLM 请求，不影响 OCR/LLM 主流程吞吐。

### 2.2 不可变约束

- 不修改专业人员校对过的抽取提示词及其 prompt hash。
- 不硬编码 GLM、论文标题、样品名或 GT 中的具体答案。
- `final.json` schema 与既有字段格式保持不变。
- GPT 专家 GT 仅用于离线评估；生产规则必须 GT-blind。
- 删除、迁移、隔离和合并的完整记录进入现有 `issues.json/.md`，不新增 `quality_audit.json`。
- 定性 tensile 不伪装为数值 scalar；继续隔离并保留原文和审计原因。
- 多 owner 明确并列、不同状态、不同条件或不同证据的真实事实不得误合并。

## 3. 选定方案

采用“双通道证据收敛”：LLM/task cache 继续作为高召回候选层；确定性 materialization 只做有来源证明的表示修复、归属收敛和安全去重。无法唯一判断的事实保留原状并标记 review，不通过宽泛删除换 precision。

未采用的方案：

- Precision-first 大面积过滤：能迅速减少输出，但会损失真实 Structure/Properties，违背双高目标。
- 只修 canonical/alias：能找回部分匹配，却无法解决 owner/condition 与跨 item precision 问题。
- 宽泛 ownerless 去重：只读模拟中 overall loose recall 从 0.4888 降至约 0.4843，因此禁止进入生产。

## 4. 架构与数据流

```text
冻结 task responses
  -> 现有 evidence gate
  -> 候选 facts（高召回）
  -> 表示层规范化
  -> evidence-local owner/state resolver
  -> condition compatibility augmentation
  -> source-assertion scoped deduplication
  -> 现有 quality quarantine + issues audit
  -> 不变 schema 的 final.json
  -> 修正后的独立评估器
  -> GPT 专家 GT / 业务 GT / v25 / 新版本四方报告
```

生产规则只读取候选 fact、inventory、source evidence 和完整 OCR/图表上下文。评估器读取最终文档并进行原子 claim 投影；两者不得共享 GT 内容或 benchmark 特例。

## 5. 组件设计

### 5.1 Properties 数值表示解析（评估层）

在 `independent_gt_comparison._value()` 中，仅当原记录没有结构化 `value_kind`/number 时，解析 v11 `Value_Raw`：

- 普通 scalar 与近似 scalar，如 `~1148`。
- 带误差 scalar，如 `595 ± 14`。
- 科学计数法，如 `2.18 × 10^6`、LaTeX `\times 10^{6}`。
- 明确 inequality 和 range。

已有结构化数值不得被二次解析或覆盖。含多个不同测量值、比较句或无法唯一确定量纲的文本保持原样，避免把一句多值描述错误压成 scalar。

该改动属于评估表示修复，不改变 `final.json`。报告必须同时给出 legacy evaluator 与 corrected evaluator 指标。

### 5.2 Structure 实体语义

- `canonical_name` 为 `unknown_entity`、`unknown`、`not_reported` 等占位值而 `name_raw` 有内容时，生产输出保留 raw identity，并将无意义 canonical 值置空，不制造 `unknown_entity_presence`。
- 评估投影中，带 nested features 的 entity 是这些 features 的容器，不再额外计为一个独立 presence claim；nested features 仍全部投影。
- 没有 features 的实体只有在证据明确断言 presence/absence 时才作为 presence claim；仅表头、区域名或从高密度/低孔隙等结果反推的实体进入 issues 审计。
- 不按固定实体词表删除 phase、carbide、precipitate 等领域事实。

### 5.3 Owner/state 归属收敛

跨 item 候选先按 axis、semantic、value、unit、condition 和 source assertion block 形成事实组。只有满足以下条件之一时才合并：

1. 证据块只明确点名一个候选 owner，其他 owner 是该 owner 的 base/generic 投影；或
2. 同一 state family 中，qualified state 有明确状态证据而 base owner 没有独立断言；或
3. 完整 YS/UTS/EL 三项束、值/单位/条件全部一致，并满足现有唯一 coded-sample 与 lineage 约束。

若证据点名多个 owner、存在并列样品、不同状态/条件、引用与本研究混合，保持多条事实。survivor 合并所有 evidence，removed fact 的完整 payload、before/after owner、rule 和 fingerprint 写入 `cross_item_duplicate_merged`。

为避免只读模拟中观察到的 recall 回退，不新增“忽略 owner 后相同即合并”的规则。

### 5.4 Tensile 条件补全

扩展现有 `PropertyContextIndex`，区分：

- `recovered`：原条件为空，恢复唯一协议。
- `augmented`：原条件已有局部信息，只补充同一测试事件中不冲突的标准、速率、方向、设备或试样信息。
- `existing`：已有信息完整或没有安全增量。
- `ambiguous/reference`：多个冲突协议或引用数据，不修改。

兼容性按规范化 discriminator 判断：

- `RT`、`room temperature`、`ambient temperature` 视为同一温度。
- 摄氏度与 Kelvin 只做已报告字面量的等价规范化，不推断未报告温度。
- 已有温度、速率、方向或标准与候选不一致时禁止 augmentation。
- 结果行中的材料处理温度不得当成测试温度。
- 文献引用和 citation-bearing comparison table 不继承当前论文测试协议。

补全只追加来源原文，不覆盖现有条件；审计码为 `property_test_context_augmented`，记录 before/after、候选、拒绝原因和来源行。

### 5.5 Tensile canonical aliases

在共享、模型无关的 canonical 层补齐来源常见别名，例如 `TE`、`EAB`、`modulus of elasticity`；只映射名称，不修改 value、unit、owner 或 condition。核心 tensile 仍限定 YS、UTS、elongation，relative ratio/retention 不并入绝对值统计。

### 5.6 审计与输出

- `final.json` 只包含最终正式事实，schema 不变。
- 所有隔离、迁移、补全、合并继续进入现有 `issues.json/.md`。
- issues 中不得只写计数；涉及删除/合并时必须保留完整原记录。
- rematerialization 回测也必须产出 issues 文件，避免正式流水线有审计而离线结果缺失。

## 6. 测试策略

### 6.1 单元测试

- 解析普通、近似、±、科学计数法、inequality、range。
- 已结构化 value 不被覆盖；多值比较文本不被压成 scalar。
- entity container 不产生额外 presence claim，nested features 保留。
- 占位 canonical name 回退到 raw identity。
- 单 owner/base-state 合并成功并完整审计。
- 并列 owner、等值但不同样品、引用 owner、不同 condition 不合并。
- partial tensile condition 只在唯一兼容协议下 augmentation。
- RT/room/ambient 兼容；温度、速率、方向冲突保持不变并 review。
- qualitative tensile 保持隔离。

### 6.2 回归测试

- 运行 Alpha25 相关完整测试集；不得减少既有覆盖。
- 对 30 篇 405 个冻结 task cache 全量重物化。
- 校验 30/30 promotable、0 fatal、0 invalid cache、0 failure。
- 对新旧输出做 JSON schema 等价检查和 prompt hash 检查。
- 对每个审计码核对数量及至少一个完整 payload。

### 6.3 评估

同时输出：

1. legacy evaluator 指标，保证历史可比性；
2. corrected evaluator 指标，修复 Value_Raw 和 container projection 失真；
3. GPT 专家 GT 对比；
4. 业务 GT 对比；
5. 每篇论文、每个 axis 的 P/R/F1 delta；
6. core tensile loose/strict 及 owner/condition residual。

## 7. 验收门槛

相对当前 v25，在同一 corrected evaluator 下：

- Overall loose precision、recall、F1 均不得下降；F1 必须实质提升。
- Core tensile loose precision、recall、F1 均不得下降；F1 必须实质提升。
- Overall strict F1 与 core tensile strict F1 均不得下降。
- owner/condition residual 总数必须下降。
- Composition loose precision、recall、F1 均不得实质下降（统计舍入容差 0.001）。
- 30 篇 promotable/fatal/invalid/failure 维持 30/0/0/0。
- prompt 文件和 prompt hash 不变，`final.json` schema 不变。
- 不新增 LLM/API 调用；确定性重物化耗时相对 v25 增幅不超过 10%。

只读模拟不是验收结果，但证明选定方向具备双高潜力：表示修复加 Structure container 去重时，v25 overall loose P/R/F1 约为 0.2479/0.5073/0.3331，core tensile 约为 0.4572/0.7703/0.5738。正式结论必须来自实现后的全量回测。

## 8. 失败处理与回滚边界

- 任一规则导致 overall/core tensile recall 下降超过 0.001，单独关闭该规则并保留其他通过项。
- 条件 augmentation 出现任何已知冲突样例，默认保持原条件并产生 review，不猜测正确协议。
- owner 合并无法从 source/inventory 唯一证明时不合并。
- corrected evaluator 若改变已有结构化业务 GT value，视为实现缺陷，必须修复后重跑。
- 回滚只针对本轮新增规则，不重置或覆盖用户工作树中的其他修改。

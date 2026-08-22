# Alpha25 表格坐标与方向性精度门控设计

## 目标

在不改变业务人员校对过的主提示词和 `final.json` 顶层 schema 的前提下，压制 GLM 抽取中最主要的过度投影：表格列标签被当成独立样品、状态行没有绑定到已有材料、以及无方向正文平均值污染方向性 tensile 事实。目标优先级为 precision > recall；无法唯一证明归属时隔离，不猜测。

## 方案

### 1. 表格列身份门控

在 materialize 阶段使用 fact 的完整 Markdown 表格证据识别列标签。`#N`、`Point N` 等标签只有在同一表头中以连续列集合出现，且证据没有把它们声明为独立材料/样品时，才认定为“列坐标”而非 material owner。列坐标不会进入 `IdentityIndex` 的 primary anchors；事实保留其原始 evidence，并以现有 property 字段承载状态/细节，不改变公共输出格式。

若同一完整表格存在唯一明确状态（例如 `After HIP1`），数值事实绑定到已有材料状态项。若状态不存在或多个候选状态无法消歧，则不创建列样品，也不自动选择状态；事实进入审计隔离，写短问题码 `table_column_owner_ambiguous`。

只有源证据明确把 `#N`/`Point N` 当作独立样品并提供样品语义时，才保留为 material owner，避免全局删除误伤真实样品。

### 2. 方向性 tensile 平均值门控

对同一 source block 的数值 core tensile 事实，若证据同时出现 horizontal/vertical（或 X/Z 等）独立坐标，而当前事实没有唯一方向坐标，则将无方向平均值从核心 `Properties` 隔离并写 `tensile_average_without_orientation`。若没有方向性兄弟、或事实本身有唯一方向/表格单元坐标，则保持现有行为。

### 3. 审计与错误处理

隔离不等于丢弃：完整 `fact.model_dump()`、source evidence、候选 owner/state、命中规则和建议动作写入现有 issues/audit 流程。迁移记录使用现有 `MaterializeIssue`，最终 `quality_audit.json` 由既有打包流程落盘。任何门控函数在证据不完整、解析失败或候选不唯一时 fail closed，保留原始事实供 review，不执行跨 owner 广播。

## 数据流

1. candidate facts/anchors 进入 `materialize_candidate`。
2. 在 `IdentityIndex` 建立前识别并标记表格列身份，阻止列标签成为 primary anchor；保留可审计的列标签信息。
3. 建立索引并执行已有 owner/state recovery。
4. 执行表格列状态绑定；唯一状态则迁移，歧义则隔离。
5. 执行已有 tensile precision / cross-item duplicate / qualitative projection gates。
6. 产出原有 `final.json`，issues/audit 增加短问题码与完整记录。

## 测试策略

- 单元测试：连续 `#1..#5` 表头不生成 5 个 item；唯一 `After HIP1` 绑定到 `MAR-M247 [After HIP1]`；真实独立 `#1 sample` 不被误杀；多状态歧义隔离并保留完整 fact。
- 单元测试：方向性表格存在时，无方向 tensile 平均值隔离；单方向/无方向表格保持事实。
- 回归测试：现有 alpha25 materialize/promotion 测试全量通过。
- 离线回测：复用 `data/output-alpha25-prompt-v5-final30-20260818` 缓存重物化，再运行独立 GT 对比，重点观察 paper_008 的 item 数、结构/性质 precision 和 core tensile precision。

## 非目标

- 不修改主提示词或 provider/model 特判。
- 不改变 `final.json` 顶层字段和既有属性 schema。
- 不使用业务 GT 或 GPT 专家 GT 参与运行时决策。
- 不对无法唯一证明的事实做“最可能”猜测。

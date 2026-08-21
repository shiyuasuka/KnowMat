# Alpha25 `respectively`/condition-coordinate pilot

日期：2026-08-21  
版本：commit `9b4f97f1`  
模式：仅使用已有 Alpha25 task cache 离线重物化；未调用 GLM、OCR 或 VLM。

## 结果

| 项目 | 结果 |
|---|---:|
| 回测论文 | 5 |
| 重物化失败 | 0 |
| fatal | 0 |
| `final.json` 格式回归 | 0 |
| 新增 `promotion_condition_label_bound` | 2（paper_029） |
| 新增 `promotion_condition_owner_reassigned` | 0（重复状态别名，安全保留原 owner） |
| 新增 `promotion_respectively_mapping_ambiguous_quarantined` | 2（paper_029） |
| 其他 4 篇新增隔离 | 0 |

## 具体变化

paper_029 中的同一段原文是：

```text
The introduction of a 300 s delay led to an approximately 4% increase in
hardness, with values rising from 334 HV to 346 HV
```

旧结果把 `334` 和 `346` 都挂在 `Ti_{64}` 且没有测试条件。新结果保留两条数值，但把源文字中已有的 `0 s delay`、`300 s delay` 写入正式 `Test_Condition`；由于缓存 inventory 同时产生了多个等价的 0 s/300 s owner 别名，未强行重绑定 owner。另一处同一指标的 `1.10/0.96 mm respectively` 没有任何 surviving 坐标，两个候选被隔离并完整写入 issues 审计。

## 结论

本轮没有改提示词，也没有把条件从邻近 chunk 推断出来。它直接压制“同一指标多值、条件丢失”的过度投影；对已有 owner/condition 坐标的正常事实不做全局收紧。下一轮若要进一步提升召回，应先清理 inventory 的等价状态别名，使唯一 source condition 可以安全重绑定，而不是放宽 `respectively` gate。

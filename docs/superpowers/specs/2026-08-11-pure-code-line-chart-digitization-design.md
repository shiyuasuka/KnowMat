# 纯代码折线图逐点数字化设计

日期：2026-08-11  
目标：在没有 VLM/API Key 的条件下，让 KnowMat 的折线图逐点 CSV 尽量接近 `曲线图带人工标注/` 中的人工标注结果。

## 目标与非目标

### 目标

- 折线逐点数值由纯代码生成，VLM 不参与点坐标生成；
- 优先利用 PDF 中的矢量路径，避免黑白线稿栅格化后无法区分曲线的问题；
- 支持线性、对数和类别 X/Y 轴，至少覆盖当前人工样本中的常见形式；
- 输出 long-format CSV，同时保留每条序列的 `kind`、像素点数、坐标标定方式和失败原因；
- 对趋势线、标记点、上下边界、均值/离散范围分别建模；
- 对无法可靠分离或标定的输入返回结构化失败，不生成伪造的均匀点。

### 非目标

- 不在本次改造中让 VLM 读取曲线数值；
- 不承诺从任意网页截图中完美恢复互相完全遮挡的黑色曲线；
- 不改变现有 `line_summary` 摘要输出的兼容格式；
- 不把柱状图、类别点图和频率分布强行转换为连续折线。

## 数据流与模块边界

```text
PDF / image
   │
   ├─ PDF 矢量路径可读 ──> vector_chart_digitizer
   │                         ├─ plot box / axis text
   │                         ├─ stroke paths / marker paths
   │                         └─ pure-code axis calibration
   │
   └─ 无矢量或矢量不足 ──> grayscale_chart_digitizer (fallback)
                              ├─ plot mask
                              ├─ axis/grid/text removal
                              └─ multi-track path extraction
                                      │
                                      v
                             line_multi result + long CSV
```

`chart_digitizer.py` 负责路由和兼容格式；新模块只负责几何恢复和结构化结果，不依赖 VLM、网络或外部 OCR 服务。

## 矢量 PDF 抽取

使用 PyMuPDF `page.get_drawings()` 和 `page.get_text("words")`：

1. 识别绘图区：寻找包含长水平/垂直边界线的最大矩形，并排除页面边缘装饰框；
2. 识别轴/网格：长线、细线、重复等间距的水平/垂直线视为结构，不进入曲线轨迹；
3. 识别趋势路径：绘图区内的 `l`/`c` stroke 路径，按线宽、跨度、虚线样式和连续性保留；Bezier 路径按曲率自适应采样；
4. 识别标记点：绘图区内的小型 filled/stroked 路径（圆、方、三角、菱形），以几何中心作为标记点；
5. 对 `dashes` 非空的 stroke 保留 `kind=trend_dashed`，不与实线合并；
6. 通过图例区域的路径顺序/线型/标记几何做标签匹配，无法可靠匹配时使用稳定的 `series_N`，并记录 `label_confidence`。

## 纯代码坐标轴标定

从 `get_text("words")` 收集靠近绘图区边界的数字刻度和类别标签：

- 数字刻度：拟合像素位置到值的两种模型：`value = a * pixel + b` 与 `log(value) = a * pixel + b`；以残差和刻度间距一致性选择 `linear` 或 `log10`；
- 类别刻度：保留离散标签及其像素中心，输出 `scale=category`；
- 双 Y 轴/上下分区：按左右边界和绘图区子区域分别建立 calibration；
- 标定结果带 `fit_residual`、参考刻度数和 `confidence`；参考不足或模型竞争接近时返回 `axis_calibration_uncertain`，不生成真实数值；
- PDF 坐标系的 Y 轴向下，映射到数据坐标时统一反向处理。

## 栅格兜底

对 PNG/JPG 或没有有效矢量路径的 PDF：

- 用最大闭合矩形/长边线定位绘图区；
- 用形态学开运算去除长水平/垂直网格线和坐标框；
- 用文字区域/边缘密度抑制刻度与图例；
- 对剩余暗墨迹做列候选提取，再用多轨迹动态规划跟踪；
- 以线宽、虚线间隔、标记形状和轨迹连续性分配 `kind`；
- 轨迹覆盖率、断裂率或相互交叉异常时降级并返回失败原因。

## 输出契约

新增内部结果结构：

```json
{
  "type": "line_multi",
  "method": "pdf_vector|grayscale_raster",
  "x_axis": {"label": "", "scale": "linear", "fit_residual": 0.0},
  "y_axes": [{"side": "left", "label": "", "scale": "linear"}],
  "series": [
    {
      "label": "series_1",
      "kind": "trend|marker|boundary|average|spread",
      "points": [[0.0, 0.0]],
      "n_points": 1,
      "label_confidence": 0.0,
      "trace_confidence": 0.0
    }
  ],
  "failure_reason": null
}
```

CSV 使用 `series,label,kind,x,y` 长格式；点按 X 升序输出。原有 `format_digitized_block()` 继续接受现有 `csv` 字段，以保持下游兼容。

## 验证计划

人工 CSV 先按 X 排序，分开评估：

1. 趋势线：X 对齐后的 MAE/RMSE、起终点误差、极值召回、曲线覆盖率；
2. 标记点：点召回、最近邻 X/Y 误差；
3. 系列识别：系列数、`kind` 和标签的 precision/recall；
4. 失败分类：矢量不可读、绘图区失败、轴标定不确定、曲线重叠、类别轴不支持。

首批回归：`Figure_3.2.1.1`、`Figure_3.5.1.2`。复杂回归：`Figure_3.2.1.10`、`Figure_3.3.1.3`、`Figure_3.5.1.1`；另用 `Figure_3.3.1.1` 验证栅格兜底。

## 风险与降级

- PDF path stream 可能把多个语义曲线合在一个 drawing 中：按子路径切分，切分不确定时保留轨迹但降低置信度；
- 图例和正文也可能包含小路径：必须限制在绘图区及图例候选框内；
- 完全重叠的曲线无法仅靠几何恢复：返回 `overlap_unresolved`，不复制同一条曲线充数；
- 文本刻度不足时不调用 VLM 兜底生成点，保留像素轨迹和失败原因供人工复核。


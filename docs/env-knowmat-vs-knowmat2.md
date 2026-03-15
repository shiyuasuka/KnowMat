# knowmat 与 knowmat2 环境对比（OCR 相关）

## 对比结论

| 项目 | knowmat（正常） | knowmat2（OCR 异常） |
|------|-----------------|----------------------|
| **paddlepaddle-gpu** | 有 3.3.0 (pypi) | **无**（仅 paddlepaddle 3.3.0） |
| paddleocr | 3.4.0 | 3.4.0 |
| paddlepaddle | 3.3.0 | 3.3.0 |
| paddlex | 3.4.2 | 3.4.2 |
| beautifulsoup4 | 4.12.3 (pypi) | 4.14.3 (conda) |
| **cssselect** | 1.4.0 (pypi) | **无** |
| **einops** | 0.8.2 (pypi) | **无** |
| **lxml** | 6.0.2 (pypi) | **无** |
| **openpyxl** | 3.1.5 (pypi) | **无** |
| **premailer** | 3.10.0 (pypi) | **无** |

## 可能原因

1. **未安装 paddlepaddle-gpu**  
   在 knowmat2 中只装了 CPU 版 `paddlepaddle`。若本机用 GPU 跑 PaddleOCR-VL，缺少 `paddlepaddle-gpu` 可能导致初始化失败或报错。
2. **缺少 PaddleOCR/PaddleX 的传递依赖**  
   `lxml`、`einops`、`cssselect`、`openpyxl`、`premailer` 等可能是 paddleocr/paddlex 的依赖，在 knowmat 里被一起装上了，knowmat2 若未装会在 import 或运行时报错。

## 修复步骤（在 knowmat2 中执行）

在 **knowmat2** 环境中依次执行：

```bash
conda activate knowmat2
```

1. **若使用 GPU**，安装 GPU 版 Paddle（与 knowmat 一致）：

   ```bash
   pip install paddlepaddle-gpu==3.3.0
   ```

   若需指定 CUDA 版本，请参考 [PaddlePaddle 安装说明](https://www.paddlepaddle.org.cn/install/quick)。

2. **补装可能缺失的依赖**（与 knowmat 对齐）：

   ```bash
   pip install lxml cssselect einops openpyxl premailer
   ```

3. **（可选）用 doc-parser 装齐 PaddleOCR 文档解析依赖**：

   ```bash
   pip install "paddleocr[doc-parser]"
   ```

4. 验证 OCR 是否可用：

   ```bash
   python -c "from paddleocr import PaddleOCRVL; print('PaddleOCRVL OK')"
   python -c "from paddleocr import PaddleOCR; e = PaddleOCR(lang='en'); print('PaddleOCR OK')"
   ```

若仍有报错，把完整报错信息贴出来即可继续排查。

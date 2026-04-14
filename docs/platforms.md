# 多平台与硬件适配说明

KnowMat 支持 **Windows**、**Linux**、**macOS**。**基础环境与 GPU 已分开配置**：默认仅装 CPU 版 Paddle，需 GPU 时再单独安装。

---

## 1. 基础环境 vs GPU（分开配置）

| 层级 | 内容 | 适用 |
|------|------|------|
| **基础（KnowMat）** | `environment.yml` / `requirements.txt`：CPU 版 `paddlepaddle`、`paddleocr[all]` 等 | 所有平台，`conda env create -f environment.yml` 即可 |
| **GPU 可选** | `requirements-gpu.txt`：`paddlepaddle-gpu` (cu129) + cuDNN | 仅 Windows/Linux + NVIDIA 显卡 |

这样 **Mac / 无 GPU 机器** 直接按 yml 或 requirements.txt 装，不会碰 GPU 包；**有 GPU** 的再用 `pip install -r requirements-gpu.txt -i ...` 叠加。

---

## 2. 平台配置参考

| 平台 | 推荐方式 | Paddle 默认 | 说明 |
|------|----------|-------------|------|
| **Windows** | 手动 Conda | GPU (cu129) | 需 NVIDIA 显卡 + CUDA；CPU 模式用 `requirements-cpu.txt` |
| **Linux** | 手动 Conda | GPU (cu129) | 有 NVIDIA 显卡时用 GPU；无 GPU 用 `requirements-cpu.txt` |
| **macOS (Intel / Apple Silicon)** | pip venv | **CPU** | 无 NVIDIA GPU，使用 `requirements.txt` |

---

## 3. Windows + NVIDIA GPU（含 4060、CUDA 12.7）

- **当前配置**：使用 **cu129** 源的 `paddlepaddle-gpu==3.3.0`。
- **CUDA 12.7 兼容性**：Paddle 官方提供 cu118、cu123、cu126、**cu129** 等预编译包，**无单独 cu127**。
  **cu129 包可在 CUDA 12.7 驱动下正常使用**（CUDA 12.x 向后兼容），因此 4060 + CUDA 12.7 用 cu129 即可。
- **若安装或运行报错**：
  - 确认已安装 [Visual C++ Redistributable](https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist)。
  - GPU OCR 需 cuDNN 9：`conda install nvidia::cudnn cuda-version=12`，见 [ocr-cudnn64_9-fix.md](ocr-cudnn64_9-fix.md)。
  - 仅用 CPU 跑 OCR：使用 `requirements-cpu.txt` 或设置 `KNOWMAT_OCR_DEVICE=cpu`。

---

## 4. Linux

- 有 **NVIDIA GPU**：安装 `requirements-gpu.txt` + cuDNN；CUDA 12.x 驱动下用 cu129 即可。
- **无 GPU 或仅用 CPU**：使用 `requirements-cpu.txt`。

---

## 5. macOS

- **Intel / Apple Silicon 均无 NVIDIA GPU**，只能使用 **CPU 版 Paddle**。
- 使用 `requirements.txt`（CPU 版 Paddle）。
- 若需 M 系列芯片上加速，请按 PaddleOCR 官方最新 MLX-VLM 指南单独配置。

---

## 6. environment.yml / requirements 说明

- **environment.yml**、**requirements.txt**：仅含 **CPU 版** Paddle（`paddlepaddle>=3.0.0`），跨平台通用，无 GPU 依赖。
- **requirements-gpu.txt**：仅 GPU 相关（`paddlepaddle-gpu==3.3.0` + `paddleocr[all]`），需配合国内源与 cuDNN 使用，见文件内注释。
- **cuDNN**：仅 Windows/Linux GPU 需要，由 `conda install nvidia::cudnn cuda-version=12` 安装，不写入 yml。

---

## 7. 小结

| 你的环境 | 建议 |
|----------|------|
| Windows，4060，CUDA 12.7 | Conda + `requirements-gpu.txt`，cu129 兼容 12.7，无需改。 |
| Windows，无 GPU / 仅 CPU | `requirements-cpu.txt` |
| Linux，有 NVIDIA GPU | Conda + `requirements-gpu.txt`，cu129 适用于 CUDA 12.x |
| Linux，无 GPU | `requirements-cpu.txt` |
| macOS（任意） | pip venv + `requirements.txt`（自动 CPU） |

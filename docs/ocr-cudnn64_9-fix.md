# OCR 报错：cudnn64_9.dll 未配置（error 126）

## 现象

运行 `python -m knowmat --ocr-only` 时，模型加载后对每页推理报错：

```
PreconditionNotMetError: The third-party dynamic library (cudnn64_9.dll) that Paddle depends on is not configured correctly. (error code is 126)
```

即 PaddlePaddle GPU 在跑推理时需要 **cuDNN 9** 的 `cudnn64_9.dll`，系统找不到或加载失败。

---

## 方案一：改用 CPU 跑 OCR（立即可用）

不依赖 cuDNN，先保证能跑通：

**当前终端一次有效：**

```powershell
$env:KNOWMAT_OCR_DEVICE = "cpu"
python -m knowmat --ocr-only
```

**长期使用**：在系统或用户环境变量里新增 `KNOWMAT_OCR_DEVICE`，值为 `cpu`。或在运行前在项目目录建 `.env`，加入一行：

```
KNOWMAT_OCR_DEVICE=cpu
```

若设置 `KNOWMAT_OCR_DEVICE=cpu` 后仍用 GPU 报错，可尝试让当前进程“看不到”GPU，从而退回到 CPU：

```powershell
$env:CUDA_VISIBLE_DEVICES = ""
python -m knowmat --ocr-only
```

缺点：OCR 会变慢，适合临时用或没有合适 cuDNN 时。

---

## 方案二：用 conda 安装 cuDNN 9（推荐，免手动拷 DLL）

在 knowmat 环境中执行（CUDA 12 与 Paddle 3.3 常见组合）：

```bash
conda activate knowmat
conda install nvidia::cudnn cuda-version=12
```

若本机仅有 CUDA 11.8，可试：

```bash
conda install nvidia::cudnn cuda-version=11.8
```

安装完成后**新开终端**再运行：

```powershell
python -m knowmat --ocr-only
```

若 conda 安装的 cuDNN 未被 Paddle 找到（仍报 126），再按方案三手动安装。

---

## 方案三：手动下载 cuDNN 9 并合并到 CUDA 目录

1. **下载 cuDNN 9**
   - 打开 [NVIDIA cuDNN 下载页](https://developer.nvidia.com/cudnn)。
   - 登录后选择 **cuDNN 9.x for CUDA 12.x**（与当前 PaddlePaddle GPU 的 CUDA 对应；若本机只有 CUDA 11.8，选 **for CUDA 11.x**）。
   - 下载 **Windows x86_64** 的 zip。

2. **解压并合并到 CUDA 目录**
   - 解压后得到 `cuda` 目录，内有 `bin`、`include`、`lib`。
   - 本机 CUDA 路径一般为 `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x` 或 `v11.8`。
   - 将解压出的 `cuda\bin\*`、`cuda\include\*`、`cuda\lib\*` 分别合并到 CUDA 目录下对应子目录。

3. **把 CUDA 的 bin 加入 PATH**，确保 `cudnn64_9.dll` 所在目录在 PATH 中，然后新开终端再运行 OCR。

若仍报 126，检查 PATH 中是否只有一份 CUDA/cuDNN，且版本与 PaddlePaddle GPU 要求一致。

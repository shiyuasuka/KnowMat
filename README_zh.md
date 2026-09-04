# KnowMat：材料科学数据抽取流水线

[English README](README.md)

KnowMat 从科学论文（PDF、TXT、Markdown）抽取可审计的材料成分、工艺、结构、
表征和性能数据。流水线使用 OpenAI 兼容的语言模型、证据绑定抽取、OCR、
图表处理和质量审计，并保持现有 `final.json` 输出格式。

## 冷启动（唯一推荐路径）

要求：Python 3.11+、一个 OpenAI 兼容 LLM endpoint，以及下方任一 OCR 后端。

```bash
git clone https://github.com/shiyuasuka/KnowMat.git
cd KnowMat
# macOS/Linux（zsh 或 bash）
python3 -m venv venv
source venv/bin/activate
# Windows PowerShell（改用下面两行）：
# py -3 -m venv venv
# .\\venv\\Scripts\\Activate.ps1
# Windows cmd.exe 激活：venv\\Scripts\\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r requirements.txt
cp .env.example .env
```

程序会自动读取 `.env`，不要执行 `source .env`；这样可以避免 CRLF 文件的行尾
污染配置。

## 配置 LLM

在 `.env` 中填写：

```dotenv
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_MODEL=your_model_name
```

模型名称和 endpoint 不会被代码硬编码。不同模型支持的 reasoning 或响应格式
参数可以保持默认，也可以按 `.env.example` 中的说明显式配置。

## OCR 后端（二选一）

### 云端 PaddleOCR（大多数用户推荐）

在 `.env` 中增加：

```dotenv
PADDLEOCR_API_TOKEN=your_paddleocr_token
PADDLEOCR_API_URL=https://paddleocr.aistudio-app.com/api/v2/ocr/jobs
```

先生成并冻结 OCR manifest，再执行 LLM 抽取：

```bash
python -m knowmat --input-folder data/raw --ocr-only --paddleocr-api \
  --force-rerun --skip-cached-ocr --new-ocr-baseline fresh
python -m knowmat --input-folder data/raw --output-dir data/output \
  --use-ocr-baseline fresh --rerun-extraction --full-pipeline \
  --workers 6 --max-runs 1
```

### NVIDIA Linux/Windows 本地 OCR

本地推理需要 NVIDIA GPU 和 CUDA。完成基础安装后执行：

```bash
python -m pip uninstall -y paddlepaddle paddlepaddle-gpu
python -m pip install -r requirements-gpu.txt \
  -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
python scripts/download_paddleocrvl_models.py
python -m knowmat --input-folder data/raw --output-dir data/output \
  --full-pipeline --force-rerun --workers 1
```

模型预下载唯一入口为 `scripts/download_paddleocrvl_models.py`，默认
PaddleOCR-VL 1.5，权重保存在 `models/`，不会提交到 git。

### macOS

生产本地 OCR 依赖 NVIDIA CUDA，macOS 不支持这条路径。Apple Silicon 或 Intel
Mac 请使用上面的云端 PaddleOCR；LLM 抽取阶段可以正常运行在 venv 中。

MinerU 仍可作为兼容 OCR 后端：配置 `MINERU_API_KEY` 后增加 `--mineru-api`。

## 可选：embedding 模型

只有属性标准化和图文对齐需要 embedding：

```bash
python -m pip install -e ".[standardization]"
python scripts/download_embedding_model.py
```

默认 CLIP 模型会下载到 Transformers 用户缓存，可用
`KNOWMAT_EMBEDDING_MODEL` 和 `KNOWMAT_EMBEDDING_DEVICE` 覆盖。

## 常用命令

```bash
# 基于已有冻结 OCR manifest 重新抽取
python -m knowmat --input-folder data/raw --output-dir data/output \
  --use-ocr-baseline fresh --rerun-extraction --workers 6 --max-runs 1

# 只处理指定论文
python -m knowmat --input-folder data/raw --only paper_001 paper_002

# 批量运行前验证 endpoint 能力
python scripts/probe_extraction_capabilities.py --model "your_model_name" \
  --output data/capability_probe.json
```

成功抽取默认不会重复三次取最高置信度。只有在明确需要多轮比较时才提高
`--max-runs`。

## 目录职责

```text
src/knowmat/       生产运行时代码
scripts/            运维、回放、评估和模型预热命令
tests/              回归测试
prompts/            提示配置
data/raw/           输入 PDF 与 OCR 中间文件
data/output-*/      抽取结果（生成物）
data/experiments/   实验缓存和回放（生成物）
reports/            评估报告（生成物）
models/             本地模型权重（生成物）
```

`v200` 及之后的实验结果和审计报告保留在本地历史目录中，但不会复制到生产
包或源码提交。

## 测试

```bash
python -m pytest -o addopts='' -q
```

完整 Alpha25 冻结 OCR 流程见
[`docs/alpha25-ocr-llm-runbook.md`](docs/alpha25-ocr-llm-runbook.md)。

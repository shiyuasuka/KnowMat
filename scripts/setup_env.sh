#!/usr/bin/env bash
# KnowMat 一键部署：创建/更新 Conda 环境 + Paddle GPU (cu129) + cuDNN + OCR 模型
# 用法：在项目根目录执行 ./scripts/setup_env.sh  或  ./scripts/setup_env.sh --cpu
# --cpu：仅安装 CPU 版 Paddle，不装 paddlepaddle-gpu / cuDNN

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
ENV_NAME="${KNOWMAT_ENV_NAME:-KnowMat}"
CPU=false
SKIP_CUDNN=false

for arg in "$@"; do
  case "$arg" in
    --cpu)    CPU=true ;;
    --skip-cudnn) SKIP_CUDNN=true ;;
  esac
done

echo "==> KnowMat 一键部署 (bash)"
echo "    项目根目录: $REPO_ROOT"
echo ""

# 1. 检查 conda
if ! command -v conda &>/dev/null; then
  echo "[错误] 未找到 conda，请先安装 Anaconda 或 Miniconda。"
  exit 1
fi

# 2. 创建或更新 conda 环境
YML="$REPO_ROOT/environment.yml"
if [[ ! -f "$YML" ]]; then
  echo "[错误] 未找到 environment.yml"
  exit 1
fi

if conda env list | grep -q "^${ENV_NAME} "; then
  echo "==> 更新现有环境: $ENV_NAME"
  conda env update -f "$YML" --prune -n "$ENV_NAME"
else
  echo "==> 创建新环境: $ENV_NAME"
  conda env create -f "$YML" -n "$ENV_NAME"
fi

# 3. 在环境中安装 Paddle + PaddleOCR
echo ""
echo "==> 在环境中安装 PaddlePaddle + PaddleOCR (cu129 源)"
if $CPU; then
  conda run -n "$ENV_NAME" python -m pip install "paddlepaddle>=3.0.0" "paddleocr[all]" -q
else
  conda run -n "$ENV_NAME" python -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/ -q
  conda run -n "$ENV_NAME" python -m pip install "paddleocr[all]" -q
fi

# 4. 可选：安装 cuDNN 9（conda）
if ! $CPU && ! $SKIP_CUDNN; then
  echo ""
  echo "==> 尝试安装 cuDNN 9 (conda install nvidia::cudnn cuda-version=12)"
  conda install -n "$ENV_NAME" nvidia::cudnn cuda-version=12 -y -q 2>/dev/null || true
fi

# 5. 下载 PaddleOCR-VL 模型
MODEL_DIR="$REPO_ROOT/models/paddleocrvl1_5"
echo ""
echo "==> 下载 PaddleOCR-VL 模型到 $MODEL_DIR"
conda run -n "$ENV_NAME" python scripts/download_paddleocrvl_models.py --model-dir "$MODEL_DIR" || true

# 6. 验证
echo ""
echo "==> 验证安装"
if conda run -n "$ENV_NAME" python -m knowmat --help &>/dev/null; then
  echo "    knowmat --help 正常"
else
  echo "    knowmat --help 失败，请检查环境"
fi

echo ""
echo "==> 一键部署完成"
echo "    激活环境: conda activate $ENV_NAME"
echo "    配置 API: 复制 .env_example 为 .env 并填写 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 等"
echo "    验证:     python -m knowmat --help"
$CPU && echo "    当前为 CPU 模式；OCR 将使用 CPU。若需 GPU，请重新运行不加 --cpu 并配置 cuDNN。"

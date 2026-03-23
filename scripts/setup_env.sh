#!/usr/bin/env bash
# KnowMat one-click deployment: Create/update Conda environment + Paddle (CPU/GPU) + cuDNN + OCR models
# Usage: ./scripts/setup_env.sh [--cpu] [--skip-cudnn]
# --cpu: Force CPU version of Paddle (macOS automatically uses CPU)
# macOS (Apple Silicon) has no NVIDIA GPU, script will use CPU by default
#
# Consistent with environment.yml, requirements.txt, and requirements-gpu.txt

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

# macOS has no NVIDIA GPU, force CPU
if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! $CPU; then
    echo "==> Detected macOS, using CPU version of Paddle (no NVIDIA GPU)"
    CPU=true
  fi
fi

echo "==> KnowMat One-Click Deployment (bash)"
echo "    Project root: $REPO_ROOT"
echo "    Platform: $(uname -s)"
echo "    Paddle: $([ "$CPU" = true ] && echo 'CPU' || echo 'GPU (cu129)')"
echo ""

# 1. Check conda
if ! command -v conda &>/dev/null; then
  echo "[Error] conda not found, please install Anaconda or Miniconda first."
  exit 1
fi

# 2. Create or update conda environment
YML="$REPO_ROOT/environment.yml"
if [[ ! -f "$YML" ]]; then
  echo "[Error] environment.yml not found"
  exit 1
fi

if conda env list | grep -q "^${ENV_NAME} "; then
  echo "==> Updating existing environment: $ENV_NAME"
  conda env update -f "$YML" --prune -n "$ENV_NAME"
else
  echo "==> Creating new environment: $ENV_NAME"
  conda env create -f "$YML" -n "$ENV_NAME"
fi

# 3. GPU optional: Override to GPU version of Paddle + PaddleOCR
# (environment.yml already installed CPU version, upgrade here if needed)
echo ""
if $CPU; then
  echo "==> Keeping CPU version of Paddle (installed by environment.yml)"
else
  echo "==> Installing GPU version of Paddle + PaddleOCR (cu129)"
  conda run -n "$ENV_NAME" python -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/ -q
  conda run -n "$ENV_NAME" python -m pip install "paddleocr[all]" -q
fi

# 4. Optional: Install cuDNN 9 (conda)
if ! $CPU && ! $SKIP_CUDNN; then
  echo ""
  echo "==> Installing cuDNN 9 (conda install nvidia::cudnn cuda-version=12)"
  conda install -n "$ENV_NAME" nvidia::cudnn cuda-version=12 -y -q 2>/dev/null || true
fi

# 5. Download PaddleOCR-VL models
MODEL_DIR="$REPO_ROOT/models/paddleocrvl1_5"
echo ""
echo "==> Downloading PaddleOCR-VL models to $MODEL_DIR"
conda run -n "$ENV_NAME" python scripts/download_paddleocrvl_models.py --model-dir "$MODEL_DIR" || true

# 6. Verify installation
echo ""
echo "==> Verifying installation"
if conda run -n "$ENV_NAME" python -m knowmat --help &>/dev/null; then
  echo "    knowmat --help OK"
else
  echo "    knowmat --help FAILED, please check environment"
fi

echo ""
echo "==> One-click deployment completed"
echo "    Activate environment: conda activate $ENV_NAME"
echo "    Configure API: Copy .env_example to .env and set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, etc."
echo "    Verify:     python -m knowmat --help"
$CPU && echo "    Current: CPU mode; OCR will use CPU. For GPU, re-run without --cpu and configure cuDNN."

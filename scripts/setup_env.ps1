# KnowMat One-Click Deployment (Windows): Conda environment + Paddle GPU (cu129, compatible with CUDA 12.x including 12.7) + cuDNN + OCR models
# Usage: .\scripts\setup_env.ps1  or  .\scripts\setup_env.ps1 -CPU
# -CPU: Install CPU version of Paddle only. For multi-platform instructions, see docs/platforms.md
#
# Consistent with environment.yml, requirements.txt, and requirements-gpu.txt

param(
    [switch]$CPU = $false,
    [switch]$SkipCudnn = $false,
    [string]$EnvName = "KnowMat"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $RepoRoot

Write-Host "==> KnowMat One-Click Deployment (PowerShell)" -ForegroundColor Cyan
Write-Host "    Project root: $RepoRoot" -ForegroundColor Gray
Write-Host ""

# 1. Check conda
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host "[Error] conda not found, please install Anaconda or Miniconda first." -ForegroundColor Red
    exit 1
}

# 2. Create or update conda environment
$yml = Join-Path $RepoRoot "environment.yml"
if (-not (Test-Path $yml)) {
    Write-Host "[Error] environment.yml not found" -ForegroundColor Red
    exit 1
}

$envExists = conda env list --json | ConvertFrom-Json | ForEach-Object { $_.envs } | Where-Object { $_ -match [regex]::Escape($EnvName) }
if ($envExists) {
    Write-Host "==> Updating existing environment: $EnvName" -ForegroundColor Yellow
    conda env update -f $yml --prune -n $EnvName
} else {
    Write-Host "==> Creating new environment: $EnvName" -ForegroundColor Yellow
    conda env create -f $yml -n $EnvName
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[Error] Failed to create/update conda environment" -ForegroundColor Red
    exit 1
}

# 3. GPU optional: Override to GPU version of Paddle + PaddleOCR
# (environment.yml already installed CPU version, upgrade here if needed)
Write-Host ""
if ($CPU) {
    Write-Host "==> Keeping CPU version of Paddle (installed by environment.yml)" -ForegroundColor Gray
} else {
    Write-Host "==> Installing GPU version of Paddle + PaddleOCR (cu129, compatible with CUDA 12.x)" -ForegroundColor Yellow
    & conda run -n $EnvName python -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/ --quiet
    & conda run -n $EnvName python -m pip install "paddleocr[all]" --quiet
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[Warning] Paddle/PaddleOCR installation may be incomplete, you can manually run later:" -ForegroundColor Yellow
    Write-Host "  conda activate $EnvName" -ForegroundColor Gray
    Write-Host "  python -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/" -ForegroundColor Gray
    Write-Host "  python -m pip install `"paddleocr[all]`"" -ForegroundColor Gray
}

# 4. Optional: Install cuDNN 9 (conda, install if OCR reports cudnn64_9.dll error)
if (-not $CPU -and -not $SkipCudnn) {
    Write-Host ""
    Write-Host "==> Installing cuDNN 9 (conda install nvidia::cudnn cuda-version=12)" -ForegroundColor Yellow
    & conda install -n $EnvName nvidia::cudnn cuda-version=12 -y --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    Automatic cuDNN installation failed; if OCR reports cudnn64_9.dll error, see docs/ocr-cudnn64_9-fix.md" -ForegroundColor Gray
    }
}

# 5. Download PaddleOCR-VL models
$ModelDir = Join-Path $RepoRoot "models\paddleocrvl1_5"
Write-Host ""
Write-Host "==> Downloading PaddleOCR-VL models to $ModelDir" -ForegroundColor Yellow
& conda run -n $EnvName python scripts/download_paddleocrvl_models.py --model-dir $ModelDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "[Warning] Model download incomplete, you can manually run: conda activate $EnvName && python scripts/download_paddleocrvl_models.py --model-dir $ModelDir" -ForegroundColor Yellow
}

# 6. Verify installation
Write-Host ""
Write-Host "==> Verifying installation" -ForegroundColor Yellow
& conda run -n $EnvName python -m knowmat --help | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    knowmat --help OK" -ForegroundColor Green
} else {
    Write-Host "    knowmat --help FAILED, please check environment" -ForegroundColor Red
}

Write-Host ""
Write-Host "==> One-click deployment completed" -ForegroundColor Green
Write-Host "    Activate environment: conda activate $EnvName" -ForegroundColor Cyan
Write-Host "    Configure API: Copy .env_example to .env and set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, etc." -ForegroundColor Cyan
Write-Host "    Verify:     python -m knowmat --help" -ForegroundColor Cyan
if ($CPU) {
    Write-Host "    Current: CPU mode; OCR will use CPU. For GPU, re-run without -CPU and configure cuDNN." -ForegroundColor Gray
}

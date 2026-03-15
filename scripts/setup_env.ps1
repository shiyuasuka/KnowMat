# KnowMat 一键部署：创建/更新 Conda 环境 + Paddle GPU (cu129) + cuDNN + OCR 模型
# 用法：在项目根目录执行 .\scripts\setup_env.ps1  或  .\scripts\setup_env.ps1 -CPU
# -CPU：仅安装 CPU 版 Paddle，不装 paddlepaddle-gpu / cuDNN

param(
    [switch]$CPU = $false,
    [switch]$SkipCudnn = $false,
    [string]$EnvName = "KnowMat"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $RepoRoot

Write-Host "==> KnowMat 一键部署 (PowerShell)" -ForegroundColor Cyan
Write-Host "    项目根目录: $RepoRoot" -ForegroundColor Gray
Write-Host ""

# 1. 检查 conda
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未找到 conda，请先安装 Anaconda 或 Miniconda。" -ForegroundColor Red
    exit 1
}

# 2. 创建或更新 conda 环境
$yml = Join-Path $RepoRoot "environment.yml"
if (-not (Test-Path $yml)) {
    Write-Host "[错误] 未找到 environment.yml" -ForegroundColor Red
    exit 1
}

$envExists = conda env list --json | ConvertFrom-Json | ForEach-Object { $_.envs } | Where-Object { $_ -match [regex]::Escape($EnvName) }
if ($envExists) {
    Write-Host "==> 更新现有环境: $EnvName" -ForegroundColor Yellow
    conda env update -f $yml --prune -n $EnvName
} else {
    Write-Host "==> 创建新环境: $EnvName" -ForegroundColor Yellow
    conda env create -f $yml -n $EnvName
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] conda 环境创建/更新失败" -ForegroundColor Red
    exit 1
}

# 3. 在 KnowMat 环境中安装 Paddle + PaddleOCR（使用国内源）
Write-Host ""
Write-Host "==> 在环境中安装 PaddlePaddle + PaddleOCR (cu129 源)" -ForegroundColor Yellow
if ($CPU) {
    & conda run -n $EnvName python -m pip install "paddlepaddle>=3.0.0" "paddleocr[all]" --quiet
} else {
    & conda run -n $EnvName python -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/ --quiet
    & conda run -n $EnvName python -m pip install "paddleocr[all]" --quiet
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[警告] Paddle/PaddleOCR 安装可能不完整，可稍后手动执行：" -ForegroundColor Yellow
    Write-Host "  conda activate $EnvName" -ForegroundColor Gray
    Write-Host "  python -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/" -ForegroundColor Gray
    Write-Host "  python -m pip install `"paddleocr[all]`"" -ForegroundColor Gray
}

# 4. 可选：安装 cuDNN 9（conda，GPU 下若报 cudnn64_9.dll 再装）
if (-not $CPU -and -not $SkipCudnn) {
    Write-Host ""
    Write-Host "==> 尝试安装 cuDNN 9 (conda install nvidia::cudnn cuda-version=12)" -ForegroundColor Yellow
    & conda install -n $EnvName nvidia::cudnn cuda-version=12 -y --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    cuDNN 自动安装未成功；若 OCR 报 cudnn64_9.dll，请见 docs/ocr-cudnn64_9-fix.md" -ForegroundColor Gray
    }
}

# 5. 下载 PaddleOCR-VL 模型
$ModelDir = Join-Path $RepoRoot "models\paddleocrvl1_5"
Write-Host ""
Write-Host "==> 下载 PaddleOCR-VL 模型到 $ModelDir" -ForegroundColor Yellow
& conda run -n $EnvName python scripts/download_paddleocrvl_models.py --model-dir $ModelDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "[警告] 模型下载未完成，可稍后执行：conda activate $EnvName && python scripts/download_paddleocrvl_models.py --model-dir $ModelDir" -ForegroundColor Yellow
}

# 6. 验证
Write-Host ""
Write-Host "==> 验证安装" -ForegroundColor Yellow
& conda run -n $EnvName python -m knowmat --help | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    knowmat --help 正常" -ForegroundColor Green
} else {
    Write-Host "    knowmat --help 失败，请检查环境" -ForegroundColor Red
}

Write-Host ""
Write-Host "==> 一键部署完成" -ForegroundColor Green
Write-Host "    激活环境: conda activate $EnvName" -ForegroundColor Cyan
Write-Host "    配置 API: 复制 .env_example 为 .env 并填写 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 等" -ForegroundColor Cyan
Write-Host "    验证:     python -m knowmat --help" -ForegroundColor Cyan
if ($CPU) {
    Write-Host "    当前为 CPU 模式；OCR 将使用 CPU。若需 GPU，请重新运行不加 -CPU 并配置 cuDNN。" -ForegroundColor Gray
}

# knowmat 环境与 environment.yml / setup_env.ps1 一致性扫描

基于当前 **knowmat** conda 环境导出结果与 `environment.yml`、`scripts/setup_env.ps1` 的对比。

---

## 1. 环境名称

| 来源 | 环境名 |
|------|--------|
| environment.yml | `KnowMat` |
| setup_env.ps1 默认 | `KnowMat` |
| 当前扫描环境 | `knowmat` |

在 Windows 上 conda 环境名通常不区分大小写，`knowmat` 与 `KnowMat` 一般指向同一环境。若在新机器上严格一致，建议统一用 `KnowMat`（与 yml 一致）。

---

## 2. environment.yml 中声明的依赖 vs 实际环境

### 2.1 Conda 显式依赖

| 包名 | yml 要求 | 实际环境 | 一致 |
|------|----------|----------|------|
| python | ==3.11 | 3.11.11 | ✓（3.11.x） |
| numpy | ==2.2.6 | 2.2.6 | ✓ |
| scipy | ==1.16.0 | 1.16.0 | ✓ |
| pandas | ==2.3.2 | 2.3.2 | ✓ |
| tqdm | ==4.67.1 | 4.67.1 | ✓ |
| click | (无版本) | 8.2.1 | ✓ |
| ipython | (无版本) | 9.10.0 | ✓ |
| matplotlib | (无版本) | 3.10.8 | ✓ |
| ipympl | (无版本) | 0.9.8 | ✓ |
| seaborn | (无版本) | 0.13.2 | ✓ |
| jupyterlab | (无版本) | 4.5.3 | ✓ |
| pytest / pytest-cov / tox / pre-commit / nbdime / nbstripout / sphinx / recommonmark | 有 | 均已安装 | ✓ |

### 2.2 Pip 显式依赖（yml 中 pip: 段）

| 包名 | yml 要求 | 实际环境 | 一致 |
|------|----------|----------|------|
| -e . (knowmat) | 可编辑安装 | knowmat 0.0.post1.dev27... | ✓ |
| langchain | ==0.3.26 | 0.3.26 | ✓ |
| langchain-community | ==0.3.27 | 0.3.27 | ✓ |
| langchain-openai | ==0.3.27 | 0.3.27 | ✓ |
| langgraph | ==0.6.10 | 0.6.10 | ✓ |
| trustcall | ==0.0.39 | 0.0.39 | ✓ |
| openai | ==1.93.2 | 1.93.2 | ✓ |
| paddlepaddle-gpu | ==3.3.0 | 3.3.0 | ✓ |
| paddleocr[all] | (all 额外) | paddleocr 3.4.0 + paddlex 等 | ✓ |
| pymupdf | ==1.24.13 | 1.24.13 | ✓ |
| beautifulsoup4 | >=4.12 | 4.12.3 | ✓ |
| lxml | >=6.0 | 6.0.2 | ✓ |
| cssselect | >=1.4 | 1.4.0 | ✓ |
| einops | >=0.8 | 0.8.2 | ✓ |
| openpyxl | >=3.1 | 3.1.5 | ✓ |
| premailer | >=3.10 | 3.10.0 | ✓ |
| pydantic | ==2.11.7 | 2.11.7 | ✓ |
| pydantic-settings | >=2.0.0 | 2.13.1 | ✓ |
| python-dotenv | ==1.1.1 | 1.1.1 | ✓ |
| colorlog | ==6.9.0 | 6.9.0 | ✓ |
| PyYAML | >=6.0 | 6.0.2 | ✓ |
| sentence-transformers | ==5.0.0 | 5.0.0 | ✓ |
| torch | ==2.8.0 | 2.8.0 | ✓ |
| torchvision | ==0.23.0 | 0.23.0 | ✓ |

### 2.3 cuDNN（由 setup_env.ps1 安装，未写在 yml 中）

| 包名 | 来源 | 实际环境 | 一致 |
|------|------|----------|------|
| cudnn / libcudnn | 脚本 step 4：conda install nvidia::cudnn cuda-version=12 | cudnn 9.14.0.64, libcudnn 9.14.0.64 | ✓ |

设计上 cuDNN 由脚本单独安装，未写入 `environment.yml`，与当前设计一致。

---

## 3. setup_env.ps1 流程与当前环境

| 步骤 | 脚本行为 | 当前 knowmat 环境 |
|------|----------|-------------------|
| 1 | 检查 conda | - |
| 2 | conda env create/update -f environment.yml | 已具备 yml 中全部 conda + pip 依赖 ✓ |
| 3 | pip install paddlepaddle-gpu (cu129) + paddleocr[all] | paddlepaddle-gpu 3.3.0、paddleocr 3.4.0 ✓ |
| 4 | conda install nvidia::cudnn cuda-version=12 | cudnn / libcudnn 9.14.0.64 ✓ |
| 5 | 下载 PaddleOCR-VL 模型 | 需在项目目录下存在 models/paddleocrvl1_5 |
| 6 | python -m knowmat --help | 若通过则环境可用 ✓ |

结论：**脚本流程与当前“完全 ok”的 knowmat 环境一致**；用同一 `environment.yml` + `setup_env.ps1` 在新机器上应能复现等效环境。

---

## 4. 可选优化建议

1. **环境名**：新环境建议统一用 `KnowMat`（与 yml 一致），避免跨平台大小写歧义。
2. **Python 版本**：若需与当前环境完全一致，可在 yml 中把 `python==3.11` 改为 `python==3.11.11`；保持 `3.11` 则继续使用 conda 解析的 3.11.x 最新版即可。
3. **无需修改**：yml 与脚本均无需新增包；当前环境多出的为传递依赖（如 langchain-core、nvidia-*、paddlex 等），由 paddleocr[all] 等拉取，属正常。

---

## 5. 总结

- **environment.yml**：其中声明的 conda 与 pip 依赖在当前 knowmat 环境中**全部存在且版本符合**。
- **setup_env.ps1**：各步骤（创建/更新环境、安装 Paddle GPU + PaddleOCR、安装 cuDNN、下载模型、验证）与当前环境**一致**；cuDNN 通过脚本安装、不写在 yml 中，符合现有设计。
- **结论**：当前 knowmat 环境与 `environment.yml` 及 `scripts/setup_env.ps1` 一致，无需对 yml 或脚本做必须修改；可按上述“可选优化”决定是否微调。

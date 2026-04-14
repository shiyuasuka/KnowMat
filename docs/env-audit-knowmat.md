# knowmat 环境与 environment.yml 一致性扫描

基于当前 **knowmat** conda 环境导出结果与 `environment.yml` 的对比。

---

## 1. 环境名称

| 来源 | 环境名 |
|------|--------|
| environment.yml | `KnowMat` |
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

### 2.3 cuDNN（GPU 用户需单独安装）

| 包名 | 安装方式 | 说明 |
|------|----------|------|
| cudnn / libcudnn | `conda install nvidia::cudnn cuda-version=12` | 仅 Windows/Linux GPU 用户需要 |

cuDNN 未写在 `environment.yml` 中，由用户按需安装。

---

## 3. 总结

- **environment.yml**：其中声明的 conda 与 pip 依赖在当前 knowmat 环境中**全部存在且版本符合**。
- **cuDNN**：GPU 用户需单独安装 `conda install nvidia::cudnn cuda-version=12`。
- **结论**：当前 knowmat 环境与 `environment.yml` 一致，无需对 yml 做必须修改。

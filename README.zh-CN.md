# OpenECRS

**Open Evidence-Centric Recommendation System（证据驱动机会推荐智能体）** —— 把公开的 AI 工具信号变成可核查、可排序的产品机会。

**[English](README.md)** · 中文版

![OpenECRS 首屏](docs/screenshots/answer-zh.png)

OpenECRS 读取已经整理好的 12 个 AI 应用场景证据库，从需求、供给缺口、可行性、商业价值四个维度评分，并在一个简洁的对话界面里回答问题。每条回答先给**一句话建议**，再给**详细数据**、原文证据 span 与行动建议，并可一键导出 **PDF 建议书**。可选接入 OpenAI 兼容的大模型 API 来改写措辞；数字、排名与证据始终由离线引擎给出，可核查、可复现。

## 功能

- **中英双语界面**：右上角 EN / 中文 切换，默认英文。
- **证据可核查**：每条结论附原文 span、来源、年份与置信度，可回溯到原始记录。
- **一句话建议 → 详细数据**：排名表、场景评分卡、对比表、证据摘录、行动建议都由离线规则引擎确定性生成。
- **PDF 建议书导出**：A4 报告（示例见 `docs/examples/OpenECRS_brief_zh.pdf`），包含建议、数据、证据、行动建议与口径局限；由本机 Chrome/Edge/Chromium 本地渲染，无需联网。
- **可选大模型 API**：支持任意 OpenAI 兼容接口（DeepSeek / OpenAI / Moonshot / 通义 DashScope 兼容模式 / 本地 Ollama）。模型只改写「一句话建议 + 说明」；调用失败会自动回退规则结果。
- **程序化 HTTP API**：`/api/chat`、`/api/pdf`、`/api/settings`、`/api/test`、`/api/health`。
- **默认完全离线**：无需 API Key、不上传数据、无外部 CDN；运行时只依赖 Python 标准库。

## 快速开始

```bash
# Python 3.11+（已在 3.14 / macOS 验证）
pip install -r requirements.txt        # pandas 只在重建 data.json 时需要

python code/agent_app.py --open        # -> http://127.0.0.1:8765
```

macOS 也可以直接双击 **`openecrs.command`** 启动并打开浏览器。

常用参数：

```bash
python code/agent_app.py --port 9000 --open   # 换端口
python code/agent_app.py --rebuild            # 从 outputs/tables/ 强制重建 data.json
```

## 中英切换

- 界面：右上角 **EN / 中文**，选择会记录在 `localStorage`，默认英文。
- 文档：英文见 [README.md](README.md)，本文件为中文版。
- 回答与 PDF 语言跟随当前界面语言（API 参数 `lang=en|zh`）。

## 接入大模型 API（可选）

点右上角齿轮，填写 **Base URL / 模型 / API Key** → 「测试连接」→ 打开开关 → 保存。界面会显示当前引擎（`Rule engine` / `LLM · 模型名`），PDF 页脚也会注明本次是否由大模型改写。

| 服务 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义 DashScope 兼容模式 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | 本地模型名，Key 随意 |

Key 只保存在本机 `outputs/agent_ui/settings.json`（0600 权限），除你填写的接口外不会发往任何地方；也支持环境变量 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `LLM_API_KEY`（`LLM_BASE_URL` / `LLM_MODEL`）。超时、Key 无效或返回格式异常时自动回退规则结果并提示。

## 程序化调用

```bash
curl -s http://127.0.0.1:8765/api/chat -H 'Content-Type: application/json' \
  -d '{"session":"demo","message":"哪个场景最值得优先做？","lang":"zh"}'

curl -s -X POST http://127.0.0.1:8765/api/pdf -H 'Content-Type: application/json' \
  -d '{"session":"demo","lang":"zh"}' -o 建议书.pdf
```

| 接口 | 说明 |
|---|---|
| `POST /api/chat` | `{session, message, lang}` → 结构化回答（建议、说明、指标、排名、对比、证据、行动、风险、快捷问题、引擎信息） |
| `POST /api/pdf` | `{session, lang}` → `application/pdf` 建议书；无本地浏览器时回退打印视图 |
| `GET /api/settings` / `POST /api/settings` | 读取（Key 脱敏）/ 保存大模型设置 |
| `POST /api/test` | 测试大模型接口连通性 |
| `GET /api/health` | 服务、数据与 PDF 后端状态 |
| `GET /api/data` | 界面使用的紧凑数据集 |

## 证据库

数据快照日期 **2026-11-20**：

- 52,007 条原始记录 → 45,306 条清洗记录（Hacker News、GitHub、arXiv、Stack Overflow、Product Hunt）。
- 19,621 个需求/供给单元 → 15,525 条需求单元 → 2,848 条高置信场景样本（18.34%）。
- 12 个 AI 应用场景，AHP 权重：需求 45% + 供给缺口 25% + 技术可行性 18% + 商业价值 12%（CR = 0.0002）。
- 15,525 条逐记录证据审查；162 条通过四门机会判定；`outputs/agent_ui/data.json` 内置 72 条原文证据。

机会总分前五：安全合规与隐私 **62.41**；多智能体与任务编排 **57.86**；知识管理与文档问答 **57.28**；编程与代码智能 **56.20**；办公协作与会议效率 **48.98**。

证据库由独立的分析流水线（采集、清洗、弱监督、评分、证据审查）产出。本仓库只包含 **Agent 运行所需** 的代码、打包数据与重建 data.json 所需的对账表，不包含原始爬取数据与微调 LoRA 适配器。

## 目录结构

```
OpenECRS/
├─ code/
│  ├─ agent_app.py        # 本地服务：静态界面 + /api/chat + /api/pdf + 设置/测试
│  ├─ agent_engine.py     # 双语的确定性推理（排名 / 单场景 / 对比 / 证据 / 风险 / 行动）
│  ├─ scenario_names.py   # 统一的英文场景名与路线名
│  ├─ agent_llm.py        # 可选 OpenAI 兼容大模型桥接（失败自动回退）
│  ├─ agent_pdf.py        # A4 建议书 HTML 模板 + 本机 Chromium PDF 渲染
│  ├─ agent_ui.html       # 单文件双语对话界面（无构建、无 CDN）
│  ├─ agent_ui_data.py    # 从 outputs/tables/ 重建 outputs/agent_ui/data.json
│  ├─ test_agent_ui.py    # 界面 / 推理 / PDF / HTTP 测试（含英文模式）
│  └─ test_agent_llm.py   # 大模型桥接测试（本地 mock 端点）
├─ outputs/
│  ├─ agent_ui/data.json  # 打包数据集：12 场景 + 72 条原文证据
│  └─ tables/             # 对账表（评分、供给、证据审查、质量卡）
├─ docs/
│  ├─ screenshots/        # 中英界面截图
│  └─ examples/           # 中英文 PDF 建议书示例
├─ openecrs.command       # macOS 一键启动
├─ requirements.txt
├─ requirements-lora.txt  # （未随包分发的）LoRA 微调依赖
└─ README.md / README.zh-CN.md
```

## 自检

```bash
cd code
python -m unittest test_agent_ui test_agent_llm -v   # 31 项
```

覆盖中英双语、排名/单场景/对比/追问逻辑、PDF 生成（无本地 Chromium 时跳过）、HTTP 层，以及基于本地 mock 端点的大模型桥接。

## 口径与局限

- 场景标签来自弱监督（词典 + TF-IDF/Logistic Regression 扩展），不是人工全量标注。
- 来源偏差：Hacker News/GitHub 占比较高，不能当作真实市场占比。
- 供给成熟度用仓库/Star/论文/Show HN 近似；付费意愿来自文本信号，不等同真实付费。
- 规则置信度**未经人工校准**（暂无金标），只作为线索使用；可选大模型只改措辞，不改变数字、排名与证据。
- 公开数据版权归各平台与作者所有。

## 许可与署名

仓库代码供研究与评估使用；引用的第三方数据片段仅用于证据溯源，版权归原作者所有。示例建议书见 `docs/examples/`。

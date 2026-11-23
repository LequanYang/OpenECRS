# OpenECRS

**Open Evidence-Centric Recommendation System（证据驱动机会推荐智能体）** —— 用 LLM 把公开的 AI 工具信号变成可核查、可排序的产品机会。

**[English](README.md)** · 中文版

![OpenECRS 首屏](docs/screenshots/hero-zh.png)

OpenECRS 是一个**完整的 Agent 系统**：**必须使用 LLM**。模型负责规划每一次回答，调用离线工具检索证据库，再撰写「一句话建议 + 详细数据 + 原文证据 + 行动建议」，可一键导出 PDF 建议书。数字与证据永远来自工具，而不是模型；如果未配置 LLM，智能体拒绝对话。

## 核心特性

- **必须有 LLM**：不再使用规则模板作答。支持 OpenAI 兼容 API，或本地 Qwen2.5-3B + LoRA 适配器。
- **真正的 Agent 循环**：`规划 → 工具 → 作答`，每轮两次模型调用；界面展示 **Agent 过程**（意图、工具调用、模型耗时）。
- **工具提供证据**：排名、场景指标、对比、证据检索；每条结论都能回溯到原文 span。
- **自然寒暄**：问候会得到简短友好的产品向导式回复（附示例问题），不再强行推荐场景，也不会暴露内部术语；数据问题仍走证据工具。
- **对话内视频**：直接问“推荐视频”即可返回按场景生成的 YouTube/B站 检索卡片（明确标注外部内容、非证据库）。
- **多语言**：支持 English / 中文 / 日本語 / Español；默认跟随系统语言，可在侧边栏切换，回答随之切换语言。
- **PDF 建议书**：一句话建议、详细数据、证据摘录、行动建议、口径局限，本地渲染。
- **可折叠侧边栏 + 官方 Logo**：展开是完整工作区，合上变成 68px 的 Logo 窄栏（新对话/历史/设置图标），不再重复 OpenECRS 文字。
- **首用引导**：定位首屏 + 60 秒 tour + 能力卡 + 示例问题，第一次打开就知道能做什么。
- **六个实际工具**：决策向导、证据浏览器、PoC 计划、预算组合、收藏工作区、外部视频，以及带趋势/来源/供给图表的场景深潜。
- **角色化回答**：创业 / 大厂 / 投资 / 产品 四种视角，prompt 与优先级随角色变化。
- **程序化 API**：`/api/chat`、`/api/pdf`、`/api/settings`、`/api/test`、`/api/health`、`/api/sessions`、`/api/evidence`、`/api/scenario_detail`、`/api/videos`、`/api/wizard`、`/api/poc`、`/api/portfolio`、`/api/workspace`。
- **历史对话保留**：对话保存在 `outputs/agent_ui/sessions.json`，左侧「历史对话」可切换，刷新页面或重启服务后自动恢复。

## 能做什么

| 工具 | 产出 |
|---|---|
| **决策向导** | 6 个约束（角色/目标/团队/预算/周期/风险）→ 3 个场景短名单，确定性评分 + 理由 + 风险点，可选 LLM 叙述。 |
| **证据浏览器** | 按场景/来源/年份/置信度/正反证据筛选 72 条原文 span，直接看原句与来源。 |
| **PoC 计划** | 2/4/8 周里程碑，含交付物、退出标准、角色、指标、数据合规清单与启发式人力/成本。 |
| **组合预算** | 给定团队、周期、预算，先做哪个、先验证哪个、放弃哪个。 |
| **场景深潜** | 机会指标、年度趋势、来源结构、供给信号（仓库/Star/论文/Show HN）与证据摘录。 |
| **收藏工作区** | 收藏场景与备注，随后让 Agent 对比收藏清单。 |
| **视频** | 按场景生成 YouTube/B站外部搜索链接（明确标注非证据库）。 |

面板与回答均双语；人力/成本为**启发式估算**，不会当成市场事实。

![场景深潜](docs/screenshots/feature-detail.png)

![决策向导](docs/screenshots/feature-wizard.png)

## 架构

```
规划 prompt ──► LLM 第 1 次 ──► 严格 JSON 计划（意图、场景、工具）
                                     │
                        离线工具（catalog / ranking / scenario / compare / evidence / search）
                                     │
作答 prompt ──► LLM 第 2 次 ──► 一句话建议 + 说明 + 行动 + 风险
                                     │
                 运行时附加指标/排名/证据 → 对话卡片 + PDF
```

Agent 行为定义在 **[skills/openecrs_agent.md](skills/openecrs_agent.md)**，由 `code/agent_prompts.py` 渲染成规划/作答 prompt。模型只负责措辞，数据真实性由运行时保证。

## 快速开始

```bash
# Python 3.11+（已在 3.14 / macOS 验证）
pip install -r requirements.txt        # pandas 只在重建 data.json 时需要

python code/agent_app.py --open        # -> http://127.0.0.1:8765
```

macOS 也可以直接双击 **`openecrs.command`**。

首次启动界面会提示需要 LLM。打开 **设置**，二选一：

### API 模式（OpenAI 兼容）

| 服务 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义 DashScope 兼容模式 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | 本地模型名，Key 随意 |

填 Key → 「测试连接」→「保存」。Key 只保存在本机 `outputs/agent_ui/settings.json`（0600）；也支持 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `LLM_API_KEY` 以及 `LLM_BASE_URL` / `LLM_MODEL`。

### 模型切换

顶栏的胶囊按钮显示当前模型配置，点击即可一键切换：列出所有已保存的配置（API Key 或本地适配器），标记当前项，并提供：

- **+ 添加模型**：新增一个 API 或本地配置（各自保存独立的 Key/路径）；
- **设置**：编辑或删除当前配置。

输入框右侧（发送按钮旁）也有同一个切换按钮，可在对话中随时切模型。
切换立即对下一条回答生效；配置保存在 `outputs/agent_ui/settings.json`（接口返回时 Key 已脱敏）。
如果选中的配置不可用，界面会显示引导横幅，而不是静默回退。

![模型切换](docs/screenshots/model-switcher.png)

### 本地微调模式

```bash
pip install -r requirements-lora.txt
# 把 Qwen2.5-3B-Instruct 权重放到 models/Qwen2.5-3B-Instruct
# 包内试训适配器在 outputs/lora/adapter_pilot
```

设置 → **本地微调**：填写基座模型路径与适配器路径 → 测试 → 保存。CPU 推理较慢，推荐 GPU。该适配器由 160 条伪标签、24 步试训得到，仅用于验证训练/推理链路，不代表准确率。

## Agent Skill

完整技能定义（角色、数据口径、工具、工作流、输出规则、护栏）见
[`skills/openecrs_agent.md`](skills/openecrs_agent.md)，与 `agent_prompts.py` 使用同一份技能文本，保证 API 与本地模型行为一致。

## 程序化调用

```bash
curl -s http://127.0.0.1:8765/api/chat -H 'Content-Type: application/json' \
  -d '{"session":"demo","message":"哪个场景最值得优先做？","lang":"zh"}'

curl -s -X POST http://127.0.0.1:8765/api/pdf -H 'Content-Type: application/json' \
  -d '{"session":"demo","lang":"zh"}' -o 建议书.pdf
```

| 接口 | 说明 |
|---|---|
| `POST /api/chat` | `{session, message, lang}` → 回答（建议、说明、指标、排名、对比、证据、行动、风险、引擎信息、Agent 过程） |
| `POST /api/pdf` | `{session, lang}` → `application/pdf` 建议书 |
| `GET/POST /api/settings` | 读取（Key 脱敏）/ 保存 LLM 设置 |
| `POST /api/test` | 测试当前后端 |
| `GET /api/health` | 服务、LLM 就绪状态、数据与 PDF 后端 |
| `GET /api/data` | 界面使用的紧凑数据集 |

未配置 LLM 时，`/api/chat` 返回 **HTTP 428** 与 `{"code": "llm_required", "hint": ...}` —— 绝不回退到模板回答。

## 证据库

快照 **2026-11-20**：52,007 条原始记录 → 45,306 条清洗记录（Hacker News、GitHub、arXiv、Stack Overflow、Product Hunt）→ 19,621 个需求/供给单元 → 15,525 条需求单元 → 2,848 条高置信场景样本（18.34%）。15,525 条证据审查、162 条四门机会、`outputs/agent_ui/data.json` 内置 72 条原文证据。

机会总分前五：安全合规与隐私 **62.41**；多智能体与任务编排 **57.86**；知识管理与文档问答 **57.28**；编程与代码智能 **56.20**；办公协作与会议效率 **48.98**。

产出证据库的分析流水线（采集、清洗、弱监督、评分、证据审查）不在本仓库内；本仓库只包含 Agent 运行时与重建 `data.json` 所需的对账表。

## 目录结构

```
OpenECRS/
├─ code/
│  ├─ agent_app.py        # HTTP 服务 + 静态界面 + API
│  ├─ agent_core.py       # Agent 循环：规划 → 工具 → 作答、会话记忆、过程记录
│  ├─ agent_prompts.py    # Agent Skill → 规划/作答 prompt（中英）
│  ├─ agent_tools.py      # 场景数据、排名、对比、证据检索等离线工具
│  ├─ agent_settings.py   # API / 本地后端设置、旧配置迁移、就绪检查
│  ├─ agent_providers.py  # 后端解析与连通性测试
│  ├─ agent_llm.py        # OpenAI 兼容 HTTP 客户端
│  ├─ agent_local.py      # 本地 Qwen2.5 + LoRA 后端（可选）
│  ├─ agent_pdf.py        # A4 建议书模板与本地 Chromium 渲染
│  ├─ agent_ui.html       # 单文件双语界面（无构建、无 CDN）
│  ├─ agent_ui_data.py    # 重建 outputs/agent_ui/data.json
│  └─ test_*.py           # 工具 / 核心 / HTTP 测试（18 项）
├─ skills/openecrs_agent.md
├─ outputs/agent_ui/data.json
├─ outputs/tables/        # 对账表（评分、证据审查、质量卡）
├─ docs/screenshots、docs/examples
├─ openecrs.command、requirements.txt、requirements-lora.txt
└─ README.md / README.zh-CN.md
```

## 语言

底部个人信息卡会展开一个紧凑、无边框的弹层：**回答设置、设置、使用说明、数据说明**。语言与回答视角统一放在 **设置 → 偏好设置**（回答设置会直接跳到该页），模型表单保持干净。语言选择器提供 **跟随系统**（默认）、English、中文、日本語、Español。“跟随系统”会读取 `navigator.language`（zh/ja/es，否则英文），选择会本地记忆；每次对话与功能请求都会携带语言，回答、prompt 与标签随之切换。ja/es 的 PDF 目前回退为英文模板。

## 角色

侧边栏的**回答视角**会改变规划与写作口吻：`创业`（可行性、MVP、2–4 周验证）、`大厂`（合规、组织协同、汇报材料）、`投资`（市场、竞争、证据强度、下行风险）、`产品`（用户痛点、路线图、指标、取舍）。角色随每次对话发送，并体现在回答中。

## 自检

```bash
cd code
python -m unittest test_agent_tools test_agent_core test_agent_http -v   # 18 项
```

覆盖离线工具、规划/作答校验（假 provider，含寒暄与角色）、未配置 LLM 的拒绝路径、HTTP 设置/测试/对话与功能端点（本地 mock OpenAI 端点）、模型配置切换、历史对话持久化、向导/PoC/组合算法、洞察聚合与视频链接，以及有浏览器时的 PDF 导出。

## 口径与局限

- 场景标签来自弱监督，不是人工全量标注。
- 来源偏差：Hacker News / GitHub 占比较高，不能当作真实市场占比。
- 供给成熟度用仓库/Star/论文/Show HN 近似；付费意愿来自文本信号。
- 规则置信度**未经人工校准**（无金标），智能体会在每份建议书中注明。
- 同一问题在不同轮次措辞可能不同；数字与证据是确定性的。
- 公开数据版权归各平台与作者所有。

## 许可与署名

仓库代码供研究与评估使用；引用的第三方数据片段仅用于证据溯源，版权归原作者所有。
## 本地版说明

本机这份 OpenECRS 额外保留了试训 LoRA 适配器 `outputs/lora/adapter_pilot/`，可用于「本地微调」后端（GitHub 仓库中未包含；仍需自行准备 Qwen2.5-3B-Instruct 基座权重）。

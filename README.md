# 航友（Hangyou）

> 面向大学生的课程资料智能问答与复习系统 —— 把"看资料"变成"问资料、测自己、记得住"。

## 它是什么

把期末周看不完的课件 PDF / DOCX / PPTX / EPUB 拖进来：

1. **问资料**：像问学长一样提问。回答分两层——黄底部分出自你的资料（带页码引用，点击核对原文），灰底部分是模型通识补充（明确标注，不冒充资料）；
2. **测自己**：从资料自动生成选择题测验，即时判分讲解析；
3. **记得住**：答错的题一键转闪卡，FSRS 遗忘曲线算法在你快忘掉的那天让它重现。支持考试冲刺模式（按考试日期 + 每日预算重排队列，错题优先，考前二刷）。

本地优先：数据全部存在本机 SQLite，不上传任何云数据库；仅提问/出题时调用大模型 API。

## 技术栈

- **前端**：React 19 + TypeScript + Vite + Tailwind CSS 4 + ts-fsrs（像素风格主题 + 昼夜切换）
- **后端**：Python 3.12 + FastAPI + SQLAlchemy + SQLite
- **检索**：BM25（rank-bm25）+ 向量（sentence-transformers MiniLM，本地 384 维）+ RRF 融合
- **LLM**：OpenAI 兼容协议（DeepSeek / GLM / Qwen 可切换），Pydantic 结构化输出约束

## 快速开始

### 1. 启动后端（默认 :8000）

```bash
cd backend
python -m venv venv && venv\Scripts\activate    # Windows
pip install -r requirements.txt
# API 配置请在网页「我的 → AI 服务设置」填写；.env 不再作为运行时回退
python run.py
```

> 首次启动会自动下载嵌入模型（约 90MB，需联网/代理；此后离线可用）。

### 2. 启动前端（默认 :5173）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173；首次进行问答、测验或讲解前，请在「我的 → AI 服务设置」填写接口地址、模型名与 API Key。

## 项目结构

```
├── frontend/          # React 前端（资料库/问答/讲解/测验/复习/统计）
├── backend/           # FastAPI 后端（解析/检索/LLM/复习计划/统计）
│   ├── app/api/       # REST 接口层
│   ├── app/core/      # parser 多格式解析 / chunker 分块 / retrieval 检索 / llm / prompts
│   ├── tests/         # pytest 单元 + 接口测试（31 项）
│   └── data/          # SQLite 库 + 上传原件（运行时生成）
├── docs/              # 开发文档（含课程交付版）与调研
├── AGENTS.md          # 协作规范
└── HANDOFF.md         # 交接状态
```

## 测试

```bash
cd backend && python -m pytest tests -q   # 31 项测试
cd frontend && npm run build              # 类型检查 + 构建
```

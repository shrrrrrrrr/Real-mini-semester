# 参考项目调研与产品线提案（2026-09-04）

> 本文档记录对用户提供的 20 个 GitHub 参考仓库的 README 调研结果，以及据此提出的产品功能线提案。
> 产品线提案**尚未经用户确认**，确认后以用户意见为准。后续 Agent 请先阅读根目录 [AGENTS.md](../AGENTS.md)。

调研结果：20 个项目中 19 个成功读取；`VIJAYAPANDIANT/smart-study-planner-reference` 返回 404（用户存在但无此仓库，应为已删除或改名），需用户补充替代链接或剔除。

---

## A. 资料问答 / RAG（5 个）

### A1. THU-MAIC/OpenMAIC

- **定位**：清华 MAIC 团队的开源多智能体交互式课堂平台，把任意主题或文档一键生成带 AI 老师、AI 同学的完整交互课程。
- **核心功能（README 原文 + 中文）**：
  - "One-click lesson generation — Describe a topic or attach your materials; the AI builds a full lesson in minutes"（一键生成课程：描述主题或附上材料，AI 几分钟内构建完整课程）
  - "Multi-agent classroom — AI teachers and peers lecture, discuss, and interact with you in real time"（多智能体课堂：AI 老师与同伴实时授课、讨论、互动）
  - "Rich scene types — Slides, quizzes, interactive HTML simulations, and project-based learning (PBL)"（丰富场景类型：幻灯片、测验、交互式 HTML 模拟、项目式学习）
  - "Whiteboard & TTS — Agents draw diagrams, write formulas, and explain out loud"（白板与语音合成：智能体画图、写公式并口头讲解）
  - "Export anywhere — Download editable .pptx slides or interactive .html pages"（到处导出：可编辑 .pptx 或交互式 .html）
  - Deep Interactive Mode 五类交互 UI："3D Visualization / Simulation / Game / Mind Map / Online Programming"（3D 可视化、模拟、游戏、思维导图、在线编程）
  - v1.0.0 Agent workbench："chat with an agent that plans your curriculum, builds and revises every page"（对话式智能体规划课程、构建并修改每一页）+ "20 built-in skills"（20 个内置技能）
- **设计/界面**：课堂播放页 + 首页生成入口双页面结构；深色模式（"Easy on the eyes for late-night study sessions"）；响应式；12 种语言 i18n。
- **用法**：`pnpm install` → 填 LLM API key → `pnpm dev`；支持 Vercel 一键部署；可选 Docker Compose + Postgres。
- **技术栈**：Next.js 16 + React 19 + TypeScript + Tailwind 4；LangGraph 多智能体编排；shadcn/ui；PostgreSQL（可选）；TTS/ASR/图像/搜索 provider 中立（含 Ollama 本地）。MIT 协议。
- **借鉴点**：
  1. 两阶段生成管线（Outline → Scenes）：先出可编辑大纲再生成内容，用户可中途干预，适合控制 AI 输出质量；
  2. 课程 DSL 与渲染器分离，数据契约与 UI 解耦；
  3. 按"场景类型"（幻灯片/测验/互动/PBL）组织学习内容，体验远超纯聊天。

### A2. santanu2908/chat-with-pdf-rag

- **定位**：极简 PDF 问答 RAG 服务，从零手写（无 LangChain），答案带引用来源分块。
- **核心功能**：
  - "Upload a PDF, ask questions, get answers grounded in the document with cited source chunks"（上传 PDF 提问，答案基于文档并附引用分块）
  - "FAISS + BM25 hybrid search (RRF)"（向量 + 关键词混合检索，倒数排名融合）
  - "cross-encoder rerank"（二阶段重排提高精度）
  - "POST /query/stream — same input, but returns SSE events"（流式 SSE 响应）
  - "Conversation memory — An in-memory session store lets users ask follow-up questions"（会话记忆支持追问）
- **设计/工程决策**："Sources are returned to the user separately, not formatted into the answer — this keeps the LLM from hallucinating citations"（来源与回答分离返回，防止 LLM 编造引用）。无前端，纯 API + Swagger UI；附 19 题自动评测脚本。
- **技术栈**：FastAPI + pypdf + sentence-transformers（all-MiniLM-L6-v2，本地免费）+ FAISS + rank-bm25 + cross-encoder 重排；LLM 一键切换 Groq/OpenAI/Anthropic。
- **借鉴点**：
  1. 混合检索 + RRF + 重排的三段式检索架构，附 v1→v3 失败案例演进记录；
  2. "guarded-slots" 重排策略：保底粗排结果 + 重排只填最后槽位；
  3. 答案与来源分离 + "not in document" 拒答约束——课程问答防幻觉的关键设计。

### A3. AI-Projects-list/Full-Stack-RAG-based-Document-Q-A-System

- **定位**：Next.js + FastAPI 全栈 RAG 文档问答系统，PDF 上传后基于内容回答问题并附引用。
- **核心功能（README 无功能列表，按端点概括）**：
  - "POST /upload — Upload and chunk a PDF"（上传并分块 PDF）
  - "GET /documents — List all uploaded documents"（文档列表管理）
  - "POST /chat — Ask a question, get RAG answer"（RAG 问答，"Get an answer with referenced source chunks" 答案带引用来源分块）
- **设计**：无截图，仅 "Basic styling"；亮点是清晰的前后端目录结构（FileUpload 与 ChatInterface 组件分离，services/ 按 pdf_processor / rag_pipeline / vector_store 分层）。
- **技术栈**：Next.js + React + TS；FastAPI + LangChain + HuggingFace；flan-t5-base + all-MiniLM + ChromaDB，全本地零 API 成本。
- **借鉴点**：最小可跑的全栈 RAG 参考结构；免费本地模型组合适合学生项目跑通 demo。

### A4. amajji/chat-interface-with-react-and-rag-from-scratch（RAGBot）

- **定位**：React 聊天界面 + 从零手写 RAG 管线的双 Tab 仪表盘应用。
- **核心功能**：
  - "File Upload — Allows users to upload documents easily to the backend"（文件上传）
  - "Document Chunking — Automatically splits documents into smaller, manageable chunks"（自动分块）
  - "Embedding Generation / Similarity Search"（Embedding 生成与相似度检索）
  - "Customizable File Processing — Users can toggle whether files should be considered for processing through the take_into_account flag"（可开关的文件处理标记：用户选择哪些文档参与检索）
  - "Database Integration — Uses SQLite and SQLAlchemy for storing file metadata, chunk data, and processing status"（元数据/分块/处理状态入库）
- **设计/界面**：Chat Tab + Uploaded Files Tab 双 Tab 仪表盘，文件处理状态可视化表格。
- **技术栈**：FastAPI + SQLite + SQLAlchemy；React + Axios。
- **借鉴点**：
  1. "上传管理 + 聊天"双 Tab 信息架构，比单一聊天框更完整；
  2. take_into_account 标志：轻量的"课程资料勾选"交互原型；
  3. 处理状态（processing status）入库，为上传-解析-索引异步流程提供状态机基础。

### A5. Apyhtml20/PaperBrain

- **定位**：AI 学习助手——上传文档后可聊天、测验、讲解、总结、生成闪卡，带按用户隔离的文档管理。
- **核心功能**：
  - "General Chat — Study assistant backed by Qwen 2.5-72B"（通用学习助手聊天）
  - "RAG Mode — Ask questions directly about your uploaded documents"（RAG 文档问答）
  - "Quiz — Auto-generated multiple-choice quizzes on any topic"（自动生成多选题测验）
  - "Flashcards — Smart cards for active recall and memorization"（主动回忆式闪卡）
  - "Explain — Concept breakdowns at beginner / intermediate / advanced level"（概念按初/中/高级三级难度拆解）
  - "Summarize — Auto-summarize any text or uploaded document"（自动总结）
  - "Document Manager — Upload PDF, TXT, DOCX → indexed per user with isolation"（按用户隔离的文档管理）
  - "Auth — JWT-based register/login with per-user data separation"（JWT 注册登录）
  - "Profile & Stats — Quiz history, streaks, and progression tracking"（测验历史、连续打卡、进度追踪）
  - "Semantic Cache — Valky-backed cache that hits on meaning, not exact text"（按语义命中的缓存）
- **设计**：完整产品截图 + Mermaid 架构图 + 缓存时序图；Docker Compose 一键起全栈。
- **技术栈**：FastAPI + SQLite/SQLAlchemy + ChromaDB（hybrid BM25 + multilingual embeddings）+ LiteLLM 级联；React + Vite。
- **借鉴点**：
  1. "面向学习场景"的功能矩阵：Quiz / Flashcards / 分级 Explain + streaks 打卡，全部围绕上传文档生成——正是课程学习产品的核心闭环；
  2. 语义缓存层：同义问题直接命中缓存跳过 LLM，省成本毫秒响应；
  3. 全栈工程完整度（JWT 鉴权、按用户隔离、可观测性）可作为小学期作品的天花板参照。

---

## B. AI 学习内容与学习规划（5 个）

### B1. Kashif-Mustari/Smart-Student-Success-Agent

- **定位**：AI 学业导师，用多 Agent 帮学生做学习计划、备考、职业规划。
- **核心功能**：
  - "AI Study Planner Agent for custom timeline scheduling"（学习计划 Agent）
  - "Personalized Timelines: daily checklists distributed over weeks leading up to your exams"（按考试日期生成逐周每日清单；按 Beginner/Intermediate/Advanced 调整强度）
  - "Weak Topics Prioritization: shifts heavier study weight onto topics you flag as weak"（弱项话题加权）
  - "Interactive MCQs: dynamically generated multiple-choice tests featuring real-time visual feedback"（动态 MCQ 测验 + 逐题解析）
  - "Skills Gap Analysis"（技能差距分析与职业路线图）
  - "Progress Persistency: saves checked-off tasks locally in your browser"（勾选进度本地持久化）
  - "AI Academic Chatbot Assistant: persistent side-docked chatbot across all routes"（全局侧边栏学业聊天助手）
- **设计**："premium, glassmorphism-based dark theme dashboard"（玻璃拟态暗色仪表盘）；SVG 自绘图表。
- **技术栈**：React + Vite + Tailwind v4 / FastAPI + Pydantic / Gemini 2.5 Flash 结构化 JSON 输出；无数据库（localStorage）。
- **借鉴点**：
  1. 强制 LLM 输出 Pydantic/JSON schema，前端 UI 直接消费结构化数据；
  2. Demo Mode 离线兜底（无 Key 也能演示全部功能）；
  3. 单一暗色玻璃拟态主题统一观感，单人项目快速做出"高级感"。

### B2. zeeshanparwez/VidyaAI

- **定位**：面向师生的全栈教学平台，教师一键生成备课方案，学生获得自适应测验与学习计划。
- **核心功能**：
  - "AI-Generated Session Plan: structured 30-minute prep plan — key concepts, common misconceptions, step-by-step teaching flow"（一键生成结构化备课方案）
  - "Live Class Mode: distraction-free fullscreen view"（无干扰全屏授课模式）
  - "Analytics & Coverage Heatmap: visual heatmap of topic coverage... overlaid with quiz performance trends"（知识点覆盖热力图）
  - "Personalised Study Plan: after each quiz the AI adapts the student's study plan — highlighting weak topics"（测后自适应学习计划）
  - "Quiz with Instant Results & Flashcards: auto-generated flashcards for every question they got wrong"（错题自动生成闪卡）
  - "Admin Panel: user management, course roster, bulk CSV import"（管理端 + CSV 批量导入）
  - 7-Agent 流水线：Schedule→Syllabus→Planning→Content(RAG)→Feedback→Adaptive→Personalise，每个 Agent 的 input/output/reasoning 落库可审计
- **技术栈**：React 18 + Vite / FastAPI + SQLAlchemy + SQLite（9 表）/ JWT + bcrypt / LangGraph / 内存向量库 RAG。
- **借鉴点**：
  1. 把"AI 决策日志（agent_decisions 表）"作为可解释性卖点，能提升课程评审评价；
  2. seed 脚本 + 演示账号让评委 30 秒进入真实场景；
  3. 测验→错题闪卡→自适应复习的闭环，正是"课程学习"产品的学习环参考。

### B3. Man0dya/Tutor-AI

- **定位**：完整学习工作流 AI 导师系统——生成结构化课程内容→出题→批改反馈→进度追踪。
- **核心功能**：
  - "Structured lessons (overview → key concepts → examples → applications → tips → summary)"（六段式结构化课程内容）
  - "Bloom/difficulty-aware questions; MCQs auto-normalized to 4 clear options with mapped answers"（按布鲁姆分类/难度出题，MCQ 规范化为 4 选项）
  - "Feedback that teaches: concise explanations plus optional study suggestions, not just a score"（批改给出教学性反馈而非仅打分）
  - "Quicker results over time: similar topics reuse cached, verified material"（语义缓存复用生成结果）
  - "Track progress and recent activity on your dashboard"（进度仪表盘）
  - 三 Agent 架构：content_generator / question_setter / feedback_evaluator
- **技术栈**：React + Vite + TS + Chakra UI / FastAPI (Motor 异步 MongoDB) + JWT / Gemini + Atlas Vector Search / Stripe。
- **借鉴点**：
  1. "内容→测验→反馈→进度"是教科书式学习闭环，直接映射课程学习场景；
  2. 语义缓存三级降级（精确命中→相似命中→新生成落缓存）省 LLM 调用费；
  3. 免费额度 + 付费墙的产品化思路，小学期项目可只留限额提示。

### B4. devesh-69/student-task-tracker

- **定位**：带 AI 子任务拆解、自动清单识别与进度追踪的学生任务管理器，本地优先 SPA。
- **核心功能**：
  - "Smart Task Management: create, edit, delete tasks with title, description, deadline, and progress tracking"（任务 CRUD + 截止日期 + 进度）
  - "Auto-Checklist Detection: type numbered lists (1., 2., 3.) - they automatically become interactive checkboxes"（输入编号列表自动变交互清单）
  - "Auto-Progress Tracking: progress calculated automatically from checked items (2/4 checked = 50%)"（勾选自动算进度百分比）
  - "Thread-Based Activity Logs: comprehensive history... persistent even after task deletion"（活动日志独立持久化）
  - "AI Assistant: intelligent task breakdowns powered by Google Gemini"（AI 拆解复杂任务为子步骤）
  - "Celebration Effects: confetti animation when you reach 100%"（100% 完成时彩带庆祝）
- **设计**：玻璃拟态 + 渐变现代 UI；无障碍（语义 HTML + 键盘导航）；危险操作二次确认 + 可撤销。
- **技术栈**：React 19 + TS + Vite + Tailwind / Gemini / localStorage。
- **借鉴点**：
  1. "自动清单识别 + 勾选算进度"零成本提升输入体验；
  2. 无 Key 可用的降级设计（AI 功能可选而非必需）；
  3. 活动日志独立于任务持久化，为"学习过程留痕"提供数据基础。

### B5. UAnirudh/IntelliPlan

- **定位**：学生 AI 规划器——从 Canvas 等 6 个 LMS 拉取作业、AI 评分排优先级、生成周学习计划并同步日历，配自适应 AI 导师 Plani。
- **核心功能**：
  - "Notion-style kanban board — Overdue, Today, Upcoming... sorted by AI priority scoring"（三栏看板 + AI 优先级排序）
  - "AI Scheduler: generates a complete multi-day study plan — focused work blocks with breaks — exports to Google Calendar"（生成含休息的块状日程并导出日历）
  - "Study & Learn: flashcards for active recall, key concepts, practice quiz, summaries + full spaced repetition system (SRS)"（闪卡/测验/摘要 + 间隔重复系统）
  - "Grade Modeler: simulate 'what if I get X% on my next test'"（成绩模拟器）
  - "Plani AI tutor... never just hands over answers; it builds understanding and checks comprehension"（苏格拉底式 AI 导师）
  - "Adaptive student model: learning profile, subject mastery (weighted moving average), mistake patterns, durable learner memory"（持久学习者模型：掌握度加权滑动平均、错误模式追踪）
  - "Push Notifications... even when the app is closed"（Web Push 截止提醒）
- **技术栈**：Flask + Jinja2 / PostgreSQL / Gemini 2.5 Flash（Groq 降级备援）/ Google Calendar API、Web Push / Sentry、PostHog。
- **借鉴点**：
  1. Plani 的"持久学习者模型"（掌握度、错误模式）是 AI 导师从聊天壳走向真差异化的范本；
  2. "LMS 只告诉你 what's due，不告诉你 when/what/how"的问题定义句式值得学习；
  3. LMS provider registry 注册表模式，集成面可渐进扩张（国内场景可换教务/雨课堂）。

---

## C. 计划与学业看板（3 个，其中 1 个 404）

### C1. shreyashankar/planner

- **定位**：基于 Google Tasks/Calendar 的命令行"智能排课"工具，自动决定何时学习、何时做作业。
- **核心功能**：
  - "List pending tasks / List upcoming events"（列出待办任务与即将到来的日程）
  - "Schedule a task/assignment and times to work on the task/assignment"（为任务安排工作时间；提供截止日期、预计总时长、单次最长专注时长、大致睡眠时间，算法保证"在截止前完成、不冲突其他日程、不让人过载"）
- **技术栈**：Python 2.7、Google Tasks/Calendar API。无 UI、无 AI。
- **借鉴点**：排课约束模型（截止时间 + 总工时 + 单次上限 + 睡眠窗口）是学习计划产品最核心的算法输入设计，可直接搬为表单字段；"不与既有日程冲突、不超载"双约束值得作为产品原则。

### C2. vincentaayush/BoilerTrack

- **定位**：Purdue 主题的学生学业仪表盘 MVP，本地追踪 GPA、课程、作业、待办与笔记资源。
- **核心功能**：
  - "Purdue-specific GPA scale and GPA calculations"（绩点计算）
  - "Current-semester GPA what-if planner"（期末 GPA 模拟）
  - "Editable assignment tracker connected to local courses"（与课程关联的作业追踪）
  - "Notes and resource link organization by course"（按课程组织笔记与资源链接）
  - "Local data import/export as JSON"（本地数据导入导出）
  - "Parses the transcript in the browser and saves only selected course records"（浏览器内解析成绩单，只存所选记录——隐私友好）
  - Demo Mode 与 Personal Mode 双模式（演示安全数据 vs 真实本地数据）
- **技术栈**：Next.js + React + TS + Tailwind + localStorage；部署 Vercel；数据层经 hooks 抽象，预留接 Supabase 路径。
- **借鉴点**：
  1. Demo/Personal 双模式 + 假数据，适合课堂演示与答辩；
  2. localStorage 经 hooks 抽象、预留 Supabase 无缝升级的渐进式架构，匹配"先本地后云端"节奏；
  3. 浏览器内解析导入（不上传原文）的隐私处理方式。

### C3. VIJAYAPANDIANT/smart-study-planner-reference

- **抓取失败**：仓库 404。用户 VIJAYAPANDIANT 存在（76 个公开仓库），但无此仓库，应为已删除、改名或从未公开。待用户补充替代链接或剔除。

---

## D. 闪卡与间隔重复（5 个）

### D1. openSRS-App/openSRS

- **定位**：开源间隔重复抽认卡系统，App + Web 全栈项目。
- **核心功能**（README 极简，概括）：抽认卡创建与复习、基于间隔重复算法的记忆调度、OAuth 账号体系。
- **技术栈**：React Native + GraphQL + MongoDB + OAuth。
- **借鉴点**：SRS 是"课程学习产品"的记忆科学理论支点；其多端复用方案与 AGENTS.md"Web 稳定后再出移动端"路径吻合。

### D2. SharmaMitchell/ZenDecks

- **定位**：支持 Markdown/LaTeX 的开源抽认卡 Web 应用，Quizlet/Anki 的免费替代品。
- **核心功能**：
  - "full Markdown and LaTeX support"（卡片正反面完整支持 Markdown 与 LaTeX——理科公式刚需）
  - "CSV import/export is fully supported, meaning that ZenDecks decks are compatible with Quizlet, Anki, Memrise, Excel"（CSV 互通导入导出）
  - "Google account sign-in"（Google 登录）
  - 数据模型：Decks → Cards(front/back) + Ratings(score 1-5) + Users 四层结构
  - "Keeps track of deck review progress for the session"（会话级复习进度追踪）
- **设计**：Framer Motion 过渡动画；Swiper.js 滑动翻卡学习模式。
- **技术栈**：TypeScript + React + Redux + SCSS / Firebase + Cloud Firestore。
- **借鉴点**：
  1. LaTeX/Markdown 卡片内容支持是大学理工课程场景的关键差异点；
  2. Decks/Cards/Ratings 集合设计与 CSV 生态互通（Anki/Quizlet 迁移成本归零）；
  3. Swiper 翻卡 + 会话进度的交互范式。

### D3. ChloeVPin/openlet

- **定位**：开源免费闪卡学习应用，用 FSRS 间隔重复算法排程复习。
- **核心功能**（README Main Capabilities 原文）：
  - "Five study modes: Use Flashcards, Learn, Write, Match, or Test mode."（五种学习模式）
  - "AI flashcard generation: Create study decks from lecture notes, textbooks, or plain text."（从讲义/教材生成卡片）
  - "Image occlusion: Mask selected areas of diagrams and medical images."（图像遮挡卡）
  - "Data import: Upload CSV files or paste multiple text items."（CSV 导入）
  - "Folders and classes: Share decks with public links and control access."（文件夹/班级共享卡组）
  - "Supabase authentication: Sign in with Google or GitHub."（OAuth 登录）
  - "Rate limiting: Use a Postgres token bucket on API routes."（API 限流）
- **技术栈**：TanStack Start（React 19 SSR）+ Tailwind v4 + Drizzle ORM + Supabase Postgres（RLS）+ Supabase Auth + Vercel；FSRS 自实现；AI 生成卡片。
- **借鉴点**：
  1. 与本项目最同构：面向学生的闪卡学习 Web 产品，技术选型（Supabase + Vercel + AI 生成）完全符合 AGENTS.md 部署规范，可参考其目录结构与 OAuth/SSR 方案；
  2. 卡组共享 + 班级权限控制，适配"课程学习"场景；
  3. Postgres 令牌桶限流，保护付费 LLM 接口的低成本防线。

### D4. Madlezz/Recall

- **定位**：本地优先、免注册的 FSRS 间隔重复应用（Tauri 桌面 + PWA），把复习做成习惯。
- **核心功能**（README Features 原文节选）：
  - "FSRS scheduling - Again / Hard / Good / Easy"（四档评分）
  - "Cloze deletion - {{c1::hidden text}}" + "Rich cards - Markdown, LaTeX, syntax-highlighted code"（填空卡/富文本卡）
  - "Anki import - .apkg (review history + FSRS state)"（Anki 迁移）
  - "FSRS optimizer from review history"（用复习历史优化参数）
  - "XP & levels … Achievements … Daily goal + confetti"（游戏化激励）
  - "Focus timer … Match game … Review calendar heatmap"（专注计时/日历热力图）
  - "Optional E2E cloud sync - AES-256-GCM + PBKDF2"（可选端到端同步）
- **设计**：Dark/Light/High-contrast 三主题；键盘优先（Space 翻面、1-4 评分、Ctrl+K 命令面板）；无障碍专项。
- **技术栈**：Tauri 2 + Rust（SQLite）；React 19 + Zustand + Dexie(IndexedDB)；FSRS 直接用 ts-fsrs。
- **借鉴点**：
  1. 完整激励体系（XP/等级/成就/连胜/每日目标 + 庆祝动效），"把复习变成习惯"的现成产品范式；
  2. 键盘优先交互 + 命令面板，代表闪卡类产品的高完成度交互标准；
  3. 统计维度（retention、leeches、overdue、热力图、30 天负载预测）可作学习看板字段清单。

### D5. open-spaced-repetition/ts-fsrs

- **定位**：TypeScript 版 FSRS 间隔重复算法工具库（官方开源实现）。
- **核心功能**：
  - 两个包："`ts-fsrs` | the scheduler for review flows"（FSRS v6 排程器）与 "`@open-spaced-repetition/binding` | the optimizer for parameter training and CSV conversion"（参数优化器）
  - `scheduler.repeat(card, date)` — "Preview all four possible outcomes before the user answers"（答题前预览四种结果）
  - `scheduler.next(card, date, Rating.Good)` — "Apply the final rating after the user has already answered"（评分后推进状态）
  - `createEmptyCard()` / `Rating` 枚举 / 卡片状态转移图
- **技术栈**：TypeScript + pnpm monorepo；Node ≥20；多语言 README（含简体中文）。
- **借鉴点**：
  1. 做"科学复习"功能的标准底座：3 个 API 即可接入完整 FSRS v6 排程，强烈建议直接引入而不自研；
  2. `repeat` 预览模式可在评分按钮上显示"下次复习间隔"，交互价值高；
  3. `binding` 包支持从复习历史优化个人化参数，后期差异化功能。

---

## E. 工程模板（2 个）

### E1. fastapi/full-stack-fastapi-template

- **定位**：FastAPI 官方维护的全栈模板（FastAPI + React + Postgres），开箱含认证、管理后台与部署方案。
- **核心能力（README Technology Stack and Features 原文节选）**：
  - "💾 PostgreSQL as the SQL database" + "🧰 SQLModel for the Python SQL database interactions (ORM)"
  - "🔒 Secure password hashing by default."（密码安全哈希）
  - "🔑 JWT (JSON Web Token) authentication."（JWT 认证）
  - "📫 Email-based password recovery."（邮件找回密码）
  - "✉️ React Email for email templates. + 📬 Mailpit for local email testing"（邮件模板与本地测试）
  - "☁️ FastAPI Cloud for deployment. + 🐋 Docker Compose … 📞 Traefik … automatic HTTPS"
  - "✅ Tests with Pytest. + 🏭 CI and CD based on GitHub Actions."
  - "🧪 Playwright for end-to-end testing. + 🤖 An automatically generated frontend client."
- **设计**：登录页、Admin 后台、Items 管理截图；深色模式（"🦇 Dark mode support"）。
- **借鉴点**：
  1. 现成工程能力最全的用户体系（JWT + 密码哈希 + 邮件找回 + 超级用户后台），若后端选 Python 可整体借用 backend 模式；
  2. 邮件链路整套方案（React Email + Mailpit），做找回密码/提醒邮件时照抄即可；
  3. CI/CD + E2E 的工程闭环是"可验证、可维护"交付标准的范本；注意与本项目 Vercel+Supabase 倾向的差异，只借模式不全栈照搬。

### E2. Buuntu/fastapi-react

- **定位**：cookiecutter 脚手架，一条命令生成带认证、管理后台、异步任务的 FastAPI+React 项目。
- **核心能力（README Features 原文节选）**：
  - "JWT authentication using OAuth2 'password flow' and PyJWT"（登录认证）
  - "Celery for background tasks and Redis as a message broker + Includes Flower for task monitoring"（后台任务与监控）
  - "Alembic for database migrations"（数据库迁移）
  - "Pytest for backend tests … transaction rollbacks after each test, and reusable Pytest fixtures"（测试体系）
  - "react-admin for the admin dashboard … same token based authentication as FastAPI backend"（管理后台）
  - "Nginx as a reverse proxy to allow backend/frontend on the same port"
- **借鉴点**：
  1. Celery 后台任务 + react-admin 管理后台的选型参考（批量生成卡片等异步场景）；
  2. conftest.py 测试 fixture 设计（每测试事务回滚 + 预置用户/超管/带 token 请求头）值得任何后端借鉴；
  3. 技术栈偏旧（Python 3.8、react-router v5），与 Vercel/Supabase 方向冲突——只借模式不借实现，官方 full-stack-fastapi-template 是更现代替代。

---

## 产品线提案（待用户确认）

### 核心主张

面向大学生的课程学习产品：**把课程资料（PDF 课件/讲义/教材）上传后，AI 帮助"快速学会"——可信问答（带出处）→ 测验收口 → 错题转闪卡 → FSRS 科学复习 → 看板追踪**。

对应学习科学闭环：**理解（问答/讲解）→ 验证（测验）→ 记忆（间隔复习）→ 反馈（看板）**。

### 功能线（6 个模块，按依赖顺序）

| # | 模块 | 内容 | 主要参考来源 |
|---|------|------|------------|
| 1 | 课程资料库 | 按课程组织；上传 PDF/TXT/DOCX；勾选哪些资料纳入问答范围；解析/索引状态可视化 | PaperBrain（Document Manager）、RAGBot（take_into_account、处理状态）、Full-Stack-RAG |
| 2 | 资料问答（RAG） | 围绕勾选资料提问；混合检索 + 重排；答案与来源片段分离展示；资料中没有答案时明确拒答；会话记忆支持追问 | chat-with-pdf-rag（混合检索、防幻觉引用）、PaperBrain（RAG Mode） |
| 3 | AI 讲解 | 摘要 + 初/中/高级分级讲解（轻量，不做完整课程生成） | PaperBrain（Explain/Summarize） |
| 4 | 智能测验 | 从勾选资料生成 MCQ；答题即时反馈 + 解析；记录答题历史 | PaperBrain（Quiz）、Tutor-AI（4 选项规范化、教学性反馈）、VidyaAI |
| 5 | 错题闪卡 + FSRS 复习 | 答错的题一键转闪卡；Again/Hard/Good/Easy 四档评分；ts-fsrs 排下次复习时间；评分按钮上预览间隔；手动加卡（Markdown/LaTeX） | VidyaAI（错题转闪卡）、ts-fsrs（排程库）、Recall/ZenDecks（交互与富文本卡）、openlet（AI 生成卡） |
| 6 | 学习看板 | 测验记录与正确率、待复习卡片数、复习热力图、连续打卡 | PaperBrain（Stats/Streaks）、Recall（热力图/统计字段清单） |

### 明确砍掉（避免功能蔓延）

- 多智能体课堂、白板、TTS、pptx/html 导出（OpenMAIC 的重课堂形态——工程量大且偏离"快速学习"主线）
- LMS/教务系统集成、成绩单解析、GPA 计算与预测（IntelliPlan/BoilerTrack——另一个产品方向）
- 教师端/管理端/班级协作共享（VidyaAI/openlet——先做单人学习体验）
- 付费墙、推送通知、移动端 App（AGENTS.md 要求 Web 稳定后再评估移动端）

### 版本划分建议（须与用户协商确认）

- **V1（最小闭环，可演示）**：模块 1 + 2 + 4 + 5——上传资料 → 问答 → 测验 → 错题卡 → 复习。这是产品核心价值链，缺一不可。
- **V1.5**：模块 3（AI 讲解）+ 模块 6（学习看板），增强留存与可感知进度。
- **V2 候选**：卡组导出/导入（CSV 互通 Anki/Quizlet）、错题驱动的个性化复习建议、连续打卡激励体系。

### 技术底座建议（符合 AGENTS.md 部署规范）

- 前端：React + TypeScript + Tailwind（Vite 或 Next.js），部署 **Vercel**
- 后端：FastAPI（RAG 管线：解析 → 分块 → 向量化 → 混合检索 → 重排 → LLM）
- 数据与鉴权：**Supabase**（Postgres + Auth），用户数据按 user_id 隔离
- 复习调度：直接引入 `ts-fsrs`（3 个 API），不自研算法
- LLM：结构化 JSON 输出（Pydantic schema 约束），LLM 提供商可切换；无 Key 时提供降级提示
- 工程：参考 full-stack-fastapi-template 的测试与迁移规范；语义缓存留作 V1.5 优化项

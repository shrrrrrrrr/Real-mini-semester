# Real mini semester — 项目交接文档

> 本文档是本项目的持续交接记录。每次完成一项可交付工作后，执行该工作的 Agent 必须更新“当前状态”“变更记录”“下一步工作”和“待用户操作”，使新 Agent 可以无需重新梳理上下文即可继续。
>
> **开始任何工作前，必须先阅读根目录的 [AGENTS.md](AGENTS.md)。** 其中保存本项目的全局协作规范；本文件只记录项目状态和临时交接信息，不重复长期规则。

## 1. 项目目标

待用户完成产品功能筛选后，开发一个面向大学生课程学习的全栈 Web 应用。项目暂定方向为“课程资料智能问答与学习规划助手”：围绕课程资料、可信问答、测验错题和学习计划形成闭环。

产品名称、最终功能范围、视觉方向和版本计划须在用户确认后补充；不得自行扩展为未确认的大型功能集合。

## 2. 全局规范入口

项目的长期开发规范已集中至 [AGENTS.md](AGENTS.md)，包括代码注释与架构、开源参考、Git 与交接、Vercel/Supabase、外部授权和版本管理要求。

后续 Agent 必须先阅读 `AGENTS.md`，再依据本文档的当前状态继续工作。

## 3. 当前状态

- 日期：2026-09-05（第三轮：北航品牌 + 书库 + 思维导图）
- 远程仓库 `main` 分支同步正常（git 推送需加 `-c http.proxy=127.0.0.1:10808`）。
- **产品更名「航友」**（原知源）；北航元素：左上角校徽（程序抠图 `frontend/src/assets/buaa-badge.png`，源图 C:\Users\shr\Desktop\UI\buaa photos\2025072815560858.png，另有 buaa-name.png / buaa-combo.png 备用）；昼夜背景 = 北航春景/夜景照片（提亮+25% 饱和+25% 像素化，`bg-day.png` / `bg-night.png`，素材处理脚本 `scripts/prep_assets.py`）。
- 本轮新增功能（全部 E2E 验证，提交 bc8dfe4）：
  1. **书库（全局共享）**：上传大部头（200MB 上限）后台索引；像素风占位封面（书名哈希对称图案）；问答页「📚 书库」勾选器把选中书并入 RAG 检索（引用显示《书名》）；书库页卡片式管理（删除/重新解析）；
  2. **今日签**：资料库页顶部每日一句 + emoji（文案在 `frontend/src/lib/quotes.ts`，用户可自行增删改）；
  3. **思维导图浮层**：SVG 横向树（根左枝右、贝塞尔连线、自实现 tidy 布局），顶部「🌳 导图」常驻按钮（与提问同款样式）；节点点击跳转、右键重命名、点外关闭；
  4. **追问反馈**：分支提问时顶部黄色横幅常驻提示"分支追问中（基于：…）"；「就此追问」按钮改短宽样式（btn-warn 黄底 + 大箭头）；
  5. chunks 表 owner 字段区分课程资料/书库（跨表引用无 FK，业务层保证完整性）；Document.chunks 关系改显式 primaryjoin。
- 测试：后端 41 项 pytest + e2e_books.py 真实 LLM 全过（含"不勾书拒答/勾书命中《图论教材》"断言）。
- 待用户提供：真实电子书资源（上传书库后可测大部头）。
  - 后端（FastAPI+SQLite）：多格式解析（PDF/DOCX/PPTX/EPUB/TXT/MD，扫描件拒收）→ 语义分块 → 本地 MiniLM 嵌入 → BM25+向量+RRF 检索 → 双层答案 SSE 流式（doc/general 分区 + 引用后端组装防编造）→ 测验生成判分 → 错题转卡 → FSRS 状态同步 → 冲刺/手动复习计划 → 统计。
  - 前端（React19+TS+Vite+Tailwind，像素风设计移植自用户参考站）：资料库/问答（双层渲染+引用抽屉）/讲解/测验/复习（三模式+四档评分带间隔预览+键盘快捷键+离线积压）/统计看板；昼夜主题切换（@property 全局插值 2100ms + 太阳月亮升降动画）。
  - 关键工程修复记录（答辩可讲的技术难点）：① torch 模型子线程首载死锁 → 主线程预热 + 双检锁；② HF 联网检查阻塞 → HF_HUB_OFFLINE；③ 旧 uvicorn reload 进程残留占 8000 端口导致"改代码不生效"假象。
- 待办：① ~~用户配置 LLM_API_KEY~~ **已完成（ElexAPI 网关：`https://elexapi.elex-tech.com/v1`，模型 glm-5.3，Key 已写入 backend/.env 不入库）**，真实 LLM 全链路联调通过：双层问答（分区+引用+多轮）、测验（3 题难度分布+判分+错题转卡）、讲解大纲（挂接片段）、统计，见 `backend/tests/e2e/e2e_llm.py`；② 前端 UI 打磨与真实课件数据测试；③ 回填开发文档占位字段（行数/截图/实测数据）；④ 答辩 PPT（含技术栈讲解，用户要求开发完毕后讲一遍"用了什么技术、为什么、为什么比别的好"）。

## 4. 参考项目（仅供调研）

完整调研结果（含各仓库功能原文摘录、设计亮点、借鉴点）见 [docs/reference-projects.md](docs/reference-projects.md)。

## 5. 变更记录

### 2026-09-02 — 初始化交接规范

- 从用户指定的 GitHub 仓库初始化本地工作区；远程仓库为空。
- 新建本交接文档，记录用户的全部长期开发规范、当前状态和调研参考方向。

### 2026-09-03 — 集中全局规范

- 新建 `AGENTS.md`，集中保存用户确认的长期全局协作规范。
- 本文档改为引用 `AGENTS.md`，后续仅维护项目状态与交接信息，避免规则重复和漂移。

### 2026-09-04 — 完成参考项目调研并提出产品线

- 通过并行子代理抓取 20 个参考仓库 README，整理功能、设计、用法与技术栈，落档 `docs/reference-projects.md`。
- `VIJAYAPANDIANT/smart-study-planner-reference` 仓库 404（用户存在但无此仓库），待用户补充替代链接或确认剔除。
- 提出聚焦产品线（资料 → 问答 → 测验 → 错题闪卡 → 看板）与 V1/V1.5/V2 版本划分建议，等待用户确认。

### 2026-09-04 — 按课程模板定稿产品开发文档

- 读取课程下发的《软件开发文档模板》（PDF，8 章节），据此生成 `docs/软件开发文档.md`。
- 文档为**设计定稿版**：需求（F01-F08）、四层架构、7 张表数据模型、4 个技术点详解（RRF 混合检索、LLM 结构化输出、FSRS 调度、SSE 流式）、测试方案（单元/接口/检索质量评估/E2E）、部署说明、答辩问答预案均已定稿，作为后续开发依据。
- 产品暂定名"知源"；代码行数、截图、实测数据、项目总结等待实现后回填。
- 用户后续需要答辩 PPT，尚未开始制作。

### 2026-09-05 — 需求讨论四轮并冻结 V1 需求基线

- 与用户逐轮确认：多格式支持（PDF/DOCX/PPTX/EPUB/TXT/MD，引用粒度跟格式走）、不做 Z-Library（版权 + 可信性原因，改双层知识源）、多分支提问 + 鸟瞰图谱（V1.5，数据库预留字段）、复习三模式 + 离线积压合并、PWA + Web Push + 邮件兜底、仅做 Web 版。
- 用户最终确认回答标准：**保留 ChatGPT 通识能力 + 上传文档为绝对可信源**，资料来源内容界面显著标注（底色高亮）；由此文档改版为"双层 RAG 问答"方案（一次 LLM 调用产出 doc/general 分区答案）。
- 重写 `docs/软件开发文档.md` 为**需求冻结版（V1）**：12 张表数据模型、12 项功能（F01-F12，F12 为 V1.5 预留）、4 个技术点、三层复习排程算法、测试方案。

### 2026-09-05 — 实现 V1 全栈应用并验证

- **架构决策（用户确认）**：本地优先——SQLite 单文件 + 本地原件存储，砍掉 Supabase/Auth/账号体系；LLM 走 OpenAI 兼容 API（联网 + Key）；仅 Web 版。
- 后端：`backend/app/`（api 路由 × 7 模块 / core：parser、chunker、indexer、retrieval、llm、prompts / models 12 表 / api_schemas 契约）；31 项 pytest 全通过。
- 前端：`frontend/src/`（6 页面 + AppShell + AnswerBlock 双层渲染组件 + lib：api(SSE)/fsrs/reviewPlan/theme/types）；`npm run build` 通过；像素风 UI 完整移植用户参考站（`C:\Users\shr\Desktop\Blogger`，只读未改）。
- E2E 验证：经 Vite 代理走完整链路（建课→上传→索引 3 chunks→SSE 问答→测验 502 优雅报错）。
- 三个实战级 bug 修复（对答辩极有价值，见"当前状态"）：线程死锁、HF 离线检查、端口残留进程。
- 提交 a3222d3 推送远程。

### 2026-09-05 — 真实 LLM 联调 + 第二轮功能迭代（用户 10 项改进）

- 用户配置 ElexAPI（glm-5.3）；真实 LLM 主链路 E2E 通过（双层问答/追问/测验/转卡/大纲/统计）。
- 用户提出 10 项交互改进并逐条确认方案后实施（详见"当前状态"清单），新增：profile API、GenTask 后台任务框架（生成不中断）、分支树接口（parent_message_id 树 + 重命名）、仅资料模式 prompt、节点展开讲解、测验/大纲历史接口。
- 前端：新增"我的"页（Profile.tsx，替代 Stats.tsx）；问答页大改（视口布局/浮层树/仅资料开关/分支追问）；讲解/测验页加历史侧栏与任务轮询；资料库加删除。
- 测试：后端 41 项 pytest 通过；新增 e2e_features.py 真实 LLM 验证 10 项新功能全过（含"仅资料模式资料外问题正确拒答""profile 读取永不返回完整 Key"两个关键断言）。
- 修复：datetime JSON 序列化（gen_tasks.result）、messages 自引用级联删除（ondelete=CASCADE）。
- 提交 a29ef23 推送远程。

### 2026-09-05 — 第三轮：北航品牌化 + 书库 + 思维导图（提交 bc8dfe4）

- 更名"航友"；北航校徽抠图（脚本 scripts/prep_assets.py，PIL 去纯色蓝背景）；
  昼夜背景照片像素化处理（提亮提饱 + 160 块像素化）。
- 书库：Book 表 + books API（像素风占位封面 make_cover、Form title 绑定）；
  chunks.owner 区分归属；问答 book_ids 勾选并入检索（doc_names 统一映射显示名）。
- 思维导图：MindMapOverlay.tsx 自实现横向 tidy 树布局 + 贝塞尔连线。
- 今日签：quotes.ts（40 条可编辑文案）。
- 追问反馈横幅 + 短宽按钮；导图按钮重摆顶部工具条。
- 修复：chunks 跨表引用 FK 约束冲突（去 FK + 显式 primaryjoin）、books Form title、documents and_ 导入。
- e2e_books.py 真实 LLM 全过。


### 2026-09-05 — 第四轮：可信引用、可解释计划与纵向对话分支（待提交）

- **引用跳转**：`AnswerBlock.tsx` 的 `[n]` 角标与“引用来源”按钮会打开右侧抽屉，显示后端原样返回的文件名、页码/章节定位和原文片段；抽屉明确说明定位不可由回答模型改写。
- **复习计划依据**：后端计划日新增 `reason` 契约，按测验错题、低稳定度、到期卡和考试倒计时生成短句；复习页增加“计划依据”展开区。
- **开发者选项**：`我的`页新增系统工作过程，说明上传解析、MiniLM+BM25+RRF、双层回答、后端引用和 FSRS 学习闭环，便于答辩讲解。
- **北航视觉与主题**：校徽背景和资料库/书库/讲解/测验/复习标题小标识统一为源图实测北航蓝 `#003f95` + 校徽；背景像素化从横向 160 格细化为 220 格并已重新生成。昼夜切换改为 760ms 同步交叉淡化，面板、文字、边框和背景使用同一时间轴，保留减少动态效果降级。
- **今日签**：资料库增加“↻ 换一条”；随机抽取时排除当前句，并以浏览器本地存储保留用户当天换出的内容。
- **对话分支**：树接口从“问题节点”改成与 `Message.parent_message_id` 同构的逐条消息树；前端为上→下展开、横向分叉、双向滚动。点击节点只回到原消息，点击回答下的“就此提问”才切入新分支；主对话仅展示根到当前分支回答的路径，旧分支不会删除，可从导图回看。
- **验证**：`frontend/npm run build` 通过；后端修改模块从 `backend` 目录导入通过。`python -m pytest tests -q` 已按 README 入口触发，但该环境未返回可读取的测试汇总；首次直接运行 `pytest -q` 因入口路径缺失而未收集测试，不应视为业务失败。

### 2026-09-05 — 第五轮：身份统一、API 显式配置与书库清理（待提交）

- **身份与图标**：问答、仅资料问答、讲解和节点展开讲解的系统提示词统一使用“航友”；FastAPI 标题、README 与依赖说明同步更名。浏览器标签页图标改为用户提供素材中处理出的北航校徽 `frontend/public/favicon.png`。
- **API 配置边界**：`llm_config_effective` 不再回退 `backend/.env`。问答、测验、讲解和“测试连接”均要求用户在“我的 → AI 服务设置”保存接口地址、模型名和 API Key；测试确认空配置返回全空，历史 `.env` Key 不会再被调用。
- **导图稳定性**：修复 SVG 节点悬停 CSS `transform` 覆盖节点定位 `transform` 的问题；节点点击不再发生高频跳动，只保留 120ms 透明度反馈。
- **北航视觉**：侧栏校徽容器明确设为实测北航蓝 `#003f95`；浏览器图标同步采用校徽。
- **书库**：经逐条核对后删除 4 本预设 `graph-textbook` 及对应索引/原文件，书库现为空。新上传书使用仅由蓝 `#247fb8` 与绿 `#75bfa6` 组成的稳定随机像素封面；书库页增加“改名/保存/取消”，改名同时刷新封面。
- **验证**：新增 API 配置和书名编辑回归测试；`npm run build` 通过，后端完整测试命令已执行且未返回失败信息；最终运行时检查确认 `book_count=0`、`strict_config={base_url: None, api_key: None, model: None}`。
## 6. 下一步工作

1. 用户上传真实电子书到书库，验证大部头索引与检索质量。
2. 复习页"载入今日计划"按钮（把 plan_days 接进复习队列）——遗留小项。
3. 回填 `docs/软件开发文档.md`：更名航友、新增书库/导图/今日签功能、行数、截图、检索实测数据、项目总结、安全说明。
4. 新手教程（用户明确后置）、答辩 PPT + 技术栈讲解。

## 7. 待用户操作

- 打开 http://localhost:5173 验收：①左上角校徽+航友 ②昼夜切换背景照片 ③今日签 ④书库上传（随便找个 PDF/EPUB 试）⑤问答页勾书提问 ⑥🌳 导图浮层 ⑦"就此追问"看横幅反馈。
- 语录不满意 → 改 `frontend/src/lib/quotes.ts`。
- 真实电子书资源就绪后上传书库测试。
### 2026-09-05 — 第六轮：Windows 与 Android 安装工程

- 继续工作前须先阅读根目录 `AGENTS.md`，本记录只说明当前状态。
- **跨端策略**：暂不做云同步。Windows 桌面端承载 FastAPI、SQLite、资料原件和 AI 配置；Android 只封装界面，通过同一 Wi-Fi 访问 Windows 服务。Android 的“我的 → 设备连接（安卓）”填写 `http://电脑局域网IP:8000/api`，Web 留空继续使用默认 `/api`。
- **Windows 工程**：新增 `backend/packaging/desktop_server.py`、`desktop/electron/`。Electron 启动时拉起 FastAPI 可执行文件，将数据放到当前用户可写目录，并以 `HOST=0.0.0.0`、`PORT=8000` 允许局域网 Android 访问。Windows 图标由北航校徽生成。
- **后端打包验证**：PyInstaller 已生成 `backend/dist/HangyouServer/HangyouServer.exe`（构建产物被 Git 忽略）；发现并修复启动器环境变量名称问题。已使用该 exe 在 `127.0.0.1:8010` 成功返回 `/api/health`：`{"ok":true,"llm_configured":false}`。
- **Android 工程**：在 `frontend/android/` 生成 Capacitor 工程，设置应用名“航友”、包名 `cn.buaa.hangyou`、北航校徽启动图标、网络权限与局域网 HTTP 访问；APK 已生成在 `frontend/android/app/build/outputs/apk/debug/app-debug.apk`（构建产物不入库）。本机 SDK 路径写入 `frontend/android/local.properties`，该文件已被 Git 忽略。
- **Windows 安装器状态**：Electron 已完成 `win-unpacked` 应用目录封装，但 NSIS 安装器下载构建组件时被当前机器的 `self-signed certificate in certificate chain` 拦截。未关闭 TLS 校验绕过风险；网络证书恢复信任后，在 `desktop/electron/` 运行 `npm run dist:win` 即可补出安装程序。
- **文档**：新增 `docs/INSTALLATION.md`，记录使用方式、Windows/Android 构建位置和局域网边界。
### 2026-09-05 — 第七轮：答辩版软件开发文档

- 基于用户提供的《软件开发文档模板.docx》完成 docs/航友软件开发文档 答辩版.docx。内容已按实际实现改写：本地 SQLite 架构、资料解析与 RRF、可信引用、LLM 配置边界、分支导图、书库、FSRS 计划、Windows/Android 现状和已完成验证。
- 以 Word 成功导出 PDF 预览，确认文件可由 Word 打开。后续答辩前应补入真实课程资料截图、案例问答截图和检索评测数据。
### 2026-09-05 — 第八轮：答辩架构示意图

- 新增 docs/assets/hangyou-system-architecture.svg：按真实系统调用链绘制前端、FastAPI、资料理解管线、SQLite/本地文件与外部 AI 服务；使用 SVG 矢量中文字体和路径连线，可直接插入答辩文档或 PPT。

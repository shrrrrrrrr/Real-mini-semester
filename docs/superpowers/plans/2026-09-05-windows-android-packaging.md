# 航友 Windows 与 Android 打包实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可运行的 Windows 桌面安装包，并建立 Android APK 工程，使安卓设备可通过同一 Wi-Fi 连接 Windows 端后端。

**Architecture:** Windows 版使用 Electron 承载 React 界面，并启动经 PyInstaller 打包的 FastAPI 本地服务，前端请求固定指向回环地址。Android 版使用 Capacitor 承载同一 React 构建产物，前端在“我的”页保存局域网后端地址；不引入云同步或远程数据库。

**Tech Stack:** React/Vite、FastAPI/SQLite、Electron Builder、PyInstaller、Capacitor Android。

**Spec:** 用户于 2026-09-05 确认：仅制作 Windows 和 Android 安装包；Android 与 Windows 后端通过同一 Wi-Fi 连接；暂不做 iOS 与跨设备同步。

## Global Constraints

- 保持本地 SQLite、资料原件和 API Key 的既有本地优先边界。
- Windows 版必须不依赖开发服务器；Android 版必须明确提示局域网后端地址与连通条件。
- iOS、云部署、账号体系和跨设备同步不在本轮范围内。
- 每项完整能力验证后更新根目录 HANDOFF.md，并以语义化提交推送 main。

---

### Task 1: 统一可配置的 API 基址

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/Profile.tsx`
- Test: `frontend` production build

- [ ] 让 REST 与 SSE 共用 API 基址解析：Web 默认 `/api`，Electron 使用构建环境变量，Android 可保存局域网地址。
- [ ] 在“我的”页增加设备连接地址输入与连通性说明；地址只保存本机设备，不同步。
- [ ] 运行 `npm run build` 验证 Web 默认路径未回归。

### Task 2: Windows 本地桌面版与安装器

**Files:**
- Create: `desktop/electron/main.cjs`
- Create: `desktop/electron/preload.cjs`
- Create: `desktop/electron/package.json`
- Create: `backend/packaging/desktop_server.py`
- Modify: `backend/app/config.py`
- Test: `desktop/electron` 打包命令和 Windows 安装器启动检查

- [ ] 将 FastAPI 数据目录改为支持桌面运行目录，避免写入程序安装目录。
- [ ] 用 PyInstaller 生成后端可执行目录，并由 Electron 主进程启动/等待健康检查/退出时清理。
- [ ] 构建 Electron NSIS 安装器，图标使用北航校徽。

### Task 3: Android Capacitor 工程与 APK

**Files:**
- Create: `frontend/capacitor.config.ts`
- Create: `frontend/android/`（Capacitor 生成）
- Modify: `frontend/package.json`
- Test: `npx cap sync android`、Gradle Debug APK 构建

- [ ] 初始化 Capacitor Android，应用名称为“航友”，使用北航校徽图标。
- [ ] 生成移动构建产物并同步到 Android 原生工程。
- [ ] 构建 debug APK；若本机缺少 Android SDK 或 JDK，记录精确缺失项并停在可恢复状态。

### Task 4: 交接、验证与发布记录

**Files:**
- Modify: `HANDOFF.md`
- Modify: `README.md`

- [ ] 记录 Windows 安装、Android APK、局域网连接方法和实际产物路径。
- [ ] 运行前端构建、后端测试与 Git 差异检查。
- [ ] 提交并推送完成的可交付物。

# 航友 Windows 与 Android 安装说明

## 使用方式

- **Windows 桌面端**：安装后直接打开“航友”。它会自动启动本机学习服务；资料、课程、问答和 AI 配置存放在当前 Windows 用户目录，不在安装目录中。
- **Android 端**：先在 Windows 上打开“航友”，再让手机和电脑连接同一 Wi-Fi。进入 Android 应用的“我的 → 设备连接（安卓）”，填写 `http://电脑局域网IP:8000/api`，例如 `http://192.168.1.8:8000/api`。
- **首次局域网访问**：若 Windows 防火墙弹出提示，允许“航友”在专用网络通信；不要在公共网络中开放。

## 构建约定

Windows 打包前，依次完成：

1. 在 `backend/` 运行 PyInstaller，生成 `dist/HangyouServer/HangyouServer.exe`。
2. 在 `frontend/` 以 `VITE_API_BASE_URL=http://127.0.0.1:8000/api` 构建，并将 `dist/` 复制到 `desktop/electron/frontend-dist/`。
3. 在 `desktop/electron/` 运行 `npm run dist:win`，输出 NSIS 安装程序。

Android 打包前，先在 `frontend/` 用默认配置构建并运行 `npx cap sync android`；随后在 `frontend/android/` 运行 `gradlew.bat assembleDebug`，输出 `app/build/outputs/apk/debug/app-debug.apk`。

## 边界

当前 Android 安装包仅包含界面，AI、资料检索与本地数据仍由 Windows 桌面端提供。因此它不是跨设备同步方案，也不能脱离已打开的 Windows 端独立问答。

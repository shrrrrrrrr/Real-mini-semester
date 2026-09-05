/**
 * 航友 Windows 桌面端启动器。
 *
 * Electron 只负责窗口与后端进程生命周期；学习数据与 AI 调用仍由原 FastAPI 服务处理。
 * 这样 Web、桌面和 Android 三端可以复用同一套业务代码，避免为了桌面版复制后端逻辑。
 */
const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('node:child_process')
const path = require('node:path')

let backendProcess = null

function backendExecutable() {
  // 打包后后端位于 extraResources；开发调试时保持相对仓库路径，便于定位问题。
  return app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'HangyouServer', 'HangyouServer.exe')
    : path.join(__dirname, '..', '..', 'backend', 'dist', 'HangyouServer', 'HangyouServer.exe')
}

function startBackend() {
  const dataDir = path.join(app.getPath('userData'), 'data')
  backendProcess = spawn(backendExecutable(), [], {
    windowsHide: true,
    env: {
      ...process.env,
      // 监听全部网卡，Android 才能通过同一 Wi-Fi 访问 Windows 后端。
      HOST: '0.0.0.0',
      PORT: '8000',
      HANGYOU_DATA_DIR: dataDir,
    },
  })
}

async function waitForBackend() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/health')
      if (response.ok) return
    } catch {
      // 后端与本地嵌入模型首次启动可能较慢，短暂重试即可。
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error('本地学习服务未能在 15 秒内启动。')
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    title: '航友',
    webPreferences: {
      // 渲染页面不需要 Node 权限，保持网页端相同的安全边界。
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  window.loadFile(path.join(__dirname, 'frontend-dist', 'index.html'))
}

app.whenReady().then(async () => {
  try {
    startBackend()
    await waitForBackend()
    createWindow()
  } catch (error) {
    dialog.showErrorBox('航友启动失败', `${error.message}\n\n请重新打开应用；若问题持续，请查看 HANDOFF.md 中的排查说明。`)
    app.quit()
  }
})

app.on('before-quit', () => {
  // 后端只服务于本次桌面应用会话，退出窗口时一并结束，避免残留占用端口。
  backendProcess?.kill()
})

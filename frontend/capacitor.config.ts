import type { CapacitorConfig } from '@capacitor/cli'

/**
 * Android 只打包前端界面，学习服务仍由同一 Wi-Fi 下的 Windows 桌面端提供。
 * 用户在“我的 → 设备连接”中填写 Windows 的局域网地址，不在安装包内保存任何密钥。
 */
const config: CapacitorConfig = {
  appId: 'cn.buaa.hangyou',
  appName: '航友',
  webDir: 'dist',
  server: {
    androidScheme: 'http',
  },
}

export default config

/**
 * 像素风主题切换按钮：太阳/月亮升降 + 星星渐显。
 * 交互细节与视觉完全移植自参考站（.theme-toggle）。
 */

import { useTheme } from '../lib/theme'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label={theme === 'dark' ? '切换浅色主题' : '切换深色主题'}
      title="切换主题"
      onClick={toggleTheme}
    >
      <span className="theme-stars" aria-hidden="true">
        <i></i>
        <i></i>
        <i></i>
        <i></i>
      </span>
      <span className="theme-sun" aria-hidden="true"></span>
      <span className="theme-moon" aria-hidden="true"></span>
    </button>
  )
}

/**
 * 主题上下文：昼夜切换（移植自参考站的主题引擎）。
 *
 * 关键机制（与参考站一致）：
 * 1. 颜色变量经 @property 注册，切换时在根节点一次性插值（760ms 全站同步变色）；
 * 2. 点击后先挂 .theme-transitioning 类，隔两帧再改 data-theme，
 *    保证背景/面板/文字在同一帧开始变色，避免逐层过渡的错拍感；
 * 3. 持久化到 localStorage，首次访问跟随系统 prefers-color-scheme；
 * 4. 尊重系统"减少动态效果"设置（CSS 层已降级，JS 层不需额外处理）。
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

const THEME_KEY = 'zhiyuan-theme'
const THEME_TRANSITION_MS = 760

const ThemeContext = createContext<{
  theme: Theme
  toggleTheme: () => void
}>({ theme: 'light', toggleTheme: () => {} })

function readInitialTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readInitialTheme)

  // 初始化：把读取的主题立刻写到根节点（首次渲染前，无过渡）
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleTheme = useCallback(() => {
    const root = document.documentElement
    const next: Theme = root.dataset.theme === 'dark' ? 'light' : 'dark'

    // 先挂过渡类 → 等两帧让浏览器绘制起始状态 → 再切换 data-theme
    // 这样所有颜色变量在同一帧开始插值，背景、面板、文字同步渐变
    root.classList.add('theme-transitioning')
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        root.dataset.theme = next
        localStorage.setItem(THEME_KEY, next)
        setTheme(next)
        // 过渡结束后摘掉类，避免影响后续局部颜色修改
        setTimeout(() => root.classList.remove('theme-transitioning'), THEME_TRANSITION_MS + 100)
      })
    })
  }, [])

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}

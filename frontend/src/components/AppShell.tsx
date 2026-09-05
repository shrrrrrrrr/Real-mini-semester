/**
 * 应用外壳：左侧像素风导航栏（桌面）/ 底栏（移动）+ 场景背景 + 路由出口。
 */

import { NavLink, Outlet } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'

const NAV_ITEMS = [
  { to: '/library', label: '资料库', num: '01' },
  { to: '/chat', label: '问答', num: '02' },
  { to: '/explain', label: '讲解', num: '03' },
  { to: '/quiz', label: '测验', num: '04' },
  { to: '/review', label: '复习', num: '05' },
]

export function AppShell() {
  return (
    <>
      {/* 像素网格背景 + 夜间星星（昼夜切换时渐显） */}
      <div className="scene-background" aria-hidden="true">
        <span className="scene-stars">
          {Array.from({ length: 18 }, (_, i) => (
            <i key={i} />
          ))}
        </span>
      </div>

      <header className="site-header">
        <div className="brand">
          <span className="brand-avatar" aria-hidden="true">
            知
          </span>
          <span className="brand-copy">
            <strong>知源</strong>
          </span>
        </div>

        <nav className="main-nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to}>
              {({ isActive }) => (
                <>
                  <b>{item.num}</b>
                  <span>{item.label}</span>
                  {isActive ? '' : ''}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="header-actions">
          <button
            className="icon-button"
            type="button"
            aria-label="统计看板"
            title="统计"
            onClick={() => (window.location.hash = '#/stats')}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 20V10M10 20V4M16 20v-8M22 20H2" />
            </svg>
          </button>
          <ThemeToggle />
        </div>
      </header>

      <main className="app-main">
        <Outlet />
      </main>
    </>
  )
}

/**
 * 应用外壳：左侧像素风导航栏（桌面）/ 底栏（移动）+ 场景背景 + 路由出口。
 *
 * 品牌呈现（北航元素）：
 * - 站名"航友"（知源更名，用户确认）；
 * - 左上角北航校徽（assets/buaa-badge.png，程序抠图产物）；
 * - 昼夜背景：白天春景 / 夜晚景色（assets/bg-day.png / bg-night.png，像素化处理）。
 */

import { NavLink, Outlet } from 'react-router-dom'
import badgeUrl from '../assets/buaa-badge.png'
import bgDayUrl from '../assets/bg-day.png'
import bgNightUrl from '../assets/bg-night.png'
import { ThemeToggle } from './ThemeToggle'

const NAV_ITEMS = [
  { to: '/library', label: '资料库', num: '01' },
  { to: '/books', label: '书库', num: '02' },
  { to: '/chat', label: '问答', num: '03' },
  { to: '/explain', label: '讲解', num: '04' },
  { to: '/quiz', label: '测验', num: '05' },
  { to: '/review', label: '复习', num: '06' },
]

export function AppShell() {
  return (
    <>
      {/* 昼夜场景：两张像素化照片交叉淡化（2100ms 与全局颜色插值同步） */}
      <div className="scene-background" aria-hidden="true">
        <img className="scene-bg-day" src={bgDayUrl} alt="" />
        <img className="scene-bg-night" src={bgNightUrl} alt="" />
        <span className="scene-veil"></span>
        <span className="scene-grid"></span>
        <span className="scene-stars">
          {Array.from({ length: 18 }, (_, i) => (
            <i key={i} />
          ))}
        </span>
      </div>

      <header className="site-header">
        <div className="brand">
          <span className="brand-avatar" aria-hidden="true">
            <img
              src={badgeUrl}
              alt="北航校徽"
              style={{ width: '100%', height: '100%', objectFit: 'contain', imageRendering: 'auto', padding: 2 }}
            />
          </span>
          <span className="brand-copy">
            <strong>航友</strong>
          </span>
        </div>

        <nav className="main-nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'active' : '')}>
              <b>{item.num}</b>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="header-actions">
          <button
            className="icon-button"
            type="button"
            aria-label="我的"
            title="我的（资料 / AI 设置 / 统计）"
            onClick={() => (window.location.hash = '#/me')}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="8" r="4"></circle>
              <path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"></path>
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

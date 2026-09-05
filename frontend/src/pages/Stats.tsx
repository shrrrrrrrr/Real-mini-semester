/**
 * 统计看板：正确率 / 待复习 / 连续天数 / 7 日复习热力图。
 */

import { useEffect, useState } from 'react'
import { api, errText } from '../lib/api'
import type { Course, Stats } from '../lib/types'
import { useToast } from '../components/Toast'

export function StatsPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [stats, setStats] = useState<Stats | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.get<Course[]>('/courses')
        setCourses(list)
        if (list.length > 0) setCourseId(list[0].id)
      } catch (e) {
        toast(errText(e), 'error')
      }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!courseId) return
    void (async () => {
      try {
        setStats(await api.get<Stats>(`/courses/${courseId}/stats`))
      } catch (e) {
        toast(errText(e), 'error')
      }
    })()
  }, [courseId, toast])

  const level = (reviewed: number): number => {
    if (reviewed === 0) return 0
    if (reviewed < 10) return 1
    if (reviewed < 25) return 2
    if (reviewed < 50) return 3
    return 4
  }

  return (
    <>
      <div className="section-label reveal">
        <span>STATS.VIEW</span>
        <p>学习统计</p>
        <i></i>
      </div>

      <div className="panel reveal delay-1" style={{ padding: '16px', marginBottom: '18px' }}>
        <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      {stats && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px', marginBottom: '18px' }}>
            {[
              { label: '闪卡总数', value: stats.total_cards },
              { label: '今日到期', value: stats.due_today },
              { label: '今日已复习', value: stats.reviewed_today },
              { label: '累计答题', value: stats.total_attempts },
              { label: '正确率', value: `${(stats.correct_rate * 100).toFixed(0)}%` },
              { label: '连续学习', value: `${stats.streak_days} 天` },
            ].map((c, i) => (
              <div key={c.label} className={`panel reveal delay-${(i % 3) + 1}`} style={{ padding: '20px', textAlign: 'center' }}>
                <div style={{ font: "700 34px/1 var(--pixel)", color: 'var(--ink-strong)' }}>{c.value}</div>
                <div style={{ font: "7px/1 var(--mono)", color: 'var(--muted)', marginTop: 8 }}>{c.label}</div>
              </div>
            ))}
          </div>

          <div className="panel reveal delay-2" style={{ padding: '20px' }}>
            <b style={{ font: "7px/1 var(--mono)" }}>近 7 天复习热力图</b>
            <div style={{ display: 'flex', gap: '10px', marginTop: '12px', alignItems: 'flex-end' }}>
              {stats.last_7_days.map((d) => (
                <div key={d.date} style={{ textAlign: 'center' }}>
                  <div className="heatmap" style={{ gridTemplateRows: 'repeat(1, 28px)' }}>
                    <i data-level={level(d.reviewed)} style={{ width: 28, height: 28 }} title={`${d.date}：复习 ${d.reviewed} 张 / 到期 ${d.due} 张`} />
                  </div>
                  <small style={{ font: "7px/1 var(--mono)", color: 'var(--muted)' }}>{d.date.slice(5)}</small>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}

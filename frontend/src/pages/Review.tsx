/**
 * 复习页：三模式（长期 FSRS / 考试冲刺 / 手动计划）+ 离线积压合并 + 四档评分。
 *
 * 核心交互（开发文档 §4.4 界面⑥）：
 * - 打开时先清"离线积压"（学习期未巩固完的卡），再进入到期队列；
 * - 卡片点空格翻面；1-4 键评分（键盘优先）；
 * - 评分按钮上预览各档对应的下次间隔（ts-fsrs repeat 预览）。
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, errText } from '../lib/api'
import type { Course, Flashcard, ReviewPlanInfo } from '../lib/types'
import {
  applyRating,
  humanInterval,
  previewIntervals,
  Rating,
  toCard,
  type Card,
} from '../lib/fsrs'
import { pickBacklog, toPlanCard } from '../lib/reviewPlan'
import { useToast } from '../components/Toast'

type Mode = 'normal' | 'sprint' | 'manual'

  const RATING_META: { rating: Exclude<Rating, Rating.Manual>; label: string; key: string; cls: string }[] = [
  { rating: Rating.Again, label: '忘了', key: '1', cls: 'rating-btn again' },
  { rating: Rating.Hard, label: '困难', key: '2', cls: 'rating-btn' },
  { rating: Rating.Good, label: '良好', key: '3', cls: 'rating-btn' },
  { rating: Rating.Easy, label: '简单', key: '4', cls: 'rating-btn easy' },
]

export function ReviewPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [cards, setCards] = useState<Flashcard[]>([])
  const [queue, setQueue] = useState<Flashcard[]>([]) // 当前待复习队列（积压优先）
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [mode, setMode] = useState<Mode>('normal')
  const [plan, setPlan] = useState<ReviewPlanInfo | null>(null)
  const [examDate, setExamDate] = useState('')
  const [budget, setBudget] = useState(30)
  const [onlyWrong, setOnlyWrong] = useState(false)
  const [dailyCount, setDailyCount] = useState(20)
  const [planDays, setPlanDays] = useState(1)
  const [busy, setBusy] = useState(false)
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

  const loadCards = useCallback(
    async (cid: string) => {
      try {
        const list = await api.get<Flashcard[]>(`/courses/${cid}/flashcards`)
        setCards(list)
        // 离线积压合并：学习期到期卡优先清，之后是正常到期队列
        const backlog = pickBacklog(list.map(toPlanCard))
          .map((p) => list.find((c) => c.id === p.id))
          .filter((c): c is Flashcard => !!c)
        const backlogIds = new Set(backlog.map((b) => b.id))
        const due = list.filter((c) => new Date(c.due) <= new Date() && !backlogIds.has(c.id))
        setQueue([...backlog, ...due])
        setIdx(0)
        setFlipped(false)
      } catch (e) {
        toast(errText(e), 'error')
      }
    },
    [toast],
  )

  useEffect(() => {
    if (courseId) void loadCards(courseId)
  }, [courseId, loadCards])

  // 载入活动计划（如有）
  useEffect(() => {
    if (!courseId) return
    void (async () => {
      try {
        const p = await api.get<ReviewPlanInfo | null>(`/courses/${courseId}/review-plans/active`)
        setPlan(p)
        if (p) setMode(p.mode === 'sprint' ? 'sprint' : 'manual')
      } catch {
        setPlan(null)
      }
    })()
  }, [courseId])

  const current = queue[idx]

  // ts-fsrs 卡片状态（从 DB 行恢复）
  const fsrsCard: Card | null = useMemo(() => {
    if (!current) return null
    return toCard({
      due: current.due,
      stability: current.stability,
      difficulty: current.difficulty,
      state: current.state,
      reps: current.reps,
      lapses: current.lapses,
      last_review: current.last_review,
    })
  }, [current])

  // 评分前预览四档间隔（渲染在按钮上）
  const preview = useMemo(() => {
    if (!fsrsCard) return null
    const now = new Date()
    const cards = previewIntervals(fsrsCard, now)
    return RATING_META.map((meta) => ({
      ...meta,
      interval: humanInterval(now, cards[meta.rating].due),
    }))
  }, [fsrsCard])

  const rate = useCallback(
    async (rating: Exclude<Rating, Rating.Manual>) => {
      if (!current || !fsrsCard || busy) return
      setBusy(true)
      try {
        // applyRating 返回 RecordLogItem { card, log }（v5 API）
        const { card: next, log } = applyRating(fsrsCard, rating)
        // 前端计算、后端存储：把新状态与本次评分日志 PATCH 回后端
        await api.patch(`/flashcards/${current.id}`, {
          due: next.due.toISOString(),
          stability: next.stability,
          difficulty: next.difficulty,
          state: next.state,
          reps: next.reps,
          lapses: next.lapses,
          last_review: next.last_review ? next.last_review.toISOString() : null,
          rating,
          scheduled_days: log.scheduled_days,
          elapsed_days: log.elapsed_days,
        })
        // 学习期"忘了"的卡当天稍后再见（离线积压策略）：追加到队列尾部
        if (rating === Rating.Again) {
          setQueue((prev) => [...prev.slice(0, idx), ...prev.slice(idx + 1), current])
        } else {
          setQueue((prev) => prev.filter((_, i) => i !== idx))
        }
        setFlipped(false)
      } catch (e) {
        toast(errText(e), 'error')
      } finally {
        setBusy(false)
      }
    },
    [current, fsrsCard, busy, idx, toast],
  )

  // 键盘快捷键：空格翻面、1-4 评分
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.code === 'Space') {
        e.preventDefault()
        setFlipped((f) => !f)
      }
      if (flipped && ['1', '2', '3', '4'].includes(e.key)) {
        void rate(([Rating.Again, Rating.Hard, Rating.Good, Rating.Easy] as const)[Number(e.key) - 1])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [flipped, rate])

  async function createSprintPlan() {
    if (!courseId || !examDate) return
    try {
      const p = await api.post<ReviewPlanInfo>('/review-plans/sprint', {
        course_id: courseId,
        exam_date: examDate,
        daily_budget_minutes: budget,
      })
      setPlan(p)
      setMode('sprint')
      toast(`已生成冲刺计划：${p.plan_days.length} 天，考前二刷已安排`)
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function createManualPlan() {
    if (!courseId) return
    try {
      const p = await api.post<ReviewPlanInfo>('/review-plans/manual', {
        course_id: courseId,
        only_wrong: onlyWrong,
        daily_card_count: dailyCount,
        days: planDays,
      })
      setPlan(p)
      setMode('manual')
      toast('已生成手动计划')
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  const active = courses.find((c) => c.id === courseId)
  const todayPlan = plan?.plan_days.find((d) => d.date === new Date().toISOString().slice(0, 10))

  return (
    <>
      <div className="section-label reveal">
        <span>REVIEW.FSRS</span>
        <p>间隔复习</p>
        <i></i>
      </div>

      <div className="panel reveal delay-1" style={{ padding: '16px', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '18px' }}>
        <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        {/* 三模式切换 */}
        {(['normal', 'sprint', 'manual'] as Mode[]).map((m) => (
          <button
            key={m}
            className="btn"
            style={mode === m ? { background: 'var(--yellow)', color: '#0b3149' } : undefined}
            onClick={() => setMode(m)}
          >
            {m === 'normal' ? '长期模式' : m === 'sprint' ? '考试冲刺' : '手动计划'}
          </button>
        ))}
        <span style={{ font: "7px/1 var(--mono)", color: 'var(--muted)' }}>
          待复习 {queue.length} 张{active ? ` · 本课共 ${cards.length} 卡` : ''}
        </span>
      </div>

      {/* 模式配置面板 */}
      {mode === 'sprint' && (
        <div className="panel reveal" style={{ padding: '16px', marginBottom: '18px', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ font: "7px/1 var(--mono)" }}>考试日期</label>
          <input className="pixel-input" type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} style={{ minHeight: 38 }} />
          <label style={{ font: "7px/1 var(--mono)" }}>每日预算</label>
          <input className="pixel-input" type="number" min={10} max={480} value={budget} onChange={(e) => setBudget(Number(e.target.value))} style={{ width: 90, minHeight: 38 }} />
          <span style={{ color: 'var(--muted)' }}>分钟</span>
          <button className="btn btn-warn" onClick={() => void createSprintPlan()}>生成冲刺计划</button>
          <span className="badge badge-warn">错题卡优先 · 脆弱卡考前 48h 二刷</span>
        </div>
      )}

      {mode === 'manual' && (
        <div className="panel reveal" style={{ padding: '16px', marginBottom: '18px', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input type="checkbox" checked={onlyWrong} onChange={(e) => setOnlyWrong(e.target.checked)} style={{ width: 16, height: 16 }} />
            仅错题卡
          </label>
          <label style={{ font: "7px/1 var(--mono)" }}>每日</label>
          <input className="pixel-input" type="number" min={5} max={200} value={dailyCount} onChange={(e) => setDailyCount(Number(e.target.value))} style={{ width: 80, minHeight: 38 }} />
          <span style={{ color: 'var(--muted)' }}>张</span>
          <label style={{ font: "7px/1 var(--mono)" }}>共</label>
          <input className="pixel-input" type="number" min={1} max={30} value={planDays} onChange={(e) => setPlanDays(Number(e.target.value))} style={{ width: 70, minHeight: 38 }} />
          <span style={{ color: 'var(--muted)' }}>天</span>
          <button className="btn btn-warn" onClick={() => void createManualPlan()}>生成计划</button>
        </div>
      )}

      {/* 计划概览 */}
      {plan && (mode === 'sprint' || mode === 'manual') && (
        <div className="panel-soft reveal" style={{ padding: '12px 16px', marginBottom: '18px' }}>
          <b style={{ font: "7px/1 var(--mono)" }}>
            {plan.mode === 'sprint' ? '冲刺计划' : '手动计划'} · 共 {plan.plan_days.length} 天
          </b>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '8px' }}>
            {plan.plan_days.map((d) => (
              <span key={d.date} className={`badge ${d.date === new Date().toISOString().slice(0, 10) ? 'badge-warn' : ''}`}>
                {d.date.slice(5)} · {d.card_ids.length} 卡 · {d.est_minutes} 分钟
              </span>
            ))}
          </div>
          {todayPlan && (
            <p style={{ margin: '8px 0 0', color: 'var(--muted)', fontSize: 13 }}>
              今日计划：复习 {todayPlan.card_ids.length} 张（点击卡片区"载入今日计划"按计划队列复习）
            </p>
          )}
          <details className="plan-reason-drawer">
            <summary>计划依据</summary>
            {plan.plan_days.map((day) => (
              <p key={day.date}>
                <b>{day.date.slice(5)}</b>：{day.reason}
              </p>
            ))}
          </details>
        </div>
      )}

      {/* 复习舞台 */}
      {current ? (
        <div className="panel reveal delay-2" style={{ padding: '20px' }}>
          <div className="flashcard-stage">
            <button
              className="flashcard"
              onClick={() => setFlipped((f) => !f)}
              aria-label={flipped ? '显示正面' : '翻面显示答案'}
            >
              <span className="badge" style={{ marginBottom: 14 }}>
                {idx + 1}/{queue.length} · {current.origin === 'quiz' ? '错题卡' : '手动卡'}
              </span>
              {!flipped ? (
                <b style={{ font: '700 22px/1.6 var(--pixel)', color: 'var(--ink-strong)' }}>{current.front}</b>
              ) : (
                <span style={{ font: '700 17px/1.8 var(--body)', color: 'var(--ink)' }}>{current.back}</span>
              )}
              <small style={{ color: 'var(--muted)', font: "7px/1 var(--mono)" }}>
                {flipped ? '按 1-4 评分 ↓' : '空格 / 点击 翻面'}
              </small>
            </button>
          </div>

          {flipped && (
            <div style={{ display: 'flex', gap: '10px' }}>
              {preview?.map((meta) => (
                <button key={meta.key} className={meta.cls} onClick={() => void rate(meta.rating)} disabled={busy}>
                  <b>{meta.label}</b>
                  <small>{meta.interval}后</small>
                  <kbd>{meta.key}</kbd>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="panel reveal delay-2" style={{ padding: '40px', textAlign: 'center' }}>
          <p style={{ color: 'var(--muted)', margin: 0 }}>
            {queue.length === 0
              ? cards.length > 0
                ? '当前没有到期的卡片——回去做一套测验，或过几天再来。'
                : '还没有闪卡。去测验页答错一道题并"转为闪卡"，复习就从这里开始。'
              : ''}
          </p>
        </div>
      )}

      {/* 说明脚注 */}
      <p style={{ color: 'var(--muted)', font: "7px/1.6 var(--mono)", marginTop: '14px' }}>
        * 长期模式按 FSRS 遗忘曲线科学排期；冲刺模式为考试强记（留存率低于科学间隔，考后建议补复习）。
      </p>
    </>
  )
}

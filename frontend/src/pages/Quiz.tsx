/**
 * 测验页：生成（后台任务，切页不中断）→ 答题 → 底部提交判分 → 错题转卡
 * + 历史侧栏（回看过往测验与作答）。
 */

import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errText, pollTask } from '../lib/api'
import type { Course, GenTaskInfo, QuizDetail, QuizListItem, QuizResult } from '../lib/types'
import { useToast } from '../components/Toast'

export function QuizPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [count, setCount] = useState(5)
  const [quiz, setQuiz] = useState<QuizDetail | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [result, setResult] = useState<QuizResult | null>(null)
  const [converted, setConverted] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<QuizListItem[]>([])
  const taskRef = useRef<{ cancel: () => void } | null>(null)
  const location = useLocation()
  const { toast } = useToast()

  const loadHistory = async (cid: string) => {
    try {
      setHistory(await api.get<QuizListItem[]>(`/quizzes?course_id=${cid}`))
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.get<Course[]>('/courses')
        setCourses(list)
        const preset = (location.state as { course?: string } | null)?.course
        if (preset && list.some((c) => c.id === preset)) setCourseId(preset)
        else if (list.length > 0) setCourseId(list[0].id)
      } catch (e) {
        toast(errText(e), 'error')
      }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (courseId) void loadHistory(courseId)
  }, [courseId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => taskRef.current?.cancel(), [])

  async function generate() {
    if (!courseId) return
    taskRef.current?.cancel()
    setQuiz(null)
    setResult(null)
    setAnswers({})
    setConverted(new Set())
    setBusy(true)
    try {
      const { task_id } = await api.post<{ task_id: string }>('/quizzes', {
        course_id: courseId,
        count,
      })
      toast('出题任务已提交——切到别的页面也不会中断')
      const { cancel, promise } = pollTask(task_id, (tk: GenTaskInfo) => {
        if (tk.status === 'failed') toast(tk.failed_reason ?? '出题失败', 'error')
      })
      taskRef.current = { cancel }
      const done = await promise
      if (done.status === 'done' && done.result) {
        setQuiz(done.result as QuizDetail)
        toast(`已生成 ${(done.result as QuizDetail).question_count} 道题`)
        void loadHistory(courseId)
      }
    } catch (e) {
      if ((e as Error).message !== 'cancelled') toast(errText(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (!quiz) return
    const items = quiz.questions
      .filter((q) => answers[q.id])
      .map((q) => ({ question_id: q.id, selected: answers[q.id] }))
    if (items.length < quiz.questions.length) {
      toast('还有题目没作答', 'error')
      return
    }
    try {
      const r = await api.post<QuizResult>(`/quizzes/${quiz.id}/submit`, { answers: items })
      setResult(r)
      toast(`得分：${r.correct}/${r.total}（正确率 ${(r.accuracy * 100).toFixed(0)}%）`)
      void loadHistory(courseId)
      // 刷新详情（补 answer/explanation）
      setQuiz(await api.get<QuizDetail>(`/quizzes/${quiz.id}`))
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function openHistory(q: QuizListItem) {
    try {
      const detail = await api.get<QuizDetail>(`/quizzes/${q.id}`)
      setQuiz(detail)
      setAnswers({})
      // 已作答的历史：恢复勾选并展示判分结果
      if (detail.attempted) {
        const restored: Record<number, string> = {}
        for (const qq of detail.questions) {
          if (qq.selected) restored[qq.id] = qq.selected
        }
        setAnswers(restored)
        setResult({
          total: detail.question_count,
          correct: detail.questions.filter((qq) => qq.is_correct).length,
          accuracy: detail.question_count
            ? detail.questions.filter((qq) => qq.is_correct).length / detail.question_count
            : 0,
          items: detail.questions.map((qq) => ({
            question_id: qq.id,
            selected: qq.selected ?? '',
            answer: qq.answer ?? '',
            is_correct: qq.is_correct ?? false,
            explanation: qq.explanation ?? '',
            stem: qq.stem,
            options: qq.options,
          })),
        })
      } else {
        setResult(null)
      }
      setConverted(new Set())
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function toFlashcard(questionId: number) {
    try {
      await api.post('/flashcards/from-quiz', { question_id: questionId })
      setConverted((prev) => new Set(prev).add(questionId))
      toast('已转为闪卡，进入复习队列')
    } catch (e) {
      if (String((e as { detail?: string }).detail ?? '').includes('已转')) {
        setConverted((prev) => new Set(prev).add(questionId))
        toast('这道题已经转过卡了')
      } else {
        toast(errText(e), 'error')
      }
    }
  }

  const LETTERS = ['A', 'B', 'C', 'D']

  return (
    <div style={{ display: 'flex', gap: '18px', alignItems: 'flex-start' }}>
      {/* 左：生成 + 历史侧栏 */}
      <div style={{ width: 260, flexShrink: 0, display: 'grid', gap: '14px' }}>
        <div className="panel reveal" style={{ padding: '16px' }}>
          <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)} style={{ width: '100%' }}>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <select className="pixel-select" value={count} onChange={(e) => setCount(Number(e.target.value))} style={{ width: '100%', marginTop: 10 }}>
            {[3, 5, 8, 10].map((n) => (
              <option key={n} value={n}>{n} 题</option>
            ))}
          </select>
          <button className="btn btn-primary" style={{ width: '100%', marginTop: 10 }} onClick={() => void generate()} disabled={busy || !courseId}>
            {busy ? '出题中…' : '生成测验'}
          </button>
        </div>

        <div className="panel reveal delay-1" style={{ padding: '14px' }}>
          <b style={{ font: "7px/1 var(--mono)", color: 'var(--ink-strong)' }}>历史测验</b>
          <div style={{ display: 'grid', gap: '8px', marginTop: '10px' }}>
            {history.map((h) => (
              <button
                key={h.id}
                className="btn"
                style={{
                  justifyContent: 'space-between', minHeight: 36, padding: '6px 10px', fontSize: 12,
                  background: quiz?.id === h.id ? 'var(--mint)' : undefined,
                  color: quiz?.id === h.id ? '#102f46' : undefined,
                }}
                onClick={() => void openHistory(h)}
              >
                <span>{new Date(h.created_at).toLocaleDateString('zh-CN')} · {h.question_count} 题</span>
                <span className={`badge ${h.attempted ? 'badge-ok' : 'badge-warn'}`}>
                  {h.attempted ? '已答' : '未答'}
                </span>
              </button>
            ))}
            {history.length === 0 && (
              <p style={{ color: 'var(--muted)', fontSize: 12, margin: 0 }}>暂无历史</p>
            )}
          </div>
        </div>
      </div>

      {/* 右：题目区 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="section-label reveal">
          <span>QUIZ.TIME</span>
          <p>智能测验</p>
          <i></i>
        </div>

        {busy && (
          <div className="panel-soft" style={{ padding: '14px' }}>
            <div className="loading-bar" />
            <p style={{ margin: '8px 0 0', color: 'var(--muted)' }}>出题中……（可切到其他页面，不会中断）</p>
          </div>
        )}

        {quiz && (
          <>
            <div style={{ display: 'grid', gap: '14px' }}>
              {quiz.questions.map((q) => {
                const r = result?.items.find((it) => it.question_id === q.id)
                return (
                  <div key={q.id} className="panel reveal" style={{ padding: '18px' }}>
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <span className="badge">{q.question_no}</span>
                      <span className="badge badge-warn">{q.difficulty}</span>
                      {r && <span className={`badge ${r.is_correct ? 'badge-ok' : 'badge-danger'}`}>{r.is_correct ? '答对' : '答错'}</span>}
                    </div>
                    <p style={{ fontWeight: 700, margin: '12px 0', lineHeight: 1.7 }}>{q.stem}</p>
                    <div style={{ display: 'grid', gap: '8px' }}>
                      {q.options.map((opt, i) => {
                        const letter = LETTERS[i]
                        const picked = answers[q.id] === letter
                        const isAnswer = r && r.answer === letter
                        return (
                          <button
                            key={i}
                            className="btn"
                            style={{
                              justifyContent: 'flex-start', textAlign: 'left', minHeight: 38, padding: '8px 12px',
                              background: isAnswer ? 'var(--mint)' : picked ? 'var(--peach)' : undefined,
                              color: isAnswer ? '#102f46' : undefined,
                              opacity: r ? (picked || isAnswer ? 1 : 0.5) : 1,
                            }}
                            disabled={!!r}
                            onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: letter }))}
                          >
                            <b style={{ marginRight: 8 }}>{letter}.</b> {opt}
                          </button>
                        )
                      })}
                    </div>
                    {r && (
                      <div className="panel-soft" style={{ padding: '12px 14px', marginTop: '10px' }}>
                        <b style={{ color: r.is_correct ? 'var(--ok)' : 'var(--danger)' }}>
                          正确答案 {r.answer}（你选了 {r.selected}）
                        </b>
                        <p style={{ margin: '6px 0 0', lineHeight: 1.7 }}>{r.explanation}</p>
                        {!r.is_correct && !converted.has(q.id) && (
                          <button className="btn btn-warn" style={{ marginTop: '10px' }} onClick={() => void toFlashcard(q.id)}>
                            转为闪卡（错题进复习队列）
                          </button>
                        )}
                        {converted.has(q.id) && (
                          <span className="badge badge-ok" style={{ marginTop: '10px' }}>已转闪卡 ✓</span>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* 底部固定提交（用户要求：放最下方） */}
            {!result && (
              <div className="panel" style={{ padding: '16px', marginTop: '14px', display: 'flex', gap: '14px', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>
                  已作答 {Object.keys(answers).length} / {quiz.questions.length} 题
                </span>
                <button
                  className="btn btn-warn"
                  onClick={() => void submit()}
                  disabled={Object.keys(answers).length < quiz.questions.length}
                >
                  提交答卷
                </button>
              </div>
            )}
          </>
        )}

        {!quiz && !busy && (
          <div className="panel reveal delay-1" style={{ padding: '40px', textAlign: 'center' }}>
            <p style={{ color: 'var(--muted)', margin: 0 }}>选择题数并生成测验；出题过程切页不中断。</p>
          </div>
        )}
      </div>
    </div>
  )
}

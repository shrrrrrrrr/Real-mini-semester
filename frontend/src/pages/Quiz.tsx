/**
 * 测验页：从勾选资料生成 MCQ → 逐题作答 → 即时判分 → 错题一键转闪卡。
 */

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errText } from '../lib/api'
import type { Course, QuizInfo, QuizResult } from '../lib/types'
import { useToast } from '../components/Toast'

export function QuizPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [count, setCount] = useState(5)
  const [busy, setBusy] = useState(false)
  const [quiz, setQuiz] = useState<QuizInfo | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [result, setResult] = useState<QuizResult | null>(null)
  const [converted, setConverted] = useState<Set<number>>(new Set())
  const location = useLocation()
  const { toast } = useToast()

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

  async function generate() {
    if (!courseId) return
    setBusy(true)
    setQuiz(null)
    setResult(null)
    setAnswers({})
    setConverted(new Set())
    try {
      const q = await api.post<QuizInfo>('/quizzes', { course_id: courseId, count })
      setQuiz(q)
      toast(`已生成 ${q.question_count} 道题（可能因内容不足略少于请求）`)
    } catch (e) {
      toast(errText(e), 'error')
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
      // 已转过的卡后端会拒绝（唯一约束），视为成功提示
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
    <>
      <div className="section-label reveal">
        <span>QUIZ.TIME</span>
        <p>智能测验</p>
        <i></i>
      </div>

      <div className="panel reveal delay-1" style={{ padding: '18px', display: 'flex', gap: '10px', marginBottom: '18px', flexWrap: 'wrap' }}>
        <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <select className="pixel-select" value={count} onChange={(e) => setCount(Number(e.target.value))}>
          {[3, 5, 8, 10].map((n) => (
            <option key={n} value={n}>{n} 题</option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={() => void generate()} disabled={busy || !courseId}>
          {busy ? '出题中…' : '生成测验'}
        </button>
        {quiz && !result && (
          <button className="btn btn-warn" onClick={() => void submit()}>
            提交答卷（{Object.keys(answers).length}/{quiz.questions.length}）
          </button>
        )}
      </div>

      {busy && <div className="panel-soft" style={{ padding: '14px' }}><div className="loading-bar" /></div>}

      {quiz && (
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
                          justifyContent: 'flex-start',
                          textAlign: 'left',
                          minHeight: 38,
                          padding: '8px 12px',
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
      )}
    </>
  )
}

/**
 * 讲解模式：输入书名/学科/章节 → 结构化大纲树（可挂接已传资料片段）。
 */

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errText } from '../lib/api'
import type { Course, ExplainInfo } from '../lib/types'
import { useToast } from '../components/Toast'

export function ExplainPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [explain, setExplain] = useState<ExplainInfo | null>(null)
  const [expanded, setExpanded] = useState<number>(0)
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
    const t = topic.trim()
    if (!t) return
    setBusy(true)
    setExplain(null)
    try {
      const result = await api.post<ExplainInfo>('/explain/outline', {
        course_id: courseId || null,
        topic: t,
      })
      setExplain(result)
      setExpanded(0)
      toast(`已生成「${t}」讲解大纲`)
    } catch (e) {
      toast(errText(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="section-label reveal">
        <span>LEARN.MAP</span>
        <p>讲解大纲</p>
        <i></i>
      </div>

      <div className="panel reveal delay-1" style={{ padding: '18px', display: 'flex', gap: '10px', marginBottom: '18px' }}>
        <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
          <option value="">（不关联课程）</option>
        </select>
        <input
          className="pixel-input"
          placeholder="输入书名、学科或章节，如：图论 / 《算法导论》第13章"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void generate()}
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" onClick={() => void generate()} disabled={busy}>
          {busy ? '生成中…' : '生成大纲'}
        </button>
      </div>

      {busy && (
        <div className="panel-soft" style={{ padding: '14px 16px' }}>
          <div className="loading-bar" />
        </div>
      )}

      {explain && (
        <div style={{ display: 'grid', gap: '12px' }}>
          {explain.sections.map((sec, i) => (
            <div key={i} className="panel reveal" style={{ padding: '18px' }}>
              <button
                className="btn"
                style={{ width: '100%', justifyContent: 'space-between', background: 'var(--yellow)', color: '#0b3149' }}
                onClick={() => setExpanded(expanded === i ? -1 : i)}
              >
                <span>{sec.title}</span>
                <span>{expanded === i ? '－' : '＋'}</span>
              </button>
              {expanded === i && (
                <div style={{ display: 'grid', gap: '10px', marginTop: '14px' }}>
                  {sec.nodes.map((node, j) => (
                    <details key={j} className="panel-soft" style={{ padding: '12px 14px' }}>
                      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>{node.title}</summary>
                      <p style={{ margin: '8px 0', color: 'var(--muted)', lineHeight: 1.7 }}>{node.summary}</p>
                      {node.linked_hint && (
                        <p style={{ margin: 0, font: "7px/1.6 var(--mono)", color: 'var(--blue-strong)' }}>
                          资料挂接：{node.linked_hint}
                          {node.linked_chunk_ids.length > 0 && ` · 命中 ${node.linked_chunk_ids.length} 个片段`}
                        </p>
                      )}
                    </details>
                  ))}
                </div>
              )}
            </div>
          ))}
          <p style={{ color: 'var(--muted)', font: "7px/1.6 var(--mono)" }}>
            * 讲解大纲基于模型通识生成；带资料挂接的节点可结合你的课件深入学习（去问答页追问）。
          </p>
        </div>
      )}
    </>
  )
}

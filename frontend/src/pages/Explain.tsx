/**
 * 讲解页：大纲生成（后台任务，切页不中断）+ 节点展开讲解 + 就这提问（预填跳转）
 * + 历史侧栏（回看过往大纲）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, errText, pollTask } from '../lib/api'
import type { Course, ExplainInfoV2, GenTaskInfo } from '../lib/types'
import { useToast } from '../components/Toast'

export function ExplainPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [topic, setTopic] = useState('')
  const [explain, setExplain] = useState<ExplainInfoV2 | null>(null)
  const [history, setHistory] = useState<ExplainInfoV2[]>([])
  const [expanded, setExpanded] = useState<number>(0)
  const [nodeBusy, setNodeBusy] = useState<string | null>(null) // "sec:node" → 任务中
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())
  const taskRef = useRef<{ cancel: () => void } | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const { toast } = useToast()

  const loadHistory = useCallback(async (cid: string | null) => {
    try {
      setHistory(await api.get<ExplainInfoV2[]>(`/explains${cid ? `?course_id=${cid}` : ''}`))
    } catch {
      /* ignore */
    }
  }, [])

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

  // 组件卸载时取消轮询（任务在服务端继续跑，回来重新拉即可）
  useEffect(() => () => taskRef.current?.cancel(), [])

  async function generate() {
    const t = topic.trim()
    if (!t) return
    taskRef.current?.cancel()
    setExplain(null)
    try {
      const { task_id } = await api.post<{ task_id: string }>('/explain/outline', {
        course_id: courseId || null,
        topic: t,
      })
      toast('生成任务已提交——切到别的页面也不会中断')
      const { cancel, promise } = pollTask(task_id, (tk: GenTaskInfo) => {
        if (tk.status === 'failed') toast(tk.failed_reason ?? '生成失败', 'error')
      })
      taskRef.current = { cancel }
      const done = await promise
      if (done.status === 'done' && done.result) {
        setExplain(done.result as ExplainInfoV2)
        setExpanded(0)
        setExpandedNodes(new Set())
        void loadHistory(courseId)
      }
    } catch (e) {
      if ((e as Error).message !== 'cancelled') toast(errText(e), 'error')
    }
  }

  async function expandNode(secI: number, nodeI: number) {
    if (!explain) return
    const key = `${secI}:${nodeI}`
    if (explain.node_contents?.[key]) {
      // 已有内容：切换展开状态
      setExpandedNodes((prev) => {
        const next = new Set(prev)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })
      return
    }
    setNodeBusy(key)
    try {
      const { task_id } = await api.post<{ task_id: string }>('/explain/node-expand', {
        explain_id: explain.id,
        sec_index: secI,
        node_index: nodeI,
      })
      const done = await pollTask(task_id, () => {}).promise
      if (done.status === 'done' && done.result) {
        const r = done.result as { key: string; content: string }
        setExplain((prev) =>
          prev ? { ...prev, node_contents: { ...(prev.node_contents ?? {}), [r.key]: r.content } } : prev,
        )
        setExpandedNodes((prev) => new Set(prev).add(r.key))
      } else {
        toast(done.failed_reason ?? '讲解生成失败', 'error')
      }
    } catch (e) {
      toast(errText(e), 'error')
    } finally {
      setNodeBusy(null)
    }
  }

  function askAbout(title: string, hint: string) {
    // 就这提问：跳问答页并预填（用户确认"预填"而非自动发）
    navigate('/chat', {
      state: { course: courseId, prefill: `${title}：${hint}。请结合我的资料详细讲解。` },
    })
  }

  return (
    <div style={{ display: 'flex', gap: '18px', alignItems: 'flex-start' }}>
      {/* 左：生成入口 + 历史侧栏 */}
      <div style={{ width: 260, flexShrink: 0, display: 'grid', gap: '14px' }}>
        <div className="panel reveal" style={{ padding: '16px' }}>
          <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)} style={{ width: '100%' }}>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
            <option value="">（不关联课程）</option>
          </select>
          <input
            className="pixel-input"
            placeholder="主题，如：图论"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void generate()}
            style={{ width: '100%', marginTop: 10, minHeight: 38 }}
          />
          <button className="btn btn-primary" style={{ width: '100%', marginTop: 10 }} onClick={() => void generate()}>
            生成大纲
          </button>
        </div>

        <div className="panel reveal delay-1" style={{ padding: '14px' }}>
          <b style={{ font: "7px/1 var(--mono)", color: 'var(--ink-strong)' }}>历史大纲</b>
          <div style={{ display: 'grid', gap: '8px', marginTop: '10px' }}>
            {history.map((h) => (
              <button
                key={h.id}
                className="btn"
                style={{
                  justifyContent: 'flex-start', minHeight: 36, padding: '6px 10px', fontSize: 12,
                  background: explain?.id === h.id ? 'var(--mint)' : undefined,
                  color: explain?.id === h.id ? '#102f46' : undefined,
                }}
                onClick={() => {
                  setExplain(h)
                  setExpanded(0)
                  setExpandedNodes(new Set())
                }}
                title={h.topic}
              >
                {h.topic.slice(0, 16)}
              </button>
            ))}
            {history.length === 0 && (
              <p style={{ color: 'var(--muted)', fontSize: 12, margin: 0 }}>暂无历史</p>
            )}
          </div>
        </div>
      </div>

      {/* 右：大纲内容 */}
      <div style={{ flex: 1, display: 'grid', gap: '12px', minWidth: 0 }}>
        <div className="section-label reveal">
          <span>LEARN.MAP</span>
          <p>讲解大纲</p>
          <i></i>
        </div>

        {explain ? (
          explain.sections.map((sec, i) => (
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
                  {sec.nodes.map((node, j) => {
                    const key = `${i}:${j}`
                    const content = explain.node_contents?.[key]
                    const isOpen = expandedNodes.has(key)
                    return (
                      <div key={j} className="panel-soft" style={{ padding: '12px 14px' }}>
                        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                          <b style={{ color: 'var(--ink-strong)' }}>{node.title}</b>
                          {node.linked_chunk_ids.length > 0 && (
                            <span className="badge badge-ok">资料×{node.linked_chunk_ids.length}</span>
                          )}
                          <button
                            className="btn"
                            style={{ minHeight: 28, padding: '3px 9px', fontSize: 11, marginLeft: 'auto' }}
                            onClick={() => void expandNode(i, j)}
                            disabled={nodeBusy === key}
                          >
                            {nodeBusy === key ? '生成中…' : content ? (isOpen ? '收起' : '展开讲解') : '展开讲解'}
                          </button>
                          <button
                            className="btn btn-warn"
                            style={{ minHeight: 28, padding: '3px 9px', fontSize: 11 }}
                            onClick={() => askAbout(node.title, node.summary || node.linked_hint)}
                            title="跳转到问答，围绕这个知识点提问"
                          >
                            就这提问 ↗
                          </button>
                        </div>
                        <p style={{ margin: '6px 0 0', color: 'var(--muted)', fontSize: 13, lineHeight: 1.6 }}>
                          {node.summary}
                        </p>
                        {content && isOpen && (
                          <div
                            style={{
                              marginTop: 10, padding: '12px 14px', whiteSpace: 'pre-wrap',
                              border: '2px dashed var(--line-strong)', background: 'var(--panel)',
                              lineHeight: 1.8, fontSize: 14,
                            }}
                          >
                            {content}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="panel reveal delay-1" style={{ padding: '40px', textAlign: 'center' }}>
            <p style={{ color: 'var(--muted)', margin: 0 }}>
              输入书名、学科或章节生成结构化大纲；生成过程切页不中断，回来还能看到结果。
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

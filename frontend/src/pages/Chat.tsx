/**
 * 资料问答页：SSE 双层答案流式渲染 + 引用核对 + 多轮追问。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errText, streamChat, type StreamCitation } from '../lib/api'
import type { Course, MessageInfo, SessionInfo } from '../lib/types'
import { AnswerBlock } from '../components/AnswerBlock'
import { useToast } from '../components/Toast'

interface StreamingState {
  segments: { layer: 'doc' | 'general'; text: string }[]
  citations: StreamCitation[] | null
  active: boolean
}

export function ChatPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState<string>('')
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<MessageInfo[]>([])
  const [question, setQuestion] = useState('')
  const [streaming, setStreaming] = useState<StreamingState | null>(null)
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | undefined>(undefined)
  const bottomRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const { toast } = useToast()

  // 载入课程列表（从资料库跳转时带 course state 预选）
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

  // 切换课程时载入会话列表
  useEffect(() => {
    if (!courseId) return
    setSessionId(null)
    setMessages([])
    void (async () => {
      try {
        setSessions(await api.get<SessionInfo[]>(`/courses/${courseId}/sessions`))
      } catch {
        /* 新课程无会话 */
      }
    })()
  }, [courseId])

  const loadMessages = useCallback(
    async (sid: string) => {
      try {
        const msgs = await api.get<MessageInfo[]>(`/sessions/${sid}/messages`)
        setMessages(msgs)
        setSessionId(sid)
      } catch (e) {
        toast(errText(e), 'error')
      }
    },
    [toast],
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming])

  async function ask() {
    const q = question.trim()
    if (!q || !courseId || busy) return
    setBusy(true)
    setQuestion('')
    setStreaming({ segments: [], citations: null, active: true })
    abortRef.current = new AbortController()
    try {
      await streamChat(
        { course_id: courseId, session_id: sessionId, question: q },
        {
          onSession: (sid, title) => {
            setSessionId(sid)
            setSessions((prev) =>
              prev.some((s) => s.id === sid) ? prev : [{ id: sid, title, created_at: new Date().toISOString() }, ...prev],
            )
          },
          onSegmentStart: (layer) => {
            setStreaming((prev) =>
              prev ? { ...prev, segments: [...prev.segments, { layer, text: '' }] } : prev,
            )
          },
          onToken: (text) => {
            setStreaming((prev) => {
              if (!prev) return prev
              const segments = [...prev.segments]
              const last = segments[segments.length - 1]
              if (last) segments[segments.length - 1] = { ...last, text: last.text + text }
              return { ...prev, segments }
            })
          },
          onCitations: (citations) => {
            setStreaming((prev) => (prev ? { ...prev, citations } : prev))
          },
          onDone: async () => {
            // 结束后从后端拉取完整消息（保证与库中数据一致）
            const sid = sessionId
            if (sid) await loadMessages(sid)
          },
          onError: (detail) => toast(detail, 'error'),
        },
        abortRef.current.signal,
      )
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast(errText(e), 'error')
    } finally {
      setStreaming(null)
      setBusy(false)
      // 刷新会话列表标题
      try {
        setSessions(await api.get<SessionInfo[]>(`/courses/${courseId}/sessions`))
      } catch {
        /* ignore */
      }
    }
  }

  return (
    <>
      <div className="section-label reveal">
        <span>ASK.DOCS</span>
        <p>资料问答</p>
        <i></i>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 300px) 1fr', gap: '18px', alignItems: 'start' }}>
        {/* 左：课程与会话 */}
        <div className="panel reveal delay-1" style={{ padding: '16px', display: 'grid', gap: '12px' }}>
          <select className="pixel-select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
            {courses.length === 0 && <option value="">（先去资料库建课程）</option>}
          </select>
          <button
            className="btn"
            onClick={() => {
              setSessionId(null)
              setMessages([])
            }}
          >
            + 新对话
          </button>
          <div style={{ display: 'grid', gap: '8px' }}>
            {sessions.map((s) => (
              <button
                key={s.id}
                className="btn"
                style={{
                  justifyContent: 'flex-start',
                  minHeight: 36,
                  padding: '6px 10px',
                  fontSize: 13,
                  background: s.id === sessionId ? 'var(--mint)' : undefined,
                  color: s.id === sessionId ? '#102f46' : undefined,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                onClick={() => void loadMessages(s.id)}
                title={s.title}
              >
                {s.title}
              </button>
            ))}
          </div>
        </div>

        {/* 右：对话流 */}
        <div className="panel reveal delay-2" style={{ padding: '20px', minHeight: '60vh', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, display: 'grid', gap: '16px', alignContent: 'start' }}>
            {messages.length === 0 && !streaming && (
              <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px 0' }}>
                问点什么吧，例如：「这份资料的核心观点是什么？」
                <br />黄底部分 = 出自你的资料（带引用可核对）；灰底部分 = 模型通识补充。
              </p>
            )}
            {messages.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="panel-soft" style={{ padding: '12px 16px', justifySelf: 'end', maxWidth: '80%' }}>
                  <b style={{ color: 'var(--blue-strong)' }}>你</b>
                  <p style={{ margin: '6px 0 0' }}>{m.content}</p>
                </div>
              ) : (
                <div key={m.id} style={{ maxWidth: '92%' }}>
                  <AnswerBlock segments={m.segments ?? [{ layer: 'general', text: m.content }]} citations={m.citations} />
                </div>
              ),
            )}

            {/* 流式中的答案 */}
            {streaming && (
              <div style={{ maxWidth: '92%' }}>
                <AnswerBlock segments={streaming.segments} citations={streaming.citations} isStreaming />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
            <textarea
              className="pixel-input"
              placeholder="围绕勾选的资料提问…（Enter 发送，Shift+Enter 换行）"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void ask()
                }
              }}
              style={{ flex: 1, minHeight: 56 }}
              disabled={busy || !courseId}
            />
            <button className="btn btn-primary" onClick={() => void ask()} disabled={busy || !courseId}>
              {busy ? '回答中…' : '提问'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

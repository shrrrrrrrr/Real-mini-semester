/**
 * 问答页：固定视口布局（对话区独立滚动）+ 双层答案 + 仅资料模式
 * + 分支对话（思源式浮层树：右侧按钮唤出、节点跳转、右键重命名、点外关闭）
 * + 就这提问预填跳转支持（location.state.prefill）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errText, streamChat, type StreamCitation } from '../lib/api'
import type { Book, Course, MessageInfo, SessionInfo, TreeNode } from '../lib/types'
import { AnswerBlock } from '../components/AnswerBlock'
import { MindMapOverlay } from '../components/MindMapOverlay'
import { useToast } from '../components/Toast'

interface StreamingState {
  segments: { layer: 'doc' | 'general'; text: string }[]
  citations: StreamCitation[] | null
  active: boolean
}

export function ChatPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<MessageInfo[]>([])
  const [question, setQuestion] = useState('')
  const [docsOnly, setDocsOnly] = useState(false)
  const [streaming, setStreaming] = useState<StreamingState | null>(null)
  const [busy, setBusy] = useState(false)
  const [tree, setTree] = useState<TreeNode[] | null>(null)
  const [showTree, setShowTree] = useState(false)
  const [treeVersion, setTreeVersion] = useState(0)
  const [profile, setProfile] = useState<{ nickname: string; avatar: string | null } | null>(null)
  const [books, setBooks] = useState<Book[]>([])
  const [selectedBooks, setSelectedBooks] = useState<Set<string>>(new Set())
  const [showBookPicker, setShowBookPicker] = useState(false)
  const [branchBanner, setBranchBanner] = useState<string | null>(null) // 追问反馈横幅
  const abortRef = useRef<AbortController | undefined>(undefined)
  const bottomRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const { toast } = useToast()

  // 载入课程（支持 location.state 跳转：{course, prefill}）
  useEffect(() => {
    void (async () => {
      try {
        const list = await api.get<Course[]>('/courses')
        setCourses(list)
        const state = location.state as { course?: string; prefill?: string } | null
        if (state?.course && list.some((c) => c.id === state.course)) setCourseId(state.course)
        else if (list.length > 0) setCourseId(list[0].id)
        if (state?.prefill) setQuestion(state.prefill) // 就这提问：预填不自动发（用户确认）
      } catch (e) {
        toast(errText(e), 'error')
      }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 书库列表（勾选参与检索）
  useEffect(() => {
    void (async () => {
      try {
        const list = await api.get<Book[]>('/books')
        setBooks(list.filter((b) => b.status === 'indexed'))
      } catch {
        /* 书库为空 */
      }
    })()
  }, [])

  // 昵称/头像（对话气泡显示"我"的身份）
  useEffect(() => {
    void (async () => {
      try {
        setProfile(await api.get('/profile'))
      } catch {
        /* 默认"我" */
      }
    })()
  }, [])

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

  // 树数据加载（打开浮层或刷新版本时）
  useEffect(() => {
    if (!sessionId || !showTree) return
    void (async () => {
      try {
        const t = await api.get<{ roots: TreeNode[] }>(`/sessions/${sessionId}/tree`)
        setTree(t.roots)
      } catch {
        setTree([])
      }
    })()
  }, [sessionId, showTree, treeVersion])

  // 点击浮层外关闭（MindMapOverlay 自带；此 effect 兼容书库选择器）
  useEffect(() => {
    if (!showBookPicker) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (!t.closest('[data-book-picker]')) setShowBookPicker(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [showBookPicker])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, streaming])

  async function ask(parentMessageId: number | null = null) {
    const q = question.trim()
    if (!q || !courseId || busy) return
    setBusy(true)
    setQuestion('')
    setStreaming({ segments: [], citations: null, active: true })
    // 追问反馈横幅：处于分支上下文时黄条常驻提示（用户确认的改进）
    if (parentMessageId) {
      const parentMsg = messages.find((m) => m.id === parentMessageId)
      const parentQ = messages.find((m) => m.id === parentMessageId - 1)
      setBranchBanner(`↳ 分支追问中（基于：${(parentQ?.content ?? parentMsg?.content ?? '上一回答').slice(0, 24)}…）`)
    }
    abortRef.current = new AbortController()
    const currentSession = sessionId
    try {
      let latestAssistantId: number | null = null
      await streamChat(
        {
          course_id: courseId,
          session_id: currentSession,
          question: q,
          parent_message_id: parentMessageId,
          docs_only: docsOnly,
          book_ids: Array.from(selectedBooks), // 书库勾选并入检索
        },
        {
          onSession: (sid, title) => {
            setSessionId(sid)
            setSessions((prev) =>
              prev.some((s) => s.id === sid) ? prev : [{ id: sid, title, created_at: new Date().toISOString() }, ...prev],
            )
          },
          onSegmentStart: (layer) => {
            setStreaming((prev) => (prev ? { ...prev, segments: [...prev.segments, { layer, text: '' }] } : prev))
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
          onDone: (messageId) => {
            latestAssistantId = messageId
          },
          onError: (detail) => toast(detail, 'error'),
        },
        abortRef.current.signal,
      )
      // 结束后拉取完整消息（与库一致），并刷新树
      const sid = sessionId ?? currentSession
      if (sid) await loadMessages(sid)
      if (latestAssistantId) setTreeVersion((v) => v + 1)
      setBranchBanner(null) // 回答完成撤横幅
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast(errText(e), 'error')
      setBranchBanner(null)
    } finally {
      setStreaming(null)
      setBusy(false)
      try {
        setSessions(await api.get<SessionInfo[]>(`/courses/${courseId}/sessions`))
      } catch {
        /* ignore */
      }
    }
  }

  // 回答完成后"就此追问"：从该 assistant 消息分岔
  function branchFrom(messageId: number) {
    // 输入框预聚焦，提示用户当前处于分支输入状态
    setQuestion('')
    void ask(messageId)
  }

  function renameTreeNode(node: TreeNode) {
    const name = prompt('重命名分支（1-60 字）', node.branch_name ?? node.content.slice(0, 24))
    if (!name || !name.trim()) return
    void (async () => {
      try {
        await api.patch(`/messages/${node.id}/rename`, { branch_name: name.trim() })
        setTreeVersion((v) => v + 1)
        toast('分支已重命名')
      } catch (e) {
        toast(errText(e), 'error')
      }
    })()
  }

  function jumpToNode(node: TreeNode) {
    // 跳转：滚动到对应 user 消息（按 id 匹配 DOM）
    setShowTree(false)
    const el = document.getElementById(`msg-${node.id}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.animate(
        [{ boxShadow: '0 0 0 3px var(--yellow)' }, { boxShadow: '0 0 0 0 transparent' }],
        { duration: 1600 },
      )
    }
  }

  const nickname = profile?.nickname ?? '我'

  return (
    <div style={{ height: 'calc(100vh - 96px)', display: 'flex', gap: '18px', alignItems: 'stretch' }}>
      {/* 左：课程与会话（独立滚动） */}
      <div className="panel reveal" style={{ width: 230, flexShrink: 0, padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', overflow: 'auto' }}>
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
        <div style={{ display: 'grid', gap: '8px', overflow: 'auto' }}>
          {sessions.map((s) => (
            <button
              key={s.id}
              className="btn"
              style={{
                justifyContent: 'flex-start', minHeight: 36, padding: '6px 10px', fontSize: 13,
                background: s.id === sessionId ? 'var(--mint)' : undefined,
                color: s.id === sessionId ? '#102f46' : undefined,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
              onClick={() => void loadMessages(s.id)}
              title={s.title}
            >
              {s.title}
            </button>
          ))}
        </div>
      </div>

      {/* 右：对话区（独立滚动，页面不再整体滚动） */}
      <div className="panel reveal delay-1" style={{ flex: 1, padding: '20px', display: 'flex', flexDirection: 'column', minHeight: 0, position: 'relative' }}>
        {/* 顶部工具条：导图开关 + 书库勾选（与"提问"按钮同款样式的常驻按钮） */}
        <div style={{ display: 'flex', gap: '10px', marginBottom: '10px', flexWrap: 'wrap', position: 'relative' }}>
          <button
            className="btn"
            style={showTree ? { background: 'var(--yellow)', color: '#0b3149' } : undefined}
            onClick={() => {
              if (!sessionId) {
                toast('先提一个问题，才有思维导图可看', 'error')
                return
              }
              setShowTree((v) => !v)
            }}
            title="问题思维导图（分支鸟瞰）"
          >
            🌳 导图
          </button>

          {/* 书库勾选（全局图书并入检索范围） */}
          <div data-book-picker style={{ position: 'relative' }}>
            <button
              className="btn"
              style={showBookPicker || selectedBooks.size > 0 ? { background: 'var(--mint)', color: '#102f46' } : undefined}
              onClick={() => setShowBookPicker((v) => !v)}
              title="勾选书库图书，提问时一起检索"
            >
              📚 书库{selectedBooks.size > 0 ? ` ×${selectedBooks.size}` : ''}
            </button>
            {showBookPicker && (
              <div
                className="panel"
                style={{ position: 'absolute', top: '110%', left: 0, zIndex: 50, width: 280, padding: '12px', background: 'var(--panel-strong)' }}
              >
                <b style={{ font: "7px/1 var(--mono)", color: 'var(--ink-strong)' }}>查这些书</b>
                {books.length === 0 ? (
                  <p style={{ color: 'var(--muted)', fontSize: 12, margin: '8px 0 0' }}>
                    书库还没有已就绪的书——去「书库」页上传教材。
                  </p>
                ) : (
                  <div style={{ display: 'grid', gap: '6px', marginTop: '8px' }}>
                    {books.map((b) => (
                      <label key={b.id} style={{ display: 'flex', gap: '8px', alignItems: 'center', cursor: 'pointer', padding: '4px 6px', border: '2px solid var(--line)', background: selectedBooks.has(b.id) ? 'var(--mint)' : 'var(--panel-soft)' }}>
                        <input
                          type="checkbox"
                          checked={selectedBooks.has(b.id)}
                          onChange={() =>
                            setSelectedBooks((prev) => {
                              const next = new Set(prev)
                              if (next.has(b.id)) next.delete(b.id)
                              else next.add(b.id)
                              return next
                            })
                          }
                          style={{ width: 15, height: 15, accentColor: 'var(--blue-strong)' }}
                        />
                        <span style={{ fontSize: 12, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.title}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 追问反馈横幅：明确提示当前处于分支上下文 */}
          {branchBanner && (
            <div
              className="badge"
              style={{
                alignSelf: 'center', padding: '8px 12px', fontSize: 11, fontWeight: 700,
                background: 'var(--yellow)', color: '#0b3149', border: '2px solid var(--line)',
              }}
            >
              {branchBanner}
            </div>
          )}
        </div>

        {/* 思维导图浮层（SVG 横向树：点外关闭、节点跳转、右键重命名） */}
        {showTree && tree && (
          <MindMapOverlay roots={tree} onJump={jumpToNode} onRename={renameTreeNode} onClose={() => setShowTree(false)} />
        )}

        <div style={{ flex: 1, overflow: 'auto', display: 'grid', gap: '16px', alignContent: 'start', minHeight: 0 }}>
          {messages.length === 0 && !streaming && (
            <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px 0' }}>
              问点什么吧，例如：「这份资料的核心观点是什么？」
              <br />黄底 = 出自你的资料（带引用可核对）；灰底 = 模型通识。
            </p>
          )}
          {messages.map((m) =>
            m.role === 'user' ? (
              <div
                key={m.id}
                id={`msg-${m.id}`}
                className="panel-soft"
                style={{ padding: '12px 16px', justifySelf: 'end', maxWidth: '80%', display: 'flex', gap: 10, alignItems: 'center' }}
              >
                {profile?.avatar && (
                  <img src={profile.avatar} alt="" style={{ width: 28, height: 28, border: '2px solid var(--line)', objectFit: 'cover' }} />
                )}
                <div>
                  <b style={{ color: 'var(--blue-strong)', fontSize: 12 }}>{m.branch_name ?? nickname}</b>
                  <p style={{ margin: '4px 0 0' }}>{m.content}</p>
                </div>
              </div>
            ) : (
              <div key={m.id} style={{ maxWidth: '92%' }}>
                <AnswerBlock segments={m.segments ?? [{ layer: 'general', text: m.content }]} citations={m.citations} />
                {/* 就此追问：短宽按钮（用户反馈原箭头太细长不明显） */}
                {!streaming && !busy && (
                  <button
                    className="btn btn-warn"
                    style={{ minHeight: 38, padding: '6px 16px', fontSize: 13, marginTop: 10, gap: 6 }}
                    onClick={() => branchFrom(m.id)}
                    title="基于这个回答继续提问，长出新分支"
                  >
                    <span style={{ fontSize: 15, lineHeight: 1 }}>↳</span> 就此追问
                  </button>
                )}
              </div>
            ),
          )}

          {streaming && (
            <div style={{ maxWidth: '92%' }}>
              <AnswerBlock segments={streaming.segments} citations={streaming.citations} isStreaming />
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={{ display: 'flex', gap: '10px', marginTop: '12px', alignItems: 'flex-end' }}>
          <label
            className="panel-soft"
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', cursor: 'pointer', userSelect: 'none' }}
            title="开启后只用你的资料回答，不出通识补充"
          >
            <input
              type="checkbox"
              checked={docsOnly}
              onChange={(e) => setDocsOnly(e.target.checked)}
              style={{ width: 15, height: 15, accentColor: 'var(--blue-strong)' }}
            />
            <span style={{ fontSize: 12, fontWeight: 700 }}>仅资料</span>
          </label>
          <textarea
            className="pixel-input"
            placeholder="围绕勾选的资料提问…（Enter 发送，Shift+Enter 换行）"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void ask(null)
              }
            }}
            style={{ flex: 1, minHeight: 56 }}
            disabled={busy || !courseId}
          />
          <button className="btn btn-primary" onClick={() => void ask(null)} disabled={busy || !courseId}>
            {busy ? '回答中…' : '提问'}
          </button>
        </div>
      </div>
    </div>
  )
}

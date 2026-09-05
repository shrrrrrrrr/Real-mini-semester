/**
 * 问答页：固定视口布局（对话区独立滚动）+ 双层答案 + 仅资料模式
 * + 分支对话（思源式浮层树：右侧按钮唤出、节点跳转、右键重命名、点外关闭）
 * + 就这提问预填跳转支持（location.state.prefill）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errText, streamChat, type StreamCitation } from '../lib/api'
import type { Course, MessageInfo, SessionInfo, TreeNode } from '../lib/types'
import { AnswerBlock } from '../components/AnswerBlock'
import { useToast } from '../components/Toast'

interface StreamingState {
  segments: { layer: 'doc' | 'general'; text: string }[]
  citations: StreamCitation[] | null
  active: boolean
}

/** 树节点组件：点击跳转、右键重命名。 */
function TreeItem({
  node,
  depth,
  onJump,
  onRename,
}: {
  node: TreeNode
  depth: number
  onJump: (n: TreeNode) => void
  onRename: (n: TreeNode) => void
}) {
  const label = node.branch_name ?? node.content.slice(0, 24)
  return (
    <div style={{ paddingLeft: depth * 14 }}>
      <div
        className="tree-node"
        style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '6px 8px', margin: '3px 0',
          border: '2px solid var(--line)', background: 'var(--panel-soft)',
          cursor: 'pointer', fontSize: 12, fontWeight: 700,
        }}
        onClick={() => onJump(node)}
        onContextMenu={(e) => {
          e.preventDefault()
          onRename(node)
        }}
        title={`${label}\n点击跳转 · 右键重命名`}
      >
        <span style={{ color: 'var(--blue-strong)' }}>Q</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        {node.children.length > 0 && (
          <span className="badge" style={{ marginLeft: 'auto' }}>{node.children.length}</span>
        )}
      </div>
      {node.children.map((c) => (
        <TreeItem key={c.id} node={c} depth={depth + 1} onJump={onJump} onRename={onRename} />
      ))}
    </div>
  )
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
  const abortRef = useRef<AbortController | undefined>(undefined)
  const bottomRef = useRef<HTMLDivElement>(null)
  const treePanelRef = useRef<HTMLDivElement>(null)
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

  // 点击浮层外关闭
  useEffect(() => {
    if (!showTree) return
    const onDown = (e: MouseEvent) => {
      if (treePanelRef.current && !treePanelRef.current.contains(e.target as Node)) {
        setShowTree(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [showTree])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, streaming])

  async function ask(parentMessageId: number | null = null) {
    const q = question.trim()
    if (!q || !courseId || busy) return
    setBusy(true)
    setQuestion('')
    setStreaming({ segments: [], citations: null, active: true })
    abortRef.current = new AbortController()
    const currentSession = sessionId
    try {
      let latestAssistantId: number | null = null
      await streamChat(
        { course_id: courseId, session_id: currentSession, question: q, parent_message_id: parentMessageId, docs_only: docsOnly },
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
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast(errText(e), 'error')
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
        {/* 浮层树按钮（右侧边缘常驻） */}
        <button
          className="btn"
          style={{ position: 'absolute', right: -14, top: '30%', zIndex: 30, minHeight: 60, width: 44, padding: 6, writingMode: 'vertical-rl' }}
          onClick={() => {
            if (!sessionId) {
              toast('先提一个问题，才有分支树可看', 'error')
              return
            }
            setShowTree((v) => !v)
          }}
          title="分支树（问题鸟瞰图）"
          aria-label="打开分支树"
        >
          树
        </button>

        {/* 分支树浮层（思源式：右侧弹出、点外关闭） */}
        {showTree && (
          <div
            ref={treePanelRef}
            className="panel"
            style={{
              position: 'absolute', right: 20, top: 16, bottom: 16, width: 300, zIndex: 40,
              padding: '14px', overflow: 'auto', background: 'var(--panel-strong)',
            }}
          >
            <b style={{ font: "7px/1 var(--mono)", color: 'var(--ink-strong)' }}>问题分支树</b>
            <p style={{ color: 'var(--muted)', fontSize: 11, margin: '4px 0 10px' }}>点击跳转 · 右键重命名分支</p>
            {tree && tree.length > 0 ? (
              tree.map((n) => (
                <TreeItem key={n.id} node={n} depth={0} onJump={jumpToNode} onRename={renameTreeNode} />
              ))
            ) : (
              <p style={{ color: 'var(--muted)', fontSize: 12 }}>暂无分支。回答完成后点"就此追问"长出新分支。</p>
            )}
          </div>
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
                {/* 就此追问：从该答案分出新分支 */}
                {!streaming && !busy && (
                  <button
                    className="btn"
                    style={{ minHeight: 30, padding: '4px 10px', fontSize: 12, marginTop: 8 }}
                    onClick={() => branchFrom(m.id)}
                    title="从这个问题继续追问，生成新分支"
                  >
                    ↳ 就此追问
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

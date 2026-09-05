/**
 * 课程资料库：建课程 → 多格式上传 → 解析状态轮询 → 范围勾选。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errText } from '../lib/api'
import type { Course, DocumentInfo } from '../lib/types'
import { useToast } from '../components/Toast'
import { currentQuote, nextQuote, type Quote } from '../lib/quotes'

const ACCEPT = '.pdf,.docx,.pptx,.epub,.txt,.md'
const POLL_MS = 1500 // 解析状态轮询间隔

const STATUS_TEXT: Record<string, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'badge badge-warn badge-pulse' },
  parsing: { label: '解析中', cls: 'badge badge-warn badge-pulse' },
  indexed: { label: '已就绪', cls: 'badge badge-ok' },
  failed: { label: '解析失败', cls: 'badge badge-danger' },
  rejected: { label: '扫描件拒收', cls: 'badge badge-danger' },
}

export function LibraryPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [activeCourse, setActiveCourse] = useState<string | null>(null)
  const [docs, setDocs] = useState<DocumentInfo[]>([])
  const [newCourse, setNewCourse] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const { toast } = useToast()
  // 今日签只在用户主动点击“换一条”时改变；刷新页面仍保留当天选中的内容。
  const [quote, setQuote] = useState<Quote>(() => currentQuote())

  const loadCourses = useCallback(async () => {
    try {
      const list = await api.get<Course[]>('/courses')
      setCourses(list)
      // 默认选中第一个课程（无课程时引导创建）
      if (list.length > 0 && !activeCourse) setActiveCourse(list[0].id)
    } catch (e) {
      toast(errText(e), 'error')
    }
  }, [activeCourse, toast])

  const loadDocs = useCallback(async (courseId: string) => {
    try {
      setDocs(await api.get<DocumentInfo[]>(`/courses/${courseId}/documents`))
    } catch (e) {
      toast(errText(e), 'error')
    }
  }, [toast])

  useEffect(() => {
    void loadCourses()
  }, [loadCourses])

  useEffect(() => {
    if (activeCourse) void loadDocs(activeCourse)
  }, [activeCourse, loadDocs])

  // 有解析中的文档时轮询刷新状态（就绪后停止）
  useEffect(() => {
    const busy = docs.some((d) => d.status === 'pending' || d.status === 'parsing')
    if (!busy || !activeCourse) return
    const t = setInterval(() => void loadDocs(activeCourse), POLL_MS)
    return () => clearInterval(t)
  }, [docs, activeCourse, loadDocs])

  async function createCourse() {
    const name = newCourse.trim()
    if (!name) return
    try {
      const c = await api.post<Course>('/courses', { name })
      setNewCourse('')
      setCourses((prev) => [c, ...prev])
      setActiveCourse(c.id)
      toast(`课程「${name}」已创建`)
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function removeCourse(courseId: string) {
    try {
      await api.delete(`/courses/${courseId}`)
      setCourses((prev) => prev.filter((c) => c.id !== courseId))
      if (activeCourse === courseId) {
        setActiveCourse(null)
        setDocs([])
      }
      toast('课程已删除')
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function uploadFiles(files: FileList | File[]) {
    if (!activeCourse) {
      toast('先创建一个课程再上传资料', 'error')
      return
    }
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.append('file', file)
        // 文件上传不走统一 JSON 封装，手动 fetch
        const resp = await fetch(`/api/courses/${activeCourse}/documents`, {
          method: 'POST',
          body: form,
        })
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({ detail: `上传失败（${resp.status}）` }))
          toast(`${file.name}：${body.detail}`, 'error')
          continue
        }
      }
      await loadDocs(activeCourse)
      toast('上传完成，后台解析中…')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function toggleRag(doc: DocumentInfo) {
    if (!activeCourse) return
    try {
      await api.patch(`/documents/${doc.id}`, { include_in_rag: !doc.include_in_rag })
      setDocs((prev) => prev.map((d) => (d.id === doc.id ? { ...d, include_in_rag: !d.include_in_rag } : d)))
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function removeDoc(doc: DocumentInfo) {
    if (!confirm(`删除资料「${doc.filename}」？相关的问答引用会失效。`)) return
    try {
      await api.delete(`/documents/${doc.id}`)
      setDocs((prev) => prev.filter((d) => d.id !== doc.id))
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  const active = courses.find((c) => c.id === activeCourse)

  return (
    <>
      <div className="section-label reveal">
        <span>COURSE.LIB</span>
        <p>课程资料库</p>
        <i></i>
      </div>

      {/* 今日签：每日一句（文案在 src/lib/quotes.ts 改） */}
      <div className="panel reveal delay-1" style={{ padding: '12px 18px', marginBottom: '18px', display: 'flex', gap: '12px', alignItems: 'center' }}>
        <span style={{ fontSize: 24 }} aria-hidden="true">{quote.emoji}</span>
        <p style={{ margin: 0, font: '700 15px/1.6 var(--body)', color: 'var(--ink-strong)' }}>{quote.text}</p>
        <button className="btn" type="button" onClick={() => setQuote((current) => nextQuote(current))} style={{ minHeight: 30, marginLeft: 'auto', padding: '5px 8px', fontSize: 11, flexShrink: 0 }}>↻ 换一条</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 340px) 1fr', gap: '18px', alignItems: 'start' }}>
        {/* 左：课程列表 */}
        <div className="panel reveal delay-1" style={{ padding: '18px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              className="pixel-input"
              placeholder="新课程名，如：数据结构"
              value={newCourse}
              onChange={(e) => setNewCourse(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void createCourse()}
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" onClick={() => void createCourse()}>新建</button>
          </div>
          <div style={{ display: 'grid', gap: '10px', marginTop: '14px' }}>
            {courses.map((c) => (
              <div key={c.id} style={{ display: 'flex', gap: '6px' }}>
                <button
                  className="btn"
                  style={{
                    flex: 1,
                    justifyContent: 'space-between',
                    background: c.id === activeCourse ? 'var(--mint)' : undefined,
                    color: c.id === activeCourse ? '#102f46' : undefined,
                  }}
                  onClick={() => setActiveCourse(c.id)}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                  <span style={{ font: "7px/1 var(--mono)", opacity: 0.8, flexShrink: 0 }}>
                    {c.indexed_count}/{c.document_count}
                  </span>
                </button>
                <button
                  className="btn btn-danger"
                  style={{ width: 40, padding: 0 }}
                  title={`删除课程「${c.name}」（连同资料、问答、测验、闪卡）`}
                  aria-label={`删除课程 ${c.name}`}
                  onClick={() => {
                    if (confirm(`删除课程「${c.name}」？\n其资料、问答、测验、闪卡将一并删除，不可恢复。`)) {
                      void removeCourse(c.id)
                    }
                  }}
                >
                  ×
                </button>
              </div>
            ))}
            {courses.length === 0 && (
              <p style={{ color: 'var(--muted)', margin: 0, lineHeight: 1.7 }}>
                还没有课程。先建一门课（比如「数据结构」），再把课件拖进去。
              </p>
            )}
          </div>
        </div>

        {/* 右：资料表格 */}
        <div className="panel reveal delay-2" style={{ padding: '18px' }}>
          {active ? (
            <>
              <div
                className="drop-hint panel-soft"
                style={{
                  padding: '26px', textAlign: 'center', cursor: 'pointer',
                  borderStyle: 'dashed', marginBottom: '14px',
                }}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  void uploadFiles(e.dataTransfer.files)
                }}
              >
                <div style={{ fontSize: '28px', color: 'var(--blue-strong)' }}>+</div>
                <strong>拖拽文件到此处，或点击选择</strong>
                <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
                  支持 PDF / DOCX / PPTX / EPUB / TXT / MD（扫描版 PDF 会被拒收）
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  hidden
                  onChange={(e) => e.target.files && void uploadFiles(e.target.files)}
                />
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse', font: '700 13px/1.5 var(--body)' }}>
                <thead>
                  <tr style={{ color: 'var(--muted)', font: "7px/1 var(--mono)", textAlign: 'left' }}>
                    <th style={{ padding: '8px' }}>文件</th>
                    <th style={{ padding: '8px' }}>状态</th>
                    <th style={{ padding: '8px' }}>范围</th>
                    <th style={{ padding: '8px' }}>块数</th>
                    <th style={{ padding: '8px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {docs.map((d) => {
                    const st = STATUS_TEXT[d.status] ?? { label: d.status, cls: 'badge' }
                    return (
                      <tr key={d.id} style={{ borderTop: '2px dashed var(--line-strong)' }}>
                        <td style={{ padding: '10px 8px' }}>
                          <div>{d.filename}</div>
                          {d.fail_reason && (
                            <div style={{ color: 'var(--danger)', fontSize: '11px' }}>{d.fail_reason}</div>
                          )}
                        </td>
                        <td style={{ padding: '10px 8px' }}><span className={st.cls}>{st.label}</span></td>
                        <td style={{ padding: '10px 8px' }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={d.include_in_rag}
                              onChange={() => void toggleRag(d)}
                              style={{ width: '16px', height: '16px', accentColor: 'var(--blue-strong)' }}
                            />
                            问答
                          </label>
                        </td>
                        <td style={{ padding: '10px 8px', font: "7px/1 var(--mono)", color: 'var(--muted)' }}>
                          {d.chunk_count}
                        </td>
                        <td style={{ padding: '10px 8px' }}>
                          <button className="btn btn-danger" style={{ minHeight: 32, padding: '4px 10px' }} onClick={() => void removeDoc(d)}>
                            删除
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                  {docs.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ padding: '20px 8px', color: 'var(--muted)', textAlign: 'center' }}>
                        这门课还没有资料
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {active.document_count > 0 && (
                <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                  <button className="btn btn-primary" onClick={() => navigate('/chat', { state: { course: active.id } })}>
                    去问答 ↗
                  </button>
                  <button className="btn" onClick={() => navigate('/quiz', { state: { course: active.id } })}>
                    去测验
                  </button>
                  <button className="btn" onClick={() => navigate('/explain', { state: { course: active.id } })}>
                    去讲解
                  </button>
                </div>
              )}
            </>
          ) : (
            <p style={{ color: 'var(--muted)', padding: '20px' }}>左侧创建课程后开始上传资料。</p>
          )}
        </div>
      </div>

      {uploading && (
        <div className="panel-soft reveal" style={{ padding: '12px 16px', marginTop: '14px' }}>
          <div className="loading-bar" />
          <p style={{ margin: '8px 0 0', color: 'var(--muted)' }}>正在上传…</p>
        </div>
      )}
    </>
  )
}

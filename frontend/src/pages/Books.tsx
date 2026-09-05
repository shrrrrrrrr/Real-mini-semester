/**
 * 书库页：全局共享电子图书——上传（后台索引）、像素风封面卡片、
 * 删除/重新解析；问答页的"📚 书库"选择器从这里取数据。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, apiUrl, errText } from '../lib/api'
import type { Book } from '../lib/types'
import { useToast } from '../components/Toast'

const ACCEPT = '.pdf,.epub,.txt,.md'
const POLL_MS = 2500  // 大书解析慢，放宽轮询间隔

const STATUS_TEXT: Record<string, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'badge badge-warn badge-pulse' },
  parsing: { label: '解析中', cls: 'badge badge-warn badge-pulse' },
  indexed: { label: '已就绪', cls: 'badge badge-ok' },
  failed: { label: '解析失败', cls: 'badge badge-danger' },
  rejected: { label: '扫描件拒收', cls: 'badge badge-danger' },
}

export function BooksPage() {
  const [books, setBooks] = useState<Book[]>([])
  const [uploading, setUploading] = useState(false)
  const [editingBookId, setEditingBookId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const load = useCallback(async () => {
    try {
      setBooks(await api.get<Book[]>('/books'))
    } catch (e) {
      toast(errText(e), 'error')
    }
  }, [toast])

  useEffect(() => {
    void load()
  }, [load])

  // 有解析中的书时轮询
  useEffect(() => {
    const busy = books.some((b) => b.status === 'pending' || b.status === 'parsing')
    if (!busy) return
    const t = setInterval(() => void load(), POLL_MS)
    return () => clearInterval(t)
  }, [books, load])

  async function upload(files: FileList | File[]) {
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.append('file', file)
        // 书名默认取文件名去扩展名（与后端逻辑一致）；用户可在书库页随时编辑
        form.append('title', file.name.replace(/\.[^.]+$/, ''))
        const resp = await fetch(apiUrl('/books'), { method: 'POST', body: form })
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({ detail: `上传失败（${resp.status}）` }))
          toast(`${file.name}：${body.detail}`, 'error')
          continue
        }
      }
      await load()
      toast('上传完成，大书解析需要几分钟，期间可做别的')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function removeBook(b: Book) {
    if (!confirm(`删除《${b.title}》？该书的所有索引将被清除。`)) return
    try {
      await api.delete(`/books/${b.id}`)
      setBooks((prev) => prev.filter((x) => x.id !== b.id))
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  function beginRename(book: Book) {
    setEditingBookId(book.id)
    setEditingTitle(book.title)
  }

  async function saveRename(book: Book) {
    const title = editingTitle.trim()
    if (!title) {
      toast('书名不能为空', 'error')
      return
    }
    try {
      const updated = await api.patch<Book>(`/books/${book.id}`, { title })
      setBooks((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      setEditingBookId(null)
      toast('书名与封面已更新')
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  async function reindex(b: Book) {
    try {
      await api.post(`/books/${b.id}/reindex`)
      await load()
    } catch (e) {
      toast(errText(e), 'error')
    }
  }

  return (
    <>
      <div className="section-label reveal">
        <span>BOOK.SHELF</span>
        <p>书库 · 全局共享</p>
        <i></i>
      </div>

      <div
        className="panel reveal delay-1"
        style={{ padding: '22px', textAlign: 'center', cursor: 'pointer', borderStyle: 'dashed', marginBottom: '18px' }}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          void upload(e.dataTransfer.files)
        }}
      >
        <div style={{ fontSize: 30, color: 'var(--blue-strong)' }}>＋</div>
        <strong>把教材 / 电子书拖到这里，或点击选择</strong>
        <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
          支持 PDF / EPUB / TXT / MD（上限 200MB）——上传后自动解析索引，之后在问答页勾选即可"查这本书"
        </p>
        <input ref={fileRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => e.target.files && void upload(e.target.files)} />
      </div>

      {uploading && (
        <div className="panel-soft" style={{ padding: '12px 16px', marginBottom: '14px' }}>
          <div className="loading-bar" />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: '16px' }}>
        {books.map((b) => {
          const st = STATUS_TEXT[b.status] ?? { label: b.status, cls: 'badge' }
          return (
            <div key={b.id} className="panel reveal" style={{ padding: '14px' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                {b.cover ? (
                  <img
                    src={b.cover}
                    alt=""
                    style={{ width: 64, height: 64, imageRendering: 'pixelated', border: '3px solid var(--line)', boxShadow: '3px 3px 0 var(--shadow)' }}
                  />
                ) : (
                  <div style={{ width: 64, height: 64, background: 'var(--mint)', display: 'grid', placeItems: 'center', border: '3px solid var(--line)' }}>📖</div>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  {editingBookId === b.id ? (
                    <input
                      className="pixel-input"
                      value={editingTitle}
                      autoFocus
                      maxLength={120}
                      onChange={(event) => setEditingTitle(event.target.value)}
                      onKeyDown={(event) => event.key === 'Enter' && void saveRename(b)}
                      style={{ width: '100%', minHeight: 34, padding: '5px 7px', fontSize: 13 }}
                      aria-label="编辑书名"
                    />
                  ) : (
                    <b style={{ font: '700 15px/1.3 var(--pixel)', color: 'var(--ink-strong)', display: 'block', overflowWrap: 'anywhere' }}>
                      {b.title}
                    </b>
                  )}
                  <span className={st.cls} style={{ marginTop: 6 }}>{st.label}</span>
                </div>
              </div>
              {b.fail_reason && (
                <p style={{ color: 'var(--danger)', fontSize: 11, margin: '8px 0 0' }}>{b.fail_reason}</p>
              )}
              <p style={{ color: 'var(--muted)', font: "7px/1.5 var(--mono)", margin: '8px 0 0' }}>
                {b.page_count > 0 ? `${b.page_count} 单元 · ${b.chunk_count} 块` : b.file_type.toUpperCase()}
              </p>
              <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                {(b.status === 'failed' || b.status === 'rejected') && (
                  <button className="btn" style={{ flex: 1, minHeight: 30, fontSize: 12 }} onClick={() => void reindex(b)}>
                    重新解析
                  </button>
                )}
                {editingBookId === b.id ? (
                  <>
                    <button className="btn btn-primary" style={{ minHeight: 30, fontSize: 12, padding: '4px 10px' }} onClick={() => void saveRename(b)}>保存</button>
                    <button className="btn" style={{ minHeight: 30, fontSize: 12, padding: '4px 10px' }} onClick={() => setEditingBookId(null)}>取消</button>
                  </>
                ) : (
                  <button className="btn" style={{ minHeight: 30, fontSize: 12, padding: '4px 10px' }} onClick={() => beginRename(b)}>改名</button>
                )}
                <button className="btn btn-danger" style={{ marginLeft: 'auto', minHeight: 30, fontSize: 12, padding: '4px 10px' }} onClick={() => void removeBook(b)}>
                  删除
                </button>
              </div>
            </div>
          )
        })}
        {books.length === 0 && !uploading && (
          <div className="panel" style={{ padding: '40px', gridColumn: '1 / -1', textAlign: 'center' }}>
            <p style={{ color: 'var(--muted)', margin: 0 }}>
              书库还是空的。把《算法导论》这类大部头传进来，提问时直接"查这本书"。
            </p>
          </div>
        )}
      </div>
    </>
  )
}

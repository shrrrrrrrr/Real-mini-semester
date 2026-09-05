/**
 * 后端 API 调用层：统一 fetch 封装 + SSE 流式解析。
 *
 * 前端所有请求以 /api 开头（开发环境经 Vite 代理转发到 FastAPI，
 * 生产环境同源部署或配置反向代理），因此无需额外 baseURL。
 */

export interface ApiError {
  status: number
  detail: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    // FastAPI 错误响应体：{"detail": "..."} 或 HTTPException 默认结构
    let detail = `请求失败（${resp.status}）`
    try {
      const body = await resp.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* 非 JSON 错误体，使用默认提示 */
    }
    throw { status: resp.status, detail } satisfies ApiError
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/** 解析 FastAPI 抛出的 ApiError 为可展示文本。 */
export function errText(e: unknown): string {
  if (e && typeof e === 'object' && 'detail' in e) {
    return String((e as ApiError).detail)
  }
  return e instanceof Error ? e.message : '未知错误'
}

/* ---------------------------------------------------------------------------
 * SSE 流式问答：POST + ReadableStream 手动解析
 * （EventSource 仅支持 GET，问答需要 POST 请求体，故用 fetch 流式读取）
 *
 * 事件协议（后端 POST /api/chat/stream）：
 *   data: {"type":"session","session_id":"...","title":"..."}
 *   data: {"type":"segment_start","layer":"doc"|"general"}
 *   data: {"type":"token","text":"..."}
 *   data: {"type":"citations","citations":[{index,chunk_id,filename,locator,snippet}]}
 *   data: {"type":"done","message_id":123}
 *   data: {"type":"error","detail":"..."}
 * ------------------------------------------------------------------------- */

export interface StreamSegment {
  layer: 'doc' | 'general'
  text: string
}

export interface StreamCitation {
  index: number
  chunk_id: number
  filename: string
  locator: string
  snippet: string
}

export interface StreamHandlers {
  onSession?: (sessionId: string, title: string) => void
  onSegmentStart?: (layer: 'doc' | 'general') => void
  onToken?: (text: string) => void
  onCitations?: (citations: StreamCitation[]) => void
  onDone?: (messageId: number) => void
  onError?: (detail: string) => void
}

export async function streamChat(
  body: {
    course_id: string
    session_id?: string | null
    question: string
    parent_message_id?: number | null
    docs_only?: boolean
  },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok || !resp.body) {
    let detail = `请求失败（${resp.status}）`
    try {
      const err = await resp.json()
      if (typeof err.detail === 'string') detail = err.detail
    } catch {
      /* 忽略非 JSON 错误体 */
    }
    handlers.onError?.(detail)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  // SSE 按 "data: {...}\n\n" 分帧；逐块读取后按行拆解
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const data = line.slice(5).trim()
      if (!data) continue
      let evt: Record<string, unknown>
      try {
        evt = JSON.parse(data)
      } catch {
        continue
      }
      switch (evt.type) {
        case 'session':
          handlers.onSession?.(String(evt.session_id), String(evt.title))
          break
        case 'segment_start':
          handlers.onSegmentStart?.(evt.layer as 'doc' | 'general')
          break
        case 'token':
          handlers.onToken?.(String(evt.text))
          break
        case 'citations':
          handlers.onCitations?.((evt.citations as StreamCitation[]) ?? [])
          break
        case 'done':
          handlers.onDone?.(Number(evt.message_id))
          break
        case 'error':
          handlers.onError?.(String(evt.detail))
          break
      }
    }
  }
}

/* ---------------------------------------------------------------------------
 * 生成任务轮询：切页面不中断（后台跑完落库，回来即见结果）
 * ------------------------------------------------------------------------- */

import type { GenTaskInfo } from './types'

export function pollTask(
  taskId: string,
  onUpdate: (t: GenTaskInfo) => void,
  intervalMs = 1500,
): { cancel: () => void; promise: Promise<GenTaskInfo> } {
  let cancelled = false
  const promise = (async () => {
    for (;;) {
      if (cancelled) throw new Error('cancelled')
      const t = await api.get<GenTaskInfo>(`/tasks/${taskId}`)
      onUpdate(t)
      if (t.status === 'done' || t.status === 'failed') return t
      await new Promise((r) => setTimeout(r, intervalMs))
    }
  })()
  return { cancel: () => (cancelled = true), promise }
}

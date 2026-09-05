/**
 * 双层答案渲染组件：本产品可信卖点的 UI 落点。
 *
 * - doc 分区：黄底高亮 + [n] 引用角标（点击展开原文核对）；
 * - general 分区：灰底虚线框 + "模型通识"标签（与资料内容强区分）；
 * - 流式渲染时逐 token 追加（isStreaming 控制光标）。
 */

import { useMemo } from 'react'
import type { StreamCitation } from '../lib/api'

interface Props {
  segments: { layer: 'doc' | 'general'; text: string }[]
  citations?: StreamCitation[] | null
  isStreaming?: boolean
}

/** 把带 [n] 角标的文本切成普通文本与角标片段，支持点击跳转引用。 */
function renderWithCitations(
  text: string,
  onCite: (n: number) => void,
) {
  const parts = text.split(/(\[\d+(?:\]\[\d+)*\])/g)
  return parts.map((part, i) => {
    const nums = part.match(/^\[(\d+)\]$/)
    if (nums) {
      const n = Number(nums[1])
      return (
        <button key={i} className="citation-chip" onClick={() => onCite(n)} title={`查看引用 ${n}`}>
          [{n}]
        </button>
      )
    }
    return <span key={i}>{part}</span>
  })
}

export function AnswerBlock({ segments, citations, isStreaming }: Props) {
  const grouped = useMemo(() => {
    // 合并相邻同层分段（流式过程中可能出现多次 segment_start）
    const out: { layer: 'doc' | 'general'; text: string }[] = []
    for (const s of segments) {
      const last = out[out.length - 1]
      if (last && last.layer === s.layer) last.text += s.text
      else out.push({ ...s })
    }
    return out
  }, [segments])

  const scrollToCitation = (n: number) => {
    const el = document.getElementById(`citation-${n}`) as HTMLDetailsElement | null
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      el.open = true
    }
  }

  if (segments.length === 0 && isStreaming) {
    return (
      <div className="panel-soft" style={{ padding: '14px 16px' }}>
        <span className="typing-cursor" /> 正在检索与思考…
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gap: '18px' }}>
      {grouped.map((seg, idx) => {
        const isLast = idx === grouped.length - 1
        if (seg.layer === 'doc') {
          return (
            <div key={idx} className="answer-doc">
              <span className="answer-doc-label">资料依据</span>
              <p style={{ margin: 0, lineHeight: 1.8 }}>
                {renderWithCitations(seg.text, scrollToCitation)}
                {isLast && isStreaming && <span className="typing-cursor" />}
              </p>
            </div>
          )
        }
        return (
          <div key={idx} className="answer-general">
            <span className="answer-general-label">[ 模型通识 · 不来自你的资料 ]</span>
          <p style={{ margin: '8px 0 0', lineHeight: 1.8 }}>
              {seg.text}
              {isLast && isStreaming && <span className="typing-cursor" />}
            </p>
          </div>
        )
      })}

      {citations && citations.length > 0 && (
        <details className="citation-drawer">
          <summary>
            引用来源 · {citations.length} 处（点击核对原文）
          </summary>
          {citations.map((c) => (
            <div key={c.index} id={`citation-${c.index}`} className="citation-item">
              <span className="locator">
                [{c.index}] 《{c.filename}》 · {c.locator}
              </span>
              <blockquote>{c.snippet}</blockquote>
            </div>
          ))}
        </details>
      )}
    </div>
  )
}

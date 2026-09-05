/**
 * 双层答案渲染组件：本产品可信卖点的 UI 落点。
 *
 * - doc 分区：黄底高亮 + [n] 引用角标（点击展开原文核对）；
 * - general 分区：灰底虚线框 + "模型通识"标签（与资料内容强区分）；
 * - 流式渲染时逐 token 追加（isStreaming 控制光标）。
 */

import { useMemo, useState } from 'react'
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

  // 右侧抽屉保存当前引用。角标不再只展开页面下方的 details，
  // 这样答案与原文可以同时留在视野中，便于答辩演示“可核对”。
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null)
  const scrollToCitation = (n: number) => setSelectedCitation(n)
  const selected = citations?.find((citation) => citation.index === selectedCitation) ?? null

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
        <>
          <button className="citation-source-button" type="button" onClick={() => setSelectedCitation((current) => current ?? citations[0].index)}>
            引用来源 · {citations.length} 处
          </button>
          {selected && (
            <aside className="citation-drawer citation-side-drawer" aria-label="引用原文抽屉">
              <div className="citation-drawer-head">
                <b>引用原文</b>
                <button type="button" onClick={() => setSelectedCitation(null)} aria-label="关闭引用抽屉">×</button>
              </div>
              <div className="citation-tabs" aria-label="选择引用">
                {citations.map((citation) => (
                  <button key={citation.index} type="button" className={citation.index === selected.index ? 'active' : ''} onClick={() => setSelectedCitation(citation.index)}>[{citation.index}]</button>
                ))}
              </div>
              <div className="citation-item">
                <span className="locator">[{selected.index}] 《{selected.filename}》 · {selected.locator}</span>
                <p className="citation-note">定位由后端检索结果生成，回答模型不能改写它。</p>
                <blockquote>{selected.snippet}</blockquote>
              </div>
            </aside>
          )}
        </>
      )}
    </div>
  )
}

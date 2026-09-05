/**
 * 思维导图浮层：SVG 横向树（根在左、分支向右展开）。
 *
 * 自实现 tidy 布局（无需引第三方图库）：
 * - 递归计算子树高度 → 节点 y 居中于子树；
 * - x 按深度等距分布；
 * - 连线用三次贝塞尔（水平起止，视觉上是"生长"感）。
 * 交互：点击节点跳转对话；右键重命名分支；点浮层外关闭。
 */

import { useEffect, useMemo, useRef } from 'react'
import type { TreeNode } from '../lib/types'

const NODE_W = 150
const NODE_H = 36
const GAP_X = 60
const GAP_Y = 14

interface LaidNode {
  node: TreeNode
  x: number
  y: number
  depth: number
  children: LaidNode[]
}

function measure(node: TreeNode, depth: number): { laid: LaidNode; height: number } {
  const kids = node.children.map((c) => measure(c, depth + 1))
  const childrenHeight = kids.reduce((s, k) => s + k.height, 0) + Math.max(0, kids.length - 1) * GAP_Y
  const height = Math.max(NODE_H, childrenHeight)
  const laid: LaidNode = { node, x: 0, y: 0, depth, children: kids.map((k) => k.laid) }
  return { laid, height }
}

function place(laid: LaidNode, x: number, yTop: number): void {
  laid.x = x
  const ownHeight = Math.max(NODE_H, subtreeHeight(laid))
  laid.y = yTop + ownHeight / 2
  let cy = yTop
  for (const child of laid.children) {
    const ch = subtreeHeight(child)
    place(child, x + NODE_W + GAP_X, cy)
    cy += ch + GAP_Y
  }
}

function subtreeHeight(laid: LaidNode): number {
  if (laid.children.length === 0) return NODE_H
  const kidsH = laid.children.reduce((s, c) => s + subtreeHeight(c), 0)
  return Math.max(NODE_H, kidsH + (laid.children.length - 1) * GAP_Y)
}

export function MindMapOverlay({
  roots,
  onJump,
  onRename,
  onClose,
}: {
  roots: TreeNode[]
  onJump: (n: TreeNode) => void
  onRename: (n: TreeNode) => void
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  // 布局：多根时纵向堆叠
  const { laid, width, height } = useMemo(() => {
    const measured = roots.map((r) => measure(r, 0))
    const GAP_ROOT = 40
    let y = 20
    const all: LaidNode[] = []
    for (const m of measured) {
      place(m.laid, 20, y)
      all.push(m.laid)
      y += m.height + GAP_ROOT
    }
    const maxDepth = (n: LaidNode): number =>
      Math.max(n.depth, ...n.children.map(maxDepth))
    const w = 20 + (all.length ? Math.max(...all.map(maxDepth)) + 1 : 1) * (NODE_W + GAP_X)
    return { laid: all, width: Math.max(w, 300), height: y }
  }, [roots])

  // 点外关闭
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [onClose])

  if (!roots.length) {
    return (
      <div ref={panelRef} className="panel" style={{ position: 'absolute', right: 24, top: 70, zIndex: 60, padding: '18px', width: 280 }}>
        <p style={{ color: 'var(--muted)', margin: 0, fontSize: 13 }}>暂无分支。回答完成后点「就此追问」长出新分支。</p>
      </div>
    )
  }

  const allNodes: LaidNode[] = []
  const collect = (n: LaidNode) => {
    allNodes.push(n)
    n.children.forEach(collect)
  }
  laid.forEach(collect)

  return (
    <div
      ref={panelRef}
      className="panel"
      style={{
        position: 'absolute', right: 24, top: 60, bottom: 80, zIndex: 60, width: 'min(760px, 92%)',
        overflow: 'auto', padding: '12px', background: 'var(--panel-strong)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <b style={{ font: "7px/1 var(--mono)", color: 'var(--ink-strong)' }}>问题思维导图</b>
        <span style={{ color: 'var(--muted)', fontSize: 11 }}>点击跳转 · 右键重命名</span>
      </div>
      <svg width={width} height={height} style={{ display: 'block' }}>
        {allNodes.map((n) =>
          n.children.map((c) => (
            <path
              key={`e-${n.node.id}-${c.node.id}`}
              d={`M ${n.x + NODE_W} ${n.y} C ${n.x + NODE_W + GAP_X / 2} ${n.y}, ${c.x - GAP_X / 2} ${c.y}, ${c.x} ${c.y}`}
              fill="none"
              stroke="var(--line-strong)"
              strokeWidth={2}
            />
          )),
        )}
        {allNodes.map((n) => (
          <g
            key={n.node.id}
            transform={`translate(${n.x}, ${n.y - NODE_H / 2})`}
            style={{ cursor: 'pointer' }}
            onClick={() => onJump(n.node)}
            onContextMenu={(e) => {
              e.preventDefault()
              onRename(n.node)
            }}
          >
            <rect
              width={NODE_W}
              height={NODE_H}
              fill={n.depth === 0 ? 'var(--yellow)' : n.node.branch_name ? 'var(--mint)' : 'var(--panel-soft)'}
              stroke="var(--line-strong)"
              strokeWidth={2}
              rx={3}
            />
            <text x={8} y={NODE_H / 2 + 4} fontSize={11} fontWeight={700} fill="var(--ink-strong)">
              {(n.node.branch_name ?? n.node.content).slice(0, 12)}
            </text>
            {n.node.children.length > 0 && (
              <text x={NODE_W - 10} y={NODE_H / 2 + 4} fontSize={10} fill="var(--muted)" textAnchor="end">
                +{n.node.children.length}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  )
}

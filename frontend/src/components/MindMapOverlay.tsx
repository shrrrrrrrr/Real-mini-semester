/**
 * 对话分支树：逐条消息、从上到下展开。
 *
 * 节点直接对应后端 Message：用户消息的子节点是回答，回答的子节点是
 * “就此提问”后产生的新问题。因此它展示的是会话分叉，而不是知识概念图。
 * 容器保留双向滚动：树变宽或变长时，用户仍可回到任何历史分支。
 */

import { useEffect, useMemo, useRef } from 'react'
import type { TreeNode } from '../lib/types'

const NODE_W = 168
const NODE_H = 58
const GAP_X = 32
const GAP_Y = 58

interface LaidNode {
  node: TreeNode
  x: number
  y: number
  depth: number
  children: LaidNode[]
  width: number
}

function measure(node: TreeNode, depth: number): LaidNode {
  const children = node.children.map((child) => measure(child, depth + 1))
  const childrenWidth = children.reduce((total, child) => total + child.width, 0) + Math.max(0, children.length - 1) * GAP_X
  return { node, x: 0, y: depth * (NODE_H + GAP_Y), depth, children, width: Math.max(NODE_W, childrenWidth) }
}

function place(laid: LaidNode, left: number): void {
  // 父节点始终位于子树正中，上下层连线不会随着分支变多而乱跳。
  laid.x = left + (laid.width - NODE_W) / 2
  let childLeft = left
  for (const child of laid.children) {
    place(child, childLeft)
    childLeft += child.width + GAP_X
  }
}

function collect(node: LaidNode, all: LaidNode[]): void {
  all.push(node)
  node.children.forEach((child) => collect(child, all))
}

export function MindMapOverlay({
  roots,
  onJump,
  onRename,
  onClose,
}: {
  roots: TreeNode[]
  onJump: (node: TreeNode) => void
  onRename: (node: TreeNode) => void
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const { nodes, width, height } = useMemo(() => {
    const laidRoots = roots.map((root) => measure(root, 0))
    let left = 28
    for (const root of laidRoots) {
      place(root, left)
      left += root.width + GAP_X * 2
    }
    const all: LaidNode[] = []
    laidRoots.forEach((root) => collect(root, all))
    const deepest = all.length ? Math.max(...all.map((node) => node.depth)) : 0
    return {
      nodes: all,
      width: Math.max(420, left + 28),
      height: Math.max(260, 42 + (deepest + 1) * (NODE_H + GAP_Y)),
    }
  }, [roots])

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [onClose])

  if (!roots.length) {
    return (
      <div ref={panelRef} className="panel branch-tree-panel branch-tree-empty">
        <p>暂无对话。先提一个问题，回答下方会出现“就此提问”。</p>
      </div>
    )
  }

  return (
    <div ref={panelRef} className="panel branch-tree-panel">
      <div className="branch-tree-head">
        <div>
          <b>对话分支</b>
          <span>每个方块是一条消息；上下为同一轮，横向为不同分支</span>
        </div>
        <button className="btn" type="button" onClick={onClose}>收起</button>
      </div>
      <div className="branch-tree-scroll">
        <svg width={width} height={height} role="img" aria-label="上下展开的对话分支树">
          {nodes.flatMap((node) => node.children.map((child) => (
            <path
              key={`edge-${node.node.id}-${child.node.id}`}
              d={`M ${node.x + NODE_W / 2} ${node.y + NODE_H} C ${node.x + NODE_W / 2} ${node.y + NODE_H + GAP_Y / 2}, ${child.x + NODE_W / 2} ${child.y - GAP_Y / 2}, ${child.x + NODE_W / 2} ${child.y}`}
              className="branch-tree-edge"
            />
          )))}
          {nodes.map((laid) => {
            const isQuestion = laid.node.role === 'user'
            const title = isQuestion ? (laid.node.branch_name ?? '提问') : '回答'
            return (
              <g
                key={laid.node.id}
                transform={`translate(${laid.x}, ${laid.y})`}
                className="branch-tree-node"
                onClick={() => onJump(laid.node)}
                onContextMenu={(event) => {
                  if (!isQuestion) return
                  event.preventDefault()
                  onRename(laid.node)
                }}
              >
                <rect width={NODE_W} height={NODE_H} className={isQuestion ? 'question' : 'answer'} />
                <text x={10} y={17} className="branch-tree-node-title">{title}</text>
                <text x={10} y={39} className="branch-tree-node-content">{laid.node.content.slice(0, 17)}{laid.node.content.length > 17 ? '…' : ''}</text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
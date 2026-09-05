/**
 * FSRS 复习调度封装（ts-fsrs v5 官方库）。
 *
 * 架构约定（开发文档 §4.1 设计决策 1）：
 * - 前端计算、后端存储、以服务器数据为准；
 * - 评分瞬间本地算出四档各自的下次间隔（repeat 预览），
 *   渲染在评分按钮上，让用户不盲选；
 * - 评分后把新状态整体 PATCH 回后端。
 *
 * ts-fsrs v5 API 要点：
 * - Rating 含 Manual(0)，评分用的四档是 Grade（Again=1..Easy=4）；
 * - repeat(card, now) 返回 IPreview（RecordLog 的四档映射，可迭代）；
 * - next(card, now, grade) 返回 RecordLogItem { card, log }。
 */

import { fsrs, Rating, type Card, type Grade, type RecordLogItem } from 'ts-fsrs'

export { Rating }
export type { Card, Grade, RecordLogItem }

const scheduler = fsrs()

/** 数据库行 → ts-fsrs Card 对象（日期字段恢复为 Date）。 */
export function toCard(row: {
  due: string
  stability: number
  difficulty: number
  state: number
  reps: number
  lapses: number
  last_review?: string | null
}): Card {
  return {
    due: new Date(row.due),
    stability: row.stability,
    difficulty: row.difficulty,
    state: row.state as Card['state'],
    reps: row.reps,
    lapses: row.lapses,
    // v5 兼容字段（deprecated 但仍在类型中）
    elapsed_days: 0,
    scheduled_days: 0,
    learning_steps: 0,
    last_review: row.last_review ? new Date(row.last_review) : undefined,
  }
}

/** 评分前预览：四档各自的新卡片状态（渲染下次间隔在评分按钮上）。 */
export function previewIntervals(card: Card, now = new Date()): Record<Grade, Card> {
  const r = scheduler.repeat(card, now)
  return {
    [Rating.Again]: r[Rating.Again].card,
    [Rating.Hard]: r[Rating.Hard].card,
    [Rating.Good]: r[Rating.Good].card,
    [Rating.Easy]: r[Rating.Easy].card,
  }
}

/** 评分后推进：返回新卡片状态 + 复习日志（写 review_logs 用）。 */
export function applyRating(card: Card, grade: Grade, now = new Date()): RecordLogItem {
  return scheduler.next(card, now, grade)
}

/** 人类可读的间隔描述：如"10分钟"、"3天"、"2.1月"。 */
export function humanInterval(from: Date, to: Date): string {
  const ms = to.getTime() - from.getTime()
  if (ms <= 0) return '现在'
  const minutes = ms / 60000
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))}分钟`
  const hours = minutes / 60
  if (hours < 24) return `${Math.round(hours)}小时`
  const days = hours / 24
  if (days < 30) return `${Math.round(days)}天`
  const months = days / 30
  if (months < 12) return `${months.toFixed(1)}月`
  return `${(months / 12).toFixed(1)}年`
}

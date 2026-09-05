/**
 * 复习排程：考试冲刺模式 + 手动计划 + 离线积压合并。
 *
 * 三件事（开发文档 §5.2 技术点③）：
 * A. 冲刺模式：紧迫度 = 到期临近 × 低稳定性 × 错题来源加权 → 重排队列，
 *    脆弱卡考前至少二刷；
 * B. 手动计划：范围（仅错题/全部）+ 每日卡量 + 天数 → 逐日切分；
 * C. 离线积压：用户非 24 小时在线，学习期短间隔卡改为"下次打开优先清"。
 */

export interface PlanCard {
  id: string
  due: string
  stability: number
  state: number
  reps: number
  lapses: number
  difficulty: number
  origin: string // quiz | manual
}

/** 从完整闪卡行提取排程所需字段（窄化接口，避免全量依赖）。 */
export function toPlanCard(c: {
  id: string
  due: string
  stability: number
  state: number
  reps: number
  lapses: number
  difficulty: number
  origin: string
}): PlanCard {
  return {
    id: c.id,
    due: c.due,
    stability: c.stability,
    state: c.state,
    reps: c.reps,
    lapses: c.lapses,
    difficulty: c.difficulty,
    origin: c.origin,
  }
}

export interface PlanDay {
  date: string
  card_ids: string[]
  est_minutes: number
}

const AVG_CARD_SECONDS = 12 // 单卡平均耗时估计（秒），用于分钟预算换算
const DAY_MS = 86400000

export function daysBetween(a: Date, b: Date): number {
  return Math.max(0, Math.round((b.getTime() - a.getTime()) / DAY_MS))
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v))
}

/** 紧迫度：到期临近、稳定性低、错题来源，三项加权（0-1）。 */
export function urgency(card: PlanCard, today: Date, examDate: Date): number {
  const daysToExam = Math.max(1, daysBetween(today, examDate))
  const dueDate = new Date(card.due)
  const dueProximity = dueDate <= today ? 1 : clamp(1 - daysBetween(today, dueDate) / daysToExam, 0, 1)
  return (
    0.4 * dueProximity +
    0.4 * (1 - clamp(card.stability / 30, 0, 1)) +
    0.2 * (card.origin === 'quiz' ? 1 : 0)
  )
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

/** 冲刺计划：按紧迫度排序切分逐日队列，脆弱卡考前 48h 二刷。 */
export function makeSprintPlan(
  cards: PlanCard[],
  examDate: Date,
  budgetMinutes: number,
  today = new Date(),
): PlanDay[] {
  const D = Math.max(1, daysBetween(today, examDate))
  const perDay = Math.max(10, Math.ceil((budgetMinutes * 60) / AVG_CARD_SECONDS))
  const ranked = [...cards].sort(
    (a, b) => urgency(b, today, examDate) - urgency(a, today, examDate),
  )
  let days = chunk(ranked, perDay).slice(0, D)
  if (days.length === 0) days = [[]]

  // 二刷：紧迫度前 30% 的卡插入考前 48h 对应日（模拟"考前最后一遍"）
  const fragile = ranked.slice(0, Math.ceil(ranked.length * 0.3))
  const secondPassIdx = Math.max(0, days.length - 2) // 计划最后一天的前一天
  for (const c of fragile) {
    // 只对未出现在最后两天的卡补二刷，避免同一天重复
    const inLastTwo = days.slice(-2).some((d) => d.some((x) => x.id === c.id))
    if (!inLastTwo) days[secondPassIdx].push(c)
  }
  return days.map((cardsOfDay, i) => ({
    date: new Date(today.getTime() + i * DAY_MS).toISOString().slice(0, 10),
    card_ids: cardsOfDay.map((c) => c.id),
    est_minutes: Math.round((cardsOfDay.length * AVG_CARD_SECONDS) / 60),
  }))
}

/** 手动计划：范围过滤 + 每日卡量 + 天数 → 逐日切分。 */
export function makeManualPlan(
  cards: PlanCard[],
  onlyWrong: boolean,
  dailyCount: number,
  days: number,
  today = new Date(),
): PlanDay[] {
  let pool = cards
  if (onlyWrong) pool = cards.filter((c) => c.origin === 'quiz')
  // 优先到期卡在前
  const sorted = [...pool].sort((a, b) => new Date(a.due).getTime() - new Date(b.due).getTime())
  const parts = chunk(sorted, dailyCount).slice(0, days)
  return (parts.length ? parts : [[]]).map((cardsOfDay, i) => ({
    date: new Date(today.getTime() + i * DAY_MS).toISOString().slice(0, 10),
    card_ids: cardsOfDay.map((c) => c.id),
    est_minutes: Math.round((cardsOfDay.length * AVG_CARD_SECONDS) / 60),
  }))
}

/** 离线积压：打开复习页时先清的卡（学习期未巩固完的）。 */
export function pickBacklog(cards: PlanCard[], now = new Date()): PlanCard[] {
  // 学习期/重新学习期（state 1/3）且已到期的卡视为积压，优先清掉
  return cards.filter((c) => {
    const learning = c.state === 1 || c.state === 3
    return learning && new Date(c.due) <= now
  })
}

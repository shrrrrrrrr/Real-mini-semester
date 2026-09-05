/**
 * 共享类型：与后端 Pydantic 契约对齐的前端类型定义。
 */

export interface Course {
  id: string
  name: string
  created_at: string
  document_count: number
  indexed_count: number
  flashcard_count: number
  due_count: number
}

export interface DocumentInfo {
  id: string
  filename: string
  file_type: string
  locator_type: string
  status: string
  fail_reason?: string | null
  include_in_rag: boolean
  page_count: number
  chunk_count: number
  created_at: string
}

export interface SessionInfo {
  id: string
  title: string
  created_at: string
}

export interface MessageInfo {
  id: number
  role: string
  content: string
  segments: { layer: 'doc' | 'general'; text: string }[] | null
  citations:
    | {
        index: number
        chunk_id: number
        filename: string
        locator: string
        snippet: string
      }[]
    | null
  created_at: string
}

export interface ExplainSection {
  title: string
  nodes: {
    title: string
    summary: string
    linked_hint: string
    linked_chunk_ids: number[]
  }[]
}

export interface ExplainInfo {
  id: string
  course_id: string | null
  topic: string
  sections: ExplainSection[]
  created_at: string
}

export interface QuizInfo {
  id: string
  course_id: string
  question_count: number
  created_at: string
  questions: {
    id: number
    question_no: number
    stem: string
    options: string[]
    difficulty: string
  }[]
}

export interface QuizResult {
  total: number
  correct: number
  accuracy: number
  items: {
    question_id: number
    selected: string
    answer: string
    is_correct: boolean
    explanation: string
    stem: string
    options: string[]
  }[]
}

export interface Flashcard {
  id: string
  course_id: string
  front: string
  back: string
  origin: string
  origin_question_id?: number | null
  due: string
  stability: number
  difficulty: number
  state: number
  reps: number
  lapses: number
  last_review?: string | null
}

export interface ReviewPlanInfo {
  id: string
  course_id: string
  mode: string
  exam_date?: string | null
  daily_budget_minutes?: number | null
  scope: Record<string, unknown>
  plan_days: { date: string; card_ids: string[]; est_minutes: number }[]
  status: string
  created_at: string
}

export interface Stats {
  course_id: string
  total_cards: number
  due_today: number
  reviewed_today: number
  total_attempts: number
  correct_rate: number
  streak_days: number
  last_7_days: { date: string; reviewed: number; due: number }[]
}

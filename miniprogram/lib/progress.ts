// 学习进度：记忆卡片、每日统计、错词、进行中的这一轮。按全局 wordId 存，换书后学过的词不用重学。
// 纯数据和纯函数，不碰 wx；读写存储在 progress-store.ts。
import { CardState, Grade } from './srs'

export type QuizKind = 'meaning' | 'cloze' | 'listen' | 'spell'
export type Step = { id: string; kind: 'intro' } | { id: string; kind: QuizKind; retry?: boolean; options?: string[] }

export interface Session {
  id: string
  bookId: string
  started: number
  steps: Step[]
  index: number
  graded: Record<string, Grade> // 每个词第一次作答的评分；重练不改
  newIds: string[]
  reviewIds: string[]
  pending?: { correct: boolean; value: string } // 已作答、还没点「继续」，退出再进来不会重复计分
  finished?: number
}

export interface DayStat {
  n: number // 新学
  r: number // 作答（首次）
  c: number // 答对（首次）
  t: number // 学习秒数
}

export interface Progress {
  version: 1
  cards: Record<string, CardState>
  days: Record<string, DayStat>
  mistakes: string[] // 最近答错的词，新的在前
  session: Session | null
}

export const emptyProgress = (): Progress => ({ version: 1, cards: {}, days: {}, mistakes: [], session: null })

export const dayKey = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function bumpDay(p: Progress, delta: Partial<DayStat>, day = dayKey()): Progress {
  const cur = p.days[day] || { n: 0, r: 0, c: 0, t: 0 }
  const next: DayStat = { n: cur.n + (delta.n || 0), r: cur.r + (delta.r || 0), c: cur.c + (delta.c || 0), t: cur.t + (delta.t || 0) }
  return { ...p, days: { ...p.days, [day]: next } }
}

/** 连续学习天数：从今天（今天还没学就从昨天）往前数。 */
export function streak(p: Progress, today = new Date()): number {
  const studied = (d: Date) => (p.days[dayKey(d)]?.r || 0) > 0
  const d = new Date(today)
  if (!studied(d)) d.setDate(d.getDate() - 1)
  let n = 0
  while (studied(d)) {
    n += 1
    d.setDate(d.getDate() - 1)
  }
  return n
}

/* ---------- 校验：本地存的数据当作不可信输入（可能被别的版本写坏） ---------- */

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const num = (v: unknown, lo = -Infinity, hi = Infinity) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi

function validCard(v: unknown): v is CardState {
  return (
    isObj(v) && num(v.due, 0) && num(v.s, 0) && num(v.d, 0, 11) && num(v.el, 0) && num(v.sd, 0) && num(v.ls, 0) &&
    num(v.reps, 0) && num(v.lapses, 0) && [0, 1, 2, 3].includes(v.st as number) &&
    (v.last === undefined || num(v.last, 0)) && num(v.seen, 0)
  )
}

const QUIZ_KINDS = ['intro', 'meaning', 'cloze', 'listen', 'spell']

function validSession(v: unknown): v is Session {
  return (
    isObj(v) && typeof v.id === 'string' && typeof v.bookId === 'string' && num(v.started, 0) &&
    Array.isArray(v.steps) && v.steps.every((s) => isObj(s) && typeof s.id === 'string' && QUIZ_KINDS.includes(s.kind as string)) &&
    num(v.index, 0) && isObj(v.graded) && Array.isArray(v.newIds) && Array.isArray(v.reviewIds)
  )
}

export function sanitizeProgress(v: unknown): Progress {
  const out = emptyProgress()
  if (!isObj(v) || v.version !== 1) return out
  if (isObj(v.cards)) for (const [k, c] of Object.entries(v.cards)) if (validCard(c)) out.cards[k] = c
  if (isObj(v.days)) {
    for (const [k, d] of Object.entries(v.days)) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(k) && isObj(d) && num(d.n, 0) && num(d.r, 0) && num(d.c, 0) && num(d.t, 0)) {
        out.days[k] = { n: d.n as number, r: d.r as number, c: d.c as number, t: d.t as number }
      }
    }
  }
  if (Array.isArray(v.mistakes)) out.mistakes = v.mistakes.filter((x): x is string => typeof x === 'string').slice(0, 300)
  if (validSession(v.session)) out.session = v.session
  return out
}

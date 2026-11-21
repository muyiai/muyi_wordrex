// FSRS 间隔复习。移植自词光 word-atlas 的 src/store/srs.ts（MIT），参数一致：
// FSRS-6、默认目标记忆率 90%、学习步长 1 分钟 / 10 分钟、重学步长 10 分钟、开启随机抖动
import { Card, createEmptyCard, fsrs, Grade, Rating, State } from 'ts-fsrs'

/** 存储用的卡片：日期存成毫秒数，备份小、JSON 安全。 */
export interface CardState {
  due: number
  s: number // 稳定度（天）
  d: number // 难度
  el: number
  sd: number
  ls: number
  reps: number
  lapses: number
  st: 0 | 1 | 2 | 3 // 新 / 学习中 / 复习 / 重学
  last?: number
  seen: number // 第一次遇到这个词的时间
}

export { Rating }
export type { Grade }

const schedulers = new Map<number, ReturnType<typeof fsrs>>()
function scheduler(retention: number) {
  let s = schedulers.get(retention)
  if (!s) {
    s = fsrs({
      request_retention: retention,
      enable_fuzz: true,
      enable_short_term: true,
      learning_steps: ['1m', '10m'],
      relearning_steps: ['10m'],
    })
    schedulers.set(retention, s)
  }
  return s
}

function toCard(c: CardState): Card {
  return {
    due: new Date(c.due),
    stability: c.s,
    difficulty: c.d,
    elapsed_days: c.el,
    scheduled_days: c.sd,
    learning_steps: c.ls,
    reps: c.reps,
    lapses: c.lapses,
    state: c.st as State,
    last_review: c.last ? new Date(c.last) : undefined,
  }
}

function fromCard(c: Card, seen: number): CardState {
  return {
    due: c.due.getTime(),
    s: c.stability,
    d: c.difficulty,
    el: c.elapsed_days,
    sd: c.scheduled_days,
    ls: c.learning_steps,
    reps: c.reps,
    lapses: c.lapses,
    st: c.state as CardState['st'],
    last: c.last_review ? c.last_review.getTime() : undefined,
    seen,
  }
}

export function review(prev: CardState | undefined, grade: Grade, now: number, retention = 0.9): CardState {
  const card = prev ? toCard(prev) : createEmptyCard(new Date(now))
  const next = scheduler(retention).next(card, new Date(now), grade).card
  return fromCard(next, prev ? prev.seen : now)
}

/** 记得牢：复习状态，且稳定度 ≥ 21 天（三周后仍有 90% 把握想起来）。 */
export const MASTERED_STABILITY = 21
export const isMastered = (c?: CardState) => !!c && c.st === 2 && c.s >= MASTERED_STABILITY

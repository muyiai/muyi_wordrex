// 移植自词光 word-atlas 的 src/store/srs.test.ts
import { describe, expect, it } from 'vitest'
import { isMastered, Rating, review } from '../miniprogram/lib/srs'

const DAY = 86400000

describe('srs', () => {
  it('新词答对很快安排复习，答错更快', () => {
    const now = Date.UTC(2026, 9, 25)
    const good = review(undefined, Rating.Good, now)
    const again = review(undefined, Rating.Again, now)
    expect(again.due).toBeLessThanOrEqual(good.due)
    expect(good.reps).toBe(1)
    expect(good.seen).toBe(now)
  })

  it('连续答对，稳定度增长到「记得牢」', () => {
    let now = Date.UTC(2026, 9, 25)
    let c = review(undefined, Rating.Good, now)
    for (let i = 0; i < 8 && !isMastered(c); i++) {
      now = Math.max(c.due, now + DAY)
      c = review(c, Rating.Good, now)
    }
    expect(isMastered(c)).toBe(true)
  })

  it('遗忘一次：稳定度下降，计一次遗忘', () => {
    let now = Date.UTC(2026, 9, 25)
    let c = review(undefined, Rating.Good, now)
    for (let i = 0; i < 5; i++) {
      now = Math.max(c.due, now + DAY)
      c = review(c, Rating.Good, now)
    }
    const before = c.s
    c = review(c, Rating.Again, c.due)
    expect(c.lapses).toBe(1)
    expect(c.s).toBeLessThan(before)
    expect(isMastered(c)).toBe(false)
  })

  it('保留第一次遇到的时间', () => {
    const first = review(undefined, Rating.Good, 1000)
    expect(review(first, Rating.Good, first.due).seen).toBe(1000)
  })
})

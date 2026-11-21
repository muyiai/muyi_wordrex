import { describe, expect, it } from 'vitest'
import { merge } from '../cloudfunctions/sync/merge'
import { Rating, review } from '../miniprogram/lib/srs'

const T = Date.UTC(2026, 10, 21)
const card = (last: number, reps = 1) => ({ ...review(undefined, Rating.Good, last), reps })

describe('云同步合并', () => {
  it('每个词取最后一次复习的那份；一样新时取复习次数多的', () => {
    const phone = { cards: { a: card(T + 1000), b: card(T, 2) } }
    const pad = { cards: { a: card(T), b: card(T, 5), c: card(T) } }
    const m = merge(pad, phone)
    expect((m.cards.a as { last: number }).last).toBe(T + 1000)
    expect((m.cards.b as { reps: number }).reps).toBe(5)
    expect(Object.keys(m.cards).sort()).toEqual(['a', 'b', 'c'])
  })

  it('每日统计取较大值，重复同步不会翻倍', () => {
    const day = { '2026-11-21': { n: 3, r: 10, c: 8, t: 300 } }
    const m1 = merge({ days: day }, { days: day })
    expect(m1.days['2026-11-21']).toEqual({ n: 3, r: 10, c: 8, t: 300 })
    const m2 = merge(m1, { days: { '2026-11-21': { n: 5, r: 4, c: 4, t: 100 } } })
    expect(m2.days['2026-11-21']).toEqual({ n: 5, r: 10, c: 8, t: 300 })
  })

  it('错词取并集，这台设备的在前', () => {
    expect(merge({ mistakes: ['x', 'y'] }, { mistakes: ['z', 'x'] }).mistakes).toEqual(['z', 'x', 'y'])
  })

  it('丢掉坏数据：坏卡片、坏日期、非字符串错词；云端为空也能合并', () => {
    const m = merge(null, { cards: { ok: card(T), bad: { due: 'x' } }, days: { nope: { n: 1, r: 1, c: 1, t: 1 } }, mistakes: [1, 'ok'], session: { x: 1 } })
    expect(Object.keys(m.cards)).toEqual(['ok'])
    expect(m.days).toEqual({})
    expect(m.mistakes).toEqual(['ok'])
    expect(m).not.toHaveProperty('session')
    expect(merge(undefined, undefined)).toEqual({ version: 1, cards: {}, days: {}, mistakes: [] })
  })
})

import { describe, expect, it } from 'vitest'
import { chunkOf, fnv1a } from '../miniprogram/lib/hash'

describe('fnv1a', () => {
  it('标准测试向量', () => {
    expect(fnv1a('')).toBe(0x811c9dc5)
    expect(fnv1a('a')).toBe(0xe40c292c)
    expect(fnv1a('foobar')).toBe(0xbf9cf968)
  })

  it('与 Python 管线（tw/build.py）结果一致，包括非 ASCII', () => {
    expect(fnv1a('library')).toBe(2432105424)
    expect(fnv1a('telephone/phone_number')).toBe(1437777356)
    expect(fnv1a("you're_welcome")).toBe(2723926615)
    expect(fnv1a('café')).toBe(2821410889)
    expect(chunkOf('how_old', 48)).toBe(35)
  })
})

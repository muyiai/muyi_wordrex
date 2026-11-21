import { describe, expect, it } from 'vitest'
import { emptyProgress, Progress, sanitizeProgress, streak } from '../miniprogram/lib/progress'
import {
  advance, answer, buildSession, clozeOf, distractors, gradeFor, quizKind, sessionStats, StudySettings, studyWords,
  todayPlan,
} from '../miniprogram/lib/session'
import { Grade, Rating, review } from '../miniprogram/lib/srs'
import { Book, BookDict, BookWord } from '../miniprogram/lib/types'

const NOW = Date.UTC(2026, 10, 21, 8)
const S: StudySettings = { dailyNew: 10, retention: 0.9, spell: true }

const bw = (id: string, zh: string, patch: Partial<BookWord> = {}): BookWord => ({
  id, hw: id.replace(/_/g, ' '), senses: [{ pos: 'n.', zh }], req: true, ...patch,
})

const book: Book = {
  id: 'ps-test-3a', stage: 'ps', edition: 'test', editionName: '测试版', publisher: '', grade: 3, term: 'a', volume: '三年级上册',
  units: [
    { name: 'Unit 1', words: [bw('ruler', '尺子'), bw('pencil', '铅笔'), bw('eraser', '橡皮'), bw('crayon', '蜡笔'),
      bw('bag', '包'), bw('pen', '钢笔'), bw('Gina', '吉娜（女名）', { req: false, kind: 'name' })] },
    { name: 'Unit 2', words: [bw('red', '红色'), bw('green', '绿色'), bw('pencil_box', '铅笔盒', { kind: 'phrase' }),
      bw('blue', '蓝色'), bw('ruler', '尺子')] },
  ],
}

const dict: BookDict = {
  ruler: { id: 'ruler', w: 'ruler', kind: 'word', senses: [{ pos: 'n.', zh: '尺子' }], src: 'gen', aid: 'tw-ruler', m: 1 | 2,
    ex: [{ en: 'I have a long ruler.', zh: '我有一把长尺子。' }, { en: 'x', zh: 'y' }] },
  pencil_box: { id: 'pencil_box', w: 'pencil box', kind: 'phrase', senses: [{ pos: 'phr.', zh: '铅笔盒' }], src: 'gen',
    ex: [{ en: 'My pencil boxes are blue.', zh: '我的铅笔盒是蓝色的。' }] },
}

const words = studyWords(book, dict, 'https://cdn.example/atlas')

describe('studyWords', () => {
  it('按单元顺序、只要要求掌握的词、去重', () => {
    expect(words.map((w) => w.id)).toEqual(['ruler', 'pencil', 'eraser', 'crayon', 'bag', 'pen', 'red', 'green', 'pencil_box', 'blue'])
    expect(words[0].unit).toBe(0)
    expect(words[6].unit).toBe(1)
  })

  it('例句挖空、媒体按位标记判断', () => {
    expect(words[0].cloze).toEqual({ before: 'I have a long ', after: '.' })
    expect(words[0].image).toBe('https://cdn.example/atlas/img/tw-ruler.webp')
    expect(words[0].audio).toBe('https://cdn.example/atlas/audio/uk/tw-ruler.mp3')
    expect(words[1].image).toBe('')
    expect(words.find((w) => w.id === 'pencil_box')!.cloze).toEqual({ before: 'My ', after: ' are blue.' })
  })

  it('没配媒体地址时没有图片和音频', () => {
    expect(studyWords(book, dict, '')[0].audio).toBe('')
  })
})

describe('clozeOf', () => {
  it('允许屈折变化，短语整段出现', () => {
    expect(clozeOf('run', 'She runs every morning.')).toEqual({ before: 'She ', after: ' every morning.' })
    expect(clozeOf('look forward to', 'We are looking forward to it.')).toEqual({ before: 'We are ', after: ' it.' })
    expect(clozeOf('take care of sb', 'Take care of her.')).toBeUndefined() // 带占位词的短语不挖空
    expect(clozeOf('apple', 'I like bananas.')).toBeUndefined()
  })
})

describe('今日计划与组题', () => {
  it('新词按课本顺序，每天上限扣掉今天已学的', () => {
    let p = emptyProgress()
    expect(todayPlan(words, p, S, NOW).fresh).toEqual(words.map((w) => w.id).slice(0, 10))
    p = { ...p, days: { '2026-11-21': { n: 7, r: 7, c: 7, t: 0 } } }
    expect(todayPlan(words, p, { ...S, dailyNew: 10 }, NOW).fresh).toHaveLength(3)
  })

  it('先复习到期的，再 5 个一组：先认识，再回忆', () => {
    const p: Progress = { ...emptyProgress(), cards: { ruler: review(undefined, Rating.Good, NOW - 86400000 * 30) } }
    const s = buildSession(words, book.id, p, { ...S, dailyNew: 5 }, NOW)
    expect(s.reviewIds).toEqual(['ruler'])
    expect(s.steps[0]).toMatchObject({ id: 'ruler' })
    expect(s.steps.slice(1, 6).every((x) => x.kind === 'intro')).toBe(true)
    expect(s.steps.slice(6).every((x) => x.kind !== 'intro')).toBe(true)
    expect(new Set(s.steps.slice(6).map((x) => x.id))).toEqual(new Set(s.newIds))
  })

  it('指定单元时只学这个单元的新词', () => {
    const s = buildSession(words, book.id, emptyProgress(), S, NOW, { unit: 1 })
    expect(s.newIds).toEqual(['red', 'green', 'pencil_box', 'blue'])
  })

  it('没有素材的题型自动跳过：没音频不出听音，没例句不出填空', () => {
    const p = emptyProgress()
    for (let salt = 0; salt < 50; salt++) {
      const pencil = words.find((w) => w.id === 'pencil')!
      expect(['meaning', 'spell']).toContain(quizKind(pencil, p, S, salt))
    }
  })

  it('干扰项来自同一本书，不重复，含正确答案', () => {
    const ruler = words[0]
    for (const kind of ['meaning', 'cloze'] as const) {
      const opts = distractors(words, ruler, kind, 42)
      expect(opts).toContain('ruler')
      expect(new Set(opts).size).toBe(opts.length)
      expect(opts.length).toBe(4)
    }
    // 书里只有一个短语时，干扰项用单词补足，不能只剩正确答案
    expect(distractors(words, words.find((w) => w.id === 'pencil_box')!, 'cloze', 1)).toHaveLength(4)
  })
})

describe('作答', () => {
  const start = (): Progress => {
    const p = emptyProgress()
    return { ...p, session: buildSession(words, book.id, p, { ...S, dailyNew: 5 }, NOW) }
  }

  it('只有第一次作答计分；答错换题型重练，重练不计分', () => {
    let p = start()
    const step = p.session!.steps.find((x) => x.kind !== 'intro')!
    p = answer(p, words, step, false, Rating.Again, 'x', NOW)
    expect(p.cards[step.id].lapses + p.cards[step.id].reps).toBeGreaterThan(0)
    expect(p.mistakes[0]).toBe(step.id)
    expect(p.days['2026-11-21']).toMatchObject({ r: 1, c: 0, n: 1 })
    const retry = p.session!.steps.find((x) => x.id === step.id && x.kind !== 'intro' && x.retry)
    expect(retry).toBeTruthy()
    const before = p.cards[step.id]
    p = answer(p, words, retry!, true, Rating.Good, 'ok', NOW + 1000)
    expect(p.cards[step.id]).toEqual(before)
    expect(p.days['2026-11-21'].r).toBe(1)
  })

  it('advance 走到最后一步标记完成，学习时间封顶 90 秒', () => {
    let p = start()
    const total = p.session!.steps.length
    for (let i = 0; i < total; i++) p = advance(p, 500, NOW)
    expect(p.session!.finished).toBe(NOW)
    expect(p.days['2026-11-21'].t).toBe(90 * total)
  })

  it('评分：答错 Again、提示 Hard、慢 Hard、拼写快 Easy', () => {
    expect(gradeFor('meaning', false, 1000, false)).toBe(Rating.Again)
    expect(gradeFor('spell', true, 3000, true)).toBe(Rating.Hard)
    expect(gradeFor('meaning', true, 12000, false)).toBe(Rating.Hard)
    expect(gradeFor('spell', true, 3000, false)).toBe(Rating.Easy)
    expect(gradeFor('cloze', true, 3000, false)).toBe(Rating.Good)
  })

  it('统计正确率', () => {
    const graded: Record<string, Grade> = { a: Rating.Good, b: Rating.Again, c: Rating.Hard }
    const s = { ...start().session!, graded }
    expect(sessionStats(s)).toEqual({ total: 3, correct: 2, accuracy: 67 })
  })
})

describe('progress', () => {
  it('校验：丢掉坏数据，保留好的', () => {
    const good = review(undefined, Rating.Good, NOW)
    const p = sanitizeProgress({ version: 1, cards: { ok: good, bad: { due: 'x' } }, days: { '2026-11-21': { n: 1, r: 2, c: 1, t: 30 }, oops: {} },
      mistakes: ['ok', 3], session: { id: 1 } })
    expect(Object.keys(p.cards)).toEqual(['ok'])
    expect(Object.keys(p.days)).toEqual(['2026-11-21'])
    expect(p.mistakes).toEqual(['ok'])
    expect(p.session).toBeNull()
    expect(sanitizeProgress('garbage')).toEqual(emptyProgress())
  })

  it('连续天数：今天没学从昨天数起', () => {
    const days = { '2026-11-19': { n: 1, r: 1, c: 1, t: 1 }, '2026-11-20': { n: 1, r: 1, c: 1, t: 1 } }
    expect(streak({ ...emptyProgress(), days }, new Date(2026, 10, 21))).toBe(2)
    expect(streak({ ...emptyProgress(), days: { ...days, '2026-11-21': { n: 0, r: 3, c: 3, t: 1 } } }, new Date(2026, 10, 21))).toBe(3)
    expect(streak(emptyProgress(), new Date(2026, 10, 21))).toBe(0)
  })
})

import { describe, expect, it } from 'vitest'
import { collocations, examplesFor, mediaUrl, phonetics, sensesText, shortMeaning, tagNames, unitStats } from '../miniprogram/lib/text'
import { BookWord, Entry } from '../miniprogram/lib/types'

const entry: Entry = {
  id: 'library',
  w: 'library',
  kind: 'word',
  uk: '/ˈlaɪbrəri/',
  us: '/ˈlaɪbreri/',
  senses: [
    { pos: 'n.', zh: '图书馆；藏书室', en: 'A place where people read or borrow books.' },
    { pos: 'n.', zh: '资料库' },
    { pos: 'n.', zh: '第三个义项' },
  ],
  ex: [
    { en: 'I borrowed three books from the library.', zh: '我从图书馆借了三本书。' },
    { en: 'Public libraries support lifelong learning.', zh: '公共图书馆支持终身学习。' },
  ],
  col: ['public library｜公共图书馆', 'no-translation'],
  aid: 'library',
  m: 1 | 2, // 有插画和英音，没有美音
  tags: ['zk', 'gk', 'unknown'],
  src: 'atlas',
}

const word = (patch: Partial<BookWord> = {}): BookWord => ({ id: 'library', hw: 'library', senses: [], req: true, ...patch })

describe('text', () => {
  it('课本释义优先，没有时取词典前两个义项', () => {
    expect(shortMeaning(word({ senses: [{ pos: 'n.', zh: '图书馆' }] }), entry)).toBe('n. 图书馆')
    expect(shortMeaning(word(), entry)).toBe('n. 图书馆；藏书室；n. 资料库')
    expect(shortMeaning(word())).toBe('')
  })

  it('没有词性的义项不加前缀', () => {
    expect(sensesText([{ pos: '', zh: '尺子' }, { pos: 'v.', zh: '统治' }])).toBe('尺子；v. 统治')
  })

  it('小学、初中只给日常短句，高中两条都给', () => {
    expect(examplesFor(entry, 'ps')).toHaveLength(1)
    expect(examplesFor(entry, 'jh')).toHaveLength(1)
    expect(examplesFor(entry, 'sh')).toHaveLength(2)
    expect(examplesFor({ ...entry, ex: undefined }, 'sh')).toEqual([])
  })

  it('搭配按全角竖线拆开', () => {
    expect(collocations(entry)).toEqual([{ en: 'public library', zh: '公共图书馆' }, { en: 'no-translation', zh: '' }])
  })

  it('媒体地址按位标记判断有没有文件', () => {
    expect(mediaUrl('https://cdn.x/atlas/', 'img', entry)).toBe('https://cdn.x/atlas/img/library.webp')
    expect(mediaUrl('https://cdn.x/atlas', 'uk', entry)).toBe('https://cdn.x/atlas/audio/uk/library.mp3')
    expect(mediaUrl('https://cdn.x/atlas', 'us', entry)).toBe('') // 没有美音
    expect(mediaUrl('', 'img', entry)).toBe('') // 没配置地址
    expect(mediaUrl('https://cdn.x', 'img', { ...entry, aid: undefined })).toBe('') // 不是词光的词
  })

  it('音标词光优先，其次课本', () => {
    expect(phonetics(word({ ipa: '/laɪbrəri/' }), entry)).toEqual({ uk: '/ˈlaɪbrəri/', us: '/ˈlaɪbreri/' })
    expect(phonetics(word({ ipa: '/laɪbrəri/' }))).toEqual({ uk: '/laɪbrəri/', us: '' })
  })

  it('考试标签只显示认识的', () => {
    expect(tagNames(entry)).toEqual(['中考', '高考'])
  })

  it('单元统计', () => {
    expect(unitStats({ name: 'Unit 1', words: [word(), word({ req: false })] })).toEqual({ total: 2, req: 1 })
  })
})

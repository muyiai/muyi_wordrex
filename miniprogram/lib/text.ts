// 页面展示用的纯函数（不碰 wx，可以单测）
import { BookWord, Entry, Example, Sense, StageCode, Unit } from './types'

export const TAG_NAMES: Record<string, string> = {
  zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', toefl: '托福', ielts: '雅思', gre: 'GRE',
}

export function sensesText(senses: Sense[]): string {
  return senses.map((s) => (s.pos ? `${s.pos} ${s.zh}` : s.zh)).join('；')
}

/** 列表里显示的释义：课本释义优先（更贴近课堂），没有时用词典的。 */
export function shortMeaning(word: BookWord, entry?: Entry): string {
  if (word.senses.length) return sensesText(word.senses)
  return entry ? sensesText(entry.senses.slice(0, 2)) : ''
}

/** 词光每个词有两条例句：ex[0] 日常短句，ex[1] 雅思语境长句。小学、初中只给短句。 */
export function examplesFor(entry: Entry, stage: StageCode): Example[] {
  const ex = entry.ex || []
  return stage === 'sh' ? ex : ex.slice(0, 1)
}

export function collocations(entry: Entry): { en: string; zh: string }[] {
  return (entry.col || []).map((c) => {
    const [en, zh = ''] = c.split('｜')
    return { en, zh }
  })
}

export function unitStats(unit: Unit): { total: number; req: number } {
  return { total: unit.words.length, req: unit.words.filter((w) => w.req).length }
}

/** 音标：词光（带重音、英美两种）优先，其次课本。 */
export function phonetics(word: BookWord, entry?: Entry): { uk: string; us: string } {
  return { uk: entry?.uk || word.ipa || '', us: entry?.us || '' }
}

export type MediaKind = 'img' | 'thumb' | 'uk' | 'us' | 'ex'
const MEDIA_BIT: Record<MediaKind, number> = { img: 1, thumb: 1, uk: 2, us: 4, ex: 8 }

/** 词光媒体文件地址；没有这个文件（媒体位为 0）或没配置地址时返回空串。 */
export function mediaUrl(base: string, kind: MediaKind, entry?: Entry): string {
  if (!base || !entry?.aid || !((entry.m || 0) & MEDIA_BIT[kind])) return ''
  const path = kind === 'img' || kind === 'thumb' ? `${kind}/${entry.aid}.webp` : `audio/${kind}/${entry.aid}.mp3`
  return `${base.replace(/\/$/, '')}/${path}`
}

export function tagNames(entry?: Entry): string[] {
  return (entry?.tags || []).filter((t) => t in TAG_NAMES).map((t) => TAG_NAMES[t])
}

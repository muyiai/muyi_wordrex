// 本地设置。学习进度另存（progress-store.ts），云同步在 M4。
const KEY = 'wordrex:settings'

export interface Settings {
  bookId: string // 当前在学的书，空串表示还没选
  hideMeaning: boolean // 单词列表里遮住释义
  reqOnly: boolean // 单词列表只看要求掌握的词
  dailyNew: number // 每天新学几个词
  spell: boolean // 出拼写题
}

const DEFAULTS: Settings = { bookId: '', hideMeaning: false, reqOnly: false, dailyNew: 10, spell: true }

export function getSettings(): Settings {
  const saved = wx.getStorageSync(KEY) as Partial<Settings> | ''
  return { ...DEFAULTS, ...(saved || {}) }
}

export function updateSettings(patch: Partial<Settings>): Settings {
  const next = { ...getSettings(), ...patch }
  wx.setStorageSync(KEY, next)
  return next
}

// 本地设置。学习进度（M3）另存，云同步在 M4。
const KEY = 'wordrex:settings'

export interface Settings {
  bookId: string // 当前在学的书，空串表示还没选
  hideMeaning: boolean // 单词列表里遮住释义
  reqOnly: boolean // 单词列表只看要求掌握的词
}

const DEFAULTS: Settings = { bookId: '', hideMeaning: false, reqOnly: false }

export function getSettings(): Settings {
  const saved = wx.getStorageSync(KEY) as Partial<Settings> | ''
  return { ...DEFAULTS, ...(saved || {}) }
}

export function updateSettings(patch: Partial<Settings>): Settings {
  const next = { ...getSettings(), ...patch }
  wx.setStorageSync(KEY, next)
  return next
}

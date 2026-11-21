// 学习进度存在本地存储（M4 再做云同步）。读出来先校验，坏数据不会让页面崩掉。
import { Progress, sanitizeProgress } from './progress'

const KEY = 'wordrex:progress'

export function loadProgress(): Progress {
  return sanitizeProgress(wx.getStorageSync(KEY))
}

export function saveProgress(p: Progress): void {
  try {
    wx.setStorageSync(KEY, p)
  } catch (err) {
    console.warn('学习进度保存失败', err) // 存储满了：这次作答丢失，不影响继续学
  }
}

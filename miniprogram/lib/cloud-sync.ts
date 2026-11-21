// 学习进度云同步（云函数 sync）。没配云开发环境时什么也不做，进度只存在本机。
import { CLOUD_ENV } from '../config'
import { Progress, sanitizeProgress } from './progress'
import { loadProgress, saveProgress } from './progress-store'

let lastSync = 0
let running: Promise<boolean> | undefined

export function initCloud(): void {
  if (CLOUD_ENV && wx.cloud) wx.cloud.init({ env: CLOUD_ENV, traceUser: true })
}

/** 传上去的部分：进行中的一轮只在本机。 */
const shareable = (p: Progress) => ({ version: p.version, cards: p.cards, days: p.days, mistakes: p.mistakes })

/**
 * 和云端合并。请求期间本地又有作答（进度变了）就不覆盖，等下次同步。
 * minInterval：距上次同步不到这么多毫秒就跳过（首页每次显示都会调用）。
 */
export function syncProgress(minInterval = 0): Promise<boolean> {
  if (!CLOUD_ENV || !wx.cloud) return Promise.resolve(false)
  if (running) return running
  if (Date.now() - lastSync < minInterval) return Promise.resolve(false)
  running = (async () => {
    const before = loadProgress()
    const snapshot = JSON.stringify(before)
    try {
      const res = await wx.cloud.callFunction({ name: 'sync', data: { progress: shareable(before) } })
      const remote = (res.result as { progress?: unknown } | undefined)?.progress
      if (!remote) return false
      const now = loadProgress()
      if (JSON.stringify(now) !== snapshot) return false // 同步期间又学了：这次不覆盖
      saveProgress({ ...sanitizeProgress({ ...(remote as object), version: 1 }), session: now.session })
      lastSync = Date.now()
      return true
    } catch (err) {
      console.warn('进度同步失败', err) // 离线时正常，下次再同步
      return false
    } finally {
      running = undefined
    }
  })()
  return running
}

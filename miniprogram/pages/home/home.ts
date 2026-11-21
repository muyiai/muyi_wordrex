import { syncProgress } from '../../lib/cloud-sync'
import { streak } from '../../lib/progress'
import { loadProgress } from '../../lib/progress-store'
import { learnedCount, masteredCount, StudyWord, todayPlan } from '../../lib/session'
import { source } from '../../lib/source'
import { getSettings } from '../../lib/store'
import { loadStudyWords, studySettings } from '../../lib/study'
import { unitStats } from '../../lib/text'

let words: StudyWord[] = []

interface UnitRow {
  name: string
  total: number
  req: number
}

Page({
  data: {
    state: 'loading' as 'loading' | 'empty' | 'ready' | 'error',
    error: '',
    bookId: '',
    edition: '',
    volume: '',
    total: 0,
    units: [] as UnitRow[],
    today: { due: 0, fresh: 0, minutes: 0, resume: false, learned: 0, mastered: 0, total: 0, streak: 0 },
  },

  onShow() {
    const { bookId } = getSettings()
    if (!bookId) {
      this.setData({ state: 'empty' })
      return
    }
    if (bookId !== this.data.bookId || this.data.state !== 'ready') this.load(bookId)
    else this.refreshToday() // 学完一轮回来，数字要更新
    syncProgress(60000).then((changed) => changed && this.data.state === 'ready' && this.refreshToday())
  },

  async load(bookId: string) {
    this.setData({ state: 'loading', bookId })
    try {
      const book = await source.book(bookId)
      words = await loadStudyWords(bookId)
      const units = book.units.map((u) => ({ name: u.name, ...unitStats(u) }))
      this.setData({
        state: 'ready',
        edition: book.editionName,
        volume: book.volume,
        total: units.reduce((n, u) => n + u.total, 0),
        units,
      })
      this.refreshToday()
    } catch (err) {
      this.setData({ state: 'error', error: (err as Error).message })
    }
  },

  /** 今日学习：到期复习、今天还能学的新词、这本书的进度。 */
  refreshToday() {
    const settings = getSettings()
    const p = loadProgress()
    const ids = words.map((w) => w.id)
    const plan = todayPlan(words, p, studySettings(settings), Date.now())
    const resume = !!p.session && !p.session.finished && p.session.bookId === settings.bookId &&
      p.session.index < p.session.steps.length
    this.setData({
      today: {
        due: plan.due.length, fresh: plan.fresh.length, minutes: plan.minutes, resume,
        learned: learnedCount(p, ids), mastered: masteredCount(p, ids), total: ids.length, streak: streak(p),
      },
    })
  },

  startLearning() {
    wx.navigateTo({ url: '/pages/learn/learn' })
  },

  openSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' })
  },

  retry() {
    this.load(this.data.bookId)
  },

  chooseBook() {
    wx.navigateTo({ url: '/pages/select/select' })
  },

  openUnit(e: WechatMiniprogram.TouchEvent) {
    const index = e.currentTarget.dataset.index as number
    wx.navigateTo({ url: `/pages/unit/unit?book=${this.data.bookId}&u=${index}` })
  },

  openAbout() {
    wx.navigateTo({ url: '/pages/about/about' })
  },
})

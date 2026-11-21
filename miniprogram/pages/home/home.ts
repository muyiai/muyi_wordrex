import { source } from '../../lib/source'
import { getSettings } from '../../lib/store'
import { unitStats } from '../../lib/text'

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
  },

  onShow() {
    const { bookId } = getSettings()
    if (!bookId) {
      this.setData({ state: 'empty' })
      return
    }
    if (bookId !== this.data.bookId || this.data.state !== 'ready') this.load(bookId)
  },

  async load(bookId: string) {
    this.setData({ state: 'loading', bookId })
    try {
      const book = await source.book(bookId)
      const units = book.units.map((u) => ({ name: u.name, ...unitStats(u) }))
      this.setData({
        state: 'ready',
        edition: book.editionName,
        volume: book.volume,
        total: units.reduce((n, u) => n + u.total, 0),
        units,
      })
    } catch (err) {
      this.setData({ state: 'error', error: (err as Error).message })
    }
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

import { source } from '../../lib/source'
import { getSettings, updateSettings } from '../../lib/store'
import { phonetics, shortMeaning } from '../../lib/text'

interface WordRow {
  index: number // 在单元里的位置（详情页上一个/下一个用）
  hw: string
  ipa: string
  meaning: string
  req: boolean
  core: boolean
  isNew: boolean
}

Page({
  data: {
    state: 'loading' as 'loading' | 'ready' | 'error',
    error: '',
    bookId: '',
    unitIndex: 0,
    unitName: '',
    all: [] as WordRow[],
    words: [] as WordRow[],
    hideMeaning: false,
    reqOnly: false,
    revealed: {} as Record<number, boolean>,
  },

  onLoad(query: Record<string, string | undefined>) {
    const { hideMeaning, reqOnly } = getSettings()
    this.setData({ bookId: query.book || '', unitIndex: Number(query.u || 0), hideMeaning, reqOnly })
    this.load()
  },

  async load() {
    this.setData({ state: 'loading' })
    try {
      const [book, dict] = await Promise.all([source.book(this.data.bookId), source.bookDict(this.data.bookId)])
      const unit = book.units[this.data.unitIndex]
      wx.setNavigationBarTitle({ title: unit.name })
      const all = unit.words.map((w, index) => ({
        index,
        hw: w.hw,
        ipa: phonetics(w, dict[w.id]).uk,
        meaning: shortMeaning(w, dict[w.id]),
        req: w.req,
        core: !!w.core,
        isNew: !!w.new,
      }))
      this.setData({ state: 'ready', unitName: unit.name, all })
      this.applyFilter()
    } catch (err) {
      this.setData({ state: 'error', error: (err as Error).message })
    }
  },

  applyFilter() {
    const words = this.data.reqOnly ? this.data.all.filter((w) => w.req) : this.data.all
    this.setData({ words })
  },

  toggleHide() {
    const hideMeaning = !this.data.hideMeaning
    updateSettings({ hideMeaning })
    this.setData({ hideMeaning, revealed: {} })
  },

  toggleReq() {
    const reqOnly = !this.data.reqOnly
    updateSettings({ reqOnly })
    this.setData({ reqOnly })
    this.applyFilter()
  },

  reveal(e: WechatMiniprogram.TouchEvent) {
    const index = e.currentTarget.dataset.index as number
    this.setData({ [`revealed.${index}`]: true })
  },

  studyUnit() {
    wx.navigateTo({ url: `/pages/learn/learn?unit=${this.data.unitIndex}` })
  },

  openWord(e: WechatMiniprogram.TouchEvent) {
    const index = e.currentTarget.dataset.index as number
    wx.navigateTo({ url: `/pages/word/word?book=${this.data.bookId}&u=${this.data.unitIndex}&i=${index}` })
  },
})

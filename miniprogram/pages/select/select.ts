import { source } from '../../lib/source'
import { getSettings, updateSettings } from '../../lib/store'
import { Stage } from '../../lib/types'

Page({
  data: {
    state: 'loading' as 'loading' | 'ready' | 'error',
    error: '',
    stages: [] as Stage[],
    stageIndex: 0,
    bookId: '',
  },

  onLoad() {
    this.load()
  },

  async load() {
    this.setData({ state: 'loading' })
    try {
      const catalog = await source.catalog()
      const { bookId } = getSettings()
      // 默认停在当前这本书所在的学段（bookId 形如 jh-pep-7a）
      const current = catalog.stages.findIndex((s) => bookId.startsWith(`${s.code}-`))
      this.setData({ state: 'ready', stages: catalog.stages, stageIndex: Math.max(0, current), bookId })
    } catch (err) {
      this.setData({ state: 'error', error: (err as Error).message })
    }
  },

  switchStage(e: WechatMiniprogram.TouchEvent) {
    this.setData({ stageIndex: e.currentTarget.dataset.index as number })
  },

  pick(e: WechatMiniprogram.TouchEvent) {
    const bookId = e.currentTarget.dataset.id as string
    updateSettings({ bookId })
    if (getCurrentPages().length > 1) wx.navigateBack()
    else wx.reLaunch({ url: '/pages/home/home' })
  },
})

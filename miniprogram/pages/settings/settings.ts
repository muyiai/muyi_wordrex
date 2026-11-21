import { getSettings, updateSettings } from '../../lib/store'

const DAILY = [5, 10, 15, 20, 30]

Page({
  data: {
    daily: DAILY,
    dailyIndex: 1,
    spell: true,
  },

  onLoad() {
    const s = getSettings()
    this.setData({ dailyIndex: Math.max(0, DAILY.indexOf(s.dailyNew)), spell: s.spell })
  },

  pickDaily(e: WechatMiniprogram.PickerChange) {
    const dailyIndex = Number(e.detail.value)
    updateSettings({ dailyNew: DAILY[dailyIndex] })
    this.setData({ dailyIndex })
  },

  toggleSpell(e: WechatMiniprogram.SwitchChange) {
    updateSettings({ spell: e.detail.value })
    this.setData({ spell: e.detail.value })
  },
})

import { source } from '../../lib/source'

Page({
  data: {
    version: '',
  },

  onLoad() {
    source
      .catalog()
      .then((c) => this.setData({ version: c.version }))
      .catch(() => this.setData({ version: '未加载' }))
  },
})

import { initCloud, syncProgress } from './lib/cloud-sync'
import { source } from './lib/source'

App({
  onLaunch() {
    initCloud()
    syncProgress() // 换了手机也能拉回进度
    source.catalog().catch((err) => console.warn('目录加载失败', err)) // 预加载，页面里还会再取
  },
})

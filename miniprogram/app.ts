import { source } from './lib/source'

App({
  onLaunch() {
    source.catalog().catch((err) => console.warn('目录加载失败', err)) // 预加载，页面里还会再取
  },
})

// data.ts 的小程序实现：wx.request 拉 JSON，缓存写到用户文件目录（storage 只有 10MB，词典放不下）
import { Cache, Fetcher } from './data'

export const wxFetcher: Fetcher = {
  getJSON<T>(url: string): Promise<T> {
    return new Promise((resolve, reject) => {
      wx.request({
        url,
        dataType: 'json',
        success: (res) => {
          if (res.statusCode === 200) resolve(res.data as T)
          else reject(new Error(`HTTP ${res.statusCode}: ${url}`))
        },
        fail: (err) => reject(new Error(err.errMsg)),
      })
    })
  },
}

const CACHE_DIR = `${wx.env.USER_DATA_PATH}/cache`

function fileOf(key: string): string {
  return `${CACHE_DIR}/${key.replace(/[^\w.@-]/g, '_')}.json`
}

export const fileCache: Cache = {
  read<T>(key: string): T | undefined {
    try {
      const text = wx.getFileSystemManager().readFileSync(fileOf(key), 'utf8') as string
      return JSON.parse(text) as T
    } catch {
      return undefined // 没缓存过
    }
  },
  write(key: string, value: unknown): void {
    const fs = wx.getFileSystemManager()
    try {
      fs.accessSync(CACHE_DIR)
    } catch {
      fs.mkdirSync(CACHE_DIR, true)
    }
    try {
      fs.writeFileSync(fileOf(key), JSON.stringify(value), 'utf8')
    } catch (err) {
      console.warn('缓存写入失败', key, err) // 空间满了也不影响使用，下次再从网络拉
    }
  },
}

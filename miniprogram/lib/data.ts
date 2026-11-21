// 数据加载：目录每次启动拉一次（很小），书和书的词典按目录版本号缓存。
// 网络和缓存都由调用方注入，单测时用假的，小程序里用 wx-io.ts 的实现。
import { Book, BookDict, Catalog } from './types'

export interface Fetcher {
  getJSON<T>(url: string): Promise<T>
}

export interface Cache {
  read<T>(key: string): T | undefined
  write(key: string, value: unknown): void
}

export class DataSource {
  private catalogPromise?: Promise<Catalog>
  private memo = new Map<string, Promise<unknown>>()

  constructor(private base: string, private fetcher: Fetcher, private cache: Cache) {}

  /** 目录：每次启动从网络拉；拉不到（离线）时用上次缓存的。 */
  catalog(): Promise<Catalog> {
    if (!this.catalogPromise) {
      this.catalogPromise = this.fetcher.getJSON<Catalog>(this.url('catalog.json')).then(
        (c) => {
          this.cache.write('catalog', c)
          return c
        },
        (err) => {
          const cached = this.cache.read<Catalog>('catalog')
          if (cached) return cached
          this.catalogPromise = undefined // 下次再试
          throw err
        },
      )
    }
    return this.catalogPromise
  }

  book(id: string): Promise<Book> {
    return this.versioned(`books/${id}.json`)
  }

  bookDict(id: string): Promise<BookDict> {
    return this.versioned(`books/${id}.dict.json`)
  }

  /** 按目录版本号缓存：数据更新（版本号变了）才重新下载。 */
  private versioned<T>(path: string): Promise<T> {
    let p = this.memo.get(path) as Promise<T> | undefined
    if (!p) {
      p = this.catalog().then(async (c) => {
        const key = `${path}@${c.version}`
        const cached = this.cache.read<T>(key)
        if (cached) return cached
        const fresh = await this.fetcher.getJSON<T>(this.url(path))
        this.cache.write(key, fresh)
        return fresh
      })
      p.catch(() => this.memo.delete(path))
      this.memo.set(path, p)
    }
    return p
  }

  private url(path: string): string {
    return `${this.base.replace(/\/$/, '')}/${path}`
  }
}

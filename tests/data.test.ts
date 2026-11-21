import { describe, expect, it } from 'vitest'
import { Cache, DataSource, Fetcher } from '../miniprogram/lib/data'

function setup(responses: Record<string, unknown>) {
  const calls: string[] = []
  let offline = false
  const fetcher: Fetcher = {
    async getJSON<T>(url: string): Promise<T> {
      calls.push(url)
      if (offline) throw new Error('offline')
      if (!(url in responses)) throw new Error(`404 ${url}`)
      return responses[url] as T
    },
  }
  const store = new Map<string, unknown>()
  const cache: Cache = {
    read: <T>(key: string) => store.get(key) as T | undefined,
    write: (key, value) => void store.set(key, value),
  }
  return { fetcher, cache, store, calls, goOffline: () => (offline = true) }
}

const BASE = 'http://data/'
const catalog = (version: string) => ({ version, dictChunks: 1, stages: [] })

describe('DataSource', () => {
  it('书按目录版本缓存：同一版本不重复下载', async () => {
    const env = setup({ 'http://data/catalog.json': catalog('v1'), 'http://data/books/ps-pep-3a.json': { id: 'ps-pep-3a' } })
    await new DataSource(BASE, env.fetcher, env.cache).book('ps-pep-3a')
    expect(env.store.has('books/ps-pep-3a.json@v1')).toBe(true)

    // 重新启动（新的 DataSource），目录版本没变：书走缓存
    env.calls.length = 0
    const book = await new DataSource(BASE, env.fetcher, env.cache).book('ps-pep-3a')
    expect(book).toEqual({ id: 'ps-pep-3a' })
    expect(env.calls).toEqual(['http://data/catalog.json'])
  })

  it('目录版本变了就重新下载', async () => {
    const env = setup({ 'http://data/catalog.json': catalog('v1'), 'http://data/books/x.dict.json': { a: 1 } })
    await new DataSource(BASE, env.fetcher, env.cache).bookDict('x')
    env.store.set('books/x.dict.json@v1', { a: 'stale' })
    const env2Responses = { 'http://data/catalog.json': catalog('v2'), 'http://data/books/x.dict.json': { a: 2 } }
    const fresh = await new DataSource(BASE, { getJSON: async <T>(u: string) => env2Responses[u as keyof typeof env2Responses] as T }, env.cache).bookDict('x')
    expect(fresh).toEqual({ a: 2 })
  })

  it('离线时用缓存的目录和书', async () => {
    const env = setup({ 'http://data/catalog.json': catalog('v1'), 'http://data/books/b.json': { id: 'b' } })
    await new DataSource(BASE, env.fetcher, env.cache).book('b')
    env.goOffline()
    const ds = new DataSource(BASE, env.fetcher, env.cache)
    expect((await ds.catalog()).version).toBe('v1')
    expect(await ds.book('b')).toEqual({ id: 'b' })
  })

  it('第一次打开就离线：报错，之后还能重试', async () => {
    const env = setup({})
    env.goOffline()
    const ds = new DataSource(BASE, env.fetcher, env.cache)
    await expect(ds.catalog()).rejects.toThrow('offline')
    await expect(ds.catalog()).rejects.toThrow('offline')
    expect(env.calls).toHaveLength(2) // 失败不会被缓存住
  })

  it('同一本书并发请求只下载一次', async () => {
    const env = setup({ 'http://data/catalog.json': catalog('v1'), 'http://data/books/b.json': { id: 'b' } })
    const ds = new DataSource(BASE, env.fetcher, env.cache)
    await Promise.all([ds.book('b'), ds.book('b'), ds.book('b')])
    expect(env.calls.filter((u) => u.endsWith('b.json'))).toHaveLength(1)
  })
})

// 管线产物（pipeline/out/build）与小程序约定的格式一致：没生成数据时跳过
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import { describe, expect, it } from 'vitest'
import { chunkOf } from '../miniprogram/lib/hash'
import { Book, BookDict, Catalog } from '../miniprogram/lib/types'

const BUILD = join(__dirname, '..', 'pipeline', 'out', 'build')
const read = <T>(path: string): T => JSON.parse(readFileSync(join(BUILD, path), 'utf8')) as T

describe.skipIf(!existsSync(join(BUILD, 'catalog.json')))('build 产物', () => {
  const catalog = read<Catalog>('catalog.json')
  const bookIds = catalog.stages.flatMap((s) => s.editions.flatMap((e) => e.books.map((b) => b.id)))

  it('目录里的每本书都有书文件和词典文件，词数对得上', () => {
    for (const s of catalog.stages) {
      for (const e of s.editions) {
        for (const meta of e.books) {
          const book = read<Book>(`books/${meta.id}.json`)
          expect(book.stage).toBe(s.code)
          expect(book.units.reduce((n, u) => n + u.words.length, 0)).toBe(meta.words)
          expect(existsSync(join(BUILD, `books/${meta.id}.dict.json`))).toBe(true)
        }
      }
    }
  })

  it('书里的词在这本书的词典文件里都有词条', () => {
    for (const id of bookIds) {
      const book = read<Book>(`books/${id}.json`)
      const dict = read<BookDict>(`books/${id}.dict.json`)
      const missing = book.units.flatMap((u) => u.words).filter((w) => !dict[w.id])
      expect(missing.map((w) => w.id)).toEqual([])
    }
  })

  it('TypeScript 的哈希能在 Python 写的分块里找到每个词', () => {
    const files = readdirSync(join(BUILD, 'dict'))
    expect(files).toHaveLength(catalog.dictChunks)
    for (const file of files) {
      const chunk = read<BookDict>(`dict/${file}`)
      const n = Number(file.replace('.json', ''))
      for (const id of Object.keys(chunk)) expect(chunkOf(id, catalog.dictChunks)).toBe(n)
    }
  })
})

describe.skipIf(!existsSync(join(BUILD, 'catalog.json')))('用真实课本组一轮题', () => {
  const books = ['ps-pep-3a', 'jh-pep-7a', 'sh-wy-b1']
  for (const id of books) {
    it(id, async () => {
      const { studyWords, buildSession } = await import('../miniprogram/lib/session')
      const { emptyProgress } = await import('../miniprogram/lib/progress')
      const words = studyWords(read<Book>(`books/${id}.json`), read<BookDict>(`books/${id}.dict.json`), 'https://cdn.example')
      expect(words.length).toBeGreaterThan(30)
      const s = buildSession(words, id, emptyProgress(), { dailyNew: 30, retention: 0.9, spell: true }, Date.UTC(2026, 10, 21))
      expect(s.newIds).toHaveLength(30)
      const kinds: Record<string, number> = {}
      for (const step of s.steps) {
        kinds[step.kind] = (kinds[step.kind] || 0) + 1
        if (step.kind === 'intro') continue
        if (step.kind === 'spell') {
          expect(words.find((w) => w.id === step.id)!.hw).toMatch(/^[A-Za-z][A-Za-z' -]*$/)
          continue
        }
        expect(step.options).toContain(step.id)
        expect(new Set(step.options).size).toBe(step.options!.length)
        expect(step.options!.length).toBeGreaterThanOrEqual(2)
      }
      expect(kinds.intro).toBe(30)
      expect((kinds.meaning || 0) + (kinds.cloze || 0)).toBeGreaterThan(15) // 新词主要出选义和填空
      // 例句挖空成功的比例（有例句的词里）
      const withEx = words.filter((w) => w.example)
      expect(withEx.filter((w) => w.cloze).length / withEx.length).toBeGreaterThan(0.8)
    })
  }
})

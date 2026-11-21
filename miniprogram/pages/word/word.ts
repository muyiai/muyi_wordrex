import { MEDIA_BASE } from '../../config'
import { source } from '../../lib/source'
import { collocations, examplesFor, mediaUrl, phonetics, sensesText, tagNames } from '../../lib/text'
import { Example, Sense } from '../../lib/types'

let audio: WechatMiniprogram.InnerAudioContext | undefined

Page({
  data: {
    state: 'loading' as 'loading' | 'ready' | 'error',
    error: '',
    bookId: '',
    unitIndex: 0,
    index: 0,
    count: 0,
    hw: '',
    uk: '',
    us: '',
    ukAudio: '',
    usAudio: '',
    exAudio: '',
    image: '',
    tags: [] as string[],
    textbook: '', // 课本释义
    senses: [] as Sense[], // 词典义项
    examples: [] as Example[],
    cols: [] as { en: string; zh: string }[],
    fam: '', // 词族、近义、反义：一行文字
    syn: '',
    ant: '',
    tip: '',
    lemma: '',
  },

  onLoad(query: Record<string, string | undefined>) {
    this.setData({ bookId: query.book || '', unitIndex: Number(query.u || 0), index: Number(query.i || 0) })
    this.load()
  },

  onUnload() {
    audio?.stop()
  },

  async load() {
    this.setData({ state: 'loading' })
    try {
      const [book, dict] = await Promise.all([source.book(this.data.bookId), source.bookDict(this.data.bookId)])
      const unit = book.units[this.data.unitIndex]
      const word = unit.words[this.data.index]
      const entry = dict[word.id]
      const { uk, us } = phonetics(word, entry)
      wx.setNavigationBarTitle({ title: word.hw })
      this.setData({
        state: 'ready',
        count: unit.words.length,
        hw: word.hw,
        uk,
        us,
        ukAudio: mediaUrl(MEDIA_BASE, 'uk', entry),
        usAudio: mediaUrl(MEDIA_BASE, 'us', entry),
        exAudio: mediaUrl(MEDIA_BASE, 'ex', entry),
        image: mediaUrl(MEDIA_BASE, 'img', entry),
        tags: tagNames(entry),
        textbook: sensesText(word.senses),
        senses: entry ? entry.senses : [],
        examples: entry ? examplesFor(entry, book.stage) : [],
        cols: entry ? collocations(entry) : [],
        fam: (entry?.fam || []).join('；'),
        syn: (entry?.syn || []).join('；'),
        ant: (entry?.ant || []).join('；'),
        tip: entry?.tip || '',
        lemma: entry?.lemma || '',
      })
    } catch (err) {
      this.setData({ state: 'error', error: (err as Error).message })
    }
  },

  play(e: WechatMiniprogram.TouchEvent) {
    const src = e.currentTarget.dataset.src as string
    if (!src) return
    audio = audio || wx.createInnerAudioContext()
    audio.stop()
    audio.src = src
    audio.play()
  },

  go(e: WechatMiniprogram.TouchEvent) {
    const index = this.data.index + (e.currentTarget.dataset.step as number)
    if (index < 0 || index >= this.data.count) return
    // redirectTo：返回键仍回到单元列表，而不是一个个词退回去
    wx.redirectTo({ url: `/pages/word/word?book=${this.data.bookId}&u=${this.data.unitIndex}&i=${index}` })
  },
})

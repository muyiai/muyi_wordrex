import { Progress, QuizKind, Session, Step } from '../../lib/progress'
import { loadProgress, saveProgress } from '../../lib/progress-store'
import { advance, answer, buildSession, gradeFor, sessionStats, StudyWord } from '../../lib/session'
import { getSettings } from '../../lib/store'
import { loadStudyWords, studySettings } from '../../lib/study'

// 词表和进度放在模块里，不进 data（data 只放当前这一题要显示的）
let words: StudyWord[] = []
let byId = new Map<string, StudyWord>()
let progress: Progress
let stepStart = 0
let audio: WechatMiniprogram.InnerAudioContext | undefined

interface Option {
  id: string
  label: string
  state: '' | 'right' | 'wrong'
}

const KIND_TITLES: Record<QuizKind | 'intro', string> = {
  intro: '新词', meaning: '选出意思', cloze: '选词填空', listen: '听音选词', spell: '拼写',
}

Page({
  data: {
    state: 'loading' as 'loading' | 'empty' | 'step' | 'done' | 'error',
    error: '',
    index: 0,
    total: 0,
    kind: 'intro' as QuizKind | 'intro',
    kindTitle: '',
    retry: false,
    hw: '',
    ipa: '',
    meaning: '',
    example: { en: '', zh: '' },
    cloze: { before: '', after: '' },
    image: '',
    hasAudio: false,
    options: [] as Option[],
    typed: '',
    hint: '',
    answered: false,
    correct: false,
    stats: { total: 0, correct: 0, accuracy: 0 },
  },

  async onLoad(query: Record<string, string | undefined>) {
    const settings = getSettings()
    try {
      words = await loadStudyWords(settings.bookId)
      byId = new Map(words.map((w) => [w.id, w]))
    } catch (err) {
      this.setData({ state: 'error', error: (err as Error).message })
      return
    }
    progress = loadProgress()
    const s = progress.session
    const resumable = s && !s.finished && s.bookId === settings.bookId && query.unit === undefined && !query.review
    if (!resumable) {
      const now = Date.now()
      const opts = { unit: query.unit !== undefined ? Number(query.unit) : undefined, reviewOnly: !!query.review }
      progress = { ...progress, session: buildSession(words, settings.bookId, progress, studySettings(settings), now, opts) }
      saveProgress(progress)
    }
    if (!(progress.session as Session).steps.length) {
      this.setData({ state: 'empty' })
      return
    }
    this.show()
  },

  onUnload() {
    if (audio) audio.stop()
  },

  /** 显示当前这一步；作答后没点继续就退出的，回来时直接显示结果。 */
  show() {
    const s = progress.session as Session
    if (s.index >= s.steps.length) {
      this.setData({ state: 'done', stats: sessionStats(s) })
      return
    }
    const step = s.steps[s.index]
    const w = byId.get(step.id)
    if (!w) {
      progress = advance(progress, 0, Date.now()) // 书的数据更新后这个词没了：跳过
      saveProgress(progress)
      this.show()
      return
    }
    const options = step.kind !== 'intro' && step.options
      ? step.options.map((id) => {
        const o = byId.get(id)
        return { id, label: o ? (step.kind === 'meaning' ? o.meaning : o.hw) : id, state: '' as Option['state'] }
      })
      : []
    stepStart = Date.now()
    this.setData({
      state: 'step',
      index: s.index,
      total: s.steps.length,
      kind: step.kind,
      kindTitle: KIND_TITLES[step.kind],
      retry: step.kind !== 'intro' && !!step.retry,
      hw: w.hw,
      ipa: w.ipa,
      meaning: w.meaning,
      example: w.example || { en: '', zh: '' },
      cloze: w.cloze || { before: '', after: '' },
      image: w.image,
      hasAudio: !!w.audio,
      options,
      typed: '',
      hint: '',
      answered: false,
      correct: false,
    })
    if (s.pending) this.reveal(s.pending.correct, s.pending.value)
    else if (step.kind === 'listen' || (step.kind === 'meaning' && w.audio)) this.play()
  },

  play() {
    const s = progress.session as Session
    const w = byId.get(s.steps[s.index].id)
    const url = w ? w.audio : ''
    if (!url) return
    audio = audio || wx.createInnerAudioContext()
    audio.stop()
    audio.src = url
    audio.play()
  },

  choose(e: WechatMiniprogram.TouchEvent) {
    if (this.data.answered) return
    const s = progress.session as Session
    const step = s.steps[s.index]
    const picked = e.currentTarget.dataset.id as string
    this.submit(step, picked === step.id, picked, false)
  },

  onType(e: WechatMiniprogram.Input) {
    this.setData({ typed: e.detail.value })
  },

  /** 拼写提示：多给一个字母。用了提示最多算 Hard。 */
  giveHint() {
    const s = progress.session as Session
    const target = (byId.get(s.steps[s.index].id) as StudyWord).hw
    const n = Math.min(target.length, this.data.hint.length + 1)
    this.setData({ hint: target.slice(0, n), typed: target.slice(0, n) })
  },

  submitSpelling() {
    if (this.data.answered) return
    const s = progress.session as Session
    const step = s.steps[s.index]
    const target = (byId.get(step.id) as StudyWord).hw
    const norm = (x: string) => x.trim().toLowerCase().replace(/\s+/g, ' ')
    this.submit(step, norm(this.data.typed) === norm(target), this.data.typed, !!this.data.hint)
  },

  submit(step: Step, correct: boolean, value: string, hinted: boolean) {
    if (step.kind === 'intro') return
    const grade = gradeFor(step.kind, correct, Date.now() - stepStart, hinted)
    progress = answer(progress, words, step, correct, grade, value, Date.now())
    saveProgress(progress)
    this.reveal(correct, value)
  },

  /** 显示对错：选择题标出正确项和选错的项。 */
  reveal(correct: boolean, value: string) {
    const s = progress.session as Session
    const step = s.steps[s.index]
    const options = this.data.options.map((o) => ({
      ...o,
      state: (o.id === step.id ? 'right' : o.id === value ? 'wrong' : '') as Option['state'],
    }))
    this.setData({ answered: true, correct, options })
    if (step.kind !== 'listen' && this.data.hasAudio) this.play()
  },

  next() {
    progress = advance(progress, (Date.now() - stepStart) / 1000, Date.now())
    saveProgress(progress)
    this.show()
  },

  goHome() {
    wx.navigateBack({ fail: () => wx.reLaunch({ url: '/pages/home/home' }) })
  },
})

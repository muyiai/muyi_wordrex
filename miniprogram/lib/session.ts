// 每日学习：先复习到期的词，再按课本单元顺序学新词（5 个一组：先认识，再打乱顺序回忆）。
// 流程和评分改编自词光 word-atlas 的 src/store/session.ts（MIT）。纯函数：输入旧进度，返回新进度。
import { Book, BookDict, StageCode } from './types'
import { Grade, isMastered, Rating, review } from './srs'
import { bumpDay, dayKey, Progress, QuizKind, Session, Step } from './progress'
import { examplesFor, mediaUrl, phonetics, shortMeaning } from './text'

/** 一本书里参与学习的词（只取要求掌握的），带出题需要的信息。 */
export interface StudyWord {
  id: string
  hw: string
  ipa: string
  meaning: string
  pos: string
  unit: number
  order: number
  isPhrase: boolean
  example?: { en: string; zh: string }
  cloze?: { before: string; after: string } // 例句挖空，空格处是这个词
  image: string // 插画地址，没有为空串
  audio: string // 英音地址，没有为空串
}

export interface StudySettings {
  dailyNew: number
  retention: number
  spell: boolean
}

/* ---------- 可复现的随机：同一轮退出再进来，题目和选项不变 ---------- */

export function hashSeed(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

export function shuffle<T>(xs: T[], seed: number): T[] {
  const out = [...xs]
  let x = Math.floor(seed) || 1
  for (let i = out.length - 1; i > 0; i--) {
    x = (Math.imul(1664525, x) + 1013904223) >>> 0
    const j = x % (i + 1)
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/* ---------- 学习用的词 ---------- */

const PLACEHOLDER = /\b(sb|sth|one's|oneself)\b|\.\.\.|…/i

/** 在例句里找到这个词并挖空：允许词干相同的屈折变化（runs、looking），不认不规则变化（took）。短语要整段出现。 */
export function clozeOf(hw: string, sentence: string): { before: string; after: string } | undefined {
  if (PLACEHOLDER.test(hw)) return undefined
  const words = hw.toLowerCase().match(/[a-z']+/g)
  if (!words || !words.length) return undefined
  const stem = (w: string) => w.slice(0, Math.max(3, w.length - 2)).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pattern = words.map((w) => (w.length <= 3 ? `${w}\\w{0,3}` : `${stem(w)}\\w*`)).join("[\\s-]+")
  const m = new RegExp(`\\b${pattern}\\b`, 'i').exec(sentence)
  if (!m) return undefined
  return { before: sentence.slice(0, m.index), after: sentence.slice(m.index + m[0].length) }
}

export function studyWords(book: Book, dict: BookDict, mediaBase: string): StudyWord[] {
  const out: StudyWord[] = []
  const seen = new Set<string>()
  book.units.forEach((unit, u) => {
    for (const w of unit.words) {
      if (!w.req || seen.has(w.id)) continue
      seen.add(w.id)
      const entry = dict[w.id]
      const example = entry ? examplesFor(entry, book.stage as StageCode)[0] : undefined
      out.push({
        id: w.id,
        hw: w.hw,
        ipa: phonetics(w, entry).uk,
        meaning: shortMeaning(w, entry),
        pos: (w.senses[0] && w.senses[0].pos) || (entry && entry.senses[0] ? entry.senses[0].pos : ''),
        unit: u,
        order: out.length,
        isPhrase: /\s/.test(w.hw.trim()),
        example,
        cloze: example ? clozeOf(w.hw, example.en) : undefined,
        image: mediaUrl(mediaBase, 'img', entry),
        audio: mediaUrl(mediaBase, 'uk', entry),
      })
    }
  })
  return out
}

/* ---------- 今日计划 ---------- */

export function dueIds(p: Progress, words: StudyWord[], now: number): string[] {
  return words
    .filter((w) => p.cards[w.id] && p.cards[w.id].due <= now)
    .sort((a, b) => p.cards[a.id].due - p.cards[b.id].due)
    .map((w) => w.id)
}

export const newToday = (p: Progress, day = dayKey()) => (p.days[day] ? p.days[day].n : 0)

/** 按课本顺序取还没学过的词；指定单元时只取这个单元的。 */
export function nextNew(words: StudyWord[], p: Progress, count: number, unit?: number): string[] {
  return words
    .filter((w) => !p.cards[w.id] && (unit === undefined || w.unit === unit))
    .slice(0, count)
    .map((w) => w.id)
}

export function todayPlan(words: StudyWord[], p: Progress, s: StudySettings, now: number) {
  const due = dueIds(p, words, now)
  const fresh = nextNew(words, p, Math.max(0, s.dailyNew - newToday(p, dayKey(new Date(now)))))
  return { due, fresh, minutes: Math.max(1, Math.round(due.length * 0.25 + fresh.length * 0.9)) }
}

/* ---------- 出题 ---------- */

function available(w: StudyWord, s: StudySettings): Record<QuizKind, boolean> {
  return {
    meaning: !!w.meaning,
    cloze: !!w.cloze,
    listen: !!w.audio,
    spell: s.spell && /^[A-Za-z][A-Za-z' -]{0,24}$/.test(w.hw) && !!(w.meaning || w.cloze),
  }
}

/** 新词、记得不牢的多出选义和例句填空；记得较牢的多出拼写和听音。没有对应素材的题型自动跳过。 */
export function quizKind(w: StudyWord, p: Progress, s: StudySettings, salt: number): QuizKind {
  const can = available(w, s)
  const c = p.cards[w.id]
  const roll = hashSeed(w.id + salt) % 100
  let prefs: QuizKind[]
  if (!c || c.s < 2) prefs = roll < 45 ? ['cloze', 'meaning', 'listen'] : roll < 85 ? ['meaning', 'cloze', 'listen'] : ['listen', 'meaning', 'cloze']
  else if (c.s >= 4 || roll < 35) prefs = roll < 75 ? ['spell', 'cloze', 'listen', 'meaning'] : ['cloze', 'listen', 'meaning', 'spell']
  else prefs = roll < 50 ? ['listen', 'cloze', 'meaning'] : ['cloze', 'meaning', 'listen']
  return prefs.find((k) => can[k]) || (['meaning', 'cloze', 'spell', 'listen'] as QuizKind[]).find((k) => can[k]) || 'meaning'
}

const coreZh = (zh: string) => zh.replace(/^[a-z.& ]+\s*/i, '').split(/[；;，,]/)[0]

/** 干扰项：同一本书里的词。选义题挑词性相同、释义不同的；填空和听音题挑首字母相同、长度相近的，短语优先配短语
 * （书里短语不够时也用单词，免得只剩正确答案一个选项）。 */
export function distractors(words: StudyWord[], target: StudyWord, kind: QuizKind, seed: number): string[] {
  const scored: [number, StudyWord][] = []
  const tCore = coreZh(target.meaning)
  for (const w of words) {
    if (w.id === target.id || w.hw.toLowerCase() === target.hw.toLowerCase()) continue
    let score = hashSeed(w.id + seed) % 100
    if (kind === 'meaning') {
      if (!w.meaning || (tCore && w.meaning.includes(tCore))) continue
      if (w.pos && w.pos === target.pos) score += 60
      if (Math.abs(w.order - target.order) < 60) score += 40
    } else {
      if (w.isPhrase === target.isPhrase) score += 1000
      if (w.hw[0] && w.hw[0].toLowerCase() === target.hw[0].toLowerCase()) score += 120
      score += Math.max(0, 60 - Math.abs(w.hw.length - target.hw.length) * 20)
    }
    scored.push([score, w])
  }
  scored.sort((a, b) => b[0] - a[0])
  const keys = new Set<string>([kind === 'meaning' ? target.meaning : target.hw.toLowerCase()])
  const picks: string[] = []
  for (const [, w] of scored) {
    const key = kind === 'meaning' ? w.meaning : w.hw.toLowerCase()
    if (keys.has(key)) continue
    keys.add(key)
    picks.push(w.id)
    if (picks.length === 3) break
  }
  return shuffle([target.id, ...picks], seed)
}

export function buildSession(words: StudyWord[], bookId: string, p: Progress, s: StudySettings, now: number,
  opts: { unit?: number; reviewOnly?: boolean } = {}): Session {
  const byId = new Map(words.map((w) => [w.id, w]))
  const plan = todayPlan(words, p, s, now)
  const reviewIds = plan.due.slice(0, 120)
  const newIds = opts.reviewOnly ? [] : opts.unit !== undefined ? nextNew(words, p, Math.max(5, s.dailyNew), opts.unit) : plan.fresh
  const steps: Step[] = []
  const quiz = (id: string, salt: number): Step => {
    const w = byId.get(id) as StudyWord
    const kind = quizKind(w, p, s, now + salt)
    return { id, kind, options: kind === 'spell' ? undefined : distractors(words, w, kind, now + salt) }
  }
  // 先复习（注意力最好的时候），再学新词：5 个一组，先认识，再打乱顺序回忆
  reviewIds.forEach((id, i) => steps.push(quiz(id, i)))
  for (let g = 0; g < newIds.length; g += 5) {
    const group = newIds.slice(g, g + 5)
    group.forEach((id) => steps.push({ id, kind: 'intro' }))
    shuffle(group, now + g).forEach((id, i) => steps.push(quiz(id, 1000 + g + i)))
  }
  return { id: `s${now}`, bookId, started: now, steps, index: 0, graded: {}, newIds, reviewIds }
}

/* ---------- 作答与评分 ---------- */

/** 答错 Again；用了提示或答得慢 Hard；答对 Good；拼写又快又对 Easy。 */
export function gradeFor(kind: QuizKind, correct: boolean, ms: number, hinted: boolean): Grade {
  if (!correct) return Rating.Again
  if (hinted) return Rating.Hard
  const slow = kind === 'spell' ? 20000 : 9000
  if (ms > slow) return Rating.Hard
  if (kind === 'spell' && ms < 6000) return Rating.Easy
  return Rating.Good
}

/** 记一次作答。每个词一轮里只有第一次作答更新记忆和统计；答错的几题之后换题型重练（最多两次），不再评分。 */
export function answer(p: Progress, words: StudyWord[], step: Step, correct: boolean, grade: Grade, value: string,
  now: number, retention = 0.9): Progress {
  const sess = p.session
  if (!sess || step.kind === 'intro') return p
  let next: Progress = { ...p, session: { ...sess, pending: { correct, value } } }
  const first = !(step.id in sess.graded) && !step.retry
  if (first) {
    next = {
      ...next,
      cards: { ...next.cards, [step.id]: review(p.cards[step.id], grade, now, retention) },
      session: { ...(next.session as Session), graded: { ...sess.graded, [step.id]: grade } },
      mistakes: correct ? next.mistakes : [step.id, ...next.mistakes.filter((x) => x !== step.id)].slice(0, 300),
    }
    next = bumpDay(next, { r: 1, c: correct ? 1 : 0, n: sess.newIds.includes(step.id) ? 1 : 0 }, dayKey(new Date(now)))
  }
  if (!correct) {
    const steps = [...(next.session as Session).steps]
    const retries = steps.filter((x) => x.id === step.id && x.kind !== 'intro' && x.retry).length
    const w = words.find((x) => x.id === step.id)
    if (retries < 2 && w) {
      const kind: QuizKind = step.kind === 'meaning' ? (w.cloze ? 'cloze' : w.audio ? 'listen' : 'meaning') : 'meaning'
      const at = Math.min(steps.length, sess.index + 4)
      steps.splice(at, 0, { id: step.id, kind, retry: true, options: distractors(words, w, kind, now) })
      next = { ...next, session: { ...(next.session as Session), steps } }
    }
  }
  return next
}

/** 进入下一步。seconds 是这一步用的时间，封顶 90 秒，免得挂机把统计撑大。 */
export function advance(p: Progress, seconds: number, now: number): Progress {
  const s = p.session
  if (!s) return p
  const index = s.index + 1
  const next = bumpDay(p, { t: Math.max(0, Math.min(90, Math.round(seconds))) }, dayKey(new Date(now)))
  return { ...next, session: { ...s, index, pending: undefined, finished: index >= s.steps.length ? now : undefined } }
}

export function sessionStats(s: Session) {
  const graded = Object.values(s.graded)
  const correct = graded.filter((g) => g !== Rating.Again).length
  return { total: graded.length, correct, accuracy: graded.length ? Math.round((correct / graded.length) * 100) : 0 }
}

export const masteredCount = (p: Progress, ids?: string[]) =>
  (ids || Object.keys(p.cards)).filter((id) => isMastered(p.cards[id])).length

export const learnedCount = (p: Progress, ids?: string[]) => (ids || Object.keys(p.cards)).filter((id) => p.cards[id]).length

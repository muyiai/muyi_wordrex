// 页面共用：加载当前书的学习用词（书和词典都走 source 的缓存）
import { MEDIA_BASE } from '../config'
import { StudySettings, StudyWord, studyWords } from './session'
import { source } from './source'
import { Settings } from './store'

export async function loadStudyWords(bookId: string): Promise<StudyWord[]> {
  const [book, dict] = await Promise.all([source.book(bookId), source.bookDict(bookId)])
  return studyWords(book, dict, MEDIA_BASE)
}

export const studySettings = (s: Settings): StudySettings => ({ dailyNew: s.dailyNew, retention: 0.9, spell: s.spell })

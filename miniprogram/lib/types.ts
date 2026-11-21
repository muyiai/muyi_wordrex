// 与 pipeline/tw/build.py 产出的 JSON 对应

export type StageCode = 'ps' | 'jh' | 'sh'

export interface BookMeta {
  id: string
  title: string // 三年级上册 / 必修 第一册
  grade: number
  units: number
  words: number
  req: number // 要求掌握的词数
  qa: boolean // 是否通过提取质量检查
}

export interface Edition {
  code: string
  name: string
  publisher: string
  books: BookMeta[]
}

export interface Stage {
  code: StageCode
  name: string
  editions: Edition[]
}

export interface Catalog {
  version: string
  dictChunks: number
  stages: Stage[]
}

export interface Sense {
  pos: string
  zh: string
  en?: string // 词光的英文释义
}

export interface BookWord {
  id: string
  hw: string
  senses: Sense[] // 课本上的释义（可能为空：课本释义缺失或乱码）
  req: boolean // 要求掌握
  core?: boolean // 黑体词
  new?: boolean // 本系列第一次出现
  ipa?: string // 课本音标
  kind?: 'phrase' | 'abbr' | 'proper' | 'name'
}

export interface Unit {
  name: string
  words: BookWord[]
}

export interface Book {
  id: string
  stage: StageCode
  edition: string
  editionName: string
  publisher: string
  grade: number
  term: string
  volume: string
  units: Unit[]
}

export interface Example {
  en: string
  zh: string
}

export interface Entry {
  id: string
  w: string
  kind: string
  uk?: string
  us?: string
  senses: Sense[]
  ex?: Example[]
  col?: string[] // "english｜中文"
  fam?: string[]
  syn?: string[]
  ant?: string[]
  tip?: string
  cefr?: string
  aid?: string // 词光 id：媒体文件名
  m?: number // 媒体位：1 插画、2 英音、4 美音、8 例句朗读
  tags?: string[] // zk 中考、gk 高考、cet4 ……
  src: 'atlas' | 'gen' | 'ecdict' | 'textbook' // gen：词光没有、按词光做法生成的词条（pipeline/tw/forge.py）
  lemma?: string
}

export type BookDict = Record<string, Entry>

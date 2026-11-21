// 给测试用的类型声明（merge.js 是云函数里直接运行的 CommonJS）
export function merge(stored: unknown, incoming: unknown): {
  version: 1
  cards: Record<string, unknown>
  days: Record<string, { n: number; r: number; c: number; t: number }>
  mistakes: string[]
}

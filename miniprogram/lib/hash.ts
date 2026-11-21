// 32 位 FNV-1a（UTF-8 字节），必须和 pipeline/tw/build.py 的 fnv1a 一致：词典分块号由它决定

function utf8(text: string): number[] {
  const bytes: number[] = []
  for (const ch of text) {
    const code = ch.codePointAt(0) as number
    if (code < 0x80) bytes.push(code)
    else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f))
    else if (code < 0x10000) bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
    else bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
  }
  return bytes
}

export function fnv1a(text: string): number {
  let h = 0x811c9dc5
  for (const b of utf8(text)) {
    h ^= b
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h >>> 0
}

export function chunkOf(wordId: string, chunks: number): number {
  return fnv1a(wordId) % chunks
}

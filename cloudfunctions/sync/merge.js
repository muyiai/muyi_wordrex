// 学习进度合并：云端存的一份 + 这台设备传上来的一份 -> 合并后的一份。两台设备离线各学各的，合并后都不丢。
//   记忆卡片：每个词取最后一次复习更新的那份（一样新时取复习次数多的）
//   每日统计：每个字段取较大值（同一份数据重复同步不会被算两次）
//   错词：并集，传上来的（这台设备上更新的）在前，最多 300 个
// 进行中的一轮（session）只在本机，不同步。两边的数据都当作不可信输入，先校验。

const isObj = (v) => !!v && typeof v === 'object' && !Array.isArray(v)
const num = (v, lo = -Infinity, hi = Infinity) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi

function validCard(c) {
  return isObj(c) && num(c.due, 0) && num(c.s, 0) && num(c.d, 0, 11) && num(c.el, 0) && num(c.sd, 0) && num(c.ls, 0) &&
    num(c.reps, 0) && num(c.lapses, 0) && [0, 1, 2, 3].includes(c.st) && (c.last === undefined || num(c.last, 0)) && num(c.seen, 0)
}

function validDay(d) {
  return isObj(d) && num(d.n, 0) && num(d.r, 0) && num(d.c, 0) && num(d.t, 0)
}

function newer(a, b) {
  const la = a.last || 0
  const lb = b.last || 0
  if (la !== lb) return la > lb ? a : b
  return a.reps >= b.reps ? a : b
}

function merge(stored, incoming) {
  const out = { version: 1, cards: {}, days: {}, mistakes: [] }
  for (const p of [stored, incoming]) {
    if (!isObj(p)) continue
    if (isObj(p.cards)) {
      for (const [id, c] of Object.entries(p.cards)) {
        if (!validCard(c)) continue
        out.cards[id] = out.cards[id] ? newer(out.cards[id], c) : c
      }
    }
    if (isObj(p.days)) {
      for (const [day, d] of Object.entries(p.days)) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !validDay(d)) continue
        const cur = out.days[day] || { n: 0, r: 0, c: 0, t: 0 }
        out.days[day] = { n: Math.max(cur.n, d.n), r: Math.max(cur.r, d.r), c: Math.max(cur.c, d.c), t: Math.max(cur.t, d.t) }
      }
    }
  }
  const mistakes = [incoming, stored].flatMap((p) => (isObj(p) && Array.isArray(p.mistakes) ? p.mistakes : []))
  out.mistakes = [...new Set(mistakes.filter((x) => typeof x === 'string'))].slice(0, 300)
  return out
}

module.exports = { merge }

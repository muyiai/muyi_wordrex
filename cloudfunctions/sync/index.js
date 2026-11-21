// 云函数 sync：把这台设备的学习进度和云端的合并，存回云端，返回合并结果。
// 用户身份取微信上下文里的 openid（调用方传不进来），每个用户只能读写自己的那一条。
const cloud = require('wx-server-sdk')
const { merge } = require('./merge')

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()

exports.main = async (event) => {
  const { OPENID } = cloud.getWXContext()
  if (!OPENID) return { error: 'no openid' }
  const doc = db.collection('progress').doc(OPENID)
  let stored = null
  try {
    stored = (await doc.get()).data.progress
  } catch (err) {
    stored = null // 第一次同步，还没有记录
  }
  const progress = merge(stored, event.progress)
  await doc.set({ data: { progress, updatedAt: Date.now() } })
  return { progress }
}

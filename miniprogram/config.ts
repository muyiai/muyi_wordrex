// 数据和媒体的地址。
// 开发：先 python run.py publish，再在仓库根目录 npm run dev:data，用本机地址；真机预览换成电脑的局域网 IP。
// 上线：云存储的访问域名加上发布目录（run.py publish 生成的 out/publish/ 上传到云存储的 wordrex/ 下），例如
//   DATA_BASE  = 'https://<云存储域名>/wordrex/data'
//   MEDIA_BASE = 'https://<云存储域名>/wordrex/media'
// 数据域名要加到小程序后台的 request 合法域名；媒体只用在 <image>、音频，不受合法域名限制。
export const DATA_BASE = 'http://localhost:8787/data'

// 词光和生成的插画、录音（img/<aid>.webp、audio/uk/<aid>.mp3 ……）所在地址。为空时不显示图片和播放按钮。
export const MEDIA_BASE = 'http://localhost:8787/media'

// 云开发环境 ID（学习进度云同步）。为空时进度只存在本机。
export const CLOUD_ENV = ''

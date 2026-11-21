# muyi_wordrex

从小学到高中、按教材版本和年级单元背英语单词的微信小程序。

- 单词来源：[ChinaTextbook](https://github.com/TapXWorld/ChinaTextbook) 里的英语教材 PDF（书后的按单元单词表）。
- 词条内容：[词光 Word Atlas](https://github.com/designfuchen/word-atlas)（CC BY 4.0，署名 “Word Atlas contributors”）+ [ECDICT](https://github.com/skywind3000/ECDICT)（MIT）。
- 本仓库不包含教材 PDF，也不再分发 PDF，只发布从中整理出的单词列表。

## 数据管线 `pipeline/`

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
cd pipeline
../.venv/bin/python run.py vendor      # 下载词光数据和 ECDICT
../.venv/bin/python run.py manifest    # 生成教材清单（config/editions.yaml 白名单）
../.venv/bin/python run.py fetch       # 下载 PDF（约 3.4 GB，分卷自动拼接）
../.venv/bin/python run.py all         # 提取 -> 清洗 -> QA -> 补全 -> 打包
../.venv/bin/python -m pytest -q
```

| 步骤 | 模块 | 产出 |
|---|---|---|
| 清单 | `tw/manifest.py` | `out/manifest.json` |
| 下载 | `tw/fetch.py` | `out/pdf/<bookId>.pdf` |
| 提取 | `tw/extract.py` | `out/extract/`：按单元词条 + 书后字母序总表 |
| 清洗 | `tw/normalize.py` | `out/normalized/`：修复连字丢字、分类、wordId、是否要求掌握 |
| QA | `tw/qa.py` | `out/qa/report.md`：按单元表与总表互相核对 |
| 补全 | `tw/enrich.py` | `out/enriched.json`：词光 / ECDICT 词条 |
| 打包 | `tw/build.py` | `out/build/`：`catalog.json`、`books/`、`dict/` |

bookId 形如 `jh-pep-7a`（初中·人教·七年级上册）、`sh-pep-b1`（高中·人教·必修第一册）。

## 小程序 `miniprogram/`

原生微信小程序 + TypeScript（微信开发者工具内置的 TypeScript 编译插件）。

```bash
# 开发工具：Node.js 22（npm）
npm install
npm run typecheck   # 用官方 miniprogram-api-typings 做类型检查
npm test            # vitest：哈希与 Python 一致、数据加载与缓存、展示逻辑、管线产物格式
npm run dev:data    # 在 http://localhost:8787 提供 pipeline/out/build 的数据
```

用微信开发者工具「导入项目」选择仓库根目录（`project.config.json` 指向 `miniprogram/`），AppID 先用测试号；
第一次打开先点「工具 → 构建 npm」（把根目录 `package.json` 的 `dependencies`，即 `ts-fsrs`，构建到 `miniprogram/miniprogram_npm/`）。
开发时数据从本机读取：工具里「详情 → 本地设置」勾选「不校验合法域名」；真机预览需把 `miniprogram/config.ts`
的 `DATA_BASE` 改成电脑的局域网 IP。上线前换成云存储 / CDN 地址（M4）。

| 页面 | 内容 |
|---|---|
| `pages/home` | 当前教材、今日学习（待复习、新词、已学、记得牢、连续天数）、单元列表；没选教材时引导去选 |
| `pages/select` | 学段 → 版本 → 册 |
| `pages/unit` | 单元单词：音标、释义（课本释义优先），遮住释义、只看要求掌握 |
| `pages/word` | 单词详情：英美音标、课本释义、词典释义、例句（小学初中只给短句）、搭配、词族、提示，上一个/下一个 |
| `pages/learn` | 学习：先复习到期的词，再按课本顺序学新词（5 个一组，先认识再回忆）；题型：选义、例句填空（有插画配图）、听音（有音频时）、拼写；FSRS 安排复习 |
| `pages/settings` | 每天新学几个词、拼写题开关 |
| `pages/about` | 数据来源与授权署名 |

浏览器预览（weweb，可选）：`npm install -g weweb-cli` 后 `npm run web`（会先把 TypeScript 编译到 `.weweb/`），
打开 http://localhost:3000。数据服务 `npm run dev:data` 带 CORS 和 JSONP（weweb 在浏览器里把 `wx.request` 实现成 JSONP）。
注意：weweb（2018 年前后的实现）没有 `wx.env`、`wx.getFileSystemManager`，它导航栏的全局 `.head` 样式也会和页面样式冲突，
所以目前页面在 weweb 里打不开。小程序代码不为 weweb 做改动，以微信开发者工具和真机为准。

数据：`catalog.json` 每次启动拉取；`books/<id>.json` 和这本书的词典 `books/<id>.dict.json` 按目录版本号缓存在
用户文件目录（`lib/data.ts`、`lib/wx-io.ts`）。

## 进度

- [x] M0 单本书跑通管线
- [x] M1 主流版本全部提取：110 本，103 本通过 QA（按单元表与书后总表互相核对），共 9,547 个词
  - 35 本扫描版用 macOS Vision OCR（`tools/ocr.swift`，`run.py ocr`）
  - 未通过的 7 本：沪教高中 6 本书后没有总表可核对（已人工抽查，中文释义字体损坏，改用词典释义）；外研小学五下 97.98%（差的 3 个词来自课外阅读词表）
- [x] 词条补全：词光没有的单词和短语按词光的做法生成（`run.py forge text`，gpt-6.2-sol），3,617 条；
  要求掌握的单词有例句和用法的：小学 98.8%、初中 99.3%、高中 99.0%；短语：小学 92.7%、初中 90.0%、高中 80.3%。
  插画（`forge images`，gpt-image-2.5-flare）3,611 张已生成，6 张被安全审核拒绝；发音和例句朗读（`forge audio`，需 ElevenLabs key）尚未生成。模型标出的问题见 `out/forge/flags.md`
- [x] M2 小程序骨架（选教材 / 单元 / 单词浏览）：代码完成，类型检查和单测通过，待在微信开发者工具里实际运行
- [x] M3 FSRS 复习与题型：代码完成，单测（含用真实课本组题）通过，待在开发者工具里实际运行；
  学习进度存在本地，复习只覆盖当前这本书的词；听音题和插画要等 M4 配好媒体地址后启用
- [ ] M4 云开发同步与资源上云
- [ ] M5 提审

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

## 进度

- [x] M0 单本书跑通管线
- [x] M1 主流版本全部提取：110 本，103 本通过 QA（按单元表与书后总表互相核对），共 9,300 个词
  - 35 本扫描版用 macOS Vision OCR（`tools/ocr.swift`，`run.py ocr`）
  - 未通过的 7 本：沪教高中 6 本书后没有总表可核对（已人工抽查，中文释义字体损坏，改用词典释义）；外研小学五下 97.98%（差的 3 个词来自课外阅读词表）
- [ ] M2 小程序骨架（教材树 / 单元 / 单词浏览）
- [ ] M3 FSRS 复习与题型
- [ ] M4 云开发同步与资源上云
- [ ] M5 提审

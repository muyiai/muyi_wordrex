"""QA：按单元表 vs 字母序总表互相核对，列出修复过的词头和词典未收录的词。

两张表是同一本书里独立排版的，提取结果一致就说明两边都没漏/没错；
不一致的地方就是需要人工看的地方。覆盖率 = 总表里的词在按单元表中找得到的比例。

通过要求覆盖率 ≥ 98%。用总表补过词（fromIndex）的书还要求按单元表里的普通词至少 95% 在总表里，
防止「按单元表其实取错了地方、再靠总表补全凑出覆盖率」这种假通过。没补过词的书不查这条：
不少书的总表本来就只收一部分词（人教小学五、六年级）。
"""
import json
import re

from .normalize import NORMALIZED_DIR, entry_id
from .paths import EXTRACT_DIR, OUT

QA_DIR = OUT / "qa"
PASS_COVERAGE = 0.98
PASS_COVERAGE_OCR = 0.90  # 扫描版：两张表各自 OCR，各有错字，对不上的部分不全是提取错误
MAX_EXTRA = 0.05


def check_book(extracted, normalized):
    words = [w for u in normalized["units"] for w in u["words"]]
    unit_ids = {w["id"] for w in words}
    # 总表本来就不收专名、人名、缩写，这些「多出来」是正常的，不列
    plain_ids = {w["id"] for w in words if w["kind"] in ("word", "phrase") and not w.get("fromIndex")}
    index_ids = {entry_id(e["hw"], e.get("ocr")) for e in extracted.get("index", [])}
    if extracted.get("ocr"):  # OCR 常丢词组里的空格（in the faceof），比较时只看字母
        squash = lambda ids: {re.sub(r"[\W_]+", "", i) for i in ids}
        unit_ids, plain_ids, index_ids = squash(unit_ids), squash(plain_ids), squash(index_ids)
    if len(index_ids) < len(words) * 0.15:
        index_ids = set()  # 太短的「总表」不是词汇表（沪教高中书后是 12 个语法术语）
    result = {
        "id": normalized["id"],
        "units": len(normalized["units"]),
        "words": len(words),
        "index": len(index_ids),
        "missing": sorted(index_ids - unit_ids),  # 总表有、按单元表没有
        "extra": sorted(plain_ids - index_ids),  # 按单元表有、总表没有
        "filled": sum(1 for w in words if w.get("fromIndex")),
        "repaired": [f"{w['raw']} -> {w['hw']}" for w in words if "raw" in w],
        "warnings": normalized["warnings"],
    }
    result["coverage"] = 1 - len(result["missing"]) / len(index_ids) if index_ids else None
    extra_ratio = len(result["extra"]) / len(plain_ids) if plain_ids else 1
    # 只有用总表补过不少词的书才可能被「凑出」覆盖率。只比单词：有的总表不收词组（译林初中）
    single = {w["id"] for w in words if w["kind"] == "word" and not w.get("fromIndex")}
    single_extra = len(single - index_ids) / len(single) if single else 1
    masked = result["filled"] >= len(words) * 0.1 and single_extra > MAX_EXTRA
    result["ocr"] = bool(extracted.get("ocr"))
    result["indexOnly"] = bool(extracted.get("indexOnly"))  # 单元是按总表的单元号重建的，覆盖率没有核对意义
    threshold = PASS_COVERAGE_OCR if result["ocr"] else PASS_COVERAGE
    result["pass"] = result["coverage"] is not None and result["coverage"] >= threshold and not masked
    return result


def render(results):
    lines = ["# 提取质量报告", "", "| 书 | 单元 | 词条 | 总表 | 覆盖率 | 总表有/单元表无 | 单元表有/总表无 | 总表补入 | 修复 | 结果 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        cov = f"{r['coverage']:.1%}" if r["coverage"] is not None else "无总表"
        if r.get("indexOnly"):
            cov += "（总表分单元）"
        elif r.get("ocr"):
            cov += "（OCR）"
        lines.append(f"| {r['id']} | {r['units']} | {r['words']} | {r['index']} | {cov} | {len(r['missing'])} "
                     f"| {len(r['extra'])} | {r['filled']} | {len(r['repaired'])} | {'通过' if r['pass'] else '待查'} |")
    for r in results:
        lines += ["", f"## {r['id']}"]
        for title, key in [("总表有、按单元表没有", "missing"), ("按单元表有、总表没有", "extra"),
                           ("词头修复", "repaired"), ("警告", "warnings")]:
            if r[key]:
                lines.append(f"- **{title}**（{len(r[key])}）：" + "，".join(r[key]))
    return "\n".join(lines) + "\n"


def main(ids=None):
    files = sorted(NORMALIZED_DIR.glob("*.json"))
    if ids:
        files = [f for f in files if f.stem in ids]
    results = []
    for f in files:
        normalized = json.loads(f.read_text(encoding="utf-8"))
        extracted = json.loads((EXTRACT_DIR / f.name).read_text(encoding="utf-8"))
        results.append(check_book(extracted, normalized))
    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "report.md").write_text(render(results), encoding="utf-8")
    (QA_DIR / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        cov = f"{r['coverage']:.1%}" if r["coverage"] is not None else "无总表"
        print(f"qa: {r['id']} 覆盖率 {cov} 缺 {len(r['missing'])} 多 {len(r['extra'])} {'通过' if r['pass'] else '待查'}")
    return results

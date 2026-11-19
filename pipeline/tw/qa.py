"""QA：按单元表 vs 字母序总表互相核对，列出修复过的词头和词典未收录的词。

两张表是同一本书里独立排版的，提取结果一致就说明两边都没漏/没错；
不一致的地方就是需要人工看的地方。覆盖率 = 总表里的词在按单元表中找得到的比例。
"""
import json

from .normalize import NORMALIZED_DIR, clean_hw, make_id, repair
from .paths import EXTRACT_DIR, OUT

QA_DIR = OUT / "qa"
PASS_COVERAGE = 0.98


def check_book(extracted, normalized):
    words = [w for u in normalized["units"] for w in u["words"]]
    unit_ids = {w["id"] for w in words}
    # 总表本来就不收专名、人名、缩写，这些「多出来」是正常的，不列
    plain_ids = {w["id"] for w in words if w["kind"] in ("word", "phrase")}
    index_ids = {make_id(repair(clean_hw(hw))) for hw in extracted.get("index", [])}
    result = {
        "id": normalized["id"],
        "units": len(normalized["units"]),
        "words": len(words),
        "index": len(index_ids),
        "missing": sorted(index_ids - unit_ids),  # 总表有、按单元表没有
        "extra": sorted(plain_ids - index_ids),  # 按单元表有、总表没有
        "repaired": [f"{w['raw']} -> {w['hw']}" for w in words if "raw" in w],
        "warnings": normalized["warnings"],
    }
    result["coverage"] = 1 - len(result["missing"]) / len(index_ids) if index_ids else None
    result["pass"] = result["coverage"] is not None and result["coverage"] >= PASS_COVERAGE
    return result


def render(results):
    lines = ["# 提取质量报告", "", "| 书 | 单元 | 词条 | 总表 | 覆盖率 | 总表有/单元表无 | 单元表有/总表无 | 修复 | 结果 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        cov = f"{r['coverage']:.1%}" if r["coverage"] is not None else "无总表"
        lines.append(f"| {r['id']} | {r['units']} | {r['words']} | {r['index']} | {cov} | {len(r['missing'])} "
                     f"| {len(r['extra'])} | {len(r['repaired'])} | {'通过' if r['pass'] else '待查'} |")
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

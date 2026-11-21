"""词光没有收录的单词和课本短语：按词光的做法生成词条（文本、插画、发音、例句朗读）。

改编自词光 word-atlas 的 scripts/atlas（MIT，© Word Atlas contributors）：编写规范、画风提示词、
ElevenLabs 声音（英音 Alice、美音 Sarah）与它一致，新旧词条看起来是一套。和词光不同的地方：
  - 读者是中小学生：例句按这个词最早出现的学段分级（小学很短的简单句），课本释义作为义项提示
  - 输入是 enrich 之后仍没有词光内容的单词和短语（OCR 杂条、人名、专名不生成）
  - 每个词一个结果文件，断点续跑，词表变了也不会错位

产物（git 忽略）：
  out/forge/text/<aid>.json                 词条
  out/forge/media/img/<aid>.webp            768px 插画；thumb/<aid>.webp 256px
  out/forge/media/audio/{uk,us,ex}/<aid>.mp3

aid 是 "tw-" 开头的文件名，和词光自己的媒体文件不会重名，上云时可以放进同一个目录。

凭据只从环境变量或 ~/.config/muyi-wordrex/secrets.env 读取，不打印、不写进仓库：
  TW_LLM_BASE_URL、TW_LLM_API_KEY  OpenAI 兼容接口（/chat/completions、/images/generations）
  TW_TEXT_MODEL、TW_IMAGE_MODEL    模型名
  ELEVENLABS_API_KEY

用法（先 --dry-run 看数量和提示词，再 --limit 试一小批）：
  python run.py forge text   [--limit N] [--workers W] [--dry-run]
  python run.py forge images [--limit N] [--workers W]
  python run.py forge audio  [--limit N] [--workers W] [--floor 30000]
"""
import argparse
import base64
import concurrent.futures as cf
import glob
import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import dicts
from .paths import OUT

FORGE = OUT / "forge"
TEXT_DIR = FORGE / "text"
MEDIA_DIR = FORGE / "media"
SECRETS = Path(os.environ.get("TW_SECRETS", Path.home() / ".config" / "muyi-wordrex" / "secrets.env"))

STAGE_ORDER = {"ps": 0, "jh": 1, "sh": 2}
TOPICS = [
    "education", "work", "technology", "science", "environment", "health", "society", "government", "economy",
    "media", "arts", "travel", "city", "nature", "daily", "emotion", "thinking", "sport", "history",
]

# 各学段的例句要求。小程序里小学、初中只显示 ex[0]，高中两条都显示
EXAMPLES = {
    "ps": ("Very simple sentence for a Chinese primary-school pupil (age 8-12): 4-8 words, A1 words only, present tense",
           "Simple sentence, 6-10 words, A1-A2 words, about school, family or daily life"),
    "jh": ("Everyday sentence for a junior-high student (age 12-15): 6-12 words, A2-B1 words, natural and vivid",
           "Sentence at Chinese zhongkao (中考) reading level: 10-16 words, B1"),
    "sh": ("Everyday sentence, 7-13 words, natural and vivid",
           "Sentence at Chinese gaokao (高考) reading level: 12-20 words, B1-B2, on a school-textbook topic"),
}

SYSTEM = """You are the lead lexicographer of an open-source English vocabulary atlas for Chinese school students who learn English with their school textbooks.
Write ORIGINAL content in your own words. The textbook meaning you receive tells you which sense the student needs; that sense MUST come first. Never copy the notes verbatim beyond the Chinese meaning.
Accuracy beats creativity: IPA, part of speech, Chinese meanings and grammar must be correct. Prefer standard British IPA for "uk" and General American for "us", with slashes.
Each input item says whether it is a single word or a phrase, and which school stage it belongs to; the stage decides how hard the example sentences may be.
Return strict JSON only: {"entries":[...]} with one entry per input item, same order, using exactly this shape:
{
 "w": the item exactly as given (fix only obvious typos, and then set "flag"),
 "uk": "/IPA/", "us": "/IPA/",
 "senses": [{"pos": "n.|v.|adj.|adv.|prep.|conj.|pron.|phr.|num.|int.|det.", "zh": "简洁中文释义，可用；分隔，≤14字", "en": "learner-friendly English definition, ≤12 words"}],  // 1-3 senses; phrases use "phr."
 "ex": [{"en": "<EX0>, uses the item exactly or an inflected form", "zh": "自然的中文翻译"},
        {"en": "<EX1>, uses the item exactly or an inflected form", "zh": "自然的中文翻译"}],
 "col": ["0-4 high-value collocations, each as 'english phrase｜中文'"],
 "fam": ["0-4 word-family members as 'word (pos)'; empty for phrases"],
 "syn": ["0-3 synonyms"], "ant": ["0-2 antonyms"],
 "tip": "≤36字中文：最有用的一条用法/辨析/记忆提示。不得编造词源；没有可靠词源就讲用法或易混词。",
 "cefr": "A1|A2|B1|B2|C1|C2",
 "topic": one of [TOPICS],
 "scene": "Depicting the FIRST sense: one concrete, visually clear illustration idea (≤28 words, English) that makes the core meaning obvious at a glance: a single moment with people/objects/places. Abstract items become a clear metaphorical scene. Never mention text, letters, signs, labels or numbers.",
 "flag": "" or short note if the item is malformed, offensive, or not real English
}
<EX0> and <EX1> depend on the stage:
[EXAMPLES]
Sentences must be safe for children, culturally neutral, and must not mention real brands or living public figures. Do not reuse the same names across entries; avoid 'Tom' and 'Mary'."""

# 与词光一致
STYLE = (
    "Mid-century modern editorial illustration, like a plate from a vintage illustrated field guide. "
    "Strict limited palette: deep ink navy, warm terracotta, mustard ochre, muted sage green and soft sky blue on warm cream paper. "
    "Flat geometric shapes, confident clean silhouettes, subtle risograph grain and paper texture, gentle shading, "
    "one clear focal subject with generous negative space, centered square composition, calm and charming mood. "
    "Absolutely no text, letters, words, numbers, captions, signs, logos, watermarks or frames."
)
VOICES = {"uk": "Xb7hH8MSUJpSbSDYk0k2", "us": "EXAVITQu4vr4xnSDxMaL"}  # Alice, Sarah（与词光一致）
TTS_MODEL = "eleven_v4_turbo"


# ---------- 凭据与 HTTP ----------

def load_env():
    env = {}
    if SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for name in ("TW_LLM_BASE_URL", "TW_LLM_API_KEY", "TW_TEXT_MODEL", "TW_IMAGE_MODEL", "ELEVENLABS_API_KEY"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def require(env, *names):
    missing = [n for n in names if not env.get(n)]
    if missing:
        raise SystemExit(f"缺少配置：{', '.join(missing)}（环境变量或 {SECRETS}）")


def post(url, payload, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def chat(env, payload, timeout=600):
    """流式请求，长输出不会被代理的空闲超时掐断。"""
    req = urllib.request.Request(
        env["TW_LLM_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps({**payload, "stream": True, "stream_options": {"include_usage": True}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + env["TW_LLM_API_KEY"]},
    )
    parts = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            line = line.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except ValueError:
                continue
            for ch in obj.get("choices", []):
                if (ch.get("delta") or {}).get("content"):
                    parts.append(ch["delta"]["content"])
            if obj.get("usage"):
                log_usage(payload["model"], obj["usage"])
    return "".join(parts)


USAGE_LOG = FORGE / "usage.jsonl"
_usage_lock = threading.Lock()


def log_usage(model, usage):
    """每次调用的 token 用量，估算全量费用用。"""
    with _usage_lock:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "model": model, **usage}) + "\n")


def with_retry(fn, tries=4, base=6):
    """重试临时故障；429 限流单独等待，不占重试次数。"""
    last, i, busy = None, 0, 0
    while i < tries:
        try:
            return fn()
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "ignore")
            last = f"HTTP {e.code}: {body}"
            if e.code in (400, 401, 403) and "rate" not in body.lower():
                raise RuntimeError(last)
            if e.code == 429 and busy < 60:
                busy += 1
                time.sleep(min(60, 5 + busy * 3))
                continue
        except Exception as e:  # 网络抖动、JSON 不合格
            last = repr(e)
        i += 1
        time.sleep(base * i)
    raise RuntimeError(last)


# ---------- 待生成的词 ----------

def aid_of(word_id):
    slug = re.sub(r"[^a-z0-9]+", "-", word_id.lower()).strip("-")[:40] or "x"
    return f"tw-{slug}-{hashlib.sha1(word_id.encode()).hexdigest()[:6]}"


def todo():
    """enrich 之后仍没有词光内容的单词和短语，带学段（最早出现的）和课本释义。"""
    entries = json.loads((OUT / "enriched.json").read_text(encoding="utf-8"))
    stage, notes = {}, {}
    for f in sorted(glob.glob(str(OUT / "build" / "books" / "*.json"))):
        if f.endswith(".dict.json"):
            continue
        book = json.loads(Path(f).read_text(encoding="utf-8"))
        for unit in book["units"]:
            for w in unit["words"]:
                if w["id"] not in stage or STAGE_ORDER[book["stage"]] < STAGE_ORDER[stage[w["id"]]]:
                    stage[w["id"]] = book["stage"]
                if w["senses"] and w["id"] not in notes:
                    notes[w["id"]] = "；".join(f"{s['pos']} {s['zh']}".strip() for s in w["senses"])
    items = []
    for wid, e in entries.items():
        if e["src"] == "atlas" or e["kind"] not in ("word", "phrase") or wid not in stage:
            continue
        if e["kind"] == "word" and not dicts.known(e["w"]):
            continue  # OCR 杂条（boildownto）、拼错的词：先修数据，不生成
        items.append({"id": wid, "word": e["w"], "kind": e["kind"], "stage": stage[wid], "notes": notes.get(wid, ""),
                      "aid": aid_of(wid)})
    # 小学、初中的词先做；同学段内单词在前
    return sorted(items, key=lambda i: (STAGE_ORDER[i["stage"]], i["kind"] != "word", i["id"]))


# ---------- 文本 ----------

def system_prompt():
    rules = "\n".join(f"- stage {s}: <EX0> = {a}; <EX1> = {b}" for s, (a, b) in EXAMPLES.items())
    return SYSTEM.replace("[TOPICS]", json.dumps(TOPICS)).replace("[EXAMPLES]", rules)


def user_prompt(batch):
    lines = []
    for it in batch:
        note = f"textbook meaning: {it['notes']}" if it["notes"] else "no textbook meaning"
        lines.append(f"- {it['word']}  ({it['kind']}, stage {it['stage']}; {note})")
    return "Items:\n" + "\n".join(lines)


def uses_item(sentence, item):
    """例句里要真的用到这个词（允许屈折变化、短语里的 sth/sb/... 占位）。"""
    text = sentence.lower()
    words = [w for w in re.findall(r"[a-z']+", item["word"].lower()) if w not in {"sth", "sb", "one's", "oneself"}]
    return all(re.search(r"\b" + re.escape(w[:max(3, len(w) - 2)]), text) for w in words[:3])


def check_entry(e, item):
    for key in ("w", "senses", "ex", "scene"):
        if not e.get(key):
            raise ValueError(f"{item['word']}: 缺少 {key}")
    if len(e["ex"]) < 2 or not all(x.get("en") and x.get("zh") for x in e["ex"][:2]):
        raise ValueError(f"{item['word']}: 例句不完整")
    if not uses_item(e["ex"][0]["en"], item):
        raise ValueError(f"{item['word']}: 例句没有用到这个词：{e['ex'][0]['en']}")


def gen_text_batch(env, model, batch):
    payload = {"model": model, "messages": [{"role": "system", "content": system_prompt()},
                                            {"role": "user", "content": user_prompt(batch)}]}

    def call():
        text = re.sub(r"^```(?:json)?|```$", "", chat(env, payload).strip()).strip()
        entries = json.loads(text)["entries"]
        if len(entries) != len(batch):
            raise ValueError(f"应有 {len(batch)} 条，返回 {len(entries)} 条")
        for e, it in zip(entries, batch):
            check_entry(e, it)
        return entries

    for e, it in zip(with_retry(call), batch):
        e.update({"id": it["id"], "aid": it["aid"], "stage": it["stage"], "kind": it["kind"], "src": it["word"]})
        (TEXT_DIR / f"{it['aid']}.json").write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def run_text(args):
    items = [it for it in todo() if not (TEXT_DIR / f"{it['aid']}.json").exists()]
    if args.limit:
        items = items[: args.limit]
    batches = [items[i: i + args.batch] for i in range(0, len(items), args.batch)]
    print(f"forge text: 待生成 {len(items)} 条，{len(batches)} 批")
    if args.dry_run:
        print("--- system ---\n" + system_prompt() + "\n--- user（第一批）---\n" + (user_prompt(batches[0]) if batches else ""))
        return
    env = load_env()
    require(env, "TW_LLM_BASE_URL", "TW_LLM_API_KEY", "TW_TEXT_MODEL")
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    run_pool(batches, lambda b: gen_text_batch(env, env["TW_TEXT_MODEL"], b), args.workers,
             label=lambda b: b[0]["word"])


# ---------- 插画 ----------

def generated():
    """已生成的词条：aid -> 词条。"""
    out = {}
    for p in sorted(TEXT_DIR.glob("*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        out[e["aid"]] = e
    return out


def gen_image(env, e):
    from PIL import Image

    payload = {"model": env["TW_IMAGE_MODEL"], "prompt": f"{STYLE}\n\nScene: {e['scene']}", "size": "1024x1024",
               "quality": "low", "n": 1}

    def call():
        raw = post(env["TW_LLM_BASE_URL"].rstrip("/") + "/images/generations", payload,
                   {"Authorization": "Bearer " + env["TW_LLM_API_KEY"]})
        b64 = json.loads(raw)["data"][0].get("b64_json")
        if not b64:
            raise ValueError("没有返回图片")
        return base64.b64decode(b64)

    image = Image.open(io.BytesIO(with_retry(call))).convert("RGB")
    for folder, size, quality in (("img", 768, 78), ("thumb", 256, 74)):
        out = MEDIA_DIR / folder / f"{e['aid']}.webp"
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_suffix(".part")
        image.resize((size, size), Image.LANCZOS).save(part, "WEBP", quality=quality, method=6)
        part.rename(out)  # 原子写入：读的人不会看到写了一半的文件


def run_images(args):
    todo_entries = [e for e in generated().values() if not (MEDIA_DIR / "img" / f"{e['aid']}.webp").exists()]
    if args.limit:
        todo_entries = todo_entries[: args.limit]
    print(f"forge images: 待生成 {len(todo_entries)} 张")
    if args.dry_run or not todo_entries:
        return
    env = load_env()
    require(env, "TW_LLM_BASE_URL", "TW_LLM_API_KEY", "TW_IMAGE_MODEL")
    run_pool(todo_entries, lambda e: gen_image(env, e), args.workers, label=lambda e: e["w"])


# ---------- 发音、例句朗读 ----------

def credits_left(key):
    req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return d["character_limit"] - d["character_count"]


def synth(key, voice, text, out):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64",
        data=json.dumps({"text": text, "model_id": TTS_MODEL, "language_code": "en"}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )

    def call():
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if len(data) < 2000:
            raise ValueError("音频太短")
        return data

    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(".part")
    part.write_bytes(with_retry(call))
    part.rename(out)


def run_audio(args):
    jobs = []
    for e in generated().values():
        for kind, voice, text in (("uk", "uk", e["w"] + "."), ("us", "us", e["w"] + "."), ("ex", "uk", e["ex"][0]["en"])):
            out = MEDIA_DIR / "audio" / kind / f"{e['aid']}.mp3"
            if not out.exists():
                jobs.append((voice, text, out))
    if args.limit:
        jobs = jobs[: args.limit]
    chars = sum(len(t) for _, t, _ in jobs)
    print(f"forge audio: 待合成 {len(jobs)} 段，约 {chars} 个字符")
    if args.dry_run or not jobs:
        return
    env = load_env()
    require(env, "ELEVENLABS_API_KEY")
    key = env["ELEVENLABS_API_KEY"]
    left = credits_left(key)
    print(f"ElevenLabs 剩余额度 {left}，低于 {args.floor} 停止")
    if left - chars < args.floor:
        raise SystemExit("额度不够合成全部，先用 --limit 分批，或调低 --floor")
    run_pool(jobs, lambda j: synth(key, VOICES[j[0]], j[1], j[2]), args.workers, label=lambda j: j[2].name)


# ---------- 公共 ----------

def run_pool(jobs, fn, workers, label):
    ok = fail = 0
    lock = threading.Lock()
    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(fn, j): j for j in jobs}
        for f in cf.as_completed(futures):
            try:
                f.result()
                with lock:
                    ok += 1
            except Exception as e:
                with lock:
                    fail += 1
                print(f"失败 {label(futures[f])}: {str(e)[:200]}", flush=True)
            if (ok + fail) % 20 == 0:
                print(f"进度 {ok + fail}/{len(jobs)} 失败 {fail}", flush=True)
    print(f"完成 成功 {ok} 失败 {fail}")


def media_bits(aid):
    """与词光一致的媒体位：1 插画、2 英音、4 美音、8 例句朗读。"""
    bits = 0
    for bit, path in ((1, f"img/{aid}.webp"), (2, f"audio/uk/{aid}.mp3"), (4, f"audio/us/{aid}.mp3"),
                      (8, f"audio/ex/{aid}.mp3")):
        if (MEDIA_DIR / path).exists():
            bits |= bit
    return bits


def load_by_id():
    """enrich 用：wordId -> 生成的词条（带媒体位）。"""
    if not TEXT_DIR.exists():
        return {}
    return {e["id"]: {**e, "m": media_bits(e["aid"])} for e in generated().values()}


def main(argv):
    ap = argparse.ArgumentParser(prog="run.py forge")
    ap.add_argument("what", choices=["text", "images", "audio"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--floor", type=int, default=30000, help="ElevenLabs 剩余额度下限")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    {"text": run_text, "images": run_images, "audio": run_audio}[args.what](args)

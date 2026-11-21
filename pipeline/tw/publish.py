"""07 发布：把要上云存储的文件整理到 out/publish/，布局和云上一致，小程序按这个布局拼地址。

  out/publish/data/catalog.json、data/books/<id>.json、data/books/<id>.dict.json、data/dict/<n>.json
  out/publish/media/img/<aid>.webp、media/thumb/<aid>.webp、media/audio/{uk,us,ex}/<aid>.mp3
  out/publish/manifest.json  每个文件的大小和 sha1：重新发布时只上传变化的（见 changed()）

媒体只放课本里用得到的：词光的（vendor/word-atlas/media，run.py vendor --media）和生成的（out/forge/media）。
文件用硬链接，不重复占磁盘。上传用 CloudBase CLI，见 README。
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

from .dicts import VENDOR
from .forge import MEDIA_DIR as FORGE_MEDIA
from .paths import BUILD_DIR, OUT

PUBLISH = OUT / "publish"
ATLAS_MEDIA = VENDOR / "word-atlas" / "media"
MEDIA_FILES = (("img", "webp"), ("thumb", "webp"), ("audio/uk", "mp3"), ("audio/us", "mp3"), ("audio/ex", "mp3"))


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)  # 跨磁盘时退回复制


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def media_aids():
    """打包好的词条里用到的媒体：aid -> 媒体位。"""
    entries = json.loads((OUT / "enriched.json").read_text(encoding="utf-8"))
    out = {}
    for e in entries.values():
        if e.get("aid") and e.get("m"):
            out[e["aid"]] = out.get(e["aid"], 0) | e["m"]
    return out


def main():
    if PUBLISH.exists():
        shutil.rmtree(PUBLISH)
    for f in BUILD_DIR.rglob("*.json"):
        link(f, PUBLISH / "data" / f.relative_to(BUILD_DIR))
    missing = []
    for aid, bits in media_aids().items():
        for folder, ext in MEDIA_FILES:
            bit = {"img": 1, "thumb": 1, "audio/uk": 2, "audio/us": 4, "audio/ex": 8}[folder]
            if not bits & bit:
                continue
            rel = f"{folder}/{aid}.{ext}"
            src = next((p for p in (ATLAS_MEDIA / rel, FORGE_MEDIA / rel) if p.exists()), None)
            if src:
                link(src, PUBLISH / "media" / rel)
            else:
                missing.append(rel)
    files = sorted(p for p in PUBLISH.rglob("*") if p.is_file())
    manifest = {str(p.relative_to(PUBLISH)): {"size": p.stat().st_size, "sha1": sha1(p)} for p in files}
    (PUBLISH / "manifest.json").write_text(json.dumps(manifest, indent=0), encoding="utf-8")
    total = sum(v["size"] for v in manifest.values())
    data = sum(v["size"] for k, v in manifest.items() if k.startswith("data/"))
    print(f"publish: {len(manifest)} 个文件，{total / 1e6:.0f} MB（数据 {data / 1e6:.0f} MB）-> {PUBLISH}")
    if missing:
        print(f"publish: 缺 {len(missing)} 个媒体文件（词条标了有、本地没有），例如 {missing[:3]}")
    return manifest


def changed(old_manifest: Path, new_manifest: Path = PUBLISH / "manifest.json"):
    """和上一次发布的清单比，列出新增或变化的文件（只上传这些）。"""
    old = json.loads(old_manifest.read_text()) if old_manifest.exists() else {}
    new = json.loads(new_manifest.read_text())
    return sorted(k for k, v in new.items() if old.get(k, {}).get("sha1") != v["sha1"])


UPLOADED = OUT / "uploaded-manifest.json"  # 上一次成功上传的清单
STAGING = OUT / "upload-staging"
CLOUD_PREFIX = "wordrex"  # 云存储里的目录：wordrex/data/…、wordrex/media/…


def upload(env_id, dry_run=False):
    """把 out/publish/ 里新增或变化的文件传到云开发的云存储。
    用 CloudBase CLI，先登录一次：npx -p @cloudbase/cli@3 tcb login"""
    import subprocess

    todo = changed(UPLOADED)
    size = sum((PUBLISH / k).stat().st_size for k in todo)
    print(f"upload: {len(todo)} 个文件要上传，{size / 1e6:.0f} MB -> 环境 {env_id} 的 {CLOUD_PREFIX}/")
    if dry_run or not todo:
        return
    if STAGING.exists():
        shutil.rmtree(STAGING)
    for k in todo:
        link(PUBLISH / k, STAGING / k)
    subprocess.run(["npx", "-y", "-p", "@cloudbase/cli@3", "tcb", "storage", "upload", str(STAGING), CLOUD_PREFIX,
                    "-e", env_id, "--times", "3"], check=True)
    shutil.copy2(PUBLISH / "manifest.json", UPLOADED)  # 成功了才记下，失败重跑会重新上传
    shutil.rmtree(STAGING)
    print("upload: 完成")

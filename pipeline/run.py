"""管线入口：python run.py <step> [book_id ...]

steps: vendor [--media] | manifest | fetch | ocr | extract | normalize | qa | enrich | build | all
       forge text|images|audio [--limit N] [--dry-run]  生成词光没有的词条（见 tw/forge.py）
       publish  整理要上云存储的数据和媒体到 out/publish/
       upload --env <环境ID> [--dry-run]  把 out/publish/ 里变化的文件传到云存储
"""
import sys
import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")  # macOS 自带 Python 的 LibreSSL

from tw import build, enrich, extract, fetch, forge, manifest, normalize, ocr, publish, qa, vendor


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    step, ids = argv[0], argv[1:]
    if step == "vendor":
        vendor.main(refresh="--refresh" in ids, media="--media" in ids)
    elif step == "manifest":
        manifest.main(refresh="--refresh" in ids)
    elif step == "fetch":
        fetch.main(ids)
    elif step == "ocr":  # 扫描版的书（没有文字层）先识别，结果缓存起来
        ocr.main(ids)
    elif step == "extract":
        extract.main(ids)
    elif step == "normalize":
        normalize.main(ids)
    elif step == "qa":
        qa.main(ids)
    elif step == "enrich":
        enrich.main()
    elif step == "build":
        build.main()
    elif step == "forge":
        forge.main(ids)
    elif step == "publish":
        publish.main()
    elif step == "upload":
        if "--env" not in ids or ids.index("--env") + 1 >= len(ids):
            print("用法：python run.py upload --env <云开发环境ID> [--dry-run]")
            return 1
        publish.upload(ids[ids.index("--env") + 1], dry_run="--dry-run" in ids)
    elif step == "all":  # 已下载的书从提取跑到打包
        extract.main(ids)
        normalize.main(ids)
        qa.main(ids)
        enrich.main()
        build.main()
    else:
        print(f"未知步骤: {step}\n{__doc__}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

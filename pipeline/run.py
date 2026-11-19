"""管线入口：python run.py <step> [book_id ...]

steps: vendor | manifest | fetch | extract | normalize | qa | enrich | build | all
"""
import sys
import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")  # macOS 自带 Python 的 LibreSSL

from tw import build, enrich, extract, fetch, manifest, normalize, qa, vendor


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    step, ids = argv[0], argv[1:]
    if step == "vendor":
        vendor.main(refresh="--refresh" in ids)
    elif step == "manifest":
        manifest.main(refresh="--refresh" in ids)
    elif step == "fetch":
        fetch.main(ids)
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

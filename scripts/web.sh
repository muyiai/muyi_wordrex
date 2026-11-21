#!/bin/sh
# 在浏览器里预览小程序（weweb）：TypeScript 先编译成 JS，连同 wxml/wxss/json 一起放到 .weweb/src，再交给 weweb。
# 需要：npm install -g weweb-cli；另开一个终端 npm run dev:data 提供数据。
# 用法：npm run web            打开 http://localhost:3000
set -e
cd "$(dirname "$0")/.."
rm -rf .weweb
npx tsc -p tsconfig.web.json
(cd miniprogram && find . -type f ! -name '*.ts' -exec sh -c 'mkdir -p "../.weweb/src/$(dirname "$1")" && cp "$1" "../.weweb/src/$1"' _ {} \;)
exec weweb .weweb/src -d .weweb/dist -p "${PORT:-3000}" -n "$@"

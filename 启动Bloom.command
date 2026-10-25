#!/usr/bin/env bash
# 双击即可启动（Finder）；窗口会留着方便看日志提示
cd "$(dirname "$0")"
bash scripts/start-local.sh
echo
echo "可关闭本窗口；服务会继续在后台运行。"
echo "下次再双击：若已在跑会直接提示地址，不会重复拉起。"
read -r -p "按回车关闭…"

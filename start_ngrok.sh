#!/bin/bash
# 方案一：用 ngrok 讓外網連線時，用此腳本啟動機器人（會自動帶入 ngrok 網址）
# 使用前請先在「另一個終端機」執行：ngrok http 5001

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "-------------------------------------------"
echo "  分隊網頁外網連線（ngrok）啟動"
echo "-------------------------------------------"
echo ""
echo "請先確認在「另一個終端機」已執行："
echo "  ngrok http 5001"
echo ""
echo "並在 ngrok 畫面上看到類似："
echo "  Forwarding  https://xxxx.ngrok-free.app -> http://localhost:5001"
echo ""

# 嘗試從 ngrok 本機 API 自動取得網址（ngrok 啟動後會開 4040 port）
NGROK_URL=""
if command -v curl >/dev/null 2>&1; then
    NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for t in d.get('tunnels', []):
        u = t.get('public_url', '')
        if u.startswith('https://'):
            print(u.rstrip('/'))
            break
except Exception:
    pass
" 2>/dev/null)
fi

if [ -n "$NGROK_URL" ]; then
    echo "已自動偵測到 ngrok 網址：$NGROK_URL"
    echo ""
    read -p "直接使用此網址啟動？[Y/n] " use_auto
    if [ "$use_auto" = "n" ] || [ "$use_auto" = "N" ]; then
        NGROK_URL=""
    fi
fi

if [ -z "$NGROK_URL" ]; then
    echo "請貼上 ngrok 畫面上顯示的 https 開頭網址（例如 https://xxxx.ngrok-free.app）："
    read -r NGROK_URL
    NGROK_URL=$(echo "$NGROK_URL" | sed 's|/$||')
fi

if [ -z "$NGROK_URL" ]; then
    echo "未輸入網址，改用 localhost（僅本機可連）。"
    export GVG_WEB_PORT=5001
    unset GVG_WEB_BASE_URL
else
    export GVG_WEB_PORT=5001
    export GVG_WEB_BASE_URL="$NGROK_URL"
    echo ""
    echo "已設定 GVG_WEB_BASE_URL=$NGROK_URL"
    echo "之後 /team_manage 產生的連結將可從外網開啟。"
    echo ""
fi

echo "正在啟動機器人…"
echo "-------------------------------------------"
exec python3 G_bot.py

# 百業戰報名 Discord 機器人 — 啟動教學（macOS / Windows）

本教學說明如何在 **macOS** 與 **Windows** 上從零開始啟動此機器人（含報名表、分隊網頁功能）。**macOS** 請從「一、環境需求」開始；**Windows** 請直接跳到下方「Windows 啟動教學」區塊。

---

## 一、環境需求

| 項目 | 說明 |
|------|------|
| 作業系統 | macOS 10.15 (Catalina) 或更新 |
| Python | **3.10 或以上**（建議 3.11 / 3.12） |
| Discord 應用程式 | 已建立好的 Bot，並取得 Token |

### 檢查是否已安裝 Python

在終端機（Terminal）執行：

```bash
python3 --version
```

若顯示 `Python 3.10.x` 或更高即可。若沒有或版本過舊，請看下一節安裝。

---

## 二、安裝 Python（若尚未安裝）

### 方法 A：使用 Homebrew（推薦）

1. 若尚未安裝 Homebrew，先安裝：
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
2. 安裝 Python：
   ```bash
   brew install python@3.12
   ```
3. 確認：
   ```bash
   python3 --version
   ```

### 方法 B：從官網安裝

1. 前往 [Python 官網](https://www.python.org/downloads/)
2. 下載 macOS 安裝檔（3.10 或以上）
3. 執行安裝程式，完成後在終端機用 `python3 --version` 確認

---

## 三、取得專案並進入目錄

假設專案放在目錄 `GvG`，在終端機執行：

```bash
cd /path/to/GvG
```

例如放在桌面下的 `GvG` 資料夾：

```bash
cd ~/Desktop/GvG
```

或你實際存放的路徑。確認目錄內有這些檔案：

- `G_bot.py` — 機器人主程式
- `requirements.txt` — Python 依賴列表
- `web/` 資料夾，內有 `index.html` — 分隊管理網頁

---

## 四、建立虛擬環境（建議）

使用虛擬環境可避免與系統其他 Python 專案衝突。

```bash
# 在 GvG 目錄下建立虛擬環境
python3 -m venv venv

# 啟動虛擬環境
source venv/bin/activate
```

啟動成功後，終端機前面會出現 `(venv)`。之後所有 `pip`、`python` 指令都在此環境內執行。

（若要離開虛擬環境，輸入 `deactivate`。）

---

## 五、安裝依賴

在**已啟動虛擬環境**的同一終端機執行：

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

（若你的環境有 `pip3` 指令，也可用 `pip3 install -r requirements.txt`。）

會安裝：

- `discord.py` — Discord 機器人
- `openpyxl` — Excel 匯出
- `flask` — 分隊管理網頁後端

若沒有錯誤，即表示安裝完成。

---

## 六、設定機器人

### 1. Discord Bot Token

1. 開啟 [Discord 開發者入口](https://discord.com/developers/applications)
2. 選擇你的應用程式（或新建一個）→ **Bot** → **Reset Token** 取得 Token
3. 用**環境變數**提供 Token，任選一種方式：
   - **方式 A**：複製 `.env.example` 為 `.env`，在 `.env` 中填入 `DISCORD_BOT_TOKEN=你的Token`（`.env` 已在 .gitignore 中，不會被提交）。
   - **方式 B**：在終端機執行一次 `export DISCORD_BOT_TOKEN=你的Token` 再啟動機器人。**Windows 使用者**若用終端機設定環境變數：CMD 用 `set DISCORD_BOT_TOKEN=你的Token`，PowerShell 用 `$env:DISCORD_BOT_TOKEN="你的Token"`（皆僅當前視窗有效）。

⚠️ **切勿將 Token 寫入程式碼或上傳到公開地方（如 GitHub）。**

### 2. 管理員名單（可選）

只有名單內的 Discord 使用者能使用管理指令（建立/刪除報名表、列出報名、取得分隊連結）。

在 `G_bot.py` 中找到 `ADMIN_USER_IDS`，將佔位 ID 改為管理員的 Discord 使用者 ID（數字）：

```python
ADMIN_USER_IDS = {
    123456789012345678,   # 改成你的 Discord 使用者 ID
}
```

取得自己的 ID：Discord 設定 → 進階 → 開啟「開發者模式」後，在使用者頭像右鍵 → 「複製使用者 ID」。

### 3. 分隊網頁對外使用（可選）

- **只在本機或同一個 Wi‑Fi**：見下方「同區網」設定（Mac IP + `GVG_WEB_BASE_URL`）。
- **要讓不在同一個 Wi‑Fi / 局域網的電腦或手機連線**：請用 **方案一：ngrok**，見下方「七之一、外網連線（ngrok）」。

---

## 七、啟動機器人

在 **GvG 目錄**、且**已啟動虛擬環境**的終端機執行：

```bash
python3 G_bot.py
```

正常啟動時會看到類似：

```
已登入為：你的機器人名稱 (ID: ...)
已載入表單數量：X，報名資料表數量：X
分隊管理網頁已於 http://0.0.0.0:5000/team 啟動（僅管理員透過 /team_manage 取得連結後可存取）
已同步 X 個 slash 指令
```

- 機器人上線後，在 Discord 可看到 Bot 為「上線」狀態。
- 分隊網頁會在同一進程內於 **port 5001** 啟動（預設，可改），無需另外開一個終端機。

### 一鍵啟動（可選）

若想之後每次少打指令，可寫一個小腳本。在 GvG 目錄建立 `start.sh`：

```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 G_bot.py
```

然後賦予執行權限並執行：

```bash
chmod +x start.sh
./start.sh
```

---

## 七之一、外網連線（ngrok，方案一）

若要讓 **不在同一個 Wi‑Fi / 局域網** 的電腦或手機也能開分隊網頁（例如人在外面用手機、朋友在家用自己網路），可用 **ngrok** 把本機的 port 暴露到外網。

### 1. 安裝 ngrok（僅需做一次）

1. 到 [ngrok 官網](https://ngrok.com/) 註冊帳號（免費即可）。
2. 依官網說明安裝 ngrok（macOS 可用 Homebrew：`brew install ngrok`）。
3. 登入後在後台取得 **Authtoken**，在終端機執行一次：
   ```bash
   ngrok config add-authtoken 你的Authtoken
   ```

### 2. 每次要開「外網連線」時的步驟

需要 **兩個終端機視窗**（都在專案目錄、有開虛擬環境的話先 `source venv/bin/activate`）。

**終端機 A：先啟動機器人（本機 port）**

```bash
cd /path/to/GvG
source venv/bin/activate   # 有建 venv 才需要
export GVG_WEB_PORT=5001
python3 G_bot.py
```

看到「分隊管理網頁已於 http://0.0.0.0:5001/team 啟動」後，**不要關**，保持執行。

**終端機 B：啟動 ngrok**

開一個**新的**終端機視窗，執行：

```bash
ngrok http 5001
```

畫面上會出現類似：

```text
Forwarding   https://abcd-12-34-56-78.ngrok-free.app -> http://localhost:5001
```

把上方的 **`https://xxxx.ngrok-free.app`**（或 `https://xxxx.ngrok.io`）整段複製起來。

**回到終端機 A：改用 ngrok 網址再啟動**

1. 在終端機 A 按 `Ctrl + C` 停止機器人。
2. 設定 ngrok 網址並重新啟動（把下面的網址換成你複製的）：

```bash
export GVG_WEB_PORT=5001
export GVG_WEB_BASE_URL="https://abcd-12-34-56-78.ngrok-free.app"
python3 G_bot.py
```

3. **終端機 B 的 ngrok 請保持執行**，不要關閉。

之後在 Discord 用 `/team_manage` 取得的連結就會是 `https://xxxx.ngrok-free.app/team?form_id=...&token=...`，**任何網路下的裝置**都能開啟。

### 3. 一鍵腳本（可選）

專案內有 `start_ngrok.sh` 時，可先手動在**另一個終端機**執行 `ngrok http 5001`，再在專案目錄執行：

```bash
chmod +x start_ngrok.sh   # 僅第一次需要
./start_ngrok.sh
```

腳本會嘗試自動偵測 ngrok 網址；若沒有偵測到，會請你貼上 ngrok 畫面上的 `https://...` 網址，然後自動設定 `GVG_WEB_BASE_URL` 並啟動機器人。

### 注意

- 免費版 ngrok 每次重開，網址都會變，所以**每次重開 ngrok 後都要重新設定 `GVG_WEB_BASE_URL` 並重啟機器人**。
- 使用時 **ngrok 那個終端機要一直開著**，關掉就無法從外網連線。

---

## 八、使用流程簡述

1. **邀請 Bot 進伺服器**  
   Discord 開發者入口 → 你的應用程式 → OAuth2 → URL Generator，勾選 `bot` 與所需權限，用產生的連結邀請。

2. **建立報名表**  
   管理員在頻道執行：`/create_form`，輸入標題與說明。

3. **成員報名**  
   成員在該報名表訊息上按「開啟報名表單」填寫並送出。

4. **分隊**  
   管理員執行：`/team_manage form_id:1`（1 改成你的報名表 ID），取得私訊連結後在瀏覽器打開，即可在網頁上篩選成員、建立隊伍、拖放分隊。

5. **查看 / 匯出名單**  
   管理員可用 `/list_signup` 看報名或匯出 Excel。

---

## 九、常見問題（macOS）

### 1. 找不到 `python3` 或 `pip` / `pip command not found`

- macOS 上請改用 **`pip3`** 或 **`python3 -m pip`**，例如：
  ```bash
  python3 -m pip install -r requirements.txt
  ```
- 在虛擬環境內啟動後，`pip` 有時仍可能未在 PATH，同樣用 `python3 -m pip install ...` 即可。
- 若連 `python3` 都沒有，請回到「二、安裝 Python」先安裝 Python。
- 若用 Homebrew 安裝 Python，可再執行：`brew link python@3.12`（依你安裝的版本調整）。

### 2. `Permission denied` 或無法執行

- 腳本需有執行權限：`chmod +x start.sh`
- 若整個專案在「下載」或「桌面」且被 macOS 阻擋，可到 **系統設定 → 隱私權與安全性** 允許終端機或你的編輯器存取該資料夾。

### 3. 無法連上網站 / localhost 拒絕連線

- **請先確認終端機有出現**：「分隊管理網頁已於 http://0.0.0.0:5001/team 啟動」。若沒有這行，代表網頁伺服器沒啟動成功，請看下方 port 佔用說明。
- **若你是用手機或另一台電腦開連結**：連結裡的 `localhost` 是指「那台裝置自己」，不是跑機器人的 Mac。請在 Mac 上開連結，或把連結裡的 `localhost` 改成 **Mac 的區域 IP**（例如 `http://192.168.1.100:5001/team?…`）。查 Mac IP：系統設定 → 網路 → 你的連線（Wi‑Fi 或乙太網路）→ 詳細內容可看到 IP。
- **Port 已被佔用**：macOS Monterey 起 AirPlay 可能佔用 port。本專案預設已改為 **5001**。若 5001 仍被佔用，可設定環境變數再啟動：
  ```bash
  export GVG_WEB_PORT=5002
  python3 G_bot.py
  ```
  並用瀏覽器打開 `http://localhost:5002/team?form_id=…&token=…`（或用手機時改成 Mac 的 IP）。

### 4. 關閉終端機後機器人就斷線

終端機關掉會一併結束程式。若想長期運行：

- **本機背景執行**：  
  `nohup python3 G_bot.py > bot.log 2>&1 &`  
  日誌會寫入 `bot.log`。結束時用 `ps aux | grep G_bot` 找到 PID，再 `kill <PID>`。
- 或使用 **launchd**、**screen** / **tmux** 等方式常駐，可依需求再設定。

### 5. 分隊連結打不開或 403

- 連結有效期限約 **1 小時**，過期請在 Discord 重新執行 `/team_manage` 取得新連結。
- 若從別台電腦或手機開啟，需已設定 `GVG_WEB_BASE_URL` 並用 ngrok（或其它方式）讓 port 5000 對外可連。

### 6. 資料存在哪裡？

- 報名與表單：同目錄下的 `forms_meta.json`、`signup_data.json`
- 分隊結果：`team_assignments.json`
- 日誌：`admin_commands.log`

建議定期備份整個 GvG 目錄（或至少這幾個 json 檔）。

---

## Windows 啟動教學

以下為 **Windows** 專用步驟；使用流程、目錄結構與「資料存在哪裡」同前述，不再重複。

### 一、環境需求（Windows）

| 項目 | 說明 |
|------|------|
| 作業系統 | Windows 10 或 11 |
| Python | **3.10 或以上**（建議 3.11 / 3.12） |
| Discord 應用程式 | 已建立好的 Bot，並取得 Token |

**檢查是否已安裝 Python**：開啟 **命令提示字元（cmd）** 或 **PowerShell**，執行：

```cmd
py -3 --version
```

或

```cmd
python --version
```

若顯示 `Python 3.10.x` 或更高即可。若沒有或版本過舊，請看下一節安裝。

### 二、安裝 Python（若尚未安裝）

1. 前往 [Python 官網](https://www.python.org/downloads/)
2. 下載 **Windows** 安裝檔（3.10 或以上）
3. 執行安裝程式時，**務必勾選「Add Python to PATH」**，再完成安裝
4. 安裝完成後，重新開啟 cmd 或 PowerShell，用 `py -3 --version` 或 `python --version` 確認

（亦可從 Microsoft Store 搜尋「Python 3.12」安裝。）

### 三、取得專案並進入目錄

假設專案放在 `C:\Users\你的使用者名稱\Desktop\GvG`，在 cmd 或 PowerShell 執行：

```cmd
cd C:\Users\你的使用者名稱\Desktop\GvG
```

或你實際存放的路徑。確認目錄內有：`G_bot.py`、`requirements.txt`、`web/` 資料夾（內有 `index.html`）。

### 四、建立虛擬環境（建議）

在 **GvG 目錄**下執行：

```cmd
python -m venv venv
```

或（若上面失敗）用：

```cmd
py -3 -m venv venv
```

**啟動虛擬環境**：

```cmd
venv\Scripts\activate
```

啟動成功後，終端機前面會出現 `(venv)`。之後的 `pip`、`python` 指令都在此環境內執行。

（若要離開虛擬環境，輸入 `deactivate`。）

### 五、安裝依賴

在**已啟動虛擬環境**的同一視窗執行：

```cmd
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

若沒有錯誤即表示安裝完成。

### 六、設定機器人

Token 與管理員名單設定請見上方「六、設定機器人」；若用終端機設定環境變數，請用 **方式 B** 的 Windows 寫法（`set` 或 `$env:DISCORD_BOT_TOKEN="..."`）。並在 `G_bot.py` 中修改 `ADMIN_USER_IDS` 為實際管理員的 Discord 使用者 ID。

### 七、啟動機器人

在 **GvG 目錄**、且**已啟動虛擬環境**的視窗執行：

```cmd
python G_bot.py
```

或：

```cmd
py G_bot.py
```

正常啟動時會看到類似「已登入為：…」「分隊管理網頁已於 http://0.0.0.0:5001/team 啟動」等訊息。機器人上線後，分隊網頁會在同一進程內於 **port 5001** 啟動。

**一鍵啟動（可選）**：在 GvG 目錄建立 `start.bat`，內容如下：

```batch
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python G_bot.py
pause
```

之後雙擊 `start.bat` 即可啟動（`pause` 可讓視窗在結束時保留，方便看錯誤訊息）。

### 八、外網連線（ngrok，Windows）

若要讓不在同一個 Wi‑Fi 的裝置開啟分隊網頁，可用 ngrok。

1. **安裝 ngrok**：到 [ngrok 官網](https://ngrok.com/) 註冊並下載 Windows 版，解壓後將 `ngrok.exe` 放在可執行路徑，或記住路徑。在終端機執行一次：`ngrok config add-authtoken 你的Authtoken`。
2. **兩個視窗**：  
   - **視窗 A**：在 GvG 目錄、已啟動 venv 下先執行 `python G_bot.py`，看到「分隊管理網頁已於…5001…啟動」後按 `Ctrl+C` 停止。  
   - **視窗 B**：開啟**另一個** cmd 或 PowerShell，執行 `ngrok http 5001`，畫面上會出現 `Forwarding https://xxxx.ngrok-free.app -> http://localhost:5001`，把 `https://xxxx.ngrok-free.app` 複製起來。  
   - **回到視窗 A**：設定網址後再啟動。  
     - **CMD**：`set GVG_WEB_BASE_URL=https://xxxx.ngrok-free.app`（換成你的網址），再 `python G_bot.py`。  
     - **PowerShell**：`$env:GVG_WEB_BASE_URL="https://xxxx.ngrok-free.app"`，再 `python G_bot.py`。  
   - **視窗 B 的 ngrok 請保持執行**，不要關閉。

之後在 Discord 用 `/team_manage` 取得的連結就會是 ngrok 網址，任何裝置都能開啟。免費版 ngrok 每次重開網址會變，需重新設定 `GVG_WEB_BASE_URL` 並重啟機器人。

### 九、常見問題（Windows）

- **找不到 `python`**：確認安裝時有勾選「Add Python to PATH」，或改用 `py -3` 執行上述指令。
- **無法連上網站 / localhost 拒絕連線**：先確認終端機有出現「分隊管理網頁已於 http://0.0.0.0:5001/team 啟動」。若用手機或另一台電腦開連結，須把連結裡的 `localhost` 改成 **這台 Windows 電腦的區域 IP**（設定 → 網路與網際網路 → 內容可查 IP），或使用 ngrok 網址。
- **Port 已被佔用**：在啟動前設定 `set GVG_WEB_PORT=5002`（CMD）或 `$env:GVG_WEB_PORT=5002`（PowerShell），再執行 `python G_bot.py`，並用 `http://localhost:5002/...` 開連結。
- **分隊連結打不開或 403**：連結約 1 小時有效，過期請在 Discord 重新執行 `/team_manage` 取得新連結；從外網開啟時需已設定 `GVG_WEB_BASE_URL` 並保持 ngrok 運行。

---

## 十、目錄結構參考

```
GvG/
├── G_bot.py              # 主程式
├── requirements.txt     # 依賴
├── README.md            # 本教學
├── venv/                # 虛擬環境（自己建立）
├── forms_meta.json      # 執行後產生
├── signup_data.json
├── team_assignments.json
├── admin_commands.log
├── web/
│   └── index.html       # 分隊網頁
└── start.sh             # 可選啟動腳本
```

---

完成以上步驟後，在 macOS 或 Windows 上即可正常啟動機器人並使用報名與分隊功能。若遇到其他錯誤訊息，可把終端機完整輸出貼出來以便排查。

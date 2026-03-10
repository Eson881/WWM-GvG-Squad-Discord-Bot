import discord
from discord import app_commands
from discord.ext import commands
import io
from datetime import datetime
from openpyxl import Workbook
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
import uuid
from threading import Lock, Thread
from typing import Dict, Any, Optional, List
from discord.errors import NotFound
import logging
import sys

# ========= Logging 設定 =========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("admin_commands.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("g_bot")

# ========= ！！！重要 ！！！ =========
# Token 請用環境變數 DISCORD_BOT_TOKEN 設定，勿寫入程式碼或上傳到 GitHub
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

# ========= 自訂「機器人管理員」名單 =========
# 只有這些使用者 ID 才能使用管理指令（/create_form /delete_form /list_signup）
# 請替換成你的 Discord 使用者 ID（右鍵頭像 → 複製使用者 ID，需先開啟開發者模式）
ADMIN_USER_IDS = {
    123456789012345678,  # 請改成實際管理員的 ID
}


def is_bot_admin(user: discord.abc.User) -> bool:
    """判斷此使用者是否為本機器人的『管理員』。"""
    return user.id in ADMIN_USER_IDS


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== 檔案名稱 ==========
FORMS_META_FILE = "forms_meta.json"      # 各報名表資料
SIGNUP_DATA_FILE = "signup_data.json"    # 各表中的玩家資料
TEAM_ASSIGNMENTS_FILE = "team_assignments.json"  # 各表單分隊資料

# ========= 資料結構 =========
# forms_meta: {form_id: { form_id, title, description, creator_id, created_at, channel_id, message_id }}
forms_meta: Dict[int, Dict[str, Any]] = {}

# signup_data: {form_id: { user_id: { ... 報名資料 ... } } }
signup_data: Dict[int, Dict[int, Dict[str, Any]]] = {}

# team_assignments: {form_id: {"teams": [{ "id": str, "name": str, "member_ids": [user_id, ...] }, ...]}}
team_assignments: Dict[int, Dict[str, Any]] = {}
_team_assignments_lock = Lock()

# 分隊網頁登入用 token（token -> {form_id, expiry}），僅記憶體
_team_manage_tokens: Dict[str, Dict[str, Any]] = {}
TOKEN_EXPIRE_SECONDS = 3600  # 1 小時

# 網頁伺服器設定（分隊管理用）
# macOS 上 port 5000 常被 AirPlay 佔用，故預設改為 5001
WEB_PORT = int(os.environ.get("GVG_WEB_PORT", "5001"))
WEB_BASE_URL = os.environ.get("GVG_WEB_BASE_URL", f"http://localhost:{WEB_PORT}")


# ========= 檔案存取工具 =========

def load_json(filename: str) -> Any:
    if not os.path.exists(filename):
        return None
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(filename: str, data: Any) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_team_assignments():
    """載入分隊資料，key 轉成 int。"""
    global team_assignments
    raw = load_json(TEAM_ASSIGNMENTS_FILE)
    if not isinstance(raw, dict):
        team_assignments = {}
        return
    out: Dict[int, Dict[str, Any]] = {}
    for k, v in raw.items():
        try:
            form_id = int(k)
        except ValueError:
            continue
        if not isinstance(v, dict) or "teams" not in v:
            out[form_id] = {"teams": []}
            continue
        teams: List[Dict[str, Any]] = []
        for t in v.get("teams", []):
            if not isinstance(t, dict):
                continue
            mid = t.get("member_ids") or []
            member_ids = [int(x) for x in mid if isinstance(x, (int, str)) and str(x).isdigit()]
            cap = t.get("captain_id")
            captain_id: Optional[int] = int(cap) if cap is not None and str(cap).isdigit() else None
            raw_prefs = t.get("style_prefs") or {}
            style_prefs: Dict[str, str] = {}
            for k, v in raw_prefs.items():
                if v in ("main", "sub"):
                    style_prefs[str(k)] = v
            teams.append({
                "id": str(t.get("id", uuid.uuid4().hex)),
                "name": str(t.get("name", "未命名隊伍")),
                "member_ids": member_ids,
                "captain_id": captain_id,
                "style_prefs": style_prefs,
            })
        out[form_id] = {"teams": teams}
    team_assignments = out


def save_team_assignments():
    """寫入分隊資料到 JSON（字串 key）。"""
    with _team_assignments_lock:
        out = {}
        for form_id, data in team_assignments.items():
            out[str(form_id)] = {
                "teams": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "member_ids": t["member_ids"],
                        "captain_id": t.get("captain_id"),
                        "style_prefs": t.get("style_prefs") or {},
                    }
                    for t in data.get("teams", [])
                ]
            }
        save_json(TEAM_ASSIGNMENTS_FILE, out)


def load_all_data():
    global forms_meta, signup_data

    fm = load_json(FORMS_META_FILE)
    sd = load_json(SIGNUP_DATA_FILE)

    forms_meta = fm if isinstance(fm, dict) else {}
    signup_data = sd if isinstance(sd, dict) else {}

    # key 是字串時轉成 int
    forms_meta_int: Dict[int, Dict[str, Any]] = {}
    for k, v in forms_meta.items():
        try:
            forms_meta_int[int(k)] = v
        except ValueError:
            continue
    forms_meta = forms_meta_int

    signup_data_int: Dict[int, Dict[int, Dict[str, Any]]] = {}
    for form_k, user_map in signup_data.items():
        try:
            form_id_int = int(form_k)
        except ValueError:
            continue
        if not isinstance(user_map, dict):
            continue
        user_map_int: Dict[int, Dict[str, Any]] = {}
        for user_k, signup in user_map.items():
            try:
                user_id_int = int(user_k)
            except ValueError:
                continue
            user_map_int[user_id_int] = signup
        signup_data_int[form_id_int] = user_map_int

    signup_data = signup_data_int
    load_team_assignments()


def save_all_data():
    # 轉回字串 key 存 JSON
    forms_meta_out = {str(k): v for k, v in forms_meta.items()}
    signup_data_out = {}
    for form_id, user_map in signup_data.items():
        signup_data_out[str(form_id)] = {str(uid): d for uid, d in user_map.items()}

    save_json(FORMS_META_FILE, forms_meta_out)
    save_json(SIGNUP_DATA_FILE, signup_data_out)


# ========= 分隊管理網頁（Flask API + 靜態頁） =========

def _ensure_team_data(form_id: int):
    """確保該 form_id 在 team_assignments 中有結構。"""
    if form_id not in team_assignments:
        team_assignments[form_id] = {"teams": []}
    return team_assignments[form_id]


def run_web_server():
    """在背景線程中執行 Flask（僅供 bot 啟動時呼叫一次）。"""
    from flask import Flask, request, jsonify, send_from_directory, send_file

    def check_team_token(form_id: int) -> Optional[str]:
        token = request.args.get("token") or (request.headers.get("Authorization") or "").replace("Bearer ", "")
        if not token:
            return "缺少 token"
        info = _team_manage_tokens.get(token)
        if not info:
            return "無效或已過期的連結，請在 Discord 重新使用 /team_manage 取得連結"
        if time.time() > info.get("expiry", 0):
            return "連結已過期，請在 Discord 重新使用 /team_manage 取得連結"
        if info.get("form_id") != form_id:
            return "此連結不適用於此表單"
        return None

    app = Flask(__name__, static_folder="web", static_url_path="")

    @app.route("/team")
    def team_page():
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        if os.path.exists(os.path.join(web_dir, "index.html")):
            return send_file(os.path.join(web_dir, "index.html"))
        return "<p>請將 web/index.html 放在機器人目錄下。</p>", 404

    @app.route("/api/forms/<int:form_id>/signups")
    def api_form_signups(form_id: int):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        form_signups = signup_data.get(form_id, {})
        main_style = request.args.get("main_style", "").strip()
        sub_style = request.args.get("sub_style", "").strip()
        rank = request.args.get("rank", "").strip()
        search = request.args.get("search", "").strip().lower()
        result = []
        for uid, d in form_signups.items():
            if main_style and (d.get("main_style") or "").split("｜")[0] != main_style:
                continue
            if sub_style and (d.get("sub_style") or "").split("｜")[0] != sub_style:
                continue
            if rank and (d.get("rank") or "") != rank:
                continue
            if search:
                gn = (d.get("game_name") or "").lower()
                dn = (d.get("discord_name") or "").lower()
                if search not in gn and search not in dn:
                    continue
            result.append({
                "user_id": uid,
                "discord_name": d.get("discord_name", ""),
                "game_name": d.get("game_name") or d.get("game_id", ""),
                "main_style": d.get("main_style", ""),
                "sub_style": d.get("sub_style", ""),
                "rank": d.get("rank", ""),
            })
        return jsonify({"signups": result})

    @app.route("/api/forms/<int:form_id>/teams")
    def api_form_teams(form_id: int):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        _ensure_team_data(form_id)
        teams = team_assignments[form_id]["teams"]
        return jsonify({"teams": [{"id": t["id"], "name": t["name"], "member_ids": t["member_ids"], "captain_id": t.get("captain_id"), "style_prefs": t.get("style_prefs") or {}} for t in teams]})

    @app.route("/api/forms/<int:form_id>/teams", methods=["POST"])
    def api_form_teams_create(form_id: int):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        data = request.get_json() or {}
        name = (data.get("name") or "未命名隊伍").strip() or "未命名隊伍"
        _ensure_team_data(form_id)
        team_id = uuid.uuid4().hex
        team_assignments[form_id]["teams"].append({"id": team_id, "name": name, "member_ids": [], "captain_id": None, "style_prefs": {}})
        save_team_assignments()
        return jsonify({"id": team_id, "name": name, "member_ids": [], "captain_id": None, "style_prefs": {}})

    @app.route("/api/forms/<int:form_id>/teams/<team_id>", methods=["PATCH"])
    def api_form_team_update(form_id: int, team_id: str):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        _ensure_team_data(form_id)
        teams = team_assignments[form_id]["teams"]
        team = next((t for t in teams if t["id"] == team_id), None)
        if not team:
            return jsonify({"error": "找不到該隊伍"}), 404
        data = request.get_json() or {}
        if "name" in data and data["name"] is not None:
            team["name"] = str(data["name"]).strip() or team["name"]
        if "member_ids" in data and isinstance(data["member_ids"], list):
            team["member_ids"] = [int(x) for x in data["member_ids"] if isinstance(x, (int, str)) and str(x).isdigit()]
        if "captain_id" in data:
            cid = data["captain_id"]
            if cid is None:
                team["captain_id"] = None
            else:
                try:
                    cid = int(cid)
                    if cid in team.get("member_ids", []):
                        team["captain_id"] = cid
                    else:
                        team["captain_id"] = None
                except (TypeError, ValueError):
                    team["captain_id"] = None
        if "style_prefs" in data and isinstance(data["style_prefs"], dict):
            if "style_prefs" not in team:
                team["style_prefs"] = {}
            member_ids_set = set(team.get("member_ids", []))
            for k, v in data["style_prefs"].items():
                if v in ("main", "sub"):
                    try:
                        uid = int(k)
                        if uid in member_ids_set:
                            team["style_prefs"][str(k)] = v
                    except (TypeError, ValueError):
                        pass
        save_team_assignments()
        return jsonify({"id": team["id"], "name": team["name"], "member_ids": team["member_ids"], "captain_id": team.get("captain_id"), "style_prefs": team.get("style_prefs") or {}})

    @app.route("/api/forms/<int:form_id>/teams/<team_id>", methods=["DELETE"])
    def api_form_team_delete(form_id: int, team_id: str):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        _ensure_team_data(form_id)
        teams = team_assignments[form_id]["teams"]
        team_assignments[form_id]["teams"] = [t for t in teams if t["id"] != team_id]
        save_team_assignments()
        return jsonify({"ok": True})

    @app.route("/api/forms/<int:form_id>/teams/<team_id>/members", methods=["POST"])
    def api_form_team_add_member(form_id: int, team_id: str):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if user_id is None:
            return jsonify({"error": "缺少 user_id"}), 400
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({"error": "user_id 必須為數字"}), 400
        _ensure_team_data(form_id)
        teams = team_assignments[form_id]["teams"]
        team = next((t for t in teams if t["id"] == team_id), None)
        if not team:
            return jsonify({"error": "找不到該隊伍"}), 404
        if user_id not in team["member_ids"]:
            team["member_ids"].append(user_id)
        if "style_prefs" not in team:
            team["style_prefs"] = {}
        save_team_assignments()
        return jsonify({"id": team["id"], "name": team["name"], "member_ids": team["member_ids"], "captain_id": team.get("captain_id"), "style_prefs": team.get("style_prefs") or {}})

    @app.route("/api/forms/<int:form_id>/teams/<team_id>/members/<int:user_id>", methods=["DELETE"])
    def api_form_team_remove_member(form_id: int, team_id: str, user_id: int):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        _ensure_team_data(form_id)
        teams = team_assignments[form_id]["teams"]
        team = next((t for t in teams if t["id"] == team_id), None)
        if not team:
            return jsonify({"error": "找不到該隊伍"}), 404
        team["member_ids"] = [x for x in team["member_ids"] if x != user_id]
        if team.get("captain_id") == user_id:
            team["captain_id"] = None
        sp = team.get("style_prefs") or {}
        if str(user_id) in sp:
            del sp[str(user_id)]
        save_team_assignments()
        return jsonify({"id": team["id"], "name": team["name"], "member_ids": team["member_ids"], "captain_id": team.get("captain_id"), "style_prefs": team.get("style_prefs") or {}})

    @app.route("/api/forms/<int:form_id>/meta")
    def api_form_meta(form_id: int):
        err = check_team_token(form_id)
        if err:
            return jsonify({"error": err}), 403
        meta = forms_meta.get(form_id)
        if not meta:
            return jsonify({"error": "找不到該表單"}), 404
        return jsonify({"form_id": form_id, "title": meta.get("title", ""), "description": meta.get("description", "")})

    try:
        logger.info(f"分隊網頁即將監聽 port {WEB_PORT} …")
        app.run(host="0.0.0.0", port=WEB_PORT, use_reloader=False, threaded=True)
    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 48:
            logger.error(
                f"分隊網頁啟動失敗：port {WEB_PORT} 已被佔用（macOS 上常見為 AirPlay）。"
                f"請在終端機設定 GVG_WEB_PORT 換一個 port，例如：export GVG_WEB_PORT=5002 後重新啟動機器人。"
            )
        else:
            logger.error(f"分隊網頁伺服器錯誤: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"分隊網頁伺服器錯誤: {e}", exc_info=True)


def get_next_form_id() -> int:
    """
    取得下一個可用的表單 ID：
    從 1 開始，找第一個「目前沒被 forms_meta 使用」的整數。
    這樣刪掉表單後，其 ID 將來可以被重用。
    """
    used_ids = set(forms_meta.keys())
    new_id = 1
    while new_id in used_ids:
        new_id += 1
    return new_id


# ---------- 共用：解析顯示文字中的邪修詳細 ----------

def split_evil_detail(style_str: Optional[str]):
    """
    將 "邪修（需下方輸入詳細）｜邪修·xxx" 或一般流派文字解析成：
    (base_label, is_evil, evil_detail)
    """
    if not style_str:
        return None, False, None
    # 若有 "｜" 當作主流派與邪修詳細的分隔
    if "｜" in style_str:
        base, detail = style_str.split("｜", 1)
    else:
        base, detail = style_str, None

    is_evil = base.startswith("邪修")
    return base, is_evil, detail


# ---------- 統計相關函式 ----------

def compute_form_stats(form_id: int) -> tuple[int, Dict[str, int]]:
    """
    回傳指定表單的統計資訊：
    - total_count: 總報名人數
    - main_style_counts: {主流派名稱: 人數}，所有邪修合併成一種「邪修」
    """
    form_signups = signup_data.get(form_id, {})
    total_count = 0
    main_style_counts: Dict[str, int] = {}

    for _uid, d in form_signups.items():
        total_count += 1
        raw_main = d.get("main_style", "") or ""
        base_main, is_evil, _detail = split_evil_detail(raw_main)

        if is_evil:
            key = "邪修"
        else:
            key = base_main or "未填主流派"

        main_style_counts[key] = main_style_counts.get(key, 0) + 1

    return total_count, main_style_counts


async def update_form_main_message(form_id: int):
    """
    根據目前的報名資料，更新該表單主訊息（頻道裡那張『百業戰報名表 #X』的 Embed），
    在描述中加入統計資訊：總人數、各主流派人數（邪修合併）。
    若找不到訊息或更新失敗，靜默忽略（避免整體流程壞掉）。
    """
    meta = forms_meta.get(form_id)
    if not meta:
        return

    channel_id = meta.get("channel_id")
    message_id = meta.get("message_id")
    if not channel_id or not message_id:
        return

    channel = bot.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.TextChannel):
        try:
            channel = await bot.fetch_channel(channel_id)  # type: ignore
        except Exception:
            return

    try:
        msg = await channel.fetch_message(message_id)  # type: ignore
    except Exception:
        return

    # 重新計算統計
    total_count, main_style_counts = compute_form_stats(form_id)

    # 基本描述
    base_title = meta.get("title", "")
    base_description = meta.get("description", "")
    description = (
        f"{base_description}\n\n"
        f"表單 ID：`{form_id}`\n"
        "請點下方按鈕開啟個人報名表單。"
    )

    # 統計區文字
    stat_lines = [f"**目前總報名人數：** {total_count} 人"]
    if main_style_counts:
        stat_lines.append("**各主流派人數（邪修合併）：**")
        for style, cnt in sorted(main_style_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            stat_lines.append(f"- {style}：{cnt} 人")
    else:
        stat_lines.append("目前尚無任何報名。")

    description += "\n\n" + "\n".join(stat_lines)

    embed = discord.Embed(
        title=f"百業戰報名表 #{form_id} - {base_title}",
        description=description,
        color=discord.Color.green(),
    )

    # 建立者名稱無法直接從 meta 拿到，只能用 ID 或保持空白；
    # 這裡保留原本 created_at 為主。
    embed.set_footer(text=f"建立時間 (UTC)：{meta.get('created_at', '未知')}")

    try:
        await msg.edit(embed=embed)
    except Exception:
        return


# ---------- 選單選項 ----------

MAIN_STYLE_OPTIONS = [
    discord.SelectOption(label="鳴金·虹", description="(無名)"),
    discord.SelectOption(label="鳴金·影", description="(九九)"),
    discord.SelectOption(label="裂石·威", description="(陌刀+槍)"),
    discord.SelectOption(label="牽絲·玉", description="(扇+傘)"),
    discord.SelectOption(label="破竹·風", description="(雙刀+繩鏢)"),
    discord.SelectOption(label="牽絲·霖", description="(奶媽)"),
    discord.SelectOption(label="邪修（需下方輸入詳細）", description="選這個後請再輸入邪修詳細流派"),
]

SUB_STYLE_OPTIONS = [
    discord.SelectOption(label="不填", description="不設定副流派"),
    discord.SelectOption(label="鳴金·虹 (無名)"),
    discord.SelectOption(label="鳴金·影 (九九)"),
    discord.SelectOption(label="裂石·威 (陌刀+槍)"),
    discord.SelectOption(label="牽絲·玉 (扇+傘)"),
    discord.SelectOption(label="破竹·風 (雙刀+繩鏢)"),
    discord.SelectOption(label="牽絲·霖 (奶媽)"),
    discord.SelectOption(label="邪修（需下方輸入詳細）"),
]

RANK_OPTIONS = [
    discord.SelectOption(label="出鞘"),
    discord.SelectOption(label="杖劍"),
    discord.SelectOption(label="遊刃"),
    discord.SelectOption(label="開山"),
    discord.SelectOption(label="斷水"),
    discord.SelectOption(label="斬風"),
    discord.SelectOption(label="流雲"),
    discord.SelectOption(label="藏鋒"),
    discord.SelectOption(label="飛花"),
    discord.SelectOption(label="無我"),
]


# ---------- 報名表 View（每張報名表 + 每位玩家） ----------

class SignupView(discord.ui.View):
    def __init__(
        self,
        user: discord.User,
        form_id: int,
        timeout: float = 600,
        existing_data: Optional[Dict[str, Any]] = None,
    ):
        """
        existing_data: 若是編輯模式，傳入原本的資料（signup_data[form_id][user_id]）
        """
        super().__init__(timeout=timeout)
        self.user = user
        self.form_id = form_id

        # 初始狀態
        self.game_name: Optional[str] = None  # 原本是 game_id，改成「遊戲名稱」

        self.main_style: Optional[str] = None
        self.main_is_evil: bool = False
        self.main_evil_detail: Optional[str] = None

        self.sub_style: Optional[str] = None
        self.sub_is_evil: bool = False
        self.sub_evil_detail: Optional[str] = None

        self.rank: Optional[str] = None

        # 如果有舊資料，帶入（相容舊版的 game_id）
        if existing_data:
            self.game_name = existing_data.get("game_name") or existing_data.get("game_id")

            # 主流派
            base, is_evil, detail = split_evil_detail(existing_data.get("main_style"))
            self.main_style = base
            self.main_is_evil = is_evil
            self.main_evil_detail = detail

            # 副流派
            sub = existing_data.get("sub_style") or ""
            if sub == "":
                self.sub_style = ""
                self.sub_is_evil = False
                self.sub_evil_detail = None
            else:
                base, is_evil, detail = split_evil_detail(sub)
                self.sub_style = base
                self.sub_is_evil = is_evil
                self.sub_evil_detail = detail

            self.rank = existing_data.get("rank")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "這張報名表不是你的，請自己按報名 Embed 上的按鈕開啟表單。",
                ephemeral=True,
            )
            return False
        return True

    # --- 按鈕：設定遊戲名稱 ---

    @discord.ui.button(label="設定遊戲名稱", style=discord.ButtonStyle.primary, row=0)
    async def set_game_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        view_self: "SignupView" = self

        class GameNameModal(discord.ui.Modal, title="輸入或修改遊戲名稱"):
            game_name = discord.ui.TextInput(
                label="遊戲名稱",
                placeholder="請輸入你的遊戲名稱",
                max_length=32,
                default=view_self.game_name or None,
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                view_self.game_name = str(self.game_name)
                await view_self.update_status_message(modal_interaction, "✅ 已更新遊戲名稱")

        await interaction.response.send_modal(GameNameModal())

    # --- 按鈕：輸入主流派邪修詳細 ---

    @discord.ui.button(
        label="輸入主流派邪修詳細",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def set_main_evil_detail(self, interaction: discord.Interaction, button: discord.ui.Button):
        view_self: "SignupView" = self
        default_text = view_self.main_evil_detail or ""

        class EvilMainModal(discord.ui.Modal, title="主流派邪修詳細"):
            detail = discord.ui.TextInput(
                label="邪修詳細流派（主流派）",
                placeholder="例如：邪修·某某流派",
                max_length=50,
                default=default_text or None,
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                view_self.main_evil_detail = str(self.detail)
                await view_self.update_status_message(modal_interaction, "✅ 已更新主流派邪修詳細")

        await interaction.response.send_modal(EvilMainModal())

    # --- 按鈕：輸入副流派邪修詳細 ---

    @discord.ui.button(
        label="輸入副流派邪修詳細",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def set_sub_evil_detail(self, interaction: discord.Interaction, button: discord.ui.Button):
        view_self: "SignupView" = self
        default_text = view_self.sub_evil_detail or ""

        class EvilSubModal(discord.ui.Modal, title="副流派邪修詳細"):
            detail = discord.ui.TextInput(
                label="邪修詳細流派（副流派）",
                placeholder="例如：九劍+無名劍",
                max_length=50,
                default=default_text or None,
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                view_self.sub_evil_detail = str(self.detail)
                await view_self.update_status_message(modal_interaction, "✅ 已更新副流派邪修詳細")

        await interaction.response.send_modal(EvilSubModal())

    # --- 下拉：主流派 ---

    @discord.ui.select(
        placeholder="選擇你的主流派",
        min_values=1,
        max_values=1,
        options=MAIN_STYLE_OPTIONS,
        row=1,
    )
    async def select_main_style(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = select.values[0]
        self.main_style = value

        if value.startswith("邪修"):
            self.main_is_evil = True
        else:
            self.main_is_evil = False
            self.main_evil_detail = None

        await self.update_status_message(interaction, "✅ 已選擇主流派")

    # --- 下拉：副流派 ---

    @discord.ui.select(
        placeholder="選擇你的副流派（可選：不填）",
        min_values=1,
        max_values=1,
        options=SUB_STYLE_OPTIONS,
        row=2,
    )
    async def select_sub_style(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = select.values[0]

        if value == "不填":
            self.sub_style = ""
            self.sub_is_evil = False
            self.sub_evil_detail = None
        else:
            self.sub_style = value
            if value.startswith("邪修"):
                self.sub_is_evil = True
            else:
                self.sub_is_evil = False
                self.sub_evil_detail = None

        await self.update_status_message(interaction, "✅ 已選擇副流派")

    # --- 下拉：PVP 段位 ---

    @discord.ui.select(
        placeholder="選擇你的 PVP 段位",
        min_values=1,
        max_values=1,
        options=RANK_OPTIONS,
        row=3,
    )
    async def select_rank(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.rank = select.values[0]
        await self.update_status_message(interaction, "✅ 已選擇段位")

    # --- 按鈕：送出（新增 / 修改）---

    @discord.ui.button(label="送出", style=discord.ButtonStyle.success, row=4)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        missing = []
        if not self.game_name:
            missing.append("遊戲名稱")
        if not self.main_style:
            missing.append("主流派")
        if not self.rank:
            missing.append("PVP 段位")

        if self.main_is_evil and not self.main_evil_detail:
            missing.append("主流派邪修詳細")
        if self.sub_is_evil and not self.sub_evil_detail:
            missing.append("副流派邪修詳細")

        if missing:
            await interaction.response.send_message(
                f"請先填完必填欄位：{', '.join(missing)}",
                ephemeral=True,
            )
            return

        # 組合顯示文字
        main_display = self.main_style or ""
        if self.main_is_evil and self.main_evil_detail:
            main_display += f"｜{self.main_evil_detail}"

        if self.sub_style == "" or self.sub_style is None:
            sub_display = ""
        else:
            sub_display = self.sub_style
            if self.sub_is_evil and self.sub_evil_detail:
                sub_display += f"｜{self.sub_evil_detail}"

        user_id = interaction.user.id
        if self.form_id not in signup_data:
            signup_data[self.form_id] = {}

        signup_data[self.form_id][user_id] = {
            "form_id": self.form_id,
            "discord_id": user_id,
            "discord_name": str(interaction.user),
            "game_name": self.game_name,  # 這裡存遊戲名稱
            "main_style": main_display,
            "sub_style": sub_display,
            "rank": self.rank,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        }

        # 存檔
        save_all_data()

        embed = discord.Embed(
            title=f"✅ 百業戰報名資料已儲存（表單 #{self.form_id}）",
            color=discord.Color.green(),
        )
        embed.add_field(name="遊戲名稱", value=self.game_name, inline=False)
        embed.add_field(name="主流派", value=main_display, inline=False)
        embed.add_field(name="副流派", value=sub_display or "（未填）", inline=False)
        embed.add_field(name="PVP 段位", value=self.rank, inline=False)

        await interaction.response.send_message(
            content="目前你的報名資料為：",
            embed=embed,
            ephemeral=True,
        )

        # 關閉按鈕與選單（訊息可能已不存在，所以加 try/except）
        for child in self.children:
            child.disabled = True
        if interaction.message:
            try:
                await interaction.message.edit(view=self)
            except NotFound:
                pass

        # 更新主報名訊息上的統計資訊
        try:
            await update_form_main_message(self.form_id)
        except Exception:
            logger.warning(f"更新表單 #{self.form_id} 主訊息統計時發生錯誤（submit）", exc_info=True)

    # --- 狀態顯示 ---

    async def update_status_message(self, interaction: discord.Interaction, tip: Optional[str] = None):
        def fmt_evil(style: Optional[str], is_evil: bool, detail: Optional[str]):
            if not style:
                return "尚未選擇"
            if is_evil:
                if detail:
                    return f"{style}｜{detail}"
                return f"{style}｜（尚未填寫邪修詳細）"
            return style

        main_display = fmt_evil(self.main_style, self.main_is_evil, self.main_evil_detail)

        if self.sub_style == "" or self.sub_style is None:
            sub_display = "（未填）"
        else:
            sub_display = fmt_evil(self.sub_style, self.sub_is_evil, self.sub_evil_detail)

        desc_lines = [
            f"**報名表 ID：** {self.form_id}",
            f"**遊戲名稱：** {self.game_name or '尚未設定'}",
            f"**主流派：** {main_display}",
            f"**副流派：** {sub_display}",
            f"**PVP 段位：** {self.rank or '尚未選擇'}",
        ]

        embed = discord.Embed(
            title="百業戰報名表單 - 填寫中",
            description="\n".join(desc_lines),
            color=discord.Color.blurple(),
        )
        if tip:
            embed.set_footer(text=tip)

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ---------- 報名表入口按鈕（管理員開啟的 Embed 下面） ----------

class FormEntryView(discord.ui.View):
    def __init__(self, form_id: int, timeout: float = 0):
        # timeout=0 代表不會自動 timeout
        super().__init__(timeout=timeout)
        self.form_id = form_id

    @discord.ui.button(label="開啟報名表單", style=discord.ButtonStyle.success, row=0)
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        form_id = self.form_id

        if form_id not in forms_meta:
            await interaction.response.send_message(
                "這張報名表已被管理員刪除或不存在。",
                ephemeral=True,
            )
            return

        # 取得玩家在此表單的舊資料（若有）
        user_id = interaction.user.id
        existing_data = signup_data.get(form_id, {}).get(user_id)

        view = SignupView(interaction.user, form_id=form_id, existing_data=existing_data)

        # 初始 Embed
        if existing_data:
            title = f"百業戰報名表單 - 修改中（表單 #{form_id}）"
            desc = (
                f"你已在這張表單報名過，現在可以修改：\n"
                f"1. 若要改遊戲名稱，按「設定遊戲名稱」\n"
                f"2. 可重新選主 / 副流派（邪修同樣要補詳細）\n"
                f"3. 可重新選 PVP 段位\n"
                f"4. 按「送出」覆蓋原報名資料\n"
            )
        else:
            title = f"百業戰報名表單 - 新報名（表單 #{form_id}）"
            desc = (
                "第一次在這張表單報名，請依序：\n"
                "1. 按「設定遊戲名稱」輸入名稱\n"
                "2. 選擇主流派（若選邪修，記得按按鈕補上邪修詳細）\n"
                "3. 選擇副流派（可選不填；若選邪修，同樣要補詳細）\n"
                "4. 選擇 PVP 段位\n"
                "5. 按「送出」完成\n"
            )

        # 狀態 Embed
        def fmt_evil(style: Optional[str], is_evil: bool, detail: Optional[str]):
            if not style:
                return "尚未選擇"
            if is_evil:
                if detail:
                    return f"{style}｜{detail}"
                return f"{style}｜（尚未填寫邪修詳細）"
            return style

        main_display = fmt_evil(view.main_style, view.main_is_evil, view.main_evil_detail)
        if view.sub_style == "" or view.sub_style is None:
            sub_display = "（未填）"
        else:
            sub_display = fmt_evil(view.sub_style, view.sub_is_evil, view.sub_evil_detail)

        embed = discord.Embed(
            title=title,
            description=(
                desc
                + "\n"
                f"**報名表 ID：** {form_id}\n"
                f"**遊戲名稱：** {view.game_name or '尚未設定'}\n"
                f"**主流派：** {main_display}\n"
                f"**副流派：** {sub_display}\n"
                f"**PVP 段位：** {view.rank or '尚未選擇'}\n"
            ),
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="修改我的報名", style=discord.ButtonStyle.primary, row=1)
    async def edit_my_signup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """直接從按鈕進入「修改報名」畫面（等同 /edit_signup）。"""
        form_id = self.form_id

        if form_id not in forms_meta:
            await interaction.response.send_message(
                "這張報名表已被管理員刪除或不存在。",
                ephemeral=True,
            )
            return

        user_id = interaction.user.id
        data = signup_data.get(form_id, {}).get(user_id)

        if not data:
            await interaction.response.send_message(
                "你在這張報名表中還沒有報名過，請先按上方「開啟報名表單」進行報名。",
                ephemeral=True,
            )
            return

        view = SignupView(interaction.user, form_id=form_id, existing_data=data)

        embed = discord.Embed(
            title=f"百業戰報名表單 - 修改中（表單 #{form_id}）",
            color=discord.Color.orange(),
        )
        game_name = data.get("game_name") or data.get("game_id", "未知")
        embed.add_field(name="遊戲名稱", value=game_name, inline=False)
        embed.add_field(name="主流派", value=data.get("main_style", "未知"), inline=False)
        embed.add_field(name="副流派", value=data.get("sub_style", "（未填）") or "（未填）", inline=False)
        embed.add_field(name="PVP 段位", value=data.get("rank", "未知"), inline=False)
        embed.set_footer(text=f"目前資料時間（UTC）：{data.get('timestamp', '未知')}")

        await interaction.response.send_message(
            content=(
                "你已經在這張報名表報名過，現在可以修改：\n"
                "1. 若要改遊戲名稱，按「設定遊戲名稱」\n"
                "2. 可重新選主 / 副流派（邪修同樣要補詳細）\n"
                "3. 可重新選 PVP 段位\n"
                "4. 按「送出」覆蓋原報名資料"
            ),
            embed=embed,
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="取消我的報名", style=discord.ButtonStyle.danger, row=1)
    async def cancel_my_signup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """直接從按鈕刪除自己的報名（等同 /delete_signup）。"""
        form_id = self.form_id

        if form_id not in forms_meta:
            await interaction.response.send_message(
                "這張報名表已被管理員刪除或不存在。",
                ephemeral=True,
            )
            return

        user_id = interaction.user.id
        if form_id not in signup_data or user_id not in signup_data[form_id]:
            await interaction.response.send_message(
                "你在這張報名表中目前沒有任何報名資料可以刪除。",
                ephemeral=True,
            )
            return

        del signup_data[form_id][user_id]
        save_all_data()

        await interaction.response.send_message(
            f"✅ 已刪除你在百業戰報名表 #{form_id} 中的報名資料。",
            ephemeral=True,
        )

        # 更新主報名訊息上的統計資訊
        try:
            await update_form_main_message(form_id)
        except Exception:
            logger.warning(f"更新表單 #{form_id} 主訊息統計時發生錯誤（按鈕取消報名）", exc_info=True)


# ---------- 報名名單分頁 View（/list_signup 文字模式） ----------

class SignupListView(discord.ui.View):
    def __init__(self, pages: list[str], form_id: int, user: discord.User, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.form_id = form_id
        self.user = user
        self.current_page = 0

        # 初始化按鈕狀態
        self.update_button_states()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # 只允許當初請求的人操作這個分頁
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "這份名單只提供給發出指令的管理員檢視。",
                ephemeral=True,
            )
            return False
        return True

    def update_button_states(self):
        # 根據目前頁數，啟用/停用上一頁/下一頁
        total_pages = len(self.pages)
        prev_button: discord.ui.Button = self.children[0]  # 上一頁
        next_button: discord.ui.Button = self.children[1]  # 下一頁

        prev_button.disabled = self.current_page <= 0
        next_button.disabled = self.current_page >= total_pages - 1

    def get_page_content(self) -> str:
        total_pages = len(self.pages)
        header = f"百業戰報名表 #{self.form_id} 目前所有報名（第 {self.current_page + 1} / {total_pages} 頁）：\n"
        return header + self.pages[self.current_page]

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_button_states()
        await interaction.response.edit_message(content=self.get_page_content(), view=self)

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_button_states()
        await interaction.response.edit_message(content=self.get_page_content(), view=self)

    @discord.ui.button(label="關閉", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        closed_text = self.get_page_content() + "\n\n（此分頁檢視已關閉）"
        await interaction.response.edit_message(content=closed_text, view=self)
        self.stop()


# ---------- Bot 事件 ----------

def _web_thread_started():
    """僅在第一次 on_ready 時啟動網頁線程。"""
    if getattr(_web_thread_started, "_started", False):
        return
    _web_thread_started._started = True
    t = Thread(target=run_web_server, daemon=True)
    t.start()
    logger.info(f"分隊管理網頁已於 http://0.0.0.0:{WEB_PORT}/team 啟動（僅管理員透過 /team_manage 取得連結後可存取）")


@bot.event
async def on_ready():
    load_all_data()
    logger.info(f"已登入為：{bot.user} (ID: {bot.user.id})")
    logger.info(f"已載入表單數量：{len(forms_meta)}，報名資料表數量：{len(signup_data)}")
    _web_thread_started()
    try:
        synced = await bot.tree.sync()
        logger.info(f"已同步 {len(synced)} 個 slash 指令")
    except Exception as e:
        logger.error(f"同步指令錯誤：{e}", exc_info=True)


# ---------- 「統一指令 log」Listener ----------

@bot.listen("on_app_command_completion")
async def log_app_command_completion(interaction: discord.Interaction, command: app_commands.Command):
    """所有 slash 指令成功執行後都會經過這裡，統一記錄。"""
    user = interaction.user
    params = {k: v for k, v in getattr(interaction, "namespace", {}).__dict__.items()} if getattr(interaction, "namespace", None) else {}
    logger.info(
        f"[CMD OK] {user} (ID: {user.id}) 在伺服器 {getattr(interaction.guild, 'id', 'DM')} "
        f"執行 /{command.qualified_name} 參數={params}"
    )


@bot.listen("on_app_command_error")
async def log_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """slash 指令出錯時也記錄。"""
    user = interaction.user
    command_name = interaction.command.qualified_name if getattr(interaction, "command", None) else "unknown"
    params = {k: v for k, v in getattr(interaction, "namespace", {}).__dict__.items()} if getattr(interaction, "namespace", None) else {}
    logger.error(
        f"[CMD ERR] {user} (ID: {user.id}) 在伺服器 {getattr(interaction.guild, 'id', 'DM')} "
        f"執行 /{command_name} 參數={params} 時出錯：{error}",
        exc_info=True,
    )

    try:
        await interaction.response.send_message(
            "執行指令時發生錯誤，已記錄在 log，請聯絡管理員。",
            ephemeral=True,
        )
    except discord.InteractionResponded:
        await interaction.followup.send(
            "執行指令時發生錯誤，已記錄在 log，請聯絡管理員。",
            ephemeral=True,
        )


# ---------- 指令區 ----------

# /create_form：建立一張新的百業戰報名表（管理用）
@bot.tree.command(name="create_form", description="（管理用）建立一張新的百業戰報名表")
@app_commands.describe(
    title="報名表標題（例如：1 月第 1 場百業戰）",
    description="報名說明（會顯示在 Embed 中）",
)
async def create_form(
    interaction: discord.Interaction,
    title: str,
    description: str,
):
    # 自訂管理員檢查
    if not is_bot_admin(interaction.user):
        await interaction.response.send_message(
            "你沒有使用此管理指令的權限。",
            ephemeral=True,
        )
        return

    form_id = get_next_form_id()

    forms_meta[form_id] = {
        "form_id": form_id,
        "title": title,
        "description": description,
        "creator_id": interaction.user.id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "channel_id": None,
        "message_id": None,
    }

    if form_id not in signup_data:
        signup_data[form_id] = {}

    save_all_data()

    # 初始統計：尚無報名
    total_count, main_style_counts = compute_form_stats(form_id)
    stat_lines = [f"**目前總報名人數：** {total_count} 人"]
    if main_style_counts:
        stat_lines.append("**各主流派人數（邪修合併）：**")
        for style, cnt in sorted(main_style_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            stat_lines.append(f"- {style}：{cnt} 人")
    else:
        stat_lines.append("目前尚無任何報名。")

    embed = discord.Embed(
        title=f"百業戰報名表 #{form_id} - {title}",
        description=(
            f"{description}\n\n"
            f"表單 ID：`{form_id}`\n"
            "請點下方按鈕開啟個人報名表單。\n\n"
            + "\n".join(stat_lines)
        ),
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"建立者：{interaction.user.display_name}｜建立時間 (UTC)：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    view = FormEntryView(form_id=form_id)

    # 先告訴管理員
    await interaction.response.send_message(
        content=f"已建立新的百業戰報名表（ID: {form_id}），並準備發佈在本頻道。",
        ephemeral=True,
    )

    # 再在頻道發一則給所有人看的訊息
    try:
        msg = await interaction.channel.send(embed=embed, view=view)  # type: ignore

        # 記錄主訊息位置
        forms_meta[form_id]["channel_id"] = msg.channel.id
        forms_meta[form_id]["message_id"] = msg.id
        save_all_data()
    except discord.Forbidden as e:
        logger.error(
            f"[CREATE_FORM] Bot 在頻道 {getattr(interaction.channel, 'id', 'unknown')} "
            f"沒有權限發送訊息或 embed：{e}"
        )
        await interaction.followup.send(
            "我在這個頻道沒有權限發送訊息或 Embed，請伺服器管理員檢查頻道權限。",
            ephemeral=True,
        )


# /delete_form：刪除整張報名表（含裡面所有報名資料）
@bot.tree.command(name="delete_form", description="（管理用）刪除一張百業戰報名表（連同所有報名資料）")
@app_commands.describe(form_id="要刪除的報名表 ID")
async def delete_form(interaction: discord.Interaction, form_id: int):
    if not is_bot_admin(interaction.user):
        await interaction.response.send_message(
            "你沒有使用此管理指令的權限。",
            ephemeral=True,
        )
        return

    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return

    # 刪除 meta 與該表的所有報名資料
    del forms_meta[form_id]
    if form_id in signup_data:
        del signup_data[form_id]

    save_all_data()

    await interaction.response.send_message(
        f"✅ 已刪除百業戰報名表 #{form_id} 及其所有報名資料。",
        ephemeral=True,
    )


# /edit_signup：編輯自己在某張表單的報名（保留後門）
@bot.tree.command(name="edit_signup", description="修改自己在指定百業戰報名表中的報名資料")
@app_commands.describe(form_id="報名表 ID")
async def edit_signup(interaction: discord.Interaction, form_id: int):
    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return

    user_id = interaction.user.id
    data = signup_data.get(form_id, {}).get(user_id)

    if not data:
        await interaction.response.send_message(
            "你在這張報名表中還沒有報名過，請先在該表的 Embed 上按按鈕進行報名。",
            ephemeral=True,
        )
        return

    view = SignupView(interaction.user, form_id=form_id, existing_data=data)

    embed = discord.Embed(
        title=f"百業戰報名表單 - 修改中（表單 #{form_id}）",
        color=discord.Color.orange(),
    )
    game_name = data.get("game_name") or data.get("game_id", "未知")
    embed.add_field(name="遊戲名稱", value=game_name, inline=False)
    embed.add_field(name="主流派", value=data.get("main_style", "未知"), inline=False)
    embed.add_field(name="副流派", value=data.get("sub_style", "（未填）") or "（未填）", inline=False)
    embed.add_field(name="PVP 段位", value=data.get("rank", "未知"), inline=False)
    embed.set_footer(text=f"目前資料時間（UTC）：{data.get('timestamp', '未知')}")

    await interaction.response.send_message(
        content=(
            "你已經在這張報名表報名過，現在可以修改：\n"
            "1. 若要改遊戲名稱，按「設定遊戲名稱」\n"
            "2. 可重新選主 / 副流派（邪修同樣要補詳細）\n"
            "3. 可重新選 PVP 段位\n"
            "4. 按「送出」覆蓋原報名資料"
        ),
        embed=embed,
        view=view,
        ephemeral=True,
    )


# /delete_signup：刪除自己在某張表單的報名（保留後門）
@bot.tree.command(name="delete_signup", description="刪除自己在指定百業戰報名表中的報名資料")
@app_commands.describe(form_id="報名表 ID")
async def delete_signup(interaction: discord.Interaction, form_id: int):
    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return

    user_id = interaction.user.id
    if form_id not in signup_data or user_id not in signup_data[form_id]:
        await interaction.response.send_message(
            "你在這張報名表中目前沒有任何報名資料可以刪除。",
            ephemeral=True,
        )
        return

    del signup_data[form_id][user_id]
    save_all_data()

    await interaction.response.send_message(
        f"✅ 已刪除你在百業戰報名表 #{form_id} 中的報名資料。",
        ephemeral=True,
    )

    # 更新主報名訊息上的統計資訊
    try:
        await update_form_main_message(form_id)
    except Exception:
        logger.warning(f"更新表單 #{form_id} 主訊息統計時發生錯誤（/delete_signup）", exc_info=True)


# /mysignup：看自己在某張表單的資料
@bot.tree.command(name="mysignup", description="查看自己在指定百業戰報名表中的報名資料")
@app_commands.describe(form_id="報名表 ID")
async def mysignup(interaction: discord.Interaction, form_id: int):
    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return

    user_id = interaction.user.id
    data = signup_data.get(form_id, {}).get(user_id)

    if not data:
        await interaction.response.send_message(
            "你在這張報名表中還沒有報名，請先在該表的 Embed 上按按鈕進行報名。",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"{interaction.user.display_name} 在百業戰報名表 #{form_id} 的資料",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Discord 帳號", value=data["discord_name"], inline=False)
    game_name = data.get("game_name") or data.get("game_id", "未填")
    embed.add_field(name="遊戲名稱", value=game_name, inline=False)
    embed.add_field(name="主流派", value=data["main_style"], inline=False)
    embed.add_field(name="副流派", value=data["sub_style"] or "（未填）", inline=False)
    embed.add_field(name="PVP 段位", value=data["rank"], inline=False)
    embed.set_footer(text=f"最後更新時間（UTC）：{data.get('timestamp', '未知')}")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# /list_signup：管理員列出某張表單所有報名，支援 Excel 匯出（文字模式為按鈕翻頁）
@bot.tree.command(name="team_manage", description="（管理用）取得分隊管理網頁連結，在網頁上可為該表單報名成員分隊")
@app_commands.describe(form_id="要分隊的報名表 ID")
async def team_manage(interaction: discord.Interaction, form_id: int):
    if not is_bot_admin(interaction.user):
        await interaction.response.send_message(
            "你沒有使用此管理指令的權限。",
            ephemeral=True,
        )
        return
    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return
    token = uuid.uuid4().hex
    _team_manage_tokens[token] = {"form_id": form_id, "expiry": time.time() + TOKEN_EXPIRE_SECONDS}
    link = f"{WEB_BASE_URL.rstrip('/')}/team?form_id={form_id}&token={token}"
    title = forms_meta[form_id].get("title", f"表單 #{form_id}")
    await interaction.response.send_message(
        f"**分隊管理連結（表單 #{form_id}：{title}）**\n"
        f"請在 **1 小時內** 使用以下連結於網頁上分隊（請勿分享給他人）：\n{link}",
        ephemeral=True,
    )


@bot.tree.command(name="list_signup", description="（管理用）列出指定百業戰報名表中的所有報名資料，支援 Excel 匯出")
@app_commands.describe(
    form_id="報名表 ID",
    format="輸出格式：text / excel",
)
@app_commands.choices(
    format=[
        app_commands.Choice(name="文字顯示", value="text"),
        app_commands.Choice(name="Excel 檔案", value="excel"),
    ]
)
async def list_signup(
    interaction: discord.Interaction,
    form_id: int,
    format: app_commands.Choice[str],
):
    if not is_bot_admin(interaction.user):
        await interaction.response.send_message(
            "你沒有使用此管理指令的權限。",
            ephemeral=True,
        )
        return

    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return

    form_signups = signup_data.get(form_id, {})
    if not form_signups:
        await interaction.response.send_message(
            f"百業戰報名表 #{form_id} 目前沒有任何報名資料。",
            ephemeral=True,
        )
        return

    # 文字模式：做成「多頁文字」+ 按鈕翻頁
    if format.value == "text":
        lines: list[str] = []
        for uid, d in form_signups.items():
            game_name = d.get("game_name") or d.get("game_id", "未填")
            line = (
                f"- <@{uid}> / 遊戲名稱: {game_name} / "
                f"主流派: {d.get('main_style', '未填')} / "
                f"副流派: {d.get('sub_style') or '無'} / "
                f"PVP 段位: {d.get('rank', '未填')}"
            )
            lines.append(line)

        # 把 lines 切成多頁，每頁內容長度 < 1900 左右，避免加 header 過 2000
        pages: list[str] = []
        current = ""
        max_len_per_page = 1900

        for line in lines:
            add_len = len(line) + (1 if current else 0)  # +1 是換行
            if len(current) + add_len > max_len_per_page:
                pages.append(current)
                current = line
            else:
                if current:
                    current += "\n" + line
                else:
                    current = line

        if current:
            pages.append(current)

        if not pages:
            pages = ["（目前沒有任何報名資料）"]

        view = SignupListView(pages=pages, form_id=form_id, user=interaction.user)
        await interaction.response.send_message(
            content=view.get_page_content(),
            view=view,
            ephemeral=True,
        )

    # Excel 模式
    elif format.value == "excel":
        wb = Workbook()
        ws = wb.active
        ws.title = f"表單#{form_id} 報名名單"

        headers = [
            "報名表 ID",
            "Discord ID",
            "Discord 名稱",
            "遊戲名稱",
            "主流派",
            "副流派",
            "PVP 段位",
            "最後更新時間 (UTC)",
        ]
        ws.append(headers)

        for uid, d in form_signups.items():
            game_name = d.get("game_name") or d.get("game_id", "")
            row = [
                form_id,
                d.get("discord_id", uid),
                d.get("discord_name", ""),
                game_name,
                d.get("main_style", ""),
                d.get("sub_style", ""),
                d.get("rank", ""),
                d.get("timestamp", ""),
            ]
            ws.append(row)

        file_stream = io.BytesIO()
        wb.save(file_stream)
        file_stream.seek(0)

        filename = f"百業戰報名名單_form{form_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file = discord.File(fp=file_stream, filename=filename)

        await interaction.response.send_message(
            content=f"這是百業戰報名表 #{form_id} 的 Excel 名單：",
            file=file,
            ephemeral=True,
        )


# /signup：保留一個後門，可直接指定 form_id 開啟表單
@bot.tree.command(name="signup", description="開啟指定百業戰報名表單（需提供表單 ID）")
@app_commands.describe(form_id="報名表 ID")
async def signup_cmd(interaction: discord.Interaction, form_id: int):
    if form_id not in forms_meta:
        await interaction.response.send_message(
            f"找不到 ID 為 {form_id} 的報名表。",
            ephemeral=True,
        )
        return

    user_id = interaction.user.id
    existing_data = signup_data.get(form_id, {}).get(user_id)
    view = SignupView(interaction.user, form_id=form_id, existing_data=existing_data)

    title = f"百業戰報名表單（表單 #{form_id}）"
    if existing_data:
        desc_prefix = "你已在這張表單報名過，現在可以修改：\n"
    else:
        desc_prefix = "第一次在這張表單報名，請依序操作：\n"

    embed = discord.Embed(
        title=title,
        description=(
            desc_prefix +
            "1. 按「設定遊戲名稱」輸入名稱\n"
            "2. 選擇主流派（若選邪修，記得按按鈕補上邪修詳細）\n"
            "3. 選擇副流派（可選不填；若選邪修，同樣要補詳細）\n"
            "4. 選擇 PVP 段位\n"
            "5. 按「送出」完成\n"
        ),
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ---------- 啟動 Bot ----------

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("未設定 DISCORD_BOT_TOKEN，請設定環境變數後再啟動（例如：export DISCORD_BOT_TOKEN=你的Token）")
        sys.exit(1)
    bot.run(BOT_TOKEN)
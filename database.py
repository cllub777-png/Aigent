"""
Database - JSON persistent storage
Handles warnings, stats, rules, broadcast chats/users
"""

import json, os, logging
from datetime import datetime
from threading import Lock
from typing import Optional, List

logger = logging.getLogger(__name__)
DB_FILE = "data/bot_db.json"

class Database:
    def __init__(self):
        self._lock = Lock()
        os.makedirs("data", exist_ok=True)
        self._d = self._load()

    def _load(self):
        try:
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"DB load error: {e}")
        return {"warnings": {}, "stats": {}, "rules": {},
                "events": [], "chats": [], "users": [], "filters": {}}

    def _save(self):
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self._d, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"DB save error: {e}")

    # ── Warnings ─────────────────────────────────────────────────
    def add_warning(self, chat_id: int, user_id: int) -> int:
        with self._lock:
            k = f"{chat_id}_{user_id}"
            self._d.setdefault("warnings", {})[k] = self._d["warnings"].get(k, 0) + 1
            count = self._d["warnings"][k]
            self._inc_stat(chat_id, "warnings")
            self._save()
            return count

    def get_warnings(self, chat_id: int, user_id: int) -> int:
        return self._d.get("warnings", {}).get(f"{chat_id}_{user_id}", 0)

    def reset_warnings(self, chat_id: int, user_id: int):
        with self._lock:
            self._d.setdefault("warnings", {})[f"{chat_id}_{user_id}"] = 0
            self._save()

    # ── Rules ─────────────────────────────────────────────────────
    def set_rules(self, chat_id: int, rules: str):
        with self._lock:
            self._d.setdefault("rules", {})[str(chat_id)] = rules
            self._save()

    def get_rules(self, chat_id: int) -> Optional[str]:
        return self._d.get("rules", {}).get(str(chat_id))

    # ── Stats ─────────────────────────────────────────────────────
    def _inc_stat(self, chat_id: int, key: str):
        s = self._d.setdefault("stats", {}).setdefault(str(chat_id), {})
        s[key] = s.get(key, 0) + 1

    def get_stats(self, chat_id: int) -> dict:
        return self._d.get("stats", {}).get(str(chat_id), {})

    # ── Events ────────────────────────────────────────────────────
    def log_event(self, etype: str, chat_id: int, user_id: int, data: dict = None):
        with self._lock:
            ev = self._d.setdefault("events", [])
            ev.append({
                "type": etype, "chat_id": chat_id,
                "user_id": user_id, "data": data or {},
                "ts": datetime.now().isoformat()
            })
            self._inc_stat(chat_id, etype)
            if len(ev) > 2000:
                self._d["events"] = ev[-2000:]
            self._save()

    # ── Broadcast: Chats ──────────────────────────────────────────
    def add_chat(self, chat_id: int):
        with self._lock:
            chats = self._d.setdefault("chats", [])
            if chat_id not in chats:
                chats.append(chat_id)
                self._save()

    def get_all_chats(self) -> List[int]:
        return list(self._d.get("chats", []))

    def remove_chat(self, chat_id: int):
        with self._lock:
            chats = self._d.get("chats", [])
            if chat_id in chats:
                chats.remove(chat_id)
                self._save()

    # ── Broadcast: Users ──────────────────────────────────────────
    def add_user(self, user_id: int):
        with self._lock:
            users = self._d.setdefault("users", [])
            if user_id not in users:
                users.append(user_id)
                self._save()

    def get_all_users(self) -> List[int]:
        return list(self._d.get("users", []))

    # ── Custom Filters ────────────────────────────────────────────
    def add_filter(self, chat_id: int, keyword: str, response: str):
        with self._lock:
            f = self._d.setdefault("filters", {}).setdefault(str(chat_id), {})
            f[keyword.lower()] = response
            self._save()

    def get_filters(self, chat_id: int) -> dict:
        return self._d.get("filters", {}).get(str(chat_id), {})

    def remove_filter(self, chat_id: int, keyword: str) -> bool:
        with self._lock:
            f = self._d.get("filters", {}).get(str(chat_id), {})
            if keyword.lower() in f:
                del f[keyword.lower()]
                self._save()
                return True
            return False

    # ── Blacklist ─────────────────────────────────────────────────
    def blacklist_add(self, chat_id: int, user_id: int, reason: str = ""):
        with self._lock:
            bl = self._d.setdefault("blacklist", {}).setdefault(str(chat_id), {})
            bl[str(user_id)] = {"reason": reason, "at": datetime.now().isoformat()}
            self._save()

    def is_blacklisted(self, chat_id: int, user_id: int) -> bool:
        return str(user_id) in self._d.get("blacklist", {}).get(str(chat_id), {})

db = Database()

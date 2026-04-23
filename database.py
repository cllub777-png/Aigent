"""
Database Module - JSON-based persistent storage
Handles warnings, bans, stats, and group settings.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)

DB_FILE = "data/bot_database.json"


class Database:
    def __init__(self):
        self._lock = Lock()
        self._ensure_dir()
        self._data = self._load()
    
    def _ensure_dir(self):
        os.makedirs("data", exist_ok=True)
    
    def _load(self) -> dict:
        try:
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"DB load error: {e}")
        return {
            "warnings": {},
            "stats": {},
            "rules": {},
            "events": []
        }
    
    def _save(self):
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"DB save error: {e}")
    
    # ── Warning System ────────────────────────────────────────────
    
    def add_warning(self, chat_id: int, user_id: int) -> int:
        """Add a warning and return total warning count."""
        with self._lock:
            key = f"{chat_id}_{user_id}"
            if "warnings" not in self._data:
                self._data["warnings"] = {}
            
            if key not in self._data["warnings"]:
                self._data["warnings"][key] = 0
            
            self._data["warnings"][key] += 1
            count = self._data["warnings"][key]
            
            # Update stats
            self._increment_stat(chat_id, "warnings")
            self._save()
            return count
    
    def get_warnings(self, chat_id: int, user_id: int) -> int:
        """Get warning count for a user."""
        key = f"{chat_id}_{user_id}"
        return self._data.get("warnings", {}).get(key, 0)
    
    def reset_warnings(self, chat_id: int, user_id: int):
        """Reset warnings for a user."""
        with self._lock:
            key = f"{chat_id}_{user_id}"
            if key in self._data.get("warnings", {}):
                self._data["warnings"][key] = 0
                self._save()
    
    # ── Rules System ──────────────────────────────────────────────
    
    def set_rules(self, chat_id: int, rules: str):
        """Set rules for a chat."""
        with self._lock:
            if "rules" not in self._data:
                self._data["rules"] = {}
            self._data["rules"][str(chat_id)] = rules
            self._save()
    
    def get_rules(self, chat_id: int) -> Optional[str]:
        """Get rules for a chat."""
        return self._data.get("rules", {}).get(str(chat_id))
    
    # ── Stats System ──────────────────────────────────────────────
    
    def _increment_stat(self, chat_id: int, stat: str):
        """Increment a stat counter (call within lock)."""
        if "stats" not in self._data:
            self._data["stats"] = {}
        
        chat_key = str(chat_id)
        if chat_key not in self._data["stats"]:
            self._data["stats"][chat_key] = {}
        
        current = self._data["stats"][chat_key].get(stat, 0)
        self._data["stats"][chat_key][stat] = current + 1
    
    def get_stats(self, chat_id: int) -> dict:
        """Get stats for a chat."""
        chat_key = str(chat_id)
        return self._data.get("stats", {}).get(chat_key, {})
    
    # ── Event Logging ─────────────────────────────────────────────
    
    def log_event(self, event_type: str, chat_id: int, user_id: int, data: dict = None):
        """Log a moderation event."""
        with self._lock:
            if "events" not in self._data:
                self._data["events"] = []
            
            event = {
                "type": event_type,
                "chat_id": chat_id,
                "user_id": user_id,
                "data": data or {},
                "timestamp": datetime.now().isoformat()
            }
            
            self._data["events"].append(event)
            
            # Map event types to stats
            stat_map = {
                "ban": "bans",
                "admin_ban": "bans",
                "mute": "mutes",
                "admin_mute": "mutes",
                "warning": "warnings",
                "member_join": "joins",
                "ai_answer": "ai_answers",
                "deletion": "deletions"
            }
            
            if event_type in stat_map:
                self._increment_stat(chat_id, stat_map[event_type])
            
            # Keep only last 1000 events to prevent file bloat
            if len(self._data["events"]) > 1000:
                self._data["events"] = self._data["events"][-1000:]
            
            self._save()
    
    def get_recent_events(self, chat_id: int, limit: int = 20) -> list:
        """Get recent events for a chat."""
        all_events = self._data.get("events", [])
        chat_events = [e for e in all_events if e["chat_id"] == chat_id]
        return chat_events[-limit:]
    
    # ── Blacklist System ──────────────────────────────────────────
    
    def add_to_blacklist(self, chat_id: int, user_id: int, reason: str = ""):
        """Add user to chat blacklist."""
        with self._lock:
            if "blacklist" not in self._data:
                self._data["blacklist"] = {}
            
            chat_key = str(chat_id)
            if chat_key not in self._data["blacklist"]:
                self._data["blacklist"][chat_key] = {}
            
            self._data["blacklist"][chat_key][str(user_id)] = {
                "reason": reason,
                "added_at": datetime.now().isoformat()
            }
            self._save()
    
    def is_blacklisted(self, chat_id: int, user_id: int) -> bool:
        """Check if user is blacklisted."""
        chat_key = str(chat_id)
        return str(user_id) in self._data.get("blacklist", {}).get(chat_key, {})
    
    # ── Custom Filter System ──────────────────────────────────────
    
    def add_filter(self, chat_id: int, keyword: str, response: str):
        """Add custom keyword filter."""
        with self._lock:
            if "filters" not in self._data:
                self._data["filters"] = {}
            
            chat_key = str(chat_id)
            if chat_key not in self._data["filters"]:
                self._data["filters"][chat_key] = {}
            
            self._data["filters"][chat_key][keyword.lower()] = response
            self._save()
    
    def get_filters(self, chat_id: int) -> dict:
        """Get all custom filters for a chat."""
        return self._data.get("filters", {}).get(str(chat_id), {})
    
    def remove_filter(self, chat_id: int, keyword: str) -> bool:
        """Remove a custom filter."""
        with self._lock:
            chat_key = str(chat_id)
            filters = self._data.get("filters", {}).get(chat_key, {})
            if keyword.lower() in filters:
                del filters[keyword.lower()]
                self._save()
                return True
            return False


# Global database instance
db = Database()

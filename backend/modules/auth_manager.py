import json
import uuid
import secrets
import hashlib
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
USERS_FILE = DATA_DIR / "users.json"
ACTIVE_SESSIONS: Dict[str, str] = {}  # token -> user_id

def hash_password(password: str, salt: str) -> str:
    """Computes PBKDF2-HMAC-SHA256 password hash."""
    return hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()

class AuthManager:
    """
    Manages user accounts, authentication sessions, and user-specific uploaded dataset registries.
    Persists user credentials and uploaded dataset associations to data/users.json.
    """
    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}  # user_id -> user dict
        self._ensure_storage()
        self._load()

    def _ensure_storage(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not USERS_FILE.exists():
                # Seed default initial user for immediate out-of-the-box convenience
                default_salt = secrets.token_hex(16)
                default_user_id = str(uuid.uuid4())
                initial_users = {
                    default_user_id: {
                        "id": default_user_id,
                        "username": "raj",
                        "display_name": "Raj",
                        "email": "raj@example.com",
                        "salt": default_salt,
                        "password_hash": hash_password("password123", default_salt),
                        "created_at": datetime.datetime.now().isoformat(),
                        "uploaded_tables": []
                    }
                }
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(initial_users, f, indent=2)
        except Exception as e:
            logger.error(f"Error initializing users storage: {e}")

    def _load(self):
        try:
            if USERS_FILE.exists():
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    self._users = json.load(f)
        except Exception as e:
            logger.error(f"Error loading users from {USERS_FILE}: {e}")

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._users, f, indent=2)
        except Exception as e:
            logger.error(f"Error persisting users to {USERS_FILE}: {e}")

    def register(
        self, 
        username: str, 
        password: str, 
        display_name: Optional[str] = None, 
        email: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Registers a new user account. Returns (user_dict, token, error_message).
        """
        clean_username = username.strip().lower()
        if not clean_username or len(clean_username) < 3:
            return None, None, "Username must be at least 3 characters."
        if not password or len(password) < 4:
            return None, None, "Password must be at least 4 characters."

        # Check for existing username
        for u in self._users.values():
            if u.get("username") == clean_username:
                return None, None, f"Username '{clean_username}' is already taken."

        salt = secrets.token_hex(16)
        user_id = str(uuid.uuid4())
        user_data = {
            "id": user_id,
            "username": clean_username,
            "display_name": (display_name or username).strip(),
            "email": (email or f"{clean_username}@example.com").strip(),
            "salt": salt,
            "password_hash": hash_password(password, salt),
            "created_at": datetime.datetime.now().isoformat(),
            "uploaded_tables": []
        }

        self._users[user_id] = user_data
        self._save()

        # Create session token
        token = secrets.token_hex(24)
        ACTIVE_SESSIONS[token] = user_id

        # Return clean user profile without salt/hash
        safe_user = self._get_safe_user(user_data)
        return safe_user, token, None

    def login(self, username: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Authenticates an existing user. Returns (user_dict, token, error_message).
        """
        clean_username = username.strip().lower()
        matched_user = None
        for u in self._users.values():
            if u.get("username") == clean_username:
                matched_user = u
                break

        if not matched_user:
            return None, None, "Invalid username or password."

        salt = matched_user.get("salt", "")
        expected_hash = hash_password(password, salt)
        if matched_user.get("password_hash") != expected_hash:
            return None, None, "Invalid username or password."

        token = secrets.token_hex(24)
        ACTIVE_SESSIONS[token] = matched_user["id"]

        safe_user = self._get_safe_user(matched_user)
        return safe_user, token, None

    def logout(self, token: str) -> bool:
        if token in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[token]
            return True
        return False

    def get_user_by_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        user_id = ACTIVE_SESSIONS.get(token)
        if not user_id:
            # Also check if token is directly a user_id
            if token in self._users:
                return self._get_safe_user(self._users[token])
            return None
        user_data = self._users.get(user_id)
        return self._get_safe_user(user_data) if user_data else None

    def get_user_by_id(self, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not user_id or user_id not in self._users:
            return None
        return self._get_safe_user(self._users[user_id])

    def record_uploaded_table(self, user_id: Optional[str], table_info: Dict[str, Any]) -> None:
        """
        Tags an ingested dataset/table to the given user account.
        """
        if not user_id or user_id not in self._users:
            # If guest or unauthenticated, find first user or store in default
            user_id = list(self._users.keys())[0] if self._users else None
            if not user_id:
                return

        user = self._users[user_id]
        if "uploaded_tables" not in user:
            user["uploaded_tables"] = []

        # Avoid duplicate table name entries
        t_name = table_info.get("table_name")
        user["uploaded_tables"] = [t for t in user["uploaded_tables"] if t.get("table_name") != t_name]
        user["uploaded_tables"].append(table_info)
        self._save()

    def get_user_uploaded_tables(self, user_id: Optional[str]) -> List[Dict[str, Any]]:
        if not user_id or user_id not in self._users:
            return []
        return self._users[user_id].get("uploaded_tables", [])

    def remove_uploaded_table(self, user_id: Optional[str], table_name: str) -> bool:
        if not user_id or user_id not in self._users:
            return False
        user = self._users[user_id]
        orig_count = len(user.get("uploaded_tables", []))
        user["uploaded_tables"] = [t for t in user.get("uploaded_tables", []) if t.get("table_name") != table_name]
        if len(user["uploaded_tables"]) != orig_count:
            self._save()
            return True
        return False

    def list_all_users(self) -> List[Dict[str, Any]]:
        return [self._get_safe_user(u) for u in self._users.values()]

    def get_allowed_tables_for_user(self, user: Optional[Dict[str, Any]], all_table_names: List[str]) -> List[str]:
        """
        Determines the accessible tables for a given user account.
        - Unauthenticated users: 0 tables.
        - Previous account 'raj': full demo/seed tables plus tables uploaded by Raj, 
          strictly excluding tables uploaded by other users.
        - Other accounts: strictly their own uploaded tables (starts empty for new accounts).
        """
        if not user:
            return []
        
        username = user.get("username")
        if username == "raj":
            other_tables = set()
            for u in self._users.values():
                if u.get("username") != "raj":
                    for t in u.get("uploaded_tables", []):
                        if t.get("table_name"):
                            other_tables.add(t.get("table_name").lower())
            return [t for t in all_table_names if t.lower() not in other_tables]

        user_tables = set(t.get("table_name", "").lower() for t in user.get("uploaded_tables", []))
        return [t for t in all_table_names if t.lower() in user_tables]

    def _get_safe_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        uploaded = user_data.get("uploaded_tables", [])
        return {
            "id": user_data.get("id"),
            "username": user_data.get("username"),
            "display_name": user_data.get("display_name"),
            "email": user_data.get("email"),
            "created_at": user_data.get("created_at"),
            "uploaded_tables": uploaded,
            "uploaded_tables_count": len(uploaded)
        }

auth_manager = AuthManager()

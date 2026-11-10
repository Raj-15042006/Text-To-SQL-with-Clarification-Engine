import os
import json
import uuid
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.modules.ambiguity import ClarificationRequest

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STORAGE_FILE = DATA_DIR / "conversations.json"

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user" or "assistant"
    content: str
    sql: Optional[str] = None
    sql_explanation: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    relationships: List[str] = Field(default_factory=list)
    thinking_steps: List[Dict[str, str]] = Field(default_factory=list)
    assumptions: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: List[Dict[str, str]] = Field(default_factory=list)
    confidence_score: Optional[int] = None
    confidence_level: Optional[str] = None
    confidence_reasons: List[str] = Field(default_factory=list)
    data_quality_warnings: List[str] = Field(default_factory=list)
    pii_warning: Optional[str] = None
    cost_info: Optional[Dict[str, Any]] = None
    ask_after_answer: Optional[Dict[str, Any]] = None
    status: str = "success"  # "success", "awaiting_clarification", "error", "schema_gap"
    clarification: Optional[ClarificationRequest] = None
    session_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    title: str = "New Chat"
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

class ConversationManager:
    def __init__(self):
        self._conversations: Dict[str, Conversation] = {}
        self._ensure_storage()
        self._load()

    def _ensure_storage(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not STORAGE_FILE.exists():
                with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                    json.dump({}, f)
        except Exception as e:
            logger.warning(f"Could not initialize conversation storage: {e}")

    def _load(self):
        try:
            if STORAGE_FILE.exists():
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for cid, cdata in data.items():
                        self._conversations[cid] = Conversation.model_validate(cdata)
        except Exception as e:
            logger.warning(f"Could not load conversations from {STORAGE_FILE}: {e}")

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {cid: conv.model_dump() for cid, conv in self._conversations.items()}
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Could not persist conversations to {STORAGE_FILE}: {e}")

    def create_conversation(self, title: Optional[str] = None, user_id: Optional[str] = None) -> Conversation:
        conv = Conversation(title=title or "New Chat", user_id=user_id)
        self._conversations[conv.id] = conv
        self._save()
        return conv

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        return self._conversations.get(conv_id)

    def list_conversations(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not user_id:
            # Unauthenticated requests receive no conversation history (strict tenancy protection)
            return []

        # Return strictly conversations owned by this user
        convs = [c for c in self._conversations.values() if c.user_id == user_id]
        sorted_convs = sorted(
            convs,
            key=lambda c: c.updated_at,
            reverse=True
        )
        return [
            {
                "id": c.id,
                "user_id": c.user_id,
                "title": c.title,
                "message_count": len(c.messages),
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "preview": c.messages[-1].content if c.messages else "No messages yet"
            }
            for c in sorted_convs
        ]

    def get_or_create(self, conv_id: Optional[str] = None, first_query: Optional[str] = None, user_id: Optional[str] = None) -> Conversation:
        if conv_id and conv_id in self._conversations:
            conv = self._conversations[conv_id]
            if user_id and not conv.user_id:
                conv.user_id = user_id
                self._save()
            return conv
        
        # Infer title from first query if available
        title = "New Chat"
        if first_query:
            clean = first_query.strip()
            title = (clean[:35] + "...") if len(clean) > 35 else clean
            
        conv = self.create_conversation(title=title, user_id=user_id)
        return conv

    def add_message(self, conv_id: str, message: ChatMessage) -> Conversation:
        conv = self._conversations.get(conv_id)
        if not conv:
            conv = self.create_conversation()
            conv.id = conv_id
            self._conversations[conv_id] = conv

        conv.messages.append(message)
        conv.updated_at = datetime.datetime.now().isoformat()
        
        # Auto-update title if it's the first user message and default title
        if len(conv.messages) == 1 and message.role == "user" and conv.title == "New Chat":
            clean = message.content.strip()
            conv.title = (clean[:38] + "...") if len(clean) > 38 else clean

        self._save()
        return conv

    def get_history_for_llm(self, conv_id: Optional[str]) -> List[Dict[str, Any]]:
        if not conv_id or conv_id not in self._conversations:
            return []
        conv = self._conversations[conv_id]
        history = []
        for m in conv.messages:
            if m.role == "user":
                history.append({"role": "user", "content": m.content})
            elif m.role == "assistant" and (m.content or m.sql):
                entry = {"role": "assistant", "content": m.content or ""}
                if m.sql:
                    entry["sql"] = m.sql
                if m.sql_explanation:
                    entry["sql_explanation"] = m.sql_explanation
                if m.rows:
                    entry["sample_rows"] = m.rows[:3]
                history.append(entry)
        return history

    def delete_conversation(self, conv_id: str) -> bool:
        if conv_id in self._conversations:
            del self._conversations[conv_id]
            self._save()
            return True
        return False

    def clear_all(self, user_id: Optional[str] = None):
        if user_id:
            to_del = [cid for cid, c in self._conversations.items() if c.user_id == user_id or c.user_id is None]
            for cid in to_del:
                self._conversations.pop(cid, None)
        else:
            self._conversations.clear()
        self._save()

conversation_manager = ConversationManager()

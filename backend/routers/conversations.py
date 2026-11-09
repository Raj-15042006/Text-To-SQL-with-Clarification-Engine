from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from backend.modules.conversation_manager import conversation_manager, Conversation, ChatMessage
from backend.modules.auth_manager import auth_manager

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Chat"

class UpdateTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)

def _get_user_id(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not isinstance(authorization, str):
        return None
    token = authorization.replace("Bearer ", "").strip()
    user = auth_manager.get_user_by_token(token)
    return user["id"] if user else None

@router.get("", response_model=List[Dict[str, Any]])
def list_conversations(authorization: Optional[str] = Header(None)):
    """Returns a list of saved chat conversations belonging to the active account."""
    user_id = _get_user_id(authorization)
    return conversation_manager.list_conversations(user_id=user_id)

@router.post("", response_model=Conversation)
def create_conversation(
    req: Optional[CreateConversationRequest] = None,
    authorization: Optional[str] = Header(None)
):
    """Creates a new empty chat conversation session bound to the active account."""
    user_id = _get_user_id(authorization)
    title = req.title if req and req.title else "New Chat"
    return conversation_manager.create_conversation(title=title, user_id=user_id)

@router.get("/{conv_id}", response_model=Conversation)
def get_conversation(conv_id: str):
    """Fetches full conversation message history and data state."""
    conv = conversation_manager.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv

@router.delete("/{conv_id}")
def delete_conversation(conv_id: str):
    """Deletes a saved conversation."""
    success = conversation_manager.delete_conversation(conv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "message": "Conversation deleted"}

@router.delete("")
def clear_all_conversations(authorization: Optional[str] = Header(None)):
    """Clears saved conversations for the active user account."""
    user_id = _get_user_id(authorization)
    conversation_manager.clear_all(user_id=user_id)
    return {"success": True, "message": "Conversations cleared for active account"}

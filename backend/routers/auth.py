from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field

from backend.modules.auth_manager import auth_manager

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4)
    display_name: Optional[str] = None
    email: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    user: Optional[Dict[str, Any]] = None
    token: Optional[str] = None
    message: Optional[str] = None

def get_current_user_from_header(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Helper to extract user profile from Authorization: Bearer <token>."""
    if not authorization or not isinstance(authorization, str):
        return None
    token = authorization.replace("Bearer ", "").strip()
    return auth_manager.get_user_by_token(token)

@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    """Registers a new user account and returns an auth session token."""
    user, token, err = auth_manager.register(
        username=req.username,
        password=req.password,
        display_name=req.display_name,
        email=req.email
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return AuthResponse(success=True, user=user, token=token, message="Registration successful")

@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Authenticates an existing user and returns an auth session token."""
    user, token, err = auth_manager.login(req.username, req.password)
    if err:
        raise HTTPException(status_code=401, detail=err)
    return AuthResponse(success=True, user=user, token=token, message="Login successful")

@router.get("/me")
def get_current_user(authorization: Optional[str] = Header(None)):
    """Returns the currently authenticated user profile and uploaded tables."""
    user = get_current_user_from_header(authorization)
    if not user:
        return {"authenticated": False, "user": None, "uploaded_tables": []}

    uploaded_tables = auth_manager.get_user_uploaded_tables(user["id"])
    return {
        "authenticated": True,
        "user": user,
        "uploaded_tables": uploaded_tables
    }

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    """Logs out the active session."""
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        auth_manager.logout(token)
    return {"success": True, "message": "Logged out successfully"}

@router.get("/users", response_model=List[Dict[str, Any]])
def list_available_users():
    """Returns list of existing user accounts for profile switching."""
    return auth_manager.list_all_users()

@router.get("/my-tables")
def get_my_uploaded_tables(authorization: Optional[str] = Header(None)):
    """Returns the tables uploaded by the currently authenticated user."""
    user = get_current_user_from_header(authorization)
    if not user:
        return []
    return auth_manager.get_user_uploaded_tables(user["id"])

import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env", override=True)

class Settings(BaseModel):
    # LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "local")
    LLM_THINKING_BUDGET: int = int(os.getenv("LLM_THINKING_BUDGET", "0"))

    # PostgreSQL Database Settings
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "postgres")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_READONLY_USER: str = os.getenv("DB_READONLY_USER", "postgres")
    DB_READONLY_PASSWORD: str = os.getenv("DB_READONLY_PASSWORD", "postgres")
    ACTIVE_DATA_SOURCE: str = os.getenv("ACTIVE_DATA_SOURCE", "sample")

    # App Settings
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    QUERY_TIMEOUT_SECONDS: int = 5
    MAX_ROW_LIMIT: int = 100

    def get_postgres_dsn(self, readonly: bool = True) -> str:
        user = self.DB_READONLY_USER if readonly else self.DB_USER
        password = self.DB_READONLY_PASSWORD if readonly else self.DB_PASSWORD
        return f"postgresql://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()

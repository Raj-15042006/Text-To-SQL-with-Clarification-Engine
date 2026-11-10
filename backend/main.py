import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.routers import query, schema, history, upload, conversations, auth, model, governance

app = FastAPI(
    title="Text-to-SQL with Clarification Engine",
    description="Ambiguity-aware natural language interface for PostgreSQL databases",
    version="1.0.0"
)

# CORS middleware for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router)
app.include_router(query.router)
app.include_router(schema.router)
app.include_router(history.router)
app.include_router(upload.router)
app.include_router(conversations.router)
app.include_router(model.router)
app.include_router(governance.router)

# Health & Info Endpoint
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.GEMINI_MODEL,
        "db_host": settings.DB_HOST,
        "db_port": settings.DB_PORT,
        "db_name": settings.DB_NAME
    }

# Frontend Static Files Serving
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_frontend_index():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Text-to-SQL Clarification API running. Frontend index.html not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)

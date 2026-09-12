import sys
from pathlib import Path

# Ensure the project root (parent of backend/) is on sys.path so fgt_upgrade is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers.jobs import router as jobs_router
from .routers.uploads import router as uploads_router
from .routers.reviews import router as reviews_router
from .routers.auth import router as auth_router
from .routers.support import router as support_router
from .routers.processing import router as processing_router

from contextlib import asynccontextmanager
from . import queue
from .security import RequestSecurity
from .settings import settings
from .build_info import VERSION

@asynccontextmanager
async def lifespan(app):
    queue.start()
    try:
        yield
    finally:
        queue.stop()

app = FastAPI(title="Release Note Review API", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(RequestSecurity)
from .api_docs import router as docs_router, configure_schema
app.include_router(docs_router)
configure_schema(app)

@app.get('/api/health')
def health():
    return {"status": "ok"}

app.include_router(jobs_router)
app.include_router(uploads_router)
app.include_router(reviews_router)
app.include_router(auth_router)
app.include_router(support_router)
app.include_router(processing_router)
from .routers.presentation import router as presentation_router
app.include_router(presentation_router)

# Serve built React frontend if present
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    # Serve hashed static assets (JS/CSS/images) directly — these have exact filenames
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    # Catch-all: any path not matched by /api/* or /assets/* returns index.html
    # so React Router handles client-side navigation (including hard refresh on /reports/*)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(404, "API route not found")
        return FileResponse(str(_frontend_dist / "index.html"))

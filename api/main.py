"""
Netlify Function handler — wraps FastAPI with Mangum.
Cold-start optimized: imports are lazy.
"""
import sys, os, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.chdir(str(HERE))

from mangum import Mangum
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Lightweight app with just health endpoints (instant)
app = FastAPI(title="Driver Dashboard", version="2.0.0")

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}

# Try to import the real app — errors are caught
_error = None
try:
    from app import app as real_app, setup_routes
    # Mount all routes from real app
    for r in real_app.routes:
        app.router.routes.append(r)
except Exception as e:
    _error = e
    tb = traceback.format_exc()
    
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def catch_all(request: Request, path: str):
        return JSONResponse(
            {"status": "error", "message": str(_error), "traceback": tb.split("\n")[-8:]},
            status_code=503
        )

handler = Mangum(app, lifespan="off")

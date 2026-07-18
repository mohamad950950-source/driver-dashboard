"""
Netlify Function handler — wraps FastAPI with Mangum.
"""
import sys
import os
from pathlib import Path

# Ensure the project root is on sys.path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.chdir(str(HERE))

# Lazy app import to avoid cold-start timeout
try:
    from app import app
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except Exception as e:
    import json, traceback
    # Fallback handler that returns the error
    from mangum import Mangum
    from fastapi import FastAPI
    app = FastAPI()
    
    @app.get("/api/health")
    def health():
        return {"status": "error", "version": "2.0.0", "detail": str(e)}
    
    @app.get("/{path:path}")
    def catch_all(path: str):
        return {"status": "error", "path": path, "detail": str(e), "traceback": traceback.format_exc()}
    
    handler = Mangum(app, lifespan="off")

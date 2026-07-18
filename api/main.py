"""
Super simple Netlify Function — no Mangum, no FastAPI.
Just a raw ASGI handler to diagnose the issue.
"""
import sys, os, json, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.chdir(str(HERE))

def handler(event, context):
    """Direct Netlify Function handler."""
    # First try: just a health check without any imports
    path = event.get("path", "/")
    method = event.get("httpMethod", "GET")
    
    if path == "/api/health" and method == "GET":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "ok", "version": "2.0.0", "stage": "pre-import"})
        }
    
    # Try importing the full app
    try:
        from mangum import Mangum
        from app import app
        mangum_handler = Mangum(app, lifespan="off")
        return mangum_handler(event, context)
    except Exception as e:
        tb = traceback.format_exc()
        # Return the error so we can see what went wrong
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "message": str(e),
                "traceback": tb.split("\n")[-10:],
                "path": path,
                "method": method
            })
        }

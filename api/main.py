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

# Import the FastAPI app
from app import app
from mangum import Mangum

# Create the Mangum handler for Netlify
handler = Mangum(app, lifespan="off")

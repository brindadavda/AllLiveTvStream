import sys
import os

# Add the 'backend' directory to the Python path
# This allows imports inside 'backend/main.py' (such as 'from app.config import settings') to resolve correctly
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.append(backend_path)

from backend.main import app

import sys
import os
import importlib.util

# This is the Vercel entry point at the repository root
# It loads the actual FastAPI app from aldlasforo/api/backend/main.py

# Get the repository root (where this file is in api/)
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to the actual application
_app_root = os.path.join(_repo_root, "aldlasforo")
_api_dir = os.path.join(_app_root, "api")
_backend_dir = os.path.join(_api_dir, "backend")
_main_path = os.path.join(_backend_dir, "main.py")

# Add necessary paths to sys.path
for _d in (_app_root, _api_dir, _backend_dir):
    if _d not in sys.path:
        sys.path.insert(0, _d)

# Load the main FastAPI application module
_spec = importlib.util.spec_from_file_location("backend.main", _main_path)
if _spec is None:
    raise ImportError(f"Cannot find backend/main.py at: {_main_path}")

_module = importlib.util.module_from_spec(_spec)
sys.modules["backend.main"] = _module
_spec.loader.exec_module(_module)

# Export the FastAPI app for Vercel
app = _module.app

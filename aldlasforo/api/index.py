import sys
import os
import importlib.util

# Absolute path to api/ (this file's directory) and to the project root
_api_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_api_dir)

# Add api/ and project root to sys.path so imports inside backend/main.py work
for _d in (_project_root, _api_dir):
    if _d not in sys.path:
        sys.path.insert(0, _d)

# Load backend/main.py by its absolute file path – immune to sys.path ordering
_main_path = os.path.join(_api_dir, "backend", "main.py")
_spec = importlib.util.spec_from_file_location("backend.main", _main_path)
if _spec is None:
    raise ImportError(f"Cannot find backend/main.py at: {_main_path}")
_module = importlib.util.module_from_spec(_spec)
sys.modules["backend.main"] = _module
_spec.loader.exec_module(_module)
app = _module.app
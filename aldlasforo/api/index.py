import sys
import os

# Add api/ directory so "from backend.main import app" resolves correctly
_api_dir = os.path.dirname(os.path.abspath(__file__))
# Add aldlasforo/ root directory for any other imports
_root_dir = os.path.dirname(_api_dir)

if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from backend.main import app
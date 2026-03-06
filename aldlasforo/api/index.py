import sys
import os

# Ensure the parent directory (aldlasforo/) is on sys.path so that
# "from backend.main import app" works whether Vercel deploys from the
# repository root or from the aldlasforo/ sub-directory.
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from backend.main import app
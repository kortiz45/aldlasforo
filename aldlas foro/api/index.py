import sys
import os

# When Vercel uses "aldlas foro" as the root directory, this file is at
# <repo>/aldlas foro/api/index.py
# The actual application lives in <repo>/aldlasforo/backend/main.py
# We add <repo>/aldlasforo to sys.path so that "from backend.main import app" works.
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_aldlasforo = os.path.join(_repo_root, "aldlasforo")
if _aldlasforo not in sys.path:
    sys.path.insert(0, _aldlasforo)

from backend.main import app

import os
import sys
import tempfile
from pathlib import Path

# Isolated temp database for tests (must be set before importing app modules)
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db  # noqa: E402

init_db()

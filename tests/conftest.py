import os
import sys
import tempfile
from pathlib import Path

os.environ["SMARTPARK_DATA"] = tempfile.mkdtemp(prefix="smartpark-test-")
os.environ["SMARTPARK_DISABLE_VISION"] = "1"
os.environ.pop("GEMINI_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

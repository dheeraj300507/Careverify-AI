"""
CareVerify - Application Entry Point
"""

import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import create_app

env = os.environ.get("FLASK_ENV", "development")
app = create_app(env)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # STEP 1 — LOCATE BACKEND SERVER
    print("Backend running on PORT:", port)
    app.run(host="0.0.0.0", port=port, debug=(env == "development"))

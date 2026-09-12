"""Start the Flask backend (avoids console quoting issues on Windows)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import app

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("FLASK_PORT", "5000"))

    # app.config["DEBUG"] is already gated to loopback-only in backend/app.py;
    # the reloader is only useful alongside the debugger.
    debug = bool(app.config.get("DEBUG"))

    print("\n" + "=" * 60)
    print("  Student Dropout Risk — Web Dashboard")
    print(f"  Open http://localhost:{port} in your browser")
    print(f"  Bind: {host}:{port}   debug: {debug}")
    print("=" * 60 + "\n")
    app.run(host=host, port=port, debug=debug, use_reloader=debug)
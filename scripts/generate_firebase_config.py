"""
Generate the browser Firebase web configuration.

Reads the public Firebase values from the environment (or `.env`) and writes
`frontend/js/firebase-config.js`, which is gitignored.

    .venv\\Scripts\\python.exe scripts\\generate_firebase_config.py

Why a generated file rather than VITE_* variables: the dashboard is a
no-build-step vanilla frontend served by Flask, so there is no bundler to
substitute `import.meta.env`. See the project plan for the trade-off.

IMPORTANT: these values are PUBLIC by design and are safe to ship to the
browser. `storageBucket` is deliberately omitted - Firebase Storage is NOT
used anywhere in this project. Never put service-account credentials or
private keys in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.env_loader import env, load_env  # noqa: E402

TARGET = PROJECT_ROOT / "frontend" / "js" / "firebase-config.js"

REQUIRED = (
    "FIREBASE_API_KEY",
    "FIREBASE_AUTH_DOMAIN",
    "FIREBASE_PROJECT_ID",
    "FIREBASE_APP_ID",
)

# Only these keys are ever written. No storageBucket, no measurementId.
FIELD_MAP = (
    ("apiKey", "FIREBASE_API_KEY"),
    ("authDomain", "FIREBASE_AUTH_DOMAIN"),
    ("projectId", "FIREBASE_PROJECT_ID"),
    ("appId", "FIREBASE_APP_ID"),
    ("messagingSenderId", "FIREBASE_MESSAGING_SENDER_ID"),
)

TEMPLATE = """/*
 * GENERATED FILE - DO NOT EDIT BY HAND, DO NOT COMMIT.
 * Regenerate with:  python scripts/generate_firebase_config.py
 *
 * The Firebase web configuration is public by design: it identifies the
 * project and is protected by Firestore security rules plus Firebase API-key
 * restrictions, not by secrecy.
 *
 * Firebase Storage is intentionally NOT configured.
 * Generated at: {generated_at}
 */
window.FIREBASE_CONFIG = {config};
"""


def build_config() -> dict:
    return {js_key: env(env_key) for js_key, env_key in FIELD_MAP}


def main() -> int:
    load_env()
    config = build_config()

    missing = [name for name in REQUIRED if not config.get(
        {
            "FIREBASE_API_KEY": "apiKey",
            "FIREBASE_AUTH_DOMAIN": "authDomain",
            "FIREBASE_PROJECT_ID": "projectId",
            "FIREBASE_APP_ID": "appId",
        }[name]
    )]

    if missing:
        print("Missing required environment variables:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nCopy .env.example to .env and fill in the Firebase web values, "
            "or export them in your shell.",
            file=sys.stderr,
        )
        return 1

    import datetime

    body = TEMPLATE.format(
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        config=json.dumps(config, indent=2),
    )
    TARGET.write_text(body, encoding="utf-8")

    # Report only the non-sensitive shape of what was written.
    print(f"Wrote {TARGET.relative_to(PROJECT_ROOT)}")
    print(f"  projectId: {config.get('projectId')}")
    print(f"  authDomain: {config.get('authDomain')}")
    print("  storageBucket: (not configured - Firebase Storage is not used)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

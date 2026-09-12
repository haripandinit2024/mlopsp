/*
 * EXAMPLE ONLY - the real `frontend/js/firebase-config.js` is gitignored.
 *
 * Generate it from your environment:
 *     python scripts/generate_firebase_config.py
 *
 * These values are public by design (they identify the Firebase project).
 * They are NOT secrets, but keep them out of git so each environment can
 * point at its own Firebase project.
 *
 * NOTE: there is deliberately no `storageBucket`. Firebase Storage is not
 * used by this project - do not add one.
 */
window.FIREBASE_CONFIG = {
  apiKey: "",
  authDomain: "",
  projectId: "",
  appId: "",
  messagingSenderId: "",
};

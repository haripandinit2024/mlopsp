/*
 * Firebase client initialisation.
 *
 * Initialises ONLY:
 *   - Firebase App
 *   - Firebase Authentication
 *   - Cloud Firestore
 *
 * Firebase Storage is intentionally NOT imported or initialised anywhere in
 * this project. Do not add `firebase-storage`, `getStorage()`, `ref()`,
 * `uploadBytes()`, `uploadBytesResumable()` or `getDownloadURL()`.
 *
 * The web configuration comes from `firebase-config.js`, generated per
 * environment by `scripts/generate_firebase_config.py`. If it is missing the
 * module still loads and reports `configured: false`, so the UI can show a
 * clear message instead of throwing a console error.
 */

import { initializeApp, getApps, getApp } from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js';
import { getAuth, setPersistence, browserLocalPersistence } from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js';

const REQUIRED_KEYS = ['apiKey', 'authDomain', 'projectId', 'appId'];

function readConfig() {
  const config = window.FIREBASE_CONFIG;
  if (!config || typeof config !== 'object') return null;
  const missing = REQUIRED_KEYS.filter((key) => !config[key]);
  if (missing.length) {
    console.warn(
      '[firebase] firebase-config.js is incomplete. Missing: ' + missing.join(', ') +
      '. Run: python scripts/generate_firebase_config.py'
    );
    return null;
  }
  return config;
}

const config = readConfig();

let app = null;
let auth = null;
let db = null;

if (config) {
  // Reuse an existing app if this module is evaluated more than once.
  app = getApps().length ? getApp() : initializeApp(config);
  auth = getAuth(app);
  db = getFirestore(app);

  // Survive page navigations within the multi-page dashboard.
  setPersistence(auth, browserLocalPersistence).catch((error) => {
    console.warn('[firebase] could not set auth persistence:', error && error.code);
  });
}

export { app, auth, db, config };
export const configured = Boolean(config);

/* Global handle for the non-module page scripts (onclick handlers etc.). */
window.FirebaseService = { app, auth, db, configured };

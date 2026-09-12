/*
 * Firebase Authentication glue for the dashboard.
 *
 * Model: hybrid session cookie.
 *   1. The browser authenticates with the Firebase JS SDK.
 *   2. It sends the resulting ID token to POST /api/auth/verify.
 *   3. The backend verifies the token with the Admin SDK, reads the role from
 *      Firestore, and sets an HttpOnly session cookie.
 *   4. Subsequent API calls and server-rendered pages use that cookie, so
 *      protected pages never flash and the raw token is not readable by JS
 *      beyond the SDK's own storage.
 *
 * The backend re-verifies the token on every session establishment, and the
 * role ALWAYS comes from the server. Anything sent from here about roles is a
 * request, never a grant.
 */

import { auth, configured } from './firebase.js';
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  GoogleAuthProvider,
  signOut,
  sendPasswordResetEmail,
  updateProfile,
  onAuthStateChanged,
  deleteUser,
} from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js';

const VERIFY_URL = '/api/auth/verify';
const LOGOUT_URL = '/api/auth/logout';
const POLL_INTERVAL_MS = 30 * 60 * 1000;

let currentUser = null;
let sessionEstablished = false;

class AuthError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'AuthError';
    this.status = status;
  }
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(body || {}),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }
  return { response, payload };
}

/**
 * Exchange the current Firebase ID token for a server session.
 * `profile` is only used on first registration.
 * Redirects to dashboard on success.
 */
async function establishSession(profile) {
  if (!auth || !auth.currentUser) {
    throw new AuthError('Not signed in.', 401);
  }
  // Force-refresh so the token is fresh enough for create_session_cookie.
  const idToken = await auth.currentUser.getIdToken(true);
  const { response, payload } = await postJson(VERIFY_URL, {
    id_token: idToken,
    name: profile && profile.name,
    role: profile && profile.role,
    invite_code: profile && profile.inviteCode,
    student_id: profile && profile.studentId,
  });

  if (!response.ok) {
    throw new AuthError(
      (payload && payload.error) || 'Could not establish a session.',
      response.status
    );
  }
  
  sessionEstablished = true;
  const user = payload.user;
  
  // Redirect to dashboard on successful login
  console.log('[auth] Session established for:', user.email, 'role:', user.role);
  window.location.href = '/dashboard';
  
  return user;
}

/**
 * Google Sign-In using popup.
 * Falls back to redirect if popup is blocked.
 */
async function signInWithGoogle() {
  if (!configured) {
    throw new AuthError(
      'Firebase is not configured. Run: python scripts/generate_firebase_config.py',
      503
    );
  }
  
  const provider = new GoogleAuthProvider();
  
  // Set custom parameters to prompt account selection
  provider.setCustomParameters({
    prompt: 'select_account'
  });
  
  try {
    // Try popup first
    const result = await signInWithPopup(auth, provider);
    return establishSession();
  } catch (error) {
    // If popup is blocked, try redirect
    if (error.code === 'auth/popup-closed-by-user') {
      throw new AuthError('Google sign-in cancelled.', 400);
    }
    if (error.code === 'auth/unauthorized-domain') {
      throw new AuthError(
        'Your browser is not authorized to use Google Sign-In. ' +
        'Please add your domain to the Firebase Console.',
        403
      );
    }
    // Try redirect as fallback
    try {
      await signInWithRedirect(auth, provider);
      // After redirect, get the result
      const redirectResult = await getRedirectResult(auth);
      if (redirectResult) {
        return establishSession();
      }
    } catch (redirectError) {
      throw new AuthError(
        'Google sign-in failed: ' + (redirectError.message || 'Unknown error'),
        redirectError.code === 'auth/popup-closed-by-user' ? 400 : 500
      );
    }
    throw error;
  }
}

/** Create the Firebase account, then the server-side profile + session. */
async function signup({ name, email, password, role, inviteCode, studentId }) {
  if (!configured) {
    throw new AuthError(
      'Firebase is not configured. Run: python scripts/generate_firebase_config.py',
      503
    );
  }

  const credential = await createUserWithEmailAndPassword(auth, email, password);
  try {
    if (name) await updateProfile(credential.user, { displayName: name });
    const user = await establishSession({ name, role, inviteCode, studentId });
    return user;
  } catch (error) {
    // Never leave an orphaned Firebase account with no application profile.
    try {
      await deleteUser(credential.user);
    } catch (cleanupError) {
      console.warn('[auth] could not roll back the Firebase user:', cleanupError);
    }
    await signOut(auth).catch(() => {});
    throw error;
  }
}

async function login(email, password) {
  if (!configured) {
    throw new AuthError(
      'Firebase is not configured. Run: python scripts/generate_firebase_config.py',
      503
    );
  }
  await signInWithEmailAndPassword(auth, email, password);
  return establishSession();
}

async function logout() {
  try {
    await fetch(LOGOUT_URL, { method: 'POST', credentials: 'same-origin' });
  } catch (error) {
    console.warn('[auth] server logout failed:', error);
  }
  sessionEstablished = false;
  currentUser = null;
  if (auth) await signOut(auth).catch(() => {});
}

async function resetPassword(email) {
  if (!configured) {
    throw new AuthError('Firebase is not configured.', 503);
  }
  await sendPasswordResetEmail(auth, email);
}

/** Ask the backend who we are, using the session cookie. */
async function fetchMe() {
  const response = await fetch('/api/auth/me', { credentials: 'same-origin' });
  if (!response.ok) return null;
  const data = await response.json();
  return data.user || null;
}

/**
 * fetch() wrapper for authenticated API calls.
 * Uses the session cookie, and transparently re-verifies once on a 401.
 */
async function authedFetch(url, options = {}) {
  const request = {
    credentials: 'same-origin',
    ...options,
    headers: { ...(options.headers || {}) },
  };
  if (request.body && typeof request.body === 'string' &&
      !request.headers['Content-Type']) {
    request.headers['Content-Type'] = 'application/json';
  }

  let response = await fetch(url, request);
  if (response.status === 401 && auth && auth.currentUser) {
    try {
      await establishSession();
      response = await fetch(url, request);
    } catch (error) {
      // Fall through and return the original 401.
    }
  }
  return response;
}

/** Redirect to /login unless an identity with an allowed role exists. */
async function requireRole(allowedRoles) {
  const roles = Array.isArray(allowedRoles) ? allowedRoles : [allowedRoles];
  const user = await fetchMe();
  if (!user) {
    window.location.replace('/login');
    return null;
  }
  if (roles.length && !roles.includes(user.role)) {
    window.location.replace('/dashboard');
    return null;
  }
  return user;
}

/** Keep the server session alive while the tab is open. */
function startSessionHeartbeat() {
  if (!auth) return () => {};
  return setInterval(() => {
    if (auth.currentUser) {
      establishSession().catch(() => {});
    }
  }, POLL_INTERVAL_MS);
}

export {
  configured,
  AuthError,
  signup,
  login,
  signInWithGoogle,
  logout,
  resetPassword,
  fetchMe,
  authedFetch,
  requireRole,
  establishSession,
  startSessionHeartbeat,
  onAuthStateChanged,
};

window.AppAuth = {
  configured,
  AuthError,
  signup,
  login,
  signInWithGoogle,
  logout,
  resetPassword,
  fetchMe,
  authedFetch,
  requireRole,
  establishSession,
  startSessionHeartbeat,
  onAuthStateChanged,
  get currentUser() {
    return auth ? auth.currentUser : null;
  },
  get sessionEstablished() {
    return sessionEstablished;
  },
};

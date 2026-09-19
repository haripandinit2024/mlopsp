/**
 * Auth Page - Login/Signup Logic
 */

// Tab switching
document.querySelectorAll('.auth-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        showForm(tabName);
    });
});

function showForm(type) {
    // Update tabs
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.auth-tab[data-tab="${type}"]`).classList.add('active');

    // Update forms
    document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
    document.getElementById(type + 'Form').classList.add('active');

    // Update footer text
    const footerText = document.getElementById('authFooterText');
    const i18n = window.I18N && window.I18N.tWith ? window.I18N : null;
    if (type === 'login') {
        const link = '<a href="#" onclick="showForm(\'signup\'); return false;">Sign up</a>';
        footerText.innerHTML = i18n ? i18n.tWith('auth.footerLogin', { link }) : 'Don\'t have an account? ' + link;
    } else {
        const link = '<a href="#" onclick="showForm(\'login\'); return false;">Login</a>';
        footerText.innerHTML = i18n ? i18n.tWith('auth.footerSignup', { link }) : 'Already have an account? ' + link;
    }

    // Hide success message
    document.getElementById('authSuccess').classList.add('hidden');
}

// Password strength indicator
const passwordInput = document.getElementById('signupPassword');
if (passwordInput) {
    passwordInput.addEventListener('input', (e) => {
        const password = e.target.value;
        const strengthBars = document.querySelectorAll('.strength-bar');
        let strength = 0;

        if (password.length >= 8) strength++;
        if (password.match(/[a-z]+/) && password.match(/[A-Z]+/)) strength++;
        if (password.match(/[0-9]+/)) strength++;
        if (password.match(/[!@#$%^&*(),.?":{}|<>]+/)) strength++;

        strengthBars.forEach((bar, index) => {
            if (index < strength) {
                bar.classList.add('active');
                bar.className = 'strength-bar active strength-' + strength;
            } else {
                bar.classList.remove('active');
            }
        });
    });
}

// --------------------------------------------------------
// Auth provider selection
// --------------------------------------------------------
// The backend decides whether it is running Firebase Authentication or the
// legacy session store (see AUTH_BACKEND in backend/authorization.py). This
// page asks /api/health and routes accordingly, so the dashboard keeps working
// before Firebase credentials are provisioned and switches over automatically
// once they are.
const AuthMode = {
    backend: 'legacy',
    firebaseReady: false,

    async detect() {
        try {
            const res = await fetch('/api/health');
            const data = await res.json();
            this.backend = (data.auth && data.auth.backend) || 'legacy';
            this.firebaseReady = this.backend === 'firebase';
        } catch (error) {
            this.backend = 'legacy';
            this.firebaseReady = false;
        }
        
        // Update UI based on auth mode
        this.updateAuthUI();
        return this.backend;
    },

    updateAuthUI() {
        const googleBtns = document.querySelectorAll('#googleSignInBtn, #googleSignInBtnSignup');
        const googleSection = document.querySelector('.auth-divider');
        const socialButtons = document.querySelector('.social-buttons');
        
        if (!this.firebaseReady) {
            // Hide Google Sign-In buttons and show a message
            googleBtns.forEach(btn => {
                if (btn) {
                    btn.style.display = 'none';
                }
            });
            
            // Show a message about Google sign-in being unavailable
            if (googleSection && socialButtons) {
                const message = document.createElement('div');
                message.className = 'auth-firebase-unavailable';
                message.style.cssText = 'text-align: center; padding: 1rem; margin: 1rem 0; color: var(--text-secondary); font-size: 0.875rem;';
                message.textContent = 'Google Sign-In is not available. Please use email/password to login.';
                
                // Insert after the divider
                googleSection.parentNode.insertBefore(message, googleSection.nextSibling);
            }
        } else {
            // Show Google Sign-In buttons
            googleBtns.forEach(btn => {
                if (btn) {
                    btn.style.display = '';
                }
            });
            
            // Remove the message if it exists
            const existingMessage = document.querySelector('.auth-firebase-unavailable');
            if (existingMessage) {
                existingMessage.remove();
            }
        }
    },

    get firebase() {
        return this.backend === 'firebase';
    },

    async login(email, password, profile) {
        if (this.firebase) return window.AppAuth.login(email, password, profile);
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Login failed');
        return data.user;
    },

    async signup(payload) {
        if (this.firebase) return window.AppAuth.signup(payload);
        const res = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Signup failed');
        return data.user;
    },

    async resetPassword(email) {
        if (this.firebase) return window.AppAuth.resetPassword(email);
        throw new Error(
            'Password reset is handled by Firebase and is not available on this deployment.'
        );
    },
};

AuthMode.detect();

// Firebase tokens expire; the server session is refreshed in the background.
AuthMode.detect().then(() => {
    if (AuthMode.firebase && window.AppAuth) window.AppAuth.startSessionHeartbeat();
});

// "Forgot password?" -> Firebase reset email.
const forgotLink = document.querySelector('.forgot-link');
if (forgotLink) {
    forgotLink.addEventListener('click', async (event) => {
        event.preventDefault();
        const email = (document.getElementById('loginEmail').value || '').trim();
        if (!email) {
            alert('Enter your email address first, then click "Forgot password?".');
            return;
        }
        try {
            await AuthMode.resetPassword(email);
            alert(`If an account exists for ${email}, a password reset link is on its way.`);
        } catch (error) {
            alert(error.message || 'Could not send the password reset email.');
        }
    });
}

// Google Sign-In button handler with role selection
async function handleGoogleSignIn() {
    const btn = document.getElementById('googleSignInBtn') || document.getElementById('googleSignInBtnSignup');
    if (!btn) return;
    
    // Check if Firebase is configured before proceeding
    if (!window.AppAuth || !window.AppAuth.configured) {
        try {
            const mod = await import('/js/firebase-auth.js');
            if (!window.AppAuth || !window.AppAuth.configured) {
                alert('Firebase authentication is not configured. Please use email/password login.');
                return;
            }
        } catch (importError) {
            console.error('Firebase module failed to load:', importError);
            alert('Firebase authentication is not configured. Please use email/password login.');
            return;
        }
    }
    
    // Show loading state
    btn.classList.add('loading');
    btn.disabled = true;
    
    try {
        // Use the new sign-in with role selection for privileged roles
        await window.AppAuth.signInWithGoogleWithRole();
        // On success, the establishSession will redirect to dashboard
        // or the auth flow will continue
    } catch (error) {
        console.error('Google sign-in error:', error);
        
        // User-friendly error messages
        let message = error.message || 'Google sign-in failed.';
        
        if (error.code === 'auth/popup-closed-by-user') {
            message = 'Sign-in cancelled. Please try again.';
        } else if (error.code === 'auth/unauthorized-domain') {
            message = 'This domain is not authorized for Google Sign-In. Please contact support.';
        } else if (error.code === 'auth/network-request-failed') {
            message = 'Network error. Please check your connection and try again.';
        } else if (error.status === 403) {
            message = error.message || 'Invite code is required for this role.';
        } else if (error.message.includes('not configured')) {
            message = 'Firebase is not configured. Please use email/password login.';
        }
        
        alert(message);
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// --------------------------------------------------------
// Google role selection modal (after a successful Google sign-in)
// --------------------------------------------------------
(function googleRoleModal() {
    const modal = document.getElementById('googleRoleModal');
    const inviteGroup = document.getElementById('googleRoleInviteGroup');
    const inviteInput = document.getElementById('googleRoleInvite');
    const studentIdGroup = document.getElementById('googleRoleStudentIdGroup');
    const studentIdInput = document.getElementById('googleRoleStudentId');
    const errorText = document.getElementById('googleRoleError');
    const accountLine = document.getElementById('googleRoleAccount');
    let resolver = null;

    if (!modal) {
        window.GoogleRoleModal = null;
        return;
    }

    function currentRole() {
        const checked = modal.querySelector('input[name="googleRole"]:checked');
        return checked ? checked.value : 'student';
    }

    function syncFields() {
        const role = currentRole();
        inviteGroup.classList.toggle('hidden', !(role === 'faculty' || role === 'admin'));
        studentIdGroup.classList.toggle('hidden', role !== 'student');
        errorText.classList.add('hidden');
        errorText.textContent = '';
    }

    function show() {
        const user = window.AppAuth && window.AppAuth.currentUser;
        const email = (user && user.email) || '';
        accountLine.textContent = email ? 'Sign in with Google · ' + email : 'Sign in with Google';
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    function hide() {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
        if (resolver) {
            const r = resolver;
            resolver = null;
            r(null);
        }
    }

    function resolvePick() {
        const role = currentRole();
        const inviteCode = inviteInput.value.trim();
        const studentIdRaw = studentIdInput.value.trim();

        if (role === 'faculty' || role === 'admin') {
            if (!inviteCode) {
                errorText.textContent = 'An invite code is required for ' + role + ' accounts.';
                errorText.classList.remove('hidden');
                inviteInput.focus();
                return;
            }
        }

        const payload = { role, inviteCode: inviteCode || null, studentId: null };
        if (role === 'student') {
            if (!studentIdRaw || !/^\d+$/.test(studentIdRaw)) {
                errorText.textContent = 'Enter your Student ID to link your risk profile.';
                errorText.classList.remove('hidden');
                studentIdInput.focus();
                return;
            }
            payload.studentId = Number(studentIdRaw);
        }

        modal.classList.add('hidden');
        document.body.style.overflow = '';
        if (resolver) {
            const r = resolver;
            resolver = null;
            r(payload);
        }
    }

    modal.querySelectorAll('input[name="googleRole"]').forEach(input => {
        input.addEventListener('change', syncFields);
    });
    document.getElementById('googleRoleConfirm').addEventListener('click', resolvePick);
    document.getElementById('googleRoleCancel').addEventListener('click', hide);
    document.getElementById('googleRoleClose').addEventListener('click', hide);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) hide();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) hide();
    });

    window.GoogleRoleModal = function () {
        syncFields();
        inviteInput.value = '';
        studentIdInput.value = '';
        show();
        return new Promise((resolve) => {
            resolver = resolve;
        });
    };
})();

// Form submissions
async function submitLoginForm() {
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    if (!email || !password) {
        alert('Please fill in all fields');
        return null;
    }

    await AuthMode.detect();
    const handoff = window.__pendingAuth || null;
    const user = await AuthMode.login(email, password, handoff);
    if (handoff) window.__pendingAuth = null;
    showSuccess('Welcome Back!', `You have successfully logged in as ${user.role}.`);
    setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
    return user;
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
        await submitLoginForm();
    } catch (err) {
        console.error('Login error:', err);
        alert(err.message || 'Unable to reach the server. Please try again.');
    }
});

// Privileged roles need an invite code; students may link their roster record.
const signupRoleSelect = document.getElementById('signupRole');
const signupInviteGroup = document.getElementById('signupInviteGroup');
const signupStudentIdGroup = document.getElementById('signupStudentIdGroup');

function syncSignupFields() {
    const role = signupRoleSelect.value;
    const privileged = role === 'faculty' || role === 'admin';
    signupInviteGroup.classList.toggle('hidden', !privileged);
    signupStudentIdGroup.classList.toggle('hidden', role !== 'student');
}

signupRoleSelect.addEventListener('change', syncSignupFields);
syncSignupFields();

document.getElementById('signupForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const firstName = document.getElementById('signupFirstName').value;
    const lastName = document.getElementById('signupLastName').value;
    const email = document.getElementById('signupEmail').value;
    const role = document.getElementById('signupRole').value;
    const password = document.getElementById('signupPassword').value;
    const confirmPassword = document.getElementById('signupConfirmPassword').value;
    const agreeTerms = document.getElementById('agreeTerms').checked;
    const inviteCode = document.getElementById('signupInviteCode').value;
    const studentId = document.getElementById('signupStudentId').value;

    if (!firstName || !lastName || !email || !role || !password || !confirmPassword) {
        alert('Please fill in all fields');
        return;
    }

    if (password !== confirmPassword) {
        alert('Passwords do not match');
        return;
    }

    if (password.length < 8) {
        alert('Password must be at least 8 characters');
        return;
    }

    if (!agreeTerms) {
        alert('Please agree to the Terms of Service');
        return;
    }

    try {
        await AuthMode.detect();
        const user = await AuthMode.signup({
            name: `${firstName} ${lastName}`.trim(),
            email,
            role,
            password,
            inviteCode: inviteCode || undefined,
            studentId: studentId ? Number(studentId) : undefined,
        });
        showSuccess('Account Created!', `Welcome, ${user.name}! Logging you in as ${user.role}.`);
        setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
    } catch (err) {
        console.error('Signup error:', err);
        alert(err.message || 'Unable to reach the server. Please try again.');
    }
});

function showSuccess(title, message) {
    // Hide forms
    document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
    document.querySelector('.auth-tabs').classList.add('hidden');
    document.querySelector('.auth-footer').classList.add('hidden');

    // Show success message
    const successDiv = document.getElementById('authSuccess');
    document.getElementById('successTitle').textContent = title;
    document.getElementById('successMessage').textContent = message;
    successDiv.classList.remove('hidden');
}

// Portal quick-logins. The Faculty and Administrator portals are gated by an
// invite code and, once accepted, sign in and land on the matching dashboard.
const PORTAL_CREDENTIALS = {
    student: { email: 'student@university.edu', password: 'password123' },
    faculty: { email: 'faculty@university.edu', password: 'password123' },
    admin: { email: 'admin@university.edu', password: 'password123' },
};

let pendingPortalRole = null;

function openPortalInviteModal(role) {
    const modal = document.getElementById('portalInviteModal');
    if (!modal) { portalLogin(role, ''); return; }

    pendingPortalRole = role;
    document.getElementById('portalInviteTitle').textContent =
        role === 'admin' ? 'Administrator access' : 'Faculty access';
    document.getElementById('portalInviteSub').textContent = role === 'admin'
        ? 'Enter your administrator invite code to continue to the admin dashboard.'
        : 'Enter your faculty invite code to continue to the faculty dashboard.';

    const input = document.getElementById('portalInviteInput');
    const error = document.getElementById('portalInviteError');
    input.value = '';
    error.textContent = '';
    error.classList.add('hidden');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    setTimeout(() => input.focus(), 0);
}

function closePortalInviteModal() {
    const modal = document.getElementById('portalInviteModal');
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
}

async function confirmPortalInvite() {
    const input = document.getElementById('portalInviteInput');
    const error = document.getElementById('portalInviteError');
    const confirmBtn = document.getElementById('portalInviteConfirm');
    const code = (input.value || '').trim();

    if (!code) {
        error.textContent = 'An invite code is required for this role.';
        error.classList.remove('hidden');
        input.focus();
        return;
    }

    const original = confirmBtn.textContent;
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Checking\u2026';
    let proceed = true;
    try {
        const res = await fetch('/api/auth/invite-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: pendingPortalRole, invite_code: code }),
        });
        if (res.status === 403 || res.status === 400) {
            const data = await res.json().catch(() => ({}));
            error.textContent = data.error || 'That invite code is not valid.';
            error.classList.remove('hidden');
            proceed = false;
        }
    } catch {
        // The API is unavailable (e.g. a static preview build); let the sign-in
        // step surface any problem instead of blocking the user here.
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = original;
    }

    if (proceed) {
        const role = pendingPortalRole;
        closePortalInviteModal();
        portalLogin(role, code);
    }
}

async function portalLogin(role, inviteCode) {
    const creds = PORTAL_CREDENTIALS[role];
    if (!creds) return;
    document.getElementById('loginEmail').value = creds.email;
    document.getElementById('loginPassword').value = creds.password;
    try {
        await submitLoginForm();
    } catch (err) {
        // No demo account for this role on the current deployment (for example
        // a Firebase-only setup): send the user to registration with the role
        // and validated invite code already filled in.
        console.warn('[auth] portal sign-in failed; offering sign-up instead:', err);
        showForm('signup');
        signupRoleSelect.value = role;
        syncSignupFields();
        const inviteField = document.getElementById('signupInviteCode');
        if (inviteField && inviteCode) inviteField.value = inviteCode;
    }
}

document.getElementById('studentPortalBtn')?.addEventListener('click', () => portalLogin('student', ''));
document.getElementById('facultyPortalBtn')?.addEventListener('click', () => openPortalInviteModal('faculty'));
document.getElementById('adminPortalBtn')?.addEventListener('click', () => openPortalInviteModal('admin'));
document.getElementById('portalInviteConfirm')?.addEventListener('click', confirmPortalInvite);
document.getElementById('portalInviteCancel')?.addEventListener('click', closePortalInviteModal);
document.getElementById('portalInviteClose')?.addEventListener('click', closePortalInviteModal);
document.getElementById('portalInviteInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); confirmPortalInvite(); }
});
(function bindPortalModalDismiss() {
    const modal = document.getElementById('portalInviteModal');
    if (!modal) return;
    modal.addEventListener('click', (e) => { if (e.target === modal) closePortalInviteModal(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) closePortalInviteModal();
    });
})();

// Keep footer text translated when language changes
document.addEventListener('i18n:change', () => {
    const activeTab = document.querySelector('.auth-tab.active');
    if (activeTab) showForm(activeTab.dataset.tab);
});

// Deep link: /login#signup opens the sign-up form directly.
// A role (plus an invite code for privileged roles) may be handed over by the
// public preview through sessionStorage or a ?role= / ?invite= query string.
const SIGNUP_HANDOFF_KEY = 'eduguard_signup_handoff';

function readSignupHandoff() {
    let handoff = null;
    try {
        const raw = sessionStorage.getItem(SIGNUP_HANDOFF_KEY);
        if (raw) {
            handoff = JSON.parse(raw);
            sessionStorage.removeItem(SIGNUP_HANDOFF_KEY);
        }
    } catch { /* malformed or unavailable storage */ }
    if (!handoff || typeof handoff !== 'object') handoff = {};

    const params = new URLSearchParams(window.location.search);
    const role = String(handoff.role || params.get('role') || '').toLowerCase();
    const inviteCode = handoff.inviteCode || params.get('invite') || '';
    // Keep the pending role around for the login path too, so an existing
    // account can be switched to the requested role on sign-in.
    window.__pendingAuth = (role === 'student' || role === 'faculty' || role === 'admin')
        ? { role: role, inviteCode: inviteCode || null }
        : null;
    return { role, inviteCode };
}

function applySignupHandoff(handoff) {
    if (!handoff || !signupRoleSelect) return false;
    const allowed = Array.from(signupRoleSelect.options).some(o => o.value === handoff.role);
    if (!allowed) return false;

    showForm('signup');
    signupRoleSelect.value = handoff.role;
    syncSignupFields();

    const inviteInput = document.getElementById('signupInviteCode');
    if (inviteInput && handoff.inviteCode) inviteInput.value = handoff.inviteCode;

    if ((handoff.role === 'faculty' || handoff.role === 'admin') && inviteInput) {
        if (!inviteInput.value) setTimeout(() => inviteInput.focus(), 50);
    }
    return true;
}

function applyAuthHash() {
    const target = (window.location.hash || '').replace('#', '').toLowerCase();
    if (target === 'signup' || target === 'login') showForm(target);
    applySignupHandoff(readSignupHandoff());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyAuthHash);
} else {
    applyAuthHash();
}
window.addEventListener('hashchange', applyAuthHash);
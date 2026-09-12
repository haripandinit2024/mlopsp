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

    async detect() {
        try {
            const res = await fetch('/api/health');
            const data = await res.json();
            this.backend = (data.auth && data.auth.backend) || 'legacy';
        } catch (error) {
            this.backend = 'legacy';
        }
        return this.backend;
    },

    get firebase() {
        return this.backend === 'firebase';
    },

    async login(email, password) {
        if (this.firebase) return window.AppAuth.login(email, password);
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

// Google Sign-In button handler
async function handleGoogleSignIn() {
    const btn = document.getElementById('googleSignInBtn');
    if (!btn) return;
    
    // Show loading state
    btn.classList.add('loading');
    btn.disabled = true;
    
    try {
        // Check if Firebase is configured
        if (!window.AppAuth || !window.AppAuth.configured) {
            alert('Firebase is not configured. Please contact support.');
            return;
        }
        
        await window.AppAuth.signInWithGoogle();
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
        }
        
        alert(message);
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// Form submissions
document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    if (!email || !password) {
        alert('Please fill in all fields');
        return;
    }

    try {
        await AuthMode.detect();
        const user = await AuthMode.login(email, password);
        showSuccess('Welcome Back!', `You have successfully logged in as ${user.role}.`);
        setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
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

// Auto-fill demo credentials (for testing)
document.getElementById('studentPortalBtn')?.addEventListener('click', () => {
    document.getElementById('loginEmail').value = 'student@university.edu';
    document.getElementById('loginPassword').value = 'password123';
});

document.getElementById('facultyPortalBtn')?.addEventListener('click', () => {
    document.getElementById('loginEmail').value = 'faculty@university.edu';
    document.getElementById('loginPassword').value = 'password123';
});

document.getElementById('adminPortalBtn')?.addEventListener('click', () => {
    document.getElementById('loginEmail').value = 'admin@university.edu';
    document.getElementById('loginPassword').value = 'password123';
});

// Keep footer text translated when language changes
document.addEventListener('i18n:change', () => {
    const activeTab = document.querySelector('.auth-tab.active');
    if (activeTab) showForm(activeTab.dataset.tab);
});
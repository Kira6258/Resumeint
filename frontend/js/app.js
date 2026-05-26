/**
 * Resumeint — Premium Core Logic
 * Handles: Authentication, Theme, Navigation, Toasts, and UI Interactions.
 */

const TOKEN_KEY = 'token';
const THEME_KEY = 'Resumeint-theme';

/* =========================================================
   THEME SYSTEM
========================================================= */

function initTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeButtons(savedTheme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem(THEME_KEY, next);

    updateThemeButtons(next);
}

function updateThemeButtons(theme) {
    const icon = theme === 'dark' ? '☀️' : '🌙';
    document.querySelectorAll('.theme-toggle-btn, #theme-toggle').forEach(btn => {
        btn.textContent = icon;
    });
}

// Pre-flight theme check to prevent flash
(function preloadTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    }
})();

/* =========================================================
   TOAST SYSTEM (Premium Aesthetic)
========================================================= */

function showToast(title, message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${icons[type]}</div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    container.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Auto-remove
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

/* =========================================================
   NAVIGATION & ACTIVE STATES
========================================================= */

function initNavigation() {
    const path = window.location.pathname.split('/').pop() || 'index.html';
    
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path) {
            link.classList.add('active');
        }
    });

    const toggle = document.querySelector('.mobile-nav-toggle');
    const menu = document.querySelector('.nav-links-wrapper');

    if (toggle && menu) {
        toggle.addEventListener('click', () => {
            menu.classList.toggle('active');
            const isOpen = menu.classList.contains('active');
            toggle.textContent = isOpen ? '✕' : '☰';
            document.body.style.overflow = isOpen ? 'hidden' : '';
        });

        // Close menu when clicking outside
        document.addEventListener('click', e => {
            if (!menu.contains(e.target) && !toggle.contains(e.target) && menu.classList.contains('active')) {
                menu.classList.remove('active');
                toggle.textContent = '☰';
                document.body.style.overflow = '';
            }
        });
    }
}

/* =========================================================
   FETCH WRAPPER (Auto-Auth & Error Handling)
========================================================= */

async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = {
        'Accept': 'application/json',
        ...(options.headers || {})
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const res = await fetch(url, {
            ...options,
            headers,
            credentials: 'include' // Important for HttpOnly cookies
        });

        if (res.status === 401) {
            localStorage.removeItem(TOKEN_KEY);
            // Only redirect if not already on public pages
            const publicPages = ['login.html', 'register.html', 'index.html', 'forgot-password.html', 'reset-password.html'];
            const isPublic = publicPages.some(page => window.location.pathname.includes(page));
            
            if (!isPublic) {
                window.location.href = 'login.html';
            }
        }

        return res;
    } catch (err) {
        console.error('Fetch error:', err);
        showToast('Network Error', 'Check your internet connection.', 'error');
        throw err;
    }
}

/* =========================================================
   AUTHENTICATION UI SYNC
========================================================= */

// Pages that require login — redirect to login.html if no token
const PROTECTED_PAGES = ['dashboard.html', 'upload.html', 'project.html', 'checkin.html', 'feedback.html', 'profile.html', 'resume-analyser.html'];

async function checkAuth() {
    const token = localStorage.getItem(TOKEN_KEY);
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    const isProtected = PROTECTED_PAGES.some(p => currentPage.includes(p));

    const elements = {
        avatar: document.getElementById('user-avatar'),
        avatarLink: document.querySelector('.nav-avatar-link'),
        logout: document.getElementById('logout-btn'),
        auth: document.getElementById('auth-buttons'),
        dashboard: document.getElementById('nav-dashboard'),
        newProject: document.getElementById('nav-new-project'),
        analyzer: document.getElementById('nav-analyzer')
    };

    if (!token) {
        // Redirect away from protected pages immediately
        if (isProtected) {
            window.location.href = 'login.html';
            return;
        }
        // On public pages: show Login/Register, hide user elements
        if (elements.avatar) elements.avatarLink && elements.avatarLink.classList.add('hidden');
        if (elements.avatarLink) elements.avatarLink.classList.add('hidden');
        if (elements.logout) elements.logout.classList.add('hidden');
        if (elements.dashboard) elements.dashboard.classList.add('hidden');
        if (elements.newProject) elements.newProject.classList.add('hidden');
        if (elements.analyzer) elements.analyzer.classList.add('hidden');
        if (elements.auth) elements.auth.classList.remove('hidden');
        return;
    }

    try {
        const res = await fetchWithAuth('/api/me');
        if (res.ok) {
            const user = await res.json();
            if (elements.avatar) {
                elements.avatar.classList.remove('hidden');
                elements.avatar.textContent = (user.name || user.email || 'U').charAt(0).toUpperCase();
            }
            if (elements.avatarLink) elements.avatarLink.classList.remove('hidden');
            if (elements.logout) elements.logout.classList.remove('hidden');
            if (elements.dashboard) elements.dashboard.classList.remove('hidden');
            if (elements.newProject) elements.newProject.classList.remove('hidden');
            if (elements.analyzer) elements.analyzer.classList.remove('hidden');
            if (elements.auth) elements.auth.classList.add('hidden');
        } else {
            // Token invalid — clear and redirect if protected
            localStorage.removeItem(TOKEN_KEY);
            if (isProtected) {
                window.location.href = 'login.html';
            } else {
                checkAuth();
            }
        }
    } catch (err) {
        console.error('Auth check failed:', err);
    }
}

function initLogout() {
    const logoutBtns = document.querySelectorAll('#logout-btn, .logout-action');
    logoutBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            try {
                await fetchWithAuth('/auth/logout');
            } catch (err) {}
            localStorage.removeItem(TOKEN_KEY);
            window.location.href = 'index.html';
        });
    });
}

/* =========================================================
   FORM HELPERS & VALIDATION
========================================================= */

function initValidation() {
    document.querySelectorAll('input, textarea').forEach(el => {
        el.addEventListener('blur', () => {
            if (!el.checkValidity()) {
                el.classList.add('input-error');
            } else {
                el.classList.remove('input-error');
            }
        });
        el.addEventListener('input', () => el.classList.remove('input-error'));
    });
}

function setButtonLoading(btn, loading = true, text = 'Processing...') {
    if (!btn) return;
    if (loading) {
        btn.dataset.original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> ${text}`;
    } else {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.original || 'Submit';
    }
}

/* =========================================================
   UI ENHANCEMENTS (Counters, Line Numbers, Anims)
========================================================= */

function initCharacterCounters() {
    const syllabus = document.getElementById('syllabus-text');
    const charCount = document.getElementById('char-count');
    if (syllabus && charCount) {
        syllabus.addEventListener('input', () => {
            charCount.textContent = `${syllabus.value.length} characters`;
        });
    }

    const code = document.getElementById('code-snippet');
    const codeCount = document.getElementById('code-char-count');
    if (code && codeCount) {
        code.addEventListener('input', () => {
            codeCount.textContent = `${code.value.length} / 5000`;
            updateLineNumbers(code);
        });
    }
}

function updateLineNumbers(textarea) {
    const lineContainer = document.getElementById('line-numbers');
    if (!lineContainer) return;
    const lines = textarea.value.split('\n').length;
    let html = '';
    for (let i = 1; i <= lines; i++) {
        html += `<div>${i}</div>`;
    }
    lineContainer.innerHTML = html;
    
    // Sync scroll
    textarea.onscroll = () => {
        lineContainer.scrollTop = textarea.scrollTop;
    };
}

function renderMarkdown(text) {
    if (!text) return '';
    let html = text
        .replace(/^## (.*$)/gim, '<h2 class="fb-section-title">$1</h2>')
        .replace(/^### (.*$)/gim, '<h3 class="fb-subsection-title">$1</h3>')
        .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*)\*/gim, '<em>$1</em>')
        .replace(/^\- (.*$)/gim, '<li class="fb-list-item">$1</li>')
        .replace(/\[SCORE:\s*(\d+\.?\d*)\s*\/\s*10\]/gim, '') // Hide score tag as it's shown in hero
        .replace(/`(.*?)`/gim, '<code class="inline-code">$1</code>');

    // Wrap lists
    html = html.replace(/(<li class="fb-list-item">.*<\/li>)/gim, '<ul class="fb-list">$1</ul>');
    // Clean up adjacent <ul> tags
    html = html.replace(/<\/ul>\n<ul class="fb-list">/gim, '');

    return html.split('\n').map(p => {
        if (p.trim().startsWith('<h') || p.trim().startsWith('<ul') || p.trim().startsWith('<li')) return p;
        return p.trim() ? `<p>${p}</p>` : '';
    }).join('');
}

function formatText(text) {
    if (!text) return '';
    // Step 1: Escape raw HTML so browser doesn't render AI-generated tags like <header>, <button> etc.
    const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    // Step 2: Apply safe markdown transforms on the escaped text
    return escaped
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`(.*?)`/g, '<code class="inline-code">$1</code>');
}

function initAnimations() {
    const animated = document.querySelectorAll('.animate-fade-in, .fade-up');
    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1 });

    animated.forEach(el => observer.observe(el));
}

/* =========================================================
   RAZORPAY PAYMENT INTEGRATION
========================================================= */

/**
 * Opens the Razorpay checkout modal.
 * @param {string} plan - 'monthly' or 'yearly'
 * @param {function} onSuccess - callback after successful payment
 */
async function openRazorpay(plan, onSuccess) {
    // Ensure Razorpay script is loaded
    if (typeof Razorpay === 'undefined') {
        showToast('Error', 'Payment system not loaded. Please refresh the page.', 'error');
        return;
    }

    try {
        // 1. Fetch public key
        const configRes = await fetch('/api/payments/config');
        const config = await configRes.json();

        if (!config.razorpay_key_id || config.razorpay_key_id === 'NOT_SET') {
            showToast('Payments Unavailable', 'Payment gateway is not configured on this server.', 'warning');
            return;
        }

        // Determine plan amount in paise
        const amount = plan === 'yearly' ? 49900 : 4900;

        // 2. Create order on backend
        const orderRes = await fetchWithAuth('/api/create-order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: amount,
                currency: 'INR',
                receipt: `receipt_${plan}`
            })
        });

        if (!orderRes.ok) {
            const err = await orderRes.json();
            showToast('Payment Error', err.detail || 'Could not create payment order.', 'error');
            return;
        }

        const order = await orderRes.json();
        const orderId = order.order_id || order.id;

        // 3. Open Razorpay checkout
        const options = {
            key: config.razorpay_key_id,
            amount: order.amount,
            currency: order.currency || 'INR',
            name: 'Resumeint',
            description: `Architect Pro ${plan.charAt(0).toUpperCase() + plan.slice(1)} Plan`,
            order_id: orderId,
            theme: { color: '#d4a24e' },
            handler: async function (response) {
                try {
                    const verifyRes = await fetchWithAuth('/api/verify-payment', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_signature: response.razorpay_signature,
                            plan: plan
                        })
                    });

                    if (verifyRes.ok) {
                        showToast('Upgrade Successful! 🎉', 'Welcome to Architect Pro!', 'success');
                        if (typeof onSuccess === 'function') {
                            setTimeout(onSuccess, 1200);
                        }
                    } else {
                        const err = await verifyRes.json();
                        showToast('Verification Failed', err.detail || 'Payment received but verification failed. Contact support.', 'error');
                    }
                } catch (err) {
                    showToast('Error', 'Verification request failed.', 'error');
                }
            },
            modal: {
                ondismiss: function () {
                    showToast('Payment Cancelled', 'Your upgrade was cancelled.', 'warning');
                }
            }
        };

        const rzp = new Razorpay(options);
        rzp.on('payment.failed', function (response) {
            console.error('Payment failed:', response.error);
            showToast('Payment Failed', response.error.description || 'Payment transaction failed. Please try again.', 'error');
        });
        rzp.open();

    } catch (err) {
        console.error('Razorpay error:', err);
        showToast('Payment Error', 'Could not initialize payment. Try again.', 'error');
    }
}

/* =========================================================
   INITIALIZATION
========================================================= */

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initNavigation();
    initLogout();
    initValidation();
    initCharacterCounters();
    initAnimations();
    checkAuth();

    // Global Theme Toggle Listener
    document.querySelectorAll('.theme-toggle-btn, #theme-toggle').forEach(btn => {
        btn.addEventListener('click', toggleTheme);
    });
});


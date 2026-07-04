/**
 * Страница входа/регистрации.
 * При загрузке: если пользователь уже авторизован — редирект на /choose.
 * После успешного входа/регистрации — редирект на /choose (робот → выбор предмета).
 */
(function () {
    'use strict';

    const form = document.getElementById('login-form');
    const emailInput = document.getElementById('login-email');
    const passwordInput = document.getElementById('login-password');
    const nameInput = document.getElementById('login-name');
    const nameLabel = document.querySelector('.login-label-name');
    const submitBtn = document.getElementById('login-submit');
    const errorEl = document.getElementById('login-error');
    const tabs = document.querySelectorAll('.login-tab');

    let mode = 'login';

    function setMode(m) {
        mode = m;
        tabs.forEach(function (t) {
            t.classList.toggle('active', t.dataset.mode === mode);
        });
        if (nameLabel) {
            nameLabel.classList.toggle('hidden', mode !== 'register');
        }
        if (nameInput) {
            nameInput.required = mode === 'register';
        }
        submitBtn.textContent = mode === 'login' ? 'Войти' : 'Зарегистрироваться';
        errorEl.classList.add('hidden');
    }

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.remove('hidden');
    }

    function hideError() {
        errorEl.classList.add('hidden');
    }

    // Уже авторизован — на выбор предмета (сервер редиректит на /choose)
    fetch('/api/me')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.user) {
                window.location.href = '/choose';
            }
        })
        .catch(function () {});

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            setMode(tab.dataset.mode);
        });
    });

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        hideError();
        var email = emailInput.value.trim();
        var password = passwordInput.value;
        var name = nameInput ? nameInput.value.trim() : '';

        if (!email || !password) {
            showError('Укажите email и пароль.');
            return;
        }
        if (mode === 'register' && password.length < 6) {
            showError('Пароль не менее 6 символов.');
            return;
        }

        submitBtn.disabled = true;
        var url = mode === 'login' ? '/api/login' : '/api/register';
        var body = mode === 'login' ? { email: email, password: password } : { email: email, password: password, name: name || undefined };

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
            .then(function (r) {
                return r.json().catch(function () {
                    throw new Error(r.status === 503
                        ? 'Сервер запускается, подождите минуту и попробуйте снова.'
                        : 'Ошибка сети. Попробуйте ещё раз.');
                }).then(function (data) {
                    if (r.status === 503) {
                        throw new Error(data.error || 'Сервер запускается, подождите минуту и попробуйте снова.');
                    }
                    return data;
                });
            })
            .then(function (data) {
                if (data.ok) {
                    window.location.href = '/choose';
                    return;
                }
                showError(data.error || 'Ошибка входа.');
                submitBtn.disabled = false;
            })
            .catch(function (err) {
                showError(err.message || 'Ошибка сети. Попробуйте ещё раз.');
                submitBtn.disabled = false;
            });
    });
})();

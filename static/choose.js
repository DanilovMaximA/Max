/**
 * Страница выбора предмета: робот Spline, кнопки Математика / Русский язык.
 * Математика → /login или /app (если авторизован)
 * Русский язык → подсказка «В разработке»
 */

const SPLINE_SCENE = 'https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode';

const btnMath = document.getElementById('btn-math');
const btnRussian = document.getElementById('btn-russian');
const toast = document.getElementById('toast');
const splineCanvas = document.getElementById('spline-canvas');
const splineLoading = document.getElementById('spline-loading');

function showToast(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.remove('hidden');
    setTimeout(function () {
        toast.classList.add('hidden');
    }, 2000);
}

function initSpline() {
    if (!splineCanvas) return;
    import('https://unpkg.com/@splinetool/runtime@1.1.3/build/runtime.js')
        .then(function (mod) {
            const Application = mod.Application || (mod.default && mod.default.Application) || mod.default;
            if (!Application) {
                const span = splineLoading && splineLoading.querySelector('span:last-child');
                if (span) span.textContent = 'Ошибка загрузки';
                return;
            }
            const app = new Application(splineCanvas);
            return app.load(SPLINE_SCENE).then(function () {
                if (splineLoading) splineLoading.classList.add('hidden');
            });
        })
        .catch(function (err) {
            console.error('Spline load error:', err);
            const span = splineLoading && splineLoading.querySelector('span:last-child');
            if (span) span.textContent = 'Робот загружается...';
        });
}

if (btnMath) {
    btnMath.href = '/app';
}

if (btnRussian) {
    btnRussian.addEventListener('click', function () {
        showToast('В разработке');
    });
}

initSpline();

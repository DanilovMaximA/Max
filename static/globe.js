/**
 * Интерактивный глобус в стиле 21st.dev (Glowing Effect).
 * Точки по сфере Фибоначчи, автовращение, перетаскивание мышью.
 */
(function () {
    'use strict';

    var canvas = document.getElementById('login-globe');
    if (!canvas) return;

    var ctx = canvas.getContext('2d');
    var rotY = 0.4;
    var rotX = 0.3;
    var autoRotateSpeed = 0.002;
    var drag = { active: false, startX: 0, startY: 0, startRotY: 0, startRotX: 0 };
    var dots = [];
    var animId = 0;
    var time = 0;

    var dotColor = 'rgba(100, 180, 255, ALPHA)';
    var radius = 0;
    var cx = 0;
    var cy = 0;
    var fov = 600;

    function rotateY(x, y, z, angle) {
        var cos = Math.cos(angle);
        var sin = Math.sin(angle);
        return [x * cos + z * sin, y, -x * sin + z * cos];
    }

    function rotateX(x, y, z, angle) {
        var cos = Math.cos(angle);
        var sin = Math.sin(angle);
        return [x, y * cos - z * sin, y * sin + z * cos];
    }

    function project(x, y, z) {
        var scale = fov / (fov + z);
        return [x * scale + cx, y * scale + cy];
    }

    function initDots() {
        dots = [];
        var numDots = 1200;
        var goldenRatio = (1 + Math.sqrt(5)) / 2;
        for (var i = 0; i < numDots; i++) {
            var theta = (2 * Math.PI * i) / goldenRatio;
            var phi = Math.acos(1 - (2 * (i + 0.5)) / numDots);
            var x = Math.cos(theta) * Math.sin(phi);
            var y = Math.cos(phi);
            var z = Math.sin(theta) * Math.sin(phi);
            dots.push([x, y, z]);
        }
    }

    function draw() {
        if (!canvas || !ctx) return;

        var dpr = window.devicePixelRatio || 1;
        var w = canvas.clientWidth;
        var h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);

        cx = w / 2;
        cy = h / 2;
        radius = Math.min(w, h) * 0.38;

        if (!drag.active) rotY += autoRotateSpeed;
        time += 0.015;

        ctx.clearRect(0, 0, w, h);

        var glowGrad = ctx.createRadialGradient(cx, cy, radius * 0.8, cx, cy, radius * 1.5);
        glowGrad.addColorStop(0, 'rgba(60, 140, 255, 0.04)');
        glowGrad.addColorStop(1, 'rgba(60, 140, 255, 0)');
        ctx.fillStyle = glowGrad;
        ctx.fillRect(0, 0, w, h);

        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(100, 180, 255, 0.08)';
        ctx.lineWidth = 1;
        ctx.stroke();

        var i, x, y, z, r, p, sx, sy, depthAlpha, dotSize;
        for (i = 0; i < dots.length; i++) {
            x = dots[i][0] * radius;
            y = dots[i][1] * radius;
            z = dots[i][2] * radius;
            r = rotateX(x, y, z, rotX);
            x = r[0]; y = r[1]; z = r[2];
            r = rotateY(x, y, z, rotY);
            x = r[0]; y = r[1]; z = r[2];
            if (z > 0) continue;
            p = project(x, y, z);
            sx = p[0]; sy = p[1];
            depthAlpha = Math.max(0.1, 1 - (z + radius) / (2 * radius));
            dotSize = 1 + depthAlpha * 0.8;
            ctx.beginPath();
            ctx.arc(sx, sy, dotSize, 0, Math.PI * 2);
            ctx.fillStyle = dotColor.replace('ALPHA', depthAlpha.toFixed(2));
            ctx.fill();
        }

        animId = requestAnimationFrame(draw);
    }

    function onPointerDown(e) {
        drag.active = true;
        drag.startX = e.clientX;
        drag.startY = e.clientY;
        drag.startRotY = rotY;
        drag.startRotX = rotX;
        canvas.setPointerCapture(e.pointerId);
    }

    function onPointerMove(e) {
        if (!drag.active) return;
        var dx = e.clientX - drag.startX;
        var dy = e.clientY - drag.startY;
        rotY = drag.startRotY + dx * 0.005;
        rotX = Math.max(-1, Math.min(1, drag.startRotX + dy * 0.005));
    }

    function onPointerUp() {
        drag.active = false;
    }

    initDots();
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointerleave', onPointerUp);
    canvas.style.cursor = 'grab';
    canvas.addEventListener('pointerdown', function () { canvas.style.cursor = 'grabbing'; });
    canvas.addEventListener('pointerup', function () { canvas.style.cursor = 'grab'; });
    canvas.addEventListener('pointerleave', function () { canvas.style.cursor = 'grab'; });

    draw();
})();

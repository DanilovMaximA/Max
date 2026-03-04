// Глобальные переменные
let currentTask = null;
let currentCorrect = null;

// Статистика
let stats = {
    total: 0,
    correct: 0,
    wrong: 0
};

// Загружаем статистику из localStorage при старте
function loadStats() {
    const saved = localStorage.getItem('fractionStats');
    if (saved) {
        stats = JSON.parse(saved);
        updateStatsDisplay();
    }
}
function saveStats() {
    localStorage.setItem('fractionStats', JSON.stringify(stats));
}
function updateStatsDisplay() {
    document.getElementById('total').textContent = stats.total;
    document.getElementById('correct').textContent = stats.correct;
    document.getElementById('wrong').textContent = stats.wrong;
}
function incTotal() { stats.total++; saveStats(); updateStatsDisplay(); }
function incCorrect() { stats.correct++; saveStats(); updateStatsDisplay(); }
function incWrong() { stats.wrong++; saveStats(); updateStatsDisplay(); }

// Загрузка новой задачи с сервера
async function fetchNewTask() {
    const response = await fetch('/api/new_task');
    const data = await response.json();
    currentTask = data.task;
    currentCorrect = data.correct;
    displayTask();
    clearInputs();
    hideAnalysis();
}

// Отображение задачи на странице
function displayTask() {
    const taskEl = document.getElementById('task-text');
    taskEl.textContent = `${currentTask.num1}/${currentTask.den1} + ${currentTask.num2}/${currentTask.den2} = ?`;
}

// Очистка полей ввода
function clearInputs() {
    document.getElementById('den-common').value = '';
    document.getElementById('num1-new').value = '';
    document.getElementById('num2-new').value = '';
    document.getElementById('result').value = '';
    // убрать классы ошибок
    document.querySelectorAll('input').forEach(inp => inp.classList.remove('error'));
}

// Скрыть блок анализа
function hideAnalysis() {
    document.getElementById('analysis').style.display = 'none';
}

// Показать блок анализа с данными
function showAnalysis(analysis, visualization, errors) {
    document.getElementById('analysis-text').textContent = analysis.text;
    // Подсветить поля с ошибками
    for (let field in errors) {
        if (errors[field]) {
            const input = document.getElementById(field === 'common_den' ? 'den-common' :
                                                   field === 'new_num1' ? 'num1-new' :
                                                   field === 'new_num2' ? 'num2-new' :
                                                   field === 'result' ? 'result' : null);
            if (input) input.classList.add('error');
        }
    }
    // Отрисовка визуализации
    drawVisualization(visualization);
    document.getElementById('analysis').style.display = 'block';
}

// Отрисовка на canvas
function drawVisualization(viz) {
    const canvas = document.getElementById('fraction-canvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Простейшая визуализация: два столбца с прямоугольниками
    // Левая колонка: исходные дроби
    ctx.fillStyle = 'blue';
    drawFraction(ctx, viz.original.num1, viz.original.den1, 50, 50, 100, 100);
    ctx.fillStyle = 'green';
    drawFraction(ctx, viz.original.num2, viz.original.den2, 200, 50, 100, 100);
    // Правая колонка: правильные приведённые дроби (можно нарисовать с общим знаменателем)
    ctx.fillStyle = 'orange';
    drawFraction(ctx, viz.correct_new_nums[0], viz.correct_common_den, 350, 50, 100, 100);
    ctx.fillStyle = 'purple';
    drawFraction(ctx, viz.correct_new_nums[1], viz.correct_common_den, 500, 50, 100, 100);
    // Можно добавить подписи
    ctx.fillStyle = 'black';
    ctx.font = '12px Arial';
    ctx.fillText('Исходные', 50, 30);
    ctx.fillText('После приведения', 350, 30);
}

// Вспомогательная функция рисования одной дроби
function drawFraction(ctx, num, den, x, y, w, h) {
    const partHeight = h / den;
    for (let i = 0; i < den; i++) {
        if (i < num) {
            ctx.fillRect(x, y + i * partHeight, w, partHeight - 1); // -1 для зазора
        } else {
            ctx.strokeRect(x, y + i * partHeight, w, partHeight - 1);
        }
    }
}

// Проверка ответа
async function checkAnswer() {
    const userAnswers = {
        common_den: parseInt(document.getElementById('den-common').value, 10),
        new_num1: parseInt(document.getElementById('num1-new').value, 10),
        new_num2: parseInt(document.getElementById('num2-new').value, 10),
        result: document.getElementById('result').value.trim()
    };
    
    const payload = {
        task: currentTask,
        user_answers: userAnswers
    };
    
    const response = await fetch('/api/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const result = await response.json();
    
    incTotal(); // увеличиваем общее число попыток
    if (result.is_correct) {
        incCorrect();
        // можно показать сообщение об успехе
        alert('Правильно!');
        // автоматически загрузить новую задачу или показать кнопку "Следующая"
        document.getElementById('next-btn').style.display = 'inline-block';
    } else {
        incWrong();
        showAnalysis(result.analysis, result.visualization, result.errors);
    }
}

// Обработчики событий
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    fetchNewTask();
    
    document.getElementById('check-btn').addEventListener('click', checkAnswer);
    document.getElementById('next-btn').addEventListener('click', () => {
        document.getElementById('next-btn').style.display = 'none';
        fetchNewTask();
    });
    document.getElementById('reset-stats').addEventListener('click', () => {
        stats = { total: 0, correct: 0, wrong: 0 };
        saveStats();
        updateStatsDisplay();
    });
});
// Глобальные переменные
let currentTask = null;
let currentCorrect = null;
let taskAlreadyCheckedCorrect = false;  // не засчитывать повторное нажатие «Проверить» для той же задачи
let currentOperation = 'add';
let currentSection = 'ordinary';
let useAltExplanation = false;
let currentAnalysis = null;

let stats = { total: 0, correct: 0, wrong: 0 };

// Соответствие полей ошибок и id элементов (для разных операций используются разные наборы)
const INPUT_IDS = {
    common_den: 'den-common',
    new_num1: 'num1-new',
    new_num2: 'num2-new',
    result: 'result',
    'result-single': 'result-single',
    comparison: 'comparison-value',
    int_part: 'int-part',
    num: 'convert-num',
    den: 'convert-den'
};

function getFieldsToShowMarks() {
    const op = currentOperation;
    if (op === 'add' || op === 'subtract') return ['common_den', 'new_num1', 'new_num2', 'result'];
    if (op === 'common_denominator') return ['common_den', 'new_num1', 'new_num2'];
    if (op === 'compare' || op === 'decimal_compare') return ['comparison'];
    if (op === 'compare_add_subtract' && currentTask) {
        if (currentTask.real_operation === 'compare') return ['comparison'];
        return ['common_den', 'new_num1', 'new_num2', 'result'];
    }
    if ((op === 'convert' || op === 'mixed_numbers') && currentTask && currentTask.convert_direction === 'improper_to_mixed')
        return ['int_part', 'num', 'den'];
    return ['result'];
}

function getElementForField(field) {
    if (field === 'comparison') {
        const v = document.getElementById('comparison-value').value;
        return document.querySelector(`.compare-btn[data-compare="${v}"]`);
    }
    if (field === 'result') {
        const id = (currentOperation === 'add' || currentOperation === 'subtract' || currentOperation === 'common_denominator' ||
            (currentOperation === 'compare_add_subtract' && currentTask && currentTask.real_operation !== 'compare')) ? 'result' : 'result-single';
        return document.getElementById(id);
    }
    const id = INPUT_IDS[field];
    return id ? document.getElementById(id) : null;
}

function loadStats() {
    const saved = localStorage.getItem('fractionStats');
    if (saved) {
        try { stats = JSON.parse(saved); } catch (e) {}
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
function updateGamificationUI(g) {
    const block = document.getElementById('gamification-stats');
    if (!g) {
        block.classList.add('hidden');
        return;
    }
    const starsDisplay = document.getElementById('stars-display');
    if (starsDisplay) {
        const icons = starsDisplay.querySelectorAll('.star-icon');
        const count = g.total_stars || 0;
        icons.forEach((icon, i) => {
            icon.classList.toggle('dim', i >= count);
            icon.classList.toggle('lit', i < count);
        });
    }
    document.getElementById('current-streak').textContent = g.current_streak;
    const chestsEl = document.getElementById('chests-count');
    if (chestsEl) chestsEl.textContent = g.chests_available || 0;
    block.classList.remove('hidden');

    if (g.new_chest && g.new_chest > 0) {
        showChestAnimation();
    }
}

function showChestAnimation() {
    const overlay = document.getElementById('chest-overlay');
    if (!overlay) return;
    overlay.classList.remove('hidden');
    overlay.classList.add('chest-show');
    setTimeout(() => {
        overlay.classList.remove('chest-show');
        overlay.classList.add('hidden');
    }, 3000);
}
function incTotal() { stats.total++; saveStats(); updateStatsDisplay(); }
function incCorrect() { stats.correct++; saveStats(); updateStatsDisplay(); }
function incWrong() { stats.wrong++; saveStats(); updateStatsDisplay(); }

const THEORY = {
    add: `Сложение дробей с разными знаменателями: найти НОК знаменателей, привести дроби, сложить числители. Пример: 1/4 + 2/3 = 3/12 + 8/12 = 11/12.`,
    subtract: `Вычитание: общий знаменатель, привести дроби, вычесть числители. Пример: 3/4 − 1/6 = 9/12 − 2/12 = 7/12.`,
    multiply: `Умножение дробей: числитель на числитель, знаменатель на знаменатель, затем сократить. (a/b)×(c/d) = (a×c)/(b×d).`,
    divide: `Деление на дробь = умножение на обратную: (a/b)÷(c/d) = (a/b)×(d/c) = (a×d)/(b×c), затем сократить.`,
    power: `Степень дроби: (a/b)^n = a^n/b^n. Возвести числитель и знаменатель в степень, затем сократить.`,
    compare: `Сравнение: привести к общему знаменателю или сравнить произведения a×d и b×c. Если a×d < b×c, то a/b < c/d.`,
    reduce: `Сокращение: найти НОД числителя и знаменателя, разделить оба на НОД. Пример: 6/8 = 3/4.`,
    convert: `Смешанное число ↔ обыкновенная дробь: целая часть a и дробь b/c дают (a×c+b)/c. Обратно: неправильная дробь num/den = (num÷den) целых и (остаток/den).`,
    decimal_add: `Сложение десятичных: уравнять количество знаков после запятой нулями, затем складывать по разрядам (целые с целыми, десятые с десятыми).`,
    decimal_subtract: `Вычитание десятичных: уравнять знаки после запятой, затем вычитать по разрядам как натуральные.`,
    decimal_multiply: `Умножение: перемножить без запятых, в произведении отделить запятой столько знаков, сколько в обоих множителях вместе.`,
    decimal_divide: `Деление: на натуральное — как обычно, запятую в частном поставить, когда закончится целая часть. На десятичную — перенести запятую вправо в обоих числах.`,
    decimal_compare: `Сравнение десятичных: поразрядно (целые, десятые, сотые…). Можно уравнять количество знаков после запятой нулями.`,
    decimal_to_common: `В числителе — число без запятой, в знаменателе — 1 и столько нулей, сколько знаков после запятой. Затем сократить.`,
    common_to_decimal: `Разделить числитель на знаменатель уголком. В частном поставить запятую, когда заканчивается деление целой части.`,
    decimal_round: `Округление: если следующая цифра 5 или больше, предыдущий разряд увеличить на 1.`
};

// Темы для «Обыкновенные дроби 5 класс» (12 действий)
const THEORY_GRADE5 = {
    add_subtract_same_den: `При одинаковых знаменателях складываем или вычитаем только числители, знаменатель не меняется. Пример: 3/7 + 2/7 = 5/7, 6/9 − 2/9 = 4/9.`,
    natural_div_fraction: `Деление натурального числа на дробь — умножение на обратную дробь: a ÷ (b/c) = a × (c/b). Пример: 4 ÷ 2/3 = 4 × 3/2 = 6.`,
    mixed_numbers: `Смешанное число — целая часть и дробная. В обыкновенную: a b/c = (a×c+b)/c. Обратно: неправильная дробь = целая часть + остаток/знаменатель.`,
    add_subtract_mixed: `Складываем и вычитаем смешанные числа: отдельно целые части и дробные; при вычитании при необходимости «занимаем» 1 из целой части.`,
    basic_property: `Основное свойство: числитель и знаменатель можно умножить или разделить на одно число — величина дроби не изменится. a/b = (a×k)/(b×k).`,
    reduce: `Сокращение: найти НОД числителя и знаменателя, разделить оба на НОД. Пример: 18/30 = 3/5 (НОД(18,30)=6).`,
    common_denominator: `Общий знаменатель — НОК знаменателей. Домножаем каждую дробь на свой дополнительный множитель. Пример: 3/4 и 5/6 → НОК=12, получаем 9/12 и 10/12.`,
    compare_add_subtract: `Сравнение: привести к общему знаменателю и сравнить числители (или сравнить a×d и b×c). Сложение и вычитание: общий знаменатель, затем сложить или вычесть числители.`,
    multiply: `Умножение дробей: числитель на числитель, знаменатель на знаменатель, затем сократить. (a/b)×(c/d) = (a×c)/(b×d).`,
    fraction_of_number: `Чтобы найти дробь от числа, умножаем число на эту дробь. Пример: 2/5 от 30 = 30 × 2/5 = 12.`,
    divide: `Деление на дробь — умножение на обратную: (a/b) ÷ (c/d) = (a/b) × (d/c).`,
    whole_from_part: `Если известно, что дробь a/b от числа равна x, то целое = x ÷ (a/b) = x × (b/a). Пример: 2/5 числа равны 16 → число = 16 × 5/2 = 40.`
};

// Темы для «Десятичные дроби 5 класс»
const THEORY_DECIMAL5 = {
    common_to_decimal: `Десятичная запись дробей: если знаменатель 10, 100, 1000 и т.д., можно записать дробь в виде десятичной. Пример: 3/10 = 0,3; 47/100 = 0,47.`,
    decimal_compare: THEORY.decimal_compare,
    decimal_add: `Сложение десятичных дробей: записываем числа столбиком, запятая под запятой. Складываем как натуральные, запятую в ответе ставим под запятыми.`,
    decimal_subtract: `Вычитание десятичных дробей: выравниваем числа по запятой, при необходимости дополняем нулями. Вычитаем как натуральные.`,
    decimal_round: `Округление десятичных: смотрим на следующий разряд. Если цифра 5, 6, 7, 8, 9 — увеличиваем предыдущую на 1, если 0–4 — оставляем без изменений. Прикидка — приблизительный результат для проверки.`,
    decimal_multiply: `Умножение десятичной дроби на натуральное число: умножаем как натуральные, затем отделяем запятой столько же знаков после запятой, сколько было в множимом. При умножении на десятичную дробь учитываем знаки после запятой в обоих множителях.`,
    decimal_divide: `Деление десятичной дроби на натуральное число: делим как натуральные, запятую в частном ставим, когда заканчивается целая часть. При делении на десятичную дробь переносим запятую вправо в обоих числах.`,
    decimal_to_common: THEORY.decimal_to_common
};
const TITLES = {
    add: 'Сложение дробей',
    subtract: 'Вычитание дробей',
    multiply: 'Умножение дробей',
    divide: 'Деление дробей',
    power: 'Возведение дроби в степень',
    compare: 'Сравнение дробей',
    reduce: 'Сокращение дробей',
    convert: 'Преобразование (смешанное ↔ обыкновенное)',
    decimal_add: 'Десятичные: сложение',
    decimal_subtract: 'Десятичные: вычитание',
    decimal_multiply: 'Десятичные: умножение',
    decimal_divide: 'Десятичные: деление',
    decimal_compare: 'Десятичные: сравнение',
    decimal_to_common: 'Десятичная → обыкновенная',
    common_to_decimal: 'Обыкновенная → десятичная',
    decimal_round: 'Округление десятичных'
};

function updateTheory() {
    const titleEl = document.getElementById('main-title');
    if (currentSection === 'ordinary') {
        titleEl.textContent = 'Обыкновенные дроби';
        const el = document.getElementById('theory-content-ordinary');
        if (el) el.textContent = THEORY[currentOperation] || '';
    } else if (currentSection === 'grade5') {
        titleEl.textContent = 'Обыкновенные дроби 5 класс';
        const el = document.getElementById('theory-content-grade5');
        if (el) el.textContent = THEORY_GRADE5[currentOperation] || THEORY[currentOperation] || '';
    } else if (currentSection === 'decimal5') {
        titleEl.textContent = 'Десятичные дроби 5 класс';
        const el = document.getElementById('theory-content-decimal5');
        if (el) el.textContent = THEORY_DECIMAL5[currentOperation] || THEORY[currentOperation] || '';
    } else {
        titleEl.textContent = 'Десятичные дроби';
        const el = document.getElementById('theory-content-decimal');
        if (el) el.textContent = THEORY[currentOperation] || '';
    }
}

function showInputsForOperation(op) {
    document.getElementById('inputs-add-subtract').classList.add('hidden');
    document.getElementById('inputs-single-result').classList.add('hidden');
    document.getElementById('inputs-compare').classList.add('hidden');
    document.getElementById('inputs-convert-mixed').classList.add('hidden');
    const singleInput = document.getElementById('result-single');

    if (op === 'add' || op === 'subtract') {
        document.getElementById('inputs-add-subtract').classList.remove('hidden');
        const resultRow = document.getElementById('result-row');
        if (resultRow) resultRow.style.display = '';
    } else if (op === 'compare_add_subtract' && currentTask && currentTask.real_operation === 'compare') {
        document.getElementById('inputs-compare').classList.remove('hidden');
    } else if (op === 'compare_add_subtract' && currentTask && (currentTask.real_operation === 'add' || currentTask.real_operation === 'subtract')) {
        document.getElementById('inputs-add-subtract').classList.remove('hidden');
        const resultRow = document.getElementById('result-row');
        if (resultRow) resultRow.style.display = '';
    } else if (op === 'common_denominator') {
        document.getElementById('inputs-add-subtract').classList.remove('hidden');
        const resultRow = document.getElementById('result-row');
        if (resultRow) resultRow.style.display = 'none';
    } else if (op === 'compare' || op === 'decimal_compare') {
        document.getElementById('inputs-compare').classList.remove('hidden');
    } else if ((op === 'convert' || op === 'mixed_numbers') && currentTask && currentTask.convert_direction === 'improper_to_mixed') {
        document.getElementById('inputs-convert-mixed').classList.remove('hidden');
    } else if (op === 'decimal_to_common') {
        document.getElementById('inputs-single-result').classList.remove('hidden');
        if (singleInput) singleInput.placeholder = 'числитель/знаменатель, например 3/4';
    } else if (op.startsWith('decimal_') || op === 'common_to_decimal' || op === 'multiply' || op === 'divide' || op === 'power' || op === 'reduce' ||
        op === 'add_subtract_same_den' || op === 'natural_div_fraction' || op === 'add_subtract_mixed' || op === 'basic_property' ||
        op === 'fraction_of_number' || op === 'whole_from_part' ||
        (op === 'convert' || op === 'mixed_numbers') && currentTask && currentTask.convert_direction === 'mixed_to_improper') {
        document.getElementById('inputs-single-result').classList.remove('hidden');
        if (singleInput) {
            if ((op.startsWith('decimal_') && op !== 'decimal_to_common') || op === 'common_to_decimal') singleInput.placeholder = 'через запятую, например 0,4';
            else if (op === 'fraction_of_number' || op === 'whole_from_part') singleInput.placeholder = 'число или дробь, например 12 или 12/1';
            else singleInput.placeholder = 'например 3/4';
        }
    }
}

async function fetchNewTask() {
    taskAlreadyCheckedCorrect = false;
    const response = await fetch(`/api/new_task?operation=${currentOperation}`);
    const data = await response.json();
    currentTask = data.task;
    currentCorrect = data.correct;
    currentOperation = currentTask.operation || currentOperation;
    syncSelectFromOperation();
    displayTask();
    clearInputs();
    hideAnalysis();
    showInputsForOperation(currentOperation);
    updateTheory();
    useAltExplanation = false;
    const btnEl = document.getElementById('not-understood-btn');
    if (btnEl) btnEl.textContent = 'Не понятно? Показать другой разбор';
}

function syncSelectFromOperation() {
    const selOrd = document.getElementById('operation-select-ordinary');
    const selDec = document.getElementById('operation-select-decimal');
    const selGrade5 = document.getElementById('operation-select-grade5');
    const selDec5 = document.getElementById('operation-select-decimal5');
    if (currentSection === 'ordinary' && selOrd) {
        selOrd.value = currentOperation;
    } else if (currentSection === 'grade5' && selGrade5) {
        selGrade5.value = currentOperation;
    } else if (currentSection === 'decimal5' && selDec5) {
        selDec5.value = currentOperation;
    } else if (selDec) {
        selDec.value = currentOperation;
    }
}

function switchSection(section) {
    currentSection = section;
    const secOrd = document.getElementById('section-ordinary');
    const secDec = document.getElementById('section-decimal');
    const secGrade5 = document.getElementById('section-grade5');
    const secDec5 = document.getElementById('section-decimal5');
    const tabOrd = document.querySelector('.tab[data-section="ordinary"]');
    const tabDec = document.querySelector('.tab[data-section="decimal"]');
    const tabGrade5 = document.querySelector('.tab[data-section="grade5"]');
    const tabDec5 = document.querySelector('.tab[data-section="decimal5"]');

    secOrd.classList.add('hidden');
    secDec.classList.add('hidden');
    if (secGrade5) secGrade5.classList.add('hidden');
    if (secDec5) secDec5.classList.add('hidden');
    if (tabOrd) { tabOrd.classList.remove('active'); tabOrd.setAttribute('aria-selected', 'false'); }
    if (tabDec) { tabDec.classList.remove('active'); tabDec.setAttribute('aria-selected', 'false'); }
    if (tabGrade5) { tabGrade5.classList.remove('active'); tabGrade5.setAttribute('aria-selected', 'false'); }
    if (tabDec5) { tabDec5.classList.remove('active'); tabDec5.setAttribute('aria-selected', 'false'); }

    if (section === 'ordinary') {
        secOrd.classList.remove('hidden');
        if (tabOrd) { tabOrd.classList.add('active'); tabOrd.setAttribute('aria-selected', 'true'); }
        currentOperation = document.getElementById('operation-select-ordinary').value;
        updateTheory();
        fetchNewTask();
    } else if (section === 'grade5') {
        if (secGrade5) secGrade5.classList.remove('hidden');
        if (tabGrade5) { tabGrade5.classList.add('active'); tabGrade5.setAttribute('aria-selected', 'true'); }
        currentOperation = document.getElementById('operation-select-grade5').value;
        updateTheory();
        fetchNewTask();
    } else if (section === 'decimal5') {
        if (secDec5) secDec5.classList.remove('hidden');
        if (tabDec5) { tabDec5.classList.add('active'); tabDec5.setAttribute('aria-selected', 'true'); }
        currentOperation = document.getElementById('operation-select-decimal5').value;
        updateTheory();
        fetchNewTask();
    } else {
        secDec.classList.remove('hidden');
        if (tabDec) { tabDec.classList.add('active'); tabDec.setAttribute('aria-selected', 'true'); }
        currentOperation = document.getElementById('operation-select-decimal').value;
        updateTheory();
        fetchNewTask();
    }
}

function displayTask() {
    const taskEl = document.getElementById('task-text');
    const t = currentTask;
    const op = currentOperation;
    if (op === 'add') {
        taskEl.textContent = `${t.num1}/${t.den1} + ${t.num2}/${t.den2} = ?`;
    } else if (op === 'subtract') {
        taskEl.textContent = `${t.num1}/${t.den1} − ${t.num2}/${t.den2} = ?`;
    } else if (op === 'multiply') {
        taskEl.textContent = `${t.num1}/${t.den1} × ${t.num2}/${t.den2} = ?`;
    } else if (op === 'divide') {
        taskEl.textContent = `(${t.num1}/${t.den1}) ÷ (${t.num2}/${t.den2}) = ?`;
    } else if (op === 'power') {
        taskEl.textContent = `(${t.num}/${t.den})^${t.exponent} = ?`;
    } else if (op === 'compare') {
        taskEl.textContent = `Сравните: ${t.num1}/${t.den1} и ${t.num2}/${t.den2}. Вставьте знак <, = или >`;
    } else if (op === 'reduce') {
        taskEl.textContent = `Сократите дробь ${t.num}/${t.den}`;
    } else if (op === 'convert') {
        if (t.convert_direction === 'mixed_to_improper') {
            taskEl.textContent = `Преобразуйте в обыкновенную дробь: ${t.int_part} ${t.num}/${t.den} = ?`;
        } else {
            taskEl.textContent = `Преобразуйте в смешанное число: ${t.num}/${t.den} = ?`;
        }
    } else if (op === 'decimal_add') {
        taskEl.textContent = `${t.a_str} + ${t.b_str} = ?`;
    } else if (op === 'decimal_subtract') {
        taskEl.textContent = `${t.a_str} − ${t.b_str} = ?`;
    } else if (op === 'decimal_multiply') {
        taskEl.textContent = `${t.a_str} × ${t.b_str} = ?`;
    } else if (op === 'decimal_divide') {
        taskEl.textContent = `${t.a_str} : ${t.b_str} = ?`;
    } else if (op === 'decimal_compare') {
        taskEl.textContent = `Сравните: ${t.a_str} и ${t.b_str}. Вставьте знак <, = или >`;
    } else if (op === 'decimal_to_common') {
        taskEl.textContent = `Преобразуйте в обыкновенную дробь: ${t.decimal_str} = ?`;
    } else if (op === 'common_to_decimal') {
        taskEl.textContent = `Преобразуйте в десятичную дробь (через запятую): ${t.num}/${t.den} = ?`;
    } else if (op === 'decimal_round') {
        const places = t.to_places === 1 ? 'десятых' : 'сотых';
        taskEl.textContent = `Округлите до ${places}: ${t.decimal_str} ≈ ?`;
    } else if (op === 'add_subtract_same_den') {
        const isSubtract = t.op_sym === '−' || t.op_sym === '-' || t.op_sym === 'subtract';
        const sym = isSubtract ? '−' : '+';
        taskEl.textContent = `${t.num1}/${t.den1} ${sym} ${t.num2}/${t.den2} = ?`;
    } else if (op === 'natural_div_fraction') {
        taskEl.textContent = `${t.natural} ÷ ${t.num}/${t.den} = ?`;
    } else if (op === 'mixed_numbers') {
        if (t.convert_direction === 'mixed_to_improper') {
            taskEl.textContent = `Преобразуйте в обыкновенную дробь: ${t.int_part} ${t.num}/${t.den} = ?`;
        } else {
            taskEl.textContent = `Преобразуйте в смешанное число: ${t.num}/${t.den} = ?`;
        }
    } else if (op === 'add_subtract_mixed') {
        const isSubtract = t.op_sym === '−' || t.op_sym === '-' || t.op_sym === 'subtract';
        const sym = isSubtract ? '−' : '+';
        taskEl.textContent = `${t.int1} ${t.n1}/${t.d1} ${sym} ${t.int2} ${t.n2}/${t.d2} = ?`;
    } else if (op === 'basic_property') {
        taskEl.textContent = `Запишите дробь ${t.num}/${t.den} со знаменателем ${t.target_den}. Ответ в виде дроби (числитель/знаменатель): ?`;
    } else if (op === 'common_denominator') {
        taskEl.textContent = `Приведите к общему знаменателю дроби ${t.num1}/${t.den1} и ${t.num2}/${t.den2}. Укажите общий знаменатель и числители после приведения.`;
    } else if (op === 'compare_add_subtract') {
        if (t.real_operation === 'compare') {
            taskEl.textContent = `Сравните: ${t.num1}/${t.den1} и ${t.num2}/${t.den2}. Знак <, = или >`;
        } else {
            const sym = t.real_operation === 'subtract' ? '−' : '+';
            taskEl.textContent = `${t.num1}/${t.den1} ${sym} ${t.num2}/${t.den2} = ?`;
        }
    } else if (op === 'fraction_of_number') {
        taskEl.textContent = `Найдите ${t.num}/${t.den} от ${t.whole}. Ответ: ?`;
    } else if (op === 'whole_from_part') {
        taskEl.textContent = `${t.num}/${t.den} числа равны ${t.part}. Найдите число. Ответ: ?`;
    } else {
        taskEl.textContent = '—';
    }
}

function clearInputs() {
    const inputs = document.querySelectorAll('.inputs-section input');
    inputs.forEach(inp => { inp.value = ''; inp.classList.remove('error', 'ok'); });
    document.querySelectorAll('.field-status').forEach(span => span.remove());
    document.querySelectorAll('.compare-btn').forEach(btn => btn.classList.remove('selected'));
    document.getElementById('comparison-value').value = '';
}

function hideAnalysis() {
    document.getElementById('analysis').style.display = 'none';
}

function showAnalysis(analysis, visualization, errors) {
    if (!analysis) return;
    currentAnalysis = analysis;
    const textEl = document.getElementById('analysis-text');
    const text = (useAltExplanation && analysis.alt_text) ? analysis.alt_text : (analysis.text || '');
    textEl.textContent = text;
    document.querySelectorAll('.inputs-section input, .compare-btn').forEach(el => el.classList.remove('error', 'selected', 'ok'));
    document.querySelectorAll('.field-status').forEach(span => span.remove());

    errors = errors || {};
    const fields = getFieldsToShowMarks();
    for (const field of fields) {
        const el = getElementForField(field);
        if (!el) continue;
        const isError = errors[field] === true;
        const hasValue = field === 'comparison'
            ? (document.getElementById('comparison-value').value || '').trim() !== ''
            : (el.value != null && String(el.value).trim() !== '');

        if (isError) {
            el.classList.add('error');
        } else if (hasValue) {
            el.classList.add('ok');
            let span = el.nextElementSibling;
            if (!span || !span.classList.contains('field-status')) {
                span = document.createElement('span');
                span.className = 'field-status';
                span.setAttribute('aria-hidden', 'true');
                span.textContent = ' ✓';
                el.parentNode.insertBefore(span, el.nextSibling);
            }
        }
    }
    drawVisualization(visualization || {});
    document.getElementById('analysis').style.display = 'block';
}

function renderLatex(container, latex) {
    if (typeof katex !== 'undefined') {
        katex.render(latex, container, { throwOnError: false, displayMode: true });
    } else {
        container.textContent = latex;
    }
}

function drawVisualization(viz) {
    const el = document.getElementById('viz-latex');
    if (!el) return;
    el.innerHTML = '';
    const op = viz.operation || 'add';

    function frac(n, d) { return `\\dfrac{${n}}{${d}}`; }
    function colored(color, content) { return `\\color{${color}}{${content}}`; }

    let lines = [];

    if ((op === 'add' || op === 'subtract') && viz.original && viz.correct_result) {
        const sym = op === 'subtract' ? '-' : '+';
        const n1 = viz.original.num1, d1 = viz.original.den1;
        const n2 = viz.original.num2, d2 = viz.original.den2;
        const r = viz.correct_result;
        lines.push(`\\text{Исходные дроби: } ${colored('#4a90e2', frac(n1, d1))} ${sym} ${colored('#50c878', frac(n2, d2))}`);
        if (viz.correct_new_nums && viz.correct_common_den) {
            const cd = viz.correct_common_den;
            const nn1 = viz.correct_new_nums[0], nn2 = viz.correct_new_nums[1];
            lines.push(`\\text{Приведение: } ${colored('#ff8c42', frac(nn1, cd))} ${sym} ${colored('#9b59b6', frac(nn2, cd))}`);
        }
        if (viz.before_reduce) {
            const br = viz.before_reduce;
            lines.push(`\\text{Действие: } ${colored('#3498db', frac(br.num, br.den))}`);
            lines.push(`\\text{Сокращение: } ${frac(br.num, br.den)} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        } else {
            lines.push(`\\text{Результат: } ${colored('#e74c3c', frac(r.num, r.den))}`);
        }
    } else if (op === 'multiply' && viz.original && viz.correct_result) {
        const n1 = viz.original.num1, d1 = viz.original.den1;
        const n2 = viz.original.num2, d2 = viz.original.den2;
        const r = viz.correct_result;
        if (viz.before_reduce) {
            const br = viz.before_reduce;
            lines.push(`${colored('#4a90e2', frac(n1, d1))} \\times ${colored('#50c878', frac(n2, d2))} = ${colored('#3498db', frac(br.num, br.den))}`);
            lines.push(`\\text{Сокращение: } ${frac(br.num, br.den)} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        } else {
            lines.push(`${colored('#4a90e2', frac(n1, d1))} \\times ${colored('#50c878', frac(n2, d2))} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        }
    } else if (op === 'divide' && viz.original && viz.correct_result) {
        const n1 = viz.original.num1, d1 = viz.original.den1;
        const n2 = viz.original.num2, d2 = viz.original.den2;
        const r = viz.correct_result;
        if (viz.before_reduce) {
            const br = viz.before_reduce;
            lines.push(`${colored('#4a90e2', frac(n1, d1))} \\div ${colored('#50c878', frac(n2, d2))} = ${colored('#4a90e2', frac(n1, d1))} \\times ${colored('#50c878', frac(d2, n2))} = ${colored('#3498db', frac(br.num, br.den))}`);
            lines.push(`\\text{Сокращение: } ${frac(br.num, br.den)} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        } else {
            lines.push(`${colored('#4a90e2', frac(n1, d1))} \\div ${colored('#50c878', frac(n2, d2))} = ${colored('#4a90e2', frac(n1, d1))} \\times ${colored('#50c878', frac(d2, n2))} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        }
    } else if (op === 'power' && viz.original && viz.correct_result) {
        const n = viz.original.num1, d = viz.original.den1, exp = viz.original.num2;
        const r = viz.correct_result;
        if (viz.before_reduce) {
            const br = viz.before_reduce;
            lines.push(`\\left(${frac(n, d)}\\right)^{${exp}} = ${frac(n + '^{' + exp + '}', d + '^{' + exp + '}')} = ${colored('#3498db', frac(br.num, br.den))}`);
            lines.push(`\\text{Сокращение: } ${frac(br.num, br.den)} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        } else {
            lines.push(`\\left(${frac(n, d)}\\right)^{${exp}} = ${frac(n + '^{' + exp + '}', d + '^{' + exp + '}')} = ${colored('#e74c3c', frac(r.num, r.den))}`);
        }
    } else if (op === 'reduce' && viz.original && viz.correct_result) {
        const n = viz.original.num1, d = viz.original.den1;
        const r = viz.correct_result;
        lines.push(`${frac(n, d)} = ${colored('#e74c3c', frac(r.num, r.den))}`);
    } else if (op === 'compare' && viz.original) {
        const n1 = viz.original.num1, d1 = viz.original.den1;
        const n2 = viz.original.num2, d2 = viz.original.den2;
        const comp = viz.comparison || '';
        const sign = comp === '<' ? '\\lt' : comp === '>' ? '\\gt' : '=';
        lines.push(`${colored('#4a90e2', frac(n1, d1))} \\; ${sign} \\; ${colored('#50c878', frac(n2, d2))}`);
    } else if (op === 'convert' && viz.task) {
        const t = viz.task;
        const r = viz.correct_result;
        if (t.convert_direction === 'mixed_to_improper' && r) {
            lines.push(`${t.int_part}\\tfrac{${t.num}}{${t.den}} = \\dfrac{${t.int_part} \\times ${t.den} + ${t.num}}{${t.den}} = ${colored('#e74c3c', frac(r.result_num, r.result_den))}`);
        } else if (r) {
            lines.push(`${frac(t.num, t.den)} = ${colored('#e74c3c', r.int_part + '\\tfrac{' + r.num + '}{' + r.den + '}')}`);
        }
    } else if (op && op.startsWith('decimal_')) {
        if (viz.correct_result && viz.correct_result.result_str) {
            lines.push(`\\text{Правильный ответ: } ${colored('#e74c3c', viz.correct_result.result_str.replace(',', '{,}'))}`);
        }
        if (viz.comparison) {
            const sign = viz.comparison === '<' ? '\\lt' : viz.comparison === '>' ? '\\gt' : '=';
            lines.push(`\\text{Правильный знак: } ${colored('#e74c3c', sign)}`);
        }
    } else if (op === 'common_to_decimal' && viz.correct_result) {
        if (viz.correct_result.result_str) {
            lines.push(`\\text{Правильный ответ: } ${colored('#e74c3c', viz.correct_result.result_str.replace(',', '{,}'))}`);
        }
    } else if (viz.correct_result && typeof viz.correct_result.num === 'number') {
        lines.push(`\\text{Правильный ответ: } ${colored('#e74c3c', frac(viz.correct_result.num, viz.correct_result.den))}`);
    }

    if (lines.length === 0) return;

    for (const latex of lines) {
        const row = document.createElement('div');
        row.className = 'viz-latex-row';
        renderLatex(row, latex);
        el.appendChild(row);
    }
}

async function checkAnswer() {
    if (taskAlreadyCheckedCorrect) return;  // повторное нажатие — не засчитывать, не переходить
    let userAnswers = {};
    const op = currentOperation;
    const useAddSubtractInputs = (op === 'add' || op === 'subtract') ||
        (op === 'common_denominator') ||
        (op === 'compare_add_subtract' && currentTask && currentTask.real_operation !== 'compare');
    const useCompareInputs = (op === 'compare') || (op === 'decimal_compare') || (op === 'compare_add_subtract' && currentTask && currentTask.real_operation === 'compare');
    const useConvertMixedInputs = (op === 'convert' || op === 'mixed_numbers') && currentTask && currentTask.convert_direction === 'improper_to_mixed';

    if (useAddSubtractInputs) {
        userAnswers = {
            common_den: parseInt(document.getElementById('den-common').value, 10) || null,
            new_num1: parseInt(document.getElementById('num1-new').value, 10) || null,
            new_num2: parseInt(document.getElementById('num2-new').value, 10) || null,
            result: document.getElementById('result').value.trim()
        };
        if (op === 'common_denominator') userAnswers.result = '';
    } else if (useCompareInputs) {
        userAnswers = { comparison: document.getElementById('comparison-value').value.trim() };
    } else if (useConvertMixedInputs) {
        const parseNum = (el) => { const v = parseInt(el.value, 10); return (el.value.trim() === '' || isNaN(v)) ? null : v; };
        userAnswers = {
            int_part: parseNum(document.getElementById('int-part')),
            num: parseNum(document.getElementById('convert-num')),
            den: parseNum(document.getElementById('convert-den'))
        };
    } else {
        const single = document.getElementById('result-single');
        userAnswers = { result: single ? single.value.trim() : '' };
    }

    const response = await fetch('/api/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: currentTask, user_answers: userAnswers, section: currentSection })
    });
    const result = await response.json();

    incTotal();
    if (result.is_correct) {
        taskAlreadyCheckedCorrect = true;
        incCorrect();
        document.getElementById('next-btn').style.display = 'inline-block';
        document.querySelectorAll('.inputs-section input, .compare-btn').forEach(el => el.classList.remove('error', 'selected', 'ok'));
        document.querySelectorAll('.field-status').forEach(span => span.remove());
        const fields = getFieldsToShowMarks();
        for (const field of fields) {
            const el = getElementForField(field);
            if (!el) continue;
            el.classList.add('ok');
            let span = el.nextElementSibling;
            if (!span || !span.classList.contains('field-status')) {
                span = document.createElement('span');
                span.className = 'field-status';
                span.setAttribute('aria-hidden', 'true');
                span.textContent = ' ✓';
                el.parentNode.insertBefore(span, el.nextSibling);
            }
        }
    } else {
        incWrong();
        useAltExplanation = false;
        const analysisEl = document.getElementById('analysis');
        const analysisTextEl = document.getElementById('analysis-text');
        if (result.analysis && (result.analysis.text || result.analysis.alt_text)) {
            try {
                showAnalysis(result.analysis, result.visualization || {}, result.errors || {});
            } catch (e) {
                analysisTextEl.textContent = result.analysis.text || result.analysis.alt_text || 'Ошибка в решении. Проверьте ответ.';
                try { drawVisualization(result.visualization || {}); } catch (_) {}
                analysisEl.style.display = 'block';
            }
            analysisEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            analysisTextEl.textContent = 'Ошибка в решении. Проверьте ответ.';
            try { if (result.visualization) drawVisualization(result.visualization); } catch (_) {}
            analysisEl.style.display = 'block';
            analysisEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
    if (result.gamification) {
        updateGamificationUI(result.gamification);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Auth: только для страницы тренажёра (/app) — если нет пользователя, редирект на вход
    function updateAuthUI(user) {
        const authUser = document.getElementById('auth-user');
        const btnLogout = document.getElementById('btn-logout');
        const btnProfile = document.getElementById('btn-profile');
        if (user) {
            authUser.textContent = user.name || user.email;
            authUser.classList.remove('hidden');
            btnLogout.classList.remove('hidden');
            if (btnProfile) btnProfile.classList.remove('hidden');
            const btnTeacher = document.getElementById('btn-teacher');
            const btnParent = document.getElementById('btn-parent');
            if (btnTeacher) btnTeacher.classList.toggle('hidden', user.role !== 'teacher' && user.role !== 'admin');
            if (btnParent) btnParent.classList.toggle('hidden', user.role !== 'parent' && user.role !== 'admin');
        } else {
            authUser.classList.add('hidden');
            btnLogout.classList.add('hidden');
            if (btnProfile) btnProfile.classList.add('hidden');
            const btnTeacher = document.getElementById('btn-teacher');
            const btnParent = document.getElementById('btn-parent');
            if (btnTeacher) btnTeacher.classList.add('hidden');
            if (btnParent) btnParent.classList.add('hidden');
        }
    }
    function checkAuth(retries = 3) {
        fetch('/api/me', { credentials: 'include' })
            .then(r => r.json())
            .then(data => {
                if (!data.user) {
                    if (retries > 0) {
                        setTimeout(() => checkAuth(retries - 1), 1500);
                    } else {
                        window.location.href = '/';
                    }
                    return;
                }
                updateAuthUI(data.user);
                return fetch('/api/gamification', { credentials: 'include' }).then(r => r.json()).then(d => {
                    if (d.gamification) updateGamificationUI(d.gamification);
                });
            })
            .catch(() => {
                if (retries > 0) {
                    setTimeout(() => checkAuth(retries - 1), 1500);
                } else {
                    window.location.href = '/';
                }
            });
    }
    checkAuth();

    document.getElementById('btn-logout').addEventListener('click', () => {
        window.location.href = '/logout';
    });

    const profileDropdown = document.getElementById('profile-dropdown');
    const btnProfile = document.getElementById('btn-profile');
    if (btnProfile && profileDropdown) {
        btnProfile.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = !profileDropdown.classList.contains('hidden');
            profileDropdown.classList.toggle('hidden', isOpen);
            btnProfile.setAttribute('aria-expanded', !isOpen);
            if (!isOpen) return;
            fetch('/api/profile').then(r => r.json()).then(data => {
                document.getElementById('profile-school-val').textContent = data.school || '—';
                document.getElementById('profile-class-val').textContent = data.school_class || '—';
                document.getElementById('profile-level-val').textContent = data.level_name || data.level || '—';
                document.getElementById('profile-stars-val').textContent = (data.total_stars != null ? data.total_stars : '0') + '/3';
                document.getElementById('profile-chests-val').textContent = data.chests_available != null ? data.chests_available : '0';
                document.getElementById('profile-teachers-val').textContent = (data.teachers && data.teachers.length) ? data.teachers.join(', ') : '—';
                const streakEl = document.getElementById('profile-streak-val');
                if (streakEl) streakEl.textContent = data.current_streak || '0';
                const bestEl = document.getElementById('profile-best-val');
                if (bestEl) bestEl.textContent = data.best_streak || '0';
            }).catch(() => {});
        });
        document.addEventListener('click', () => {
            profileDropdown.classList.add('hidden');
            btnProfile.setAttribute('aria-expanded', 'false');
        });
        profileDropdown.addEventListener('click', (e) => e.stopPropagation());
    }

    loadStats();
    currentSection = 'ordinary';
    currentOperation = document.getElementById('operation-select-ordinary').value;
    updateTheory();
    fetchNewTask();

    document.querySelectorAll('.tab[data-section]').forEach(tab => {
        tab.addEventListener('click', () => {
            const section = tab.dataset.section;
            if (section === currentSection) return;
            switchSection(section);
        });
    });

    document.getElementById('operation-select-ordinary').addEventListener('change', (e) => {
        if (currentSection !== 'ordinary') return;
        currentOperation = e.target.value;
        updateTheory();
        fetchNewTask();
    });

    document.getElementById('operation-select-decimal').addEventListener('change', (e) => {
        if (currentSection !== 'decimal') return;
        currentOperation = e.target.value;
        updateTheory();
        fetchNewTask();
    });

    const selGrade5 = document.getElementById('operation-select-grade5');
    if (selGrade5) {
        selGrade5.addEventListener('change', (e) => {
            if (currentSection !== 'grade5') return;
            currentOperation = e.target.value;
            updateTheory();
            fetchNewTask();
        });
    }

    const selDec5 = document.getElementById('operation-select-decimal5');
    if (selDec5) {
        selDec5.addEventListener('change', (e) => {
            if (currentSection !== 'decimal5') return;
            currentOperation = e.target.value;
            updateTheory();
            fetchNewTask();
        });
    }

    document.querySelectorAll('.compare-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.compare-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            document.getElementById('comparison-value').value = btn.dataset.compare;
        });
    });

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

    document.getElementById('not-understood-btn').addEventListener('click', () => {
        useAltExplanation = !useAltExplanation;
        const analysisEl = document.getElementById('analysis-text');
        const btnEl = document.getElementById('not-understood-btn');
        if (currentAnalysis) {
            if (useAltExplanation && currentAnalysis.alt_text) {
                analysisEl.textContent = currentAnalysis.alt_text;
                btnEl.textContent = 'Показать обычный разбор';
            } else {
                analysisEl.textContent = currentAnalysis.text;
                btnEl.textContent = 'Не понятно? Показать другой разбор';
            }
        }
    });
});

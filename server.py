# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, send_from_directory, session, redirect
import json
import random
import math
import webbrowser
import threading
import os
import re
from decimal import Decimal, ROUND_HALF_UP
import bcrypt

from models import db, User, Topic, Attempt, ErrorLabel, UserTopicProgress, EventLog, UserStats, UserReward, UserStudentLink, ROLE_STUDENT, ROLE_TEACHER, ROLE_PARENT, ROLE_ADMIN, ROLES
from error_detector import detect_error_type
from ai_service import ai_service
from gamification import update_gamification
from auth_provider import SessionAuthProvider

# Путь к static относительно server.py — так же работает при деплое (Render и т.д.)
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, static_folder=_static_dir)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', 'sqlite:///matema.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Сессия на Render: куки при переходе по ссылкам
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
db.init_app(app)

VALID_OPERATIONS = [
    'add', 'subtract', 'multiply', 'divide', 'power', 'compare', 'reduce', 'convert',
    'add_subtract_same_den', 'natural_div_fraction', 'mixed_numbers', 'add_subtract_mixed',
    'basic_property', 'common_denominator', 'compare_add_subtract', 'fraction_of_number', 'whole_from_part',
    'decimal_add', 'decimal_subtract', 'decimal_multiply', 'decimal_divide',
    'decimal_compare', 'decimal_to_common', 'common_to_decimal', 'decimal_round'
]


def gcd(a, b):
    return math.gcd(a, b) if a and b else 1


def lcm(a, b):
    return a * b // gcd(a, b) if a and b else 1


def generate_fraction():
    """Несократимая дробь: числитель 1..9, знаменатель 2..9."""
    while True:
        num = random.randint(1, 9)
        den = random.randint(2, 9)
        if gcd(num, den) == 1:
            return num, den


def generate_reducible_fraction():
    """Сократимая дробь: числитель и знаменатель 2..12, НОД > 1."""
    while True:
        num = random.randint(2, 12)
        den = random.randint(2, 12)
        if gcd(num, den) > 1:
            return num, den


def generate_task():
    """Две дроби с разными знаменателями."""
    num1, den1 = generate_fraction()
    num2, den2 = generate_fraction()
    while den2 == den1:
        num2, den2 = generate_fraction()
    return num1, den1, num2, den2


# --- Вычисление правильных ответов по операциям ---

def compute_add_subtract(num1, den1, num2, den2, operation):
    common_den = lcm(den1, den2)
    new_num1 = num1 * (common_den // den1)
    new_num2 = num2 * (common_den // den2)
    res_num = new_num1 - new_num2 if operation == 'subtract' else new_num1 + new_num2
    g = gcd(abs(res_num), common_den)
    out = {
        'common_den': common_den,
        'new_num1': new_num1,
        'new_num2': new_num2,
        'result_num': res_num // g,
        'result_den': common_den // g,
        'operation': operation
    }
    if g > 1:
        out['before_reduce'] = {'num': res_num, 'den': common_den}
    return out


def compute_multiply(num1, den1, num2, den2):
    p_num = num1 * num2
    p_den = den1 * den2
    g = gcd(p_num, p_den)
    out = {'result_num': p_num // g, 'result_den': p_den // g}
    if g > 1:
        out['before_reduce'] = {'num': p_num, 'den': p_den}
    return out


def compute_divide(num1, den1, num2, den2):
    # (a/b) / (c/d) = (a*d)/(b*c)
    p_num = num1 * den2
    p_den = den1 * num2
    g = gcd(p_num, p_den)
    out = {'result_num': p_num // g, 'result_den': p_den // g}
    if g > 1:
        out['before_reduce'] = {'num': p_num, 'den': p_den}
    return out


def compute_power(num, den, exponent):
    res_num = num ** exponent
    res_den = den ** exponent
    g = gcd(res_num, res_den)
    out = {'result_num': res_num // g, 'result_den': res_den // g}
    if g > 1:
        out['before_reduce'] = {'num': res_num, 'den': res_den}
    return out


def compute_compare(num1, den1, num2, den2):
    # a/b ? c/d  =>  a*d ? b*c
    left = num1 * den2
    right = num2 * den1
    if left < right:
        comparison = '<'
    elif left > right:
        comparison = '>'
    else:
        comparison = '='
    return {'comparison': comparison}


def compute_reduce(num, den):
    g = gcd(num, den)
    return {'result_num': num // g, 'result_den': den // g}


def mixed_to_improper(int_part, num, den):
    res_num = int_part * den + num
    return {'result_num': res_num, 'result_den': den}


def improper_to_mixed(num, den):
    int_part = num // den
    rest = num % den
    return {'int_part': int_part, 'num': rest, 'den': den}


# --- Десятичные дроби: представление (числитель, 10^places), отображение через запятую ---

def _decimal_to_str(num, den):
    """Число num/den (den = 10^k) в строку с запятой."""
    if den <= 0:
        return "0"
    q, r = divmod(num, den)
    s = str(q)
    if r:
        frac = str(r).zfill(len(str(den)) - 1).rstrip('0')
        if frac:
            s += ',' + frac
    return s


def _parse_decimal(s):
    """Строку с запятой или точкой в (числитель, знаменатель) или None."""
    if s is None or not isinstance(s, str):
        return None
    s = s.strip().replace(',', '.')
    if not s:
        return None
    try:
        d = Decimal(s)
        # конвертируем в (int_num, 10^places)
        as_str = d.as_tuple()
        digits = list(as_str.digits)
        exp = as_str.exponent
        if exp >= 0:
            num = int(Decimal(s)) if s else 0
            return (num, 1)
        # например 12.35 -> digits=[1,2,3,5], exp=-2 -> 1235/100
        num = sum(d * 10 ** (len(digits) - 1 - i) for i, d in enumerate(digits))
        if as_str.sign:
            num = -num
        den = 10 ** (-exp)
        return (num, den)
    except Exception:
        return None


def _gen_decimal_int(max_integral=99, max_decimals=3):
    """Случайная десятичная дробь: возвращает (num, den), den = 10^k."""
    decimals = random.randint(1, max_decimals)
    den = 10 ** decimals
    integral = random.randint(0, max_integral)
    fractional = random.randint(0, den - 1) if decimals else 0
    num = integral * den + fractional
    return (num, den)


@app.route('/')
def index():
    if get_current_user():
        return redirect('/choose')
    return send_from_directory('static', 'login.html')


@app.route('/login')
def login_redirect():
    return redirect('/')


@app.route('/choose')
def choose_page():
    if not get_current_user():
        return redirect('/')
    return send_from_directory('static', 'choose.html')


@app.route('/index')
@app.route('/index.html')
def index_redirect():
    return redirect('/')


@app.route('/app')
def app_page():
    if not get_current_user():
        return redirect('/')
    return send_from_directory('static', 'index.html')


@app.route('/app/profile')
def profile_page():
    if not get_current_user():
        return redirect('/')
    return send_from_directory('static', 'profile.html')


@app.route('/teacher')
def teacher_page():
    return send_from_directory('static', 'teacher.html')


@app.route('/parent')
def parent_page():
    return send_from_directory('static', 'parent.html')


def get_current_user():
    """Return current User from auth provider (session or future messenger)."""
    prov = _auth_provider_for_request()
    user_id = prov.get_current_user_id()
    return User.query.get(user_id) if user_id else None


def _auth_provider_for_request():
    """Use session; later can switch to MessengerAuthProvider for API requests from bot."""
    return SessionAuthProvider(session)


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip() or None
    role = (data.get('role') or ROLE_STUDENT).strip().lower()
    if role not in ROLES:
        role = ROLE_STUDENT
    if not email or not re.match(r'^[\w\.\-]+@[\w\.\-]+\.[a-z]{2,}$', email):
        return jsonify({'ok': False, 'error': 'Некорректный email'}), 400
    if len(password) < 6:
        return jsonify({'ok': False, 'error': 'Пароль не менее 6 символов'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'ok': False, 'error': 'Пользователь с таким email уже есть'}), 400
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user = User(email=email, password_hash=password_hash, name=name, role=role)
    db.session.add(user)
    db.session.flush()
    stats = UserStats(user_id=user.id, total_stars=0, lifetime_stars=0, chests_available=0)
    db.session.add(stats)
    db.session.commit()
    _auth_provider_for_request().set_user(user.id)
    ev = EventLog(user_id=user.id, event_type='register', payload=None)
    db.session.add(ev)
    db.session.commit()
    return jsonify({'ok': True, 'user': {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role}})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = (data.get('password') or '').encode('utf-8')
    if not email or not password:
        return jsonify({'ok': False, 'error': 'Укажите email и пароль'}), 400
    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash or not bcrypt.checkpw(password, user.password_hash.encode('utf-8')):
        return jsonify({'ok': False, 'error': 'Неверный email или пароль'}), 401
    _auth_provider_for_request().set_user(user.id)
    ev = EventLog(user_id=user.id, event_type='login', payload=None)
    db.session.add(ev)
    db.session.commit()
    return jsonify({'ok': True, 'user': {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role}})


@app.route('/api/logout', methods=['POST', 'GET'])
def logout():
    prov = _auth_provider_for_request()
    user_id = prov.get_current_user_id()
    if user_id:
        ev = EventLog(user_id=user_id, event_type='logout', payload=None)
        db.session.add(ev)
        db.session.commit()
    prov.clear_user()
    return jsonify({'ok': True})


@app.route('/logout', methods=['GET', 'POST'])
def logout_redirect():
    """Выход: очистить сессию и редирект на страницу входа."""
    prov = _auth_provider_for_request()
    user_id = prov.get_current_user_id()
    if user_id:
        ev = EventLog(user_id=user_id, event_type='logout', payload=None)
        db.session.add(ev)
        db.session.commit()
    prov.clear_user()
    return redirect('/')


@app.route('/api/me')
def me():
    user = get_current_user()
    if not user:
        return jsonify({'user': None})
    return jsonify({'user': {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role}})


@app.route('/api/gamification')
def api_gamification():
    """Current user's stars, streak, status, chests, topic progress."""
    user = get_current_user()
    if not user:
        return jsonify({'gamification': None})
    stats = UserStats.query.filter_by(user_id=user.id).first()
    if not stats:
        stats = UserStats(user_id=user.id, total_stars=0, lifetime_stars=0, chests_available=0)
        db.session.add(stats)
        db.session.commit()
    topics_progress = []
    for prog in UserTopicProgress.query.filter_by(user_id=user.id):
        topic = Topic.query.get(prog.topic_id)
        pct = round(100 * prog.correct_attempts / max(1, prog.total_attempts))
        topics_progress.append({
            'operation': topic.operation if topic else None,
            'name': topic.name if topic else None,
            'total_attempts': prog.total_attempts,
            'correct_attempts': prog.correct_attempts,
            'progress_pct': pct,
            'best_streak': prog.best_streak,
        })
    from gamification import STATUS_NAMES
    return jsonify({
        'gamification': {
            'total_stars': stats.total_stars,
            'lifetime_stars': stats.lifetime_stars or 0,
            'current_streak': stats.current_streak,
            'best_streak': stats.best_streak,
            'status': stats.status,
            'status_name': STATUS_NAMES.get(stats.status, stats.status),
            'chests_available': stats.chests_available,
            'topics_progress': topics_progress,
        }
    })


@app.route('/api/profile')
def api_profile_get():
    """Профиль текущего пользователя: школа, класс, уровень, звёзды, сундуки, учитель."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    stats = UserStats.query.filter_by(user_id=user.id).first()
    if not stats:
        stats = UserStats(user_id=user.id, total_stars=0, lifetime_stars=0, chests_available=0)
        db.session.add(stats)
        db.session.commit()
    from gamification import STATUS_NAMES
    teachers = []
    for link in UserStudentLink.query.filter_by(student_id=user.id).filter(UserStudentLink.teacher_id.isnot(None)):
        t = User.query.get(link.teacher_id)
        if t:
            teachers.append(t.name or t.email)
    return jsonify({
        'name': user.name or '',
        'email': user.email or '',
        'school': getattr(user, 'school', None) or '',
        'school_class': getattr(user, 'school_class', None) or '',
        'level': stats.status,
        'level_name': STATUS_NAMES.get(stats.status, stats.status),
        'total_stars': stats.total_stars,
        'lifetime_stars': stats.lifetime_stars or 0,
        'chests_available': stats.chests_available,
        'current_streak': stats.current_streak,
        'best_streak': stats.best_streak,
        'teachers': teachers,
    })


@app.route('/api/profile', methods=['PATCH', 'PUT'])
def api_profile_update():
    """Обновить школу и класс текущего пользователя."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    if 'school' in data:
        user.school = (data['school'] or '').strip() or None
    if 'school_class' in data:
        user.school_class = (data['school_class'] or '').strip() or None
    db.session.commit()
    return jsonify({'ok': True, 'school': user.school, 'school_class': user.school_class})


def require_role(*roles):
    """Decorator: require current user to have one of the roles."""
    def wrapper(f):
        from functools import wraps
        @wraps(f)
        def inner(*args, **kwargs):
            user = get_current_user()
            if not user or user.role not in roles:
                return jsonify({'error': 'Forbidden'}), 403
            return f(*args, **kwargs)
        return inner
    return wrapper


@app.route('/api/teacher/students')
@require_role(ROLE_TEACHER, ROLE_ADMIN)
def api_teacher_students():
    """List students (linked to teacher or all if admin)."""
    user = get_current_user()
    if user.role == ROLE_ADMIN:
        students = User.query.filter_by(role=ROLE_STUDENT).all()
    else:
        links = UserStudentLink.query.filter_by(teacher_id=user.id).all()
        student_ids = [l.student_id for l in links]
        students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []
    out = []
    for s in students:
        stats = UserStats.query.filter_by(user_id=s.id).first()
        prog = UserTopicProgress.query.filter_by(user_id=s.id).all()
        out.append({
            'id': s.id,
            'email': s.email,
            'name': s.name,
            'total_stars': stats.total_stars if stats else 0,
            'current_streak': stats.current_streak if stats else 0,
            'topics_count': len(prog),
            'progress_summary': [{'operation': Topic.query.get(p.topic_id).operation if Topic.query.get(p.topic_id) else None, 'progress_pct': round(100 * p.correct_attempts / max(1, p.total_attempts))} for p in prog],
        })
    return jsonify({'students': out})


@app.route('/api/teacher/students/<int:student_id>')
@require_role(ROLE_TEACHER, ROLE_ADMIN)
def api_teacher_student_detail(student_id):
    """One student: progress, attempts, error types."""
    user = get_current_user()
    if user.role != ROLE_ADMIN:
        link = UserStudentLink.query.filter_by(teacher_id=user.id, student_id=student_id).first()
        if not link:
            return jsonify({'error': 'Forbidden'}), 403
    student = User.query.get(student_id)
    if not student or student.role != ROLE_STUDENT:
        return jsonify({'error': 'Not found'}), 404
    stats = UserStats.query.filter_by(user_id=student.id).first()
    prog_list = UserTopicProgress.query.filter_by(user_id=student.id).all()
    topics_progress = []
    for p in prog_list:
        topic = Topic.query.get(p.topic_id)
        topics_progress.append({
            'operation': topic.operation if topic else None,
            'name': topic.name if topic else None,
            'total_attempts': p.total_attempts,
            'correct_attempts': p.correct_attempts,
            'progress_pct': round(100 * p.correct_attempts / max(1, p.total_attempts)),
            'best_streak': p.best_streak,
        })
    attempts = Attempt.query.filter_by(user_id=student.id).order_by(Attempt.created_at.desc()).limit(100).all()
    error_counts = {}
    for a in attempts:
        if not a.is_correct and a.errors:
            for k, v in a.errors.items():
                if v and isinstance(v, bool):
                    error_counts[k] = error_counts.get(k, 0) + 1
    from gamification import STATUS_NAMES
    return jsonify({
        'student': {'id': student.id, 'email': student.email, 'name': student.name},
        'gamification': {
            'total_stars': stats.total_stars if stats else 0,
            'current_streak': stats.current_streak if stats else 0,
            'best_streak': stats.best_streak if stats else 0,
            'status': stats.status if stats else 'concentration_qi',
            'status_name': STATUS_NAMES.get(stats.status, stats.status) if stats else 'Концентрация ци',
            'chests_available': stats.chests_available if stats else 0,
        },
        'topics_progress': topics_progress,
        'recent_attempts': [{'id': a.id, 'operation': a.operation, 'is_correct': a.is_correct, 'created_at': a.created_at.isoformat() if a.created_at else None} for a in attempts[:20]],
        'error_type_counts': error_counts,
    })


@app.route('/api/parent/children')
@require_role(ROLE_PARENT, ROLE_ADMIN)
def api_parent_children():
    """List children linked to parent."""
    user = get_current_user()
    if user.role == ROLE_ADMIN:
        students = User.query.filter_by(role=ROLE_STUDENT).all()
    else:
        links = UserStudentLink.query.filter_by(parent_id=user.id).all()
        student_ids = [l.student_id for l in links]
        students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []
    out = [{'id': s.id, 'email': s.email, 'name': s.name} for s in students]
    return jsonify({'children': out})


@app.route('/api/parent/children/<int:child_id>/dashboard')
@require_role(ROLE_PARENT, ROLE_ADMIN)
def api_parent_dashboard(child_id):
    """Dashboard for one child: progress, achievements."""
    user = get_current_user()
    if user.role != ROLE_ADMIN:
        link = UserStudentLink.query.filter_by(parent_id=user.id, student_id=child_id).first()
        if not link:
            return jsonify({'error': 'Forbidden'}), 403
    student = User.query.get(child_id)
    if not student or student.role != ROLE_STUDENT:
        return jsonify({'error': 'Not found'}), 404
    stats = UserStats.query.filter_by(user_id=student.id).first()
    prog_list = UserTopicProgress.query.filter_by(user_id=student.id).all()
    topics_progress = [{'name': Topic.query.get(p.topic_id).name if Topic.query.get(p.topic_id) else None, 'progress_pct': round(100 * p.correct_attempts / max(1, p.total_attempts))} for p in prog_list]
    events = EventLog.query.filter_by(user_id=student.id).order_by(EventLog.created_at.desc()).limit(20).all()
    from gamification import STATUS_NAMES
    return jsonify({
        'child': {'id': student.id, 'email': student.email, 'name': student.name},
        'total_stars': stats.total_stars if stats else 0,
        'current_streak': stats.current_streak if stats else 0,
        'best_streak': stats.best_streak if stats else 0,
        'status': stats.status if stats else 'concentration_qi',
        'status_name': STATUS_NAMES.get(stats.status, stats.status) if stats else 'Концентрация ци',
        'chests_available': stats.chests_available if stats else 0,
        'topics_progress': topics_progress,
        'recent_events': [{'event_type': e.event_type, 'created_at': e.created_at.isoformat() if e.created_at else None} for e in events],
    })


@app.route('/api/new_task', methods=['GET'])
def new_task():
    operation = request.args.get('operation', 'add')
    if operation not in VALID_OPERATIONS:
        operation = 'add'

    current_user = get_current_user()
    if current_user:
        ev = EventLog(user_id=current_user.id, event_type='task_start', payload={'operation': operation})
        db.session.add(ev)
        db.session.commit()

    if operation == 'add':
        num1, den1, num2, den2 = generate_task()
        correct = compute_add_subtract(num1, den1, num2, den2, 'add')
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2, 'operation': 'add'},
            'correct': correct
        })

    if operation == 'subtract':
        num1, den1, num2, den2 = generate_task()
        test_common = lcm(den1, den2)
        t1 = num1 * (test_common // den1)
        t2 = num2 * (test_common // den2)
        if t1 < t2:
            num1, den1, num2, den2 = num2, den2, num1, den1
        correct = compute_add_subtract(num1, den1, num2, den2, 'subtract')
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2, 'operation': 'subtract'},
            'correct': correct
        })

    if operation == 'multiply':
        num1, den1, num2, den2 = generate_task()
        correct = compute_multiply(num1, den1, num2, den2)
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2, 'operation': 'multiply'},
            'correct': correct
        })

    if operation == 'divide':
        num1, den1, num2, den2 = generate_task()
        correct = compute_divide(num1, den1, num2, den2)
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2, 'operation': 'divide'},
            'correct': correct
        })

    if operation == 'power':
        num, den = generate_fraction()
        exponent = random.randint(2, 4)
        correct = compute_power(num, den, exponent)
        return jsonify({
            'task': {'num': num, 'den': den, 'exponent': exponent, 'operation': 'power'},
            'correct': correct
        })

    if operation == 'compare':
        num1, den1, num2, den2 = generate_task()
        correct = compute_compare(num1, den1, num2, den2)
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2, 'operation': 'compare'},
            'correct': correct
        })

    if operation == 'reduce':
        num, den = generate_reducible_fraction()
        correct = compute_reduce(num, den)
        return jsonify({
            'task': {'num': num, 'den': den, 'operation': 'reduce'},
            'correct': correct
        })

    if operation == 'convert':
        direction = random.choice(['mixed_to_improper', 'improper_to_mixed'])
        if direction == 'mixed_to_improper':
            int_part = random.randint(1, 5)
            num, den = generate_fraction()
            correct = mixed_to_improper(int_part, num, den)
            return jsonify({
                'task': {'int_part': int_part, 'num': num, 'den': den, 'operation': 'convert', 'convert_direction': 'mixed_to_improper'},
                'correct': correct
            })
        else:
            # improper: числитель > знаменатель, но не слишком большой
            den = random.randint(2, 9)
            num = random.randint(den + 1, den * 5)
            correct = improper_to_mixed(num, den)
            return jsonify({
                'task': {'num': num, 'den': den, 'operation': 'convert', 'convert_direction': 'improper_to_mixed'},
                'correct': correct
            })

    # --- Обыкновенные дроби 5 класс (12 тем) ---

    if operation == 'add_subtract_same_den':
        den = random.randint(2, 12)
        num1 = random.randint(1, den - 1)
        num2 = random.randint(1, den - 1)
        op_add = random.choice([True, False])
        if not op_add and num1 < num2:
            num1, num2 = num2, num1
        real_op = 'add' if op_add else 'subtract'
        correct = compute_add_subtract(num1, den, num2, den, real_op)
        return jsonify({
            'task': {'num1': num1, 'den1': den, 'num2': num2, 'den2': den, 'operation': 'add_subtract_same_den', 'op_sym': '+' if op_add else '−'},
            'correct': correct
        })

    if operation == 'natural_div_fraction':
        natural = random.randint(2, 12)
        num, den = generate_fraction()
        if num == 0:
            num = 1
        res_num = natural * den
        res_den = num
        g = gcd(res_num, res_den)
        res_num, res_den = res_num // g, res_den // g
        return jsonify({
            'task': {'natural': natural, 'num': num, 'den': den, 'operation': 'natural_div_fraction'},
            'correct': {'result_num': res_num, 'result_den': res_den}
        })

    if operation == 'mixed_numbers':
        direction = random.choice(['mixed_to_improper', 'improper_to_mixed'])
        if direction == 'mixed_to_improper':
            int_part = random.randint(1, 5)
            num, den = generate_fraction()
            correct = mixed_to_improper(int_part, num, den)
            return jsonify({
                'task': {'int_part': int_part, 'num': num, 'den': den, 'operation': 'mixed_numbers', 'convert_direction': 'mixed_to_improper'},
                'correct': correct
            })
        else:
            den = random.randint(2, 9)
            num = random.randint(den + 1, den * 5)
            correct = improper_to_mixed(num, den)
            return jsonify({
                'task': {'num': num, 'den': den, 'operation': 'mixed_numbers', 'convert_direction': 'improper_to_mixed'},
                'correct': correct
            })

    if operation == 'add_subtract_mixed':
        d1 = random.randint(2, 8)
        d2 = random.randint(2, 8)
        int1 = random.randint(1, 4)
        n1 = random.randint(1, d1 - 1)
        int2 = random.randint(1, 4)
        n2 = random.randint(1, d2 - 1)
        op_add = random.choice([True, False])
        num1, den1 = int1 * d1 + n1, d1
        num2, den2 = int2 * d2 + n2, d2
        if not op_add and num1 * den2 < num2 * den1:
            int1, n1, d1, int2, n2, d2 = int2, n2, d2, int1, n1, d1
            num1, den1, num2, den2 = num2, den2, num1, den1
        real_op = 'add' if op_add else 'subtract'
        correct = compute_add_subtract(num1, den1, num2, den2, real_op)
        return jsonify({
            'task': {'int1': int1, 'n1': n1, 'd1': d1, 'int2': int2, 'n2': n2, 'd2': d2,
                     'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2,
                     'operation': 'add_subtract_mixed', 'op_sym': '+' if op_add else '−'},
            'correct': correct
        })

    if operation == 'basic_property':
        num, den = generate_fraction()
        k = random.randint(2, 5)
        target_den = den * k
        res_num = num * k
        res_den = target_den
        return jsonify({
            'task': {'num': num, 'den': den, 'target_den': target_den, 'operation': 'basic_property'},
            'correct': {'result_num': res_num, 'result_den': res_den}
        })

    if operation == 'common_denominator':
        num1, den1, num2, den2 = generate_task()
        common = lcm(den1, den2)
        new_num1 = num1 * (common // den1)
        new_num2 = num2 * (common // den2)
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2, 'operation': 'common_denominator'},
            'correct': {'common_den': common, 'new_num1': new_num1, 'new_num2': new_num2}
        })

    if operation == 'compare_add_subtract':
        real = random.choice(['compare', 'add', 'subtract'])
        num1, den1, num2, den2 = generate_task()
        if real == 'subtract':
            test_common = lcm(den1, den2)
            t1 = num1 * (test_common // den1)
            t2 = num2 * (test_common // den2)
            if t1 < t2:
                num1, den1, num2, den2 = num2, den2, num1, den1
        if real == 'compare':
            correct = compute_compare(num1, den1, num2, den2)
        else:
            correct = compute_add_subtract(num1, den1, num2, den2, real)
        return jsonify({
            'task': {'num1': num1, 'den1': den1, 'num2': num2, 'den2': den2,
                     'operation': 'compare_add_subtract', 'real_operation': real},
            'correct': correct
        })

    if operation == 'fraction_of_number':
        num, den = generate_fraction()
        whole = random.randint(5, 50)
        res_num = whole * num
        res_den = den
        g = gcd(res_num, res_den)
        res_num, res_den = res_num // g, res_den // g
        return jsonify({
            'task': {'num': num, 'den': den, 'whole': whole, 'operation': 'fraction_of_number'},
            'correct': {'result_num': res_num, 'result_den': res_den}
        })

    if operation == 'whole_from_part':
        num, den = generate_fraction()
        part = random.randint(2, 30)
        whole_num = part * den
        whole_den = num
        g = gcd(whole_num, whole_den)
        whole_num, whole_den = whole_num // g, whole_den // g
        return jsonify({
            'task': {'num': num, 'den': den, 'part': part, 'operation': 'whole_from_part'},
            'correct': {'result_num': whole_num, 'result_den': whole_den}
        })

    # --- Десятичные дроби ---

    if operation == 'decimal_add':
        a_num, a_den = _gen_decimal_int(50, 2)
        b_num, b_den = _gen_decimal_int(50, 2)
        common = a_den * b_den // gcd(a_den, b_den)
        r_num = a_num * (common // a_den) + b_num * (common // b_den)
        r_den = common
        return jsonify({
            'task': {
                'operation': 'decimal_add',
                'a_num': a_num, 'a_den': a_den,
                'b_num': b_num, 'b_den': b_den,
                'a_str': _decimal_to_str(a_num, a_den),
                'b_str': _decimal_to_str(b_num, b_den),
            },
            'correct': {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        })

    if operation == 'decimal_subtract':
        a_num, a_den = _gen_decimal_int(50, 2)
        b_num, b_den = _gen_decimal_int(50, 2)
        common = a_den * b_den // gcd(a_den, b_den)
        a_val = a_num * (common // a_den)
        b_val = b_num * (common // b_den)
        if a_val < b_val:
            a_num, a_den, b_num, b_den = b_num, b_den, a_num, a_den
            common = a_den * b_den // gcd(a_den, b_den)
            a_val = a_num * (common // a_den)
            b_val = b_num * (common // b_den)
        r_num = a_val - b_val
        r_den = common
        return jsonify({
            'task': {
                'operation': 'decimal_subtract',
                'a_num': a_num, 'a_den': a_den,
                'b_num': b_num, 'b_den': b_den,
                'a_str': _decimal_to_str(a_num, a_den),
                'b_str': _decimal_to_str(b_num, b_den),
            },
            'correct': {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        })

    if operation == 'decimal_multiply':
        a_num, a_den = _gen_decimal_int(20, 2)
        b_num, b_den = _gen_decimal_int(20, 2)
        r_num = a_num * b_num
        r_den = a_den * b_den
        g = gcd(r_num, r_den)
        r_num, r_den = r_num // g, r_den // g
        return jsonify({
            'task': {
                'operation': 'decimal_multiply',
                'a_num': a_num, 'a_den': a_den,
                'b_num': b_num, 'b_den': b_den,
                'a_str': _decimal_to_str(a_num, a_den),
                'b_str': _decimal_to_str(b_num, b_den),
            },
            'correct': {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        })

    if operation == 'decimal_divide':
        # Делимое и натуральный делитель или простая десятичная, чтобы результат был конечным
        if random.random() < 0.5:
            a_num, a_den = _gen_decimal_int(30, 1)
            b = random.randint(2, 9)
            r_num = a_num
            r_den = a_den * b
            g = gcd(r_num, r_den)
            r_num, r_den = r_num // g, r_den // g
            return jsonify({
                'task': {'operation': 'decimal_divide', 'a_str': _decimal_to_str(a_num, a_den), 'b_str': str(b), 'b_int': b, 'a_num': a_num, 'a_den': a_den},
                'correct': {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
            })
        else:
            a_num, a_den = _gen_decimal_int(20, 1)
            b_num, b_den = _gen_decimal_int(5, 1)
            if b_num == 0:
                b_num = 1
            r_num = a_num * b_den
            r_den = a_den * b_num
            g = gcd(r_num, r_den)
            r_num, r_den = r_num // g, r_den // g
            return jsonify({
                'task': {
                    'operation': 'decimal_divide',
                    'a_str': _decimal_to_str(a_num, a_den), 'b_str': _decimal_to_str(b_num, b_den),
                    'a_num': a_num, 'a_den': a_den, 'b_num': b_num, 'b_den': b_den
                },
                'correct': {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
            })

    if operation == 'decimal_compare':
        a_num, a_den = _gen_decimal_int(30, 2)
        b_num, b_den = _gen_decimal_int(30, 2)
        left = a_num * b_den
        right = b_num * a_den
        if left < right:
            comp = '<'
        elif left > right:
            comp = '>'
        else:
            comp = '='
        return jsonify({
            'task': {
                'operation': 'decimal_compare',
                'a_str': _decimal_to_str(a_num, a_den), 'b_str': _decimal_to_str(b_num, b_den),
                'a_num': a_num, 'a_den': a_den, 'b_num': b_num, 'b_den': b_den,
            },
            'correct': {'comparison': comp}
        })

    if operation == 'decimal_to_common':
        # Десятичная -> обыкновенная: 0,75 -> 3/4
        den_10 = random.choice([10, 100])
        num = random.randint(1, den_10 - 1)
        g = gcd(num, den_10)
        res_num = num // g
        res_den = den_10 // g
        return jsonify({
            'task': {'operation': 'decimal_to_common', 'decimal_str': _decimal_to_str(num, den_10), 'num': num, 'den': den_10},
            'correct': {'result_num': res_num, 'result_den': res_den, 'result_str': f'{res_num}/{res_den}'}
        })

    if operation == 'common_to_decimal':
        num, den = random.choice([(1, 2), (1, 4), (3, 4), (1, 5), (2, 5), (3, 5), (4, 5), (1, 8), (3, 8), (5, 8), (7, 8)])
        result_num = num * (10 ** 4) // den
        result_den = 10 ** 4
        while result_den > 1 and result_num % 10 == 0:
            result_num //= 10
            result_den //= 10
        result_str = _decimal_to_str(result_num, result_den)
        return jsonify({
            'task': {'operation': 'common_to_decimal', 'num': num, 'den': den},
            'correct': {'result_num': result_num, 'result_den': result_den, 'result_str': result_str}
        })

    if operation == 'decimal_round':
        integral = random.randint(0, 99)
        frac_digits = random.randint(3, 5)
        den = 10 ** frac_digits
        frac = random.randint(0, den - 1)
        num = integral * den + frac
        to_places = random.randint(1, 2)
        d = Decimal(num) / Decimal(den)
        rounded = d.quantize(Decimal(10) ** -to_places, rounding=ROUND_HALF_UP)
        r_num = int(rounded * (10 ** to_places))
        r_den = 10 ** to_places
        return jsonify({
            'task': {
                'operation': 'decimal_round',
                'decimal_str': _decimal_to_str(num, den),
                'num': num, 'den': den,
                'to_places': to_places
            },
            'correct': {'result_str': _decimal_to_str(r_num, r_den), 'result_num': r_num, 'result_den': r_den}
        })

    return jsonify({'task': {}, 'correct': {}})


def _decimal_equals(user_str, correct_num, correct_den):
    """Сравнивает ввод пользователя (строка с запятой) с правильным (num, den)."""
    parsed = _parse_decimal(user_str)
    if not parsed:
        return False
    u_num, u_den = parsed
    if correct_den == 0:
        return False
    return u_num * correct_den == correct_num * u_den


def _decimal_error_parts(user_str, correct_num, correct_den):
    """При неверном ответе возвращает (ошибка в целой части, ошибка в дробной части)."""
    parsed = _parse_decimal(user_str)
    if not parsed or correct_den <= 0:
        return (True, True)
    u_num, u_den = parsed
    correct_int = correct_num // correct_den
    correct_frac = correct_num % correct_den
    user_int = u_num // u_den
    user_frac = (u_num % u_den) * correct_den // u_den
    return (user_int != correct_int, user_frac != correct_frac)


def _decimal_result_error_hint(errors):
    """Текст подсказки для разбора: ошибка в целой части, в дробной или в обоих."""
    if not errors.get('result'):
        return ""
    err_int = errors.get('result_integer', False)
    err_frac = errors.get('result_fractional', False)
    if err_int and not err_frac:
        return "Ошибка в вычислении целой части числа. "
    if err_frac and not err_int:
        return "Ошибка в вычислении числа после запятой. "
    if err_int and err_frac:
        return "Ошибка и в целой части, и в части после запятой. "
    return ""


def parse_result(s):
    """Парсит строку ответа с обыкновенной дробью.

    Допускаются варианты:
    - 'num/den'  → (num, den)
    - 'k'        → (k, 1)  (целое число как дробь с знаменателем 1)

    Возвращает (num, den) или None.
    """
    s = (s or '').strip()
    if '/' not in s:
        # Разрешаем целое число как дробь со знаменателем 1 (например, 1 == 1/1).
        try:
            n = int(s)
        except ValueError:
            return None
        return (n, 1)
    parts = s.split('/')
    if len(parts) != 2:
        return None
    try:
        n = int(parts[0].strip())
        d = int(parts[1].strip())
        if d <= 0:
            return None
        return (n, d)
    except ValueError:
        return None


def _result_matches(parsed, correct):
    """Сравнение ответа ученика с правильной дробью из correct.

    - обычный случай: числитель и знаменатель должны совпасть;
    - если правильный числитель 0, разрешаем любую дробь вида 0/den
      и целое 0 (parsed = (0, 1)).
    """
    if not parsed:
        return False
    n, d = parsed
    if correct.get('result_num') == 0 and n == 0:
        return True
    return n == correct.get('result_num') and d == correct.get('result_den')


def build_analysis(operation, is_correct, errors, task, correct, user, detailed=False):
    """Формирует текст разбора и alt_text для любой операции. detailed=True — развёрнутый разбор для 5 класса."""
    text = ""
    alt_text = ""

    if is_correct:
        text = "Верно! Молодец!"
        alt_text = "Отлично! Вы правильно выполнили все шаги."
        return text, alt_text

    # Ошибка
    if operation in ('add', 'subtract'):
        op_sym = '−' if operation == 'subtract' else '+'
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        if errors.get('common_den'):
            if detailed:
                text = f"Разбор по шагам.\n\nШаг 1 — Общий знаменатель. Чтобы {'сложить' if operation == 'add' else 'вычесть'} дроби с разными знаменателями, их сначала приводят к одному знаменателю. Он должен делиться на оба: на {den1} и на {den2}. Это НОК({den1}, {den2}) = {correct['common_den']}. Проверка: {correct['common_den']} ÷ {den1} = {correct['common_den'] // den1}, {correct['common_den']} ÷ {den2} = {correct['common_den'] // den2}. Исправьте общий знаменатель."
                alt_text = f"НОК({den1}, {den2}) = {correct['common_den']}. Переберите кратные большего из знаменателей, пока не найдётся число, делящееся на оба."
            else:
                text = f"Общий знаменатель должен делиться на {den1} и {den2}. Правильный: {correct['common_den']}."
                alt_text = f"НОК({den1}, {den2}) = {correct['common_den']}. Проверка: {correct['common_den']} ÷ {den1} = {correct['common_den']//den1}, {correct['common_den']} ÷ {den2} = {correct['common_den']//den2}."
        elif errors.get('new_num1') or errors.get('new_num2'):
            if detailed:
                text = f"Разбор по шагам.\n\nШаг 2 — Приведение к общему знаменателю. Общий знаменатель {correct['common_den']}. Для дроби {num1}/{den1} дополнительный множитель = {correct['common_den']} ÷ {den1} = {correct['common_den']//den1}. Получаем: {num1}×{correct['common_den']//den1} = {correct['new_num1']}, т.е. {correct['new_num1']}/{correct['common_den']}. Для {num2}/{den2}: множитель = {correct['common_den']//den2}, получаем {correct['new_num2']}/{correct['common_den']}. Проверьте оба числителя."
                alt_text = f"Правило: числитель и знаменатель умножаем на (общий_знаменатель ÷ знаменатель). {num1}/{den1} → {correct['new_num1']}/{correct['common_den']}, {num2}/{den2} → {correct['new_num2']}/{correct['common_den']}."
            else:
                text = f"Неправильный дополнительный множитель. Для {num1}/{den1} → {correct['new_num1']}/{correct['common_den']}, для {num2}/{den2} → {correct['new_num2']}/{correct['common_den']}."
                alt_text = f"Числитель и знаменатель умножаем на (общий_знаменатель / знаменатель). {num1}/{den1} = {num1}×{correct['common_den']//den1}/{correct['common_den']} = {correct['new_num1']}/{correct['common_den']}."
        elif errors.get('result'):
            raw = correct['new_num1'] - correct['new_num2'] if operation == 'subtract' else correct['new_num1'] + correct['new_num2']
            g = gcd(abs(raw), correct['common_den'])
            if detailed:
                if g == 1:
                    text = f"Разбор по шагам.\n\nШаг 3 — Действие с числителями. Дроби приведены к знаменателю {correct['common_den']}. {'Складываем' if operation == 'add' else 'Вычитаем'} числители: {correct['new_num1']} {op_sym} {correct['new_num2']} = {raw}. Знаменатель тот же: {raw}/{correct['common_den']}. НОД({raw}, {correct['common_den']}) = 1 — дробь несократима. Ответ: {correct['result_num']}/{correct['result_den']}."
                    alt_text = f"При одинаковых знаменателях: числители {'складываем' if operation == 'add' else 'вычитаем'}, знаменатель не меняем. {correct['new_num1']}/{correct['common_den']} {op_sym} {correct['new_num2']}/{correct['common_den']} = {raw}/{correct['common_den']}. НОД = 1 — не сокращаем. Ответ: {correct['result_num']}/{correct['result_den']}."
                else:
                    text = f"Разбор по шагам.\n\nШаг 3 — Действие и сокращение. Числители: {correct['new_num1']} {op_sym} {correct['new_num2']} = {raw}. Получаем {raw}/{correct['common_den']}. Сокращаем: НОД({raw}, {correct['common_den']}) = {g}. Делим числитель и знаменатель на {g}: получается {correct['result_num']}/{correct['result_den']}. Ответ: {correct['result_num']}/{correct['result_den']}."
                    alt_text = f"После {'сложения' if operation == 'add' else 'вычитания'} числителей: {raw}/{correct['common_den']}. Сокращаем на НОД = {g} → {correct['result_num']}/{correct['result_den']}."
            elif g == 1:
                text = f"{'Разность' if operation == 'subtract' else 'Сумма'} числителей = {raw}. НОД = 1 — значит, не сокращаем вовсе. Ответ: {correct['result_num']}/{correct['result_den']}."
                alt_text = f"{correct['new_num1']}/{correct['common_den']} {op_sym} {correct['new_num2']}/{correct['common_den']} = {raw}/{correct['common_den']}. НОД = 1 — дробь уже несократима, не сокращаем вовсе."
            else:
                text = f"{'Разность' if operation == 'subtract' else 'Сумма'} числителей = {raw}. Сокращаем на НОД = {g}. Ответ: {correct['result_num']}/{correct['result_den']}."
                alt_text = f"{correct['new_num1']}/{correct['common_den']} {op_sym} {correct['new_num2']}/{correct['common_den']} = {raw}/{correct['common_den']}. Сокращаем на НОД = {g} — получается {correct['result_num']}/{correct['result_den']}."
    elif operation == 'multiply':
        a, b, c, d = task['num1'], task['den1'], task['num2'], task['den2']
        prod_num, prod_den = a * c, b * d
        g = gcd(prod_num, prod_den)
        if detailed:
            text = f"Разбор по шагам.\n\nШаг 1 — Умножение дробей. Правило: числитель на числитель, знаменатель на знаменатель. {a}/{b} × {c}/{d} = (a×c)/(b×d) = {a}×{c}/{b}×{d} = {prod_num}/{prod_den}.\n\nШаг 2 — Сокращение. НОД({prod_num}, {prod_den}) = {g}. Делим числитель и знаменатель на {g}: {prod_num} ÷ {g} = {correct['result_num']}, {prod_den} ÷ {g} = {correct['result_den']}. Ответ: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"Умножение дробей: (числитель×числитель)/(знаменатель×знаменатель). {a}/{b} × {c}/{d} = {prod_num}/{prod_den}. После сокращения на НОД = {g} получаем {correct['result_num']}/{correct['result_den']}."
        elif g == 1:
            text = f"Произведение дробей: ({a}×{c})/({b}×{d}) = {prod_num}/{prod_den}. НОД = 1 — не сокращаем вовсе. Ответ: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"{a}/{b} × {c}/{d} = {prod_num}/{prod_den}. Дробь уже несократима."
        else:
            text = f"Произведение дробей: ({a}×{c})/({b}×{d}) = {prod_num}/{prod_den}. После сокращения на НОД = {g}: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"{a}/{b} × {c}/{d} = {prod_num}/{prod_den}. НОД({prod_num},{prod_den}) = {g}. Делим числитель и знаменатель — получается {correct['result_num']}/{correct['result_den']}."
    elif operation == 'divide':
        a, b, c, d = task['num1'], task['den1'], task['num2'], task['den2']
        quot_num, quot_den = a * d, b * c
        g = gcd(quot_num, quot_den)
        if detailed:
            text = f"Разбор по шагам.\n\nШаг 1 — Деление на дробь заменяем умножением на обратную. Обратная к {c}/{d} — это {d}/{c}. Значит ({a}/{b}) ÷ ({c}/{d}) = ({a}/{b}) × ({d}/{c}) = (a×d)/(b×c) = {a}×{d}/{b}×{c} = {quot_num}/{quot_den}.\n\nШаг 2 — Сокращение. НОД({quot_num}, {quot_den}) = {g}. Делим числитель и знаменатель на {g}. Ответ: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"Правило: деление на дробь = умножение на обратную. ({a}/{b}) ÷ ({c}/{d}) = ({a}/{b}) × ({d}/{c}) = {quot_num}/{quot_den}. После сокращения: {correct['result_num']}/{correct['result_den']}."
        elif g == 1:
            text = f"Деление на дробь = умножение на обратную: {a}/{b} × {d}/{c} = {quot_num}/{quot_den}. НОД = 1 — не сокращаем вовсе."
            alt_text = f"({a}/{b}) ÷ ({c}/{d}) = {a*d}/{b*c}. Дробь уже несократима."
        else:
            text = f"Деление на дробь = умножение на обратную: {a}/{b} × {d}/{c} = {quot_num}/{quot_den}. Сокращаем на НОД = {g}: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"({a}/{b}) ÷ ({c}/{d}) = ({a}/{b}) × ({d}/{c}) = {quot_num}/{quot_den}. После сокращения: {correct['result_num']}/{correct['result_den']}."
    elif operation == 'power':
        num, den, n = task['num'], task['den'], task['exponent']
        res_num, res_den = num ** n, den ** n
        g = gcd(res_num, res_den)
        if detailed:
            text = f"Разбор по шагам.\n\nСтепень дроби: числитель и знаменатель возводим в степень отдельно. ({num}/{den})^{n} = {num}^{n}/{den}^{n} = {res_num}/{res_den}. НОД({res_num}, {res_den}) = {g}. Сокращаем: делим числитель и знаменатель на {g}. Ответ: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"Правило: (a/b)^n = a^n / b^n. ({num}/{den})^{n} = {res_num}/{res_den}. После сокращения на НОД = {g} получаем {correct['result_num']}/{correct['result_den']}."
        elif g == 1:
            text = f"({num}/{den})^{n} = {res_num}/{res_den}. НОД = 1 — не сокращаем вовсе."
            alt_text = f"Степень дроби = степень числителя и знаменателя: {num}^{n}/{den}^{n} = {res_num}/{res_den}. Дробь уже несократима."
        else:
            text = f"({num}/{den})^{n} = {res_num}/{res_den}. Сокращаем на НОД = {g}: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"Степень дроби = степень числителя и знаменателя: {num}^{n}/{den}^{n} = {res_num}/{res_den}. Сокращаем НОД."
    elif operation == 'compare':
        a, b, c, d = task['num1'], task['den1'], task['num2'], task['den2']
        if detailed:
            text = f"Разбор по шагам.\n\nЧтобы сравнить дроби {a}/{b} и {c}/{d}, можно привести их к общему знаменателю и сравнить числители. Другой способ — сравнить произведения «крестом»: a×d и c×b. Здесь {a}×{d} = {a*d}, {c}×{b} = {c*b}. Поскольку {a*d} {correct['comparison']} {c*b}, то {a}/{b} {correct['comparison']} {c}/{d}. Правильный знак: {correct['comparison']}."
            alt_text = f"Сравнение дробей: если a×d < c×b, то a/b < c/d; если a×d > c×b, то a/b > c/d; если равны — дроби равны. У нас {a}×{d} = {a*d}, {c}×{b} = {c*b}, значит {a}/{b} {correct['comparison']} {c}/{d}."
        else:
            text = f"Приводим к общему знаменателю или сравниваем произведения: {a}×{d} = {a*d}, {c}×{b} = {c*b}. Знак: {correct['comparison']}."
            alt_text = f"{a}/{b} {correct['comparison']} {c}/{d}, так как {a*d} {correct['comparison']} {c*b}."
    elif operation == 'reduce':
        num, den = task['num'], task['den']
        g = gcd(num, den)
        if detailed:
            text = f"Разбор по шагам.\n\nСокращение дроби — деление числителя и знаменателя на одно и то же число (на их НОД). НОД({num}, {den}) = {g}. Делим: {num} ÷ {g} = {correct['result_num']}, {den} ÷ {g} = {correct['result_den']}. Итого: {num}/{den} = {correct['result_num']}/{correct['result_den']}. Дробь {correct['result_num']}/{correct['result_den']} уже несократима."
            alt_text = f"Чтобы сократить дробь, найдите НОД числителя и знаменателя, затем разделите оба на него. НОД({num}, {den}) = {g}. {num}/{den} = {correct['result_num']}/{correct['result_den']}."
        else:
            text = f"НОД({num}, {den}) = {g}. {num}/{den} = {num//g}/{den//g}."
            alt_text = f"Делим числитель и знаменатель на {g}: {num}÷{g}/{den}÷{g} = {correct['result_num']}/{correct['result_den']}."
    elif operation == 'convert':
        direction = task.get('convert_direction', 'mixed_to_improper')
        if direction == 'mixed_to_improper':
            i, n, d = task['int_part'], task['num'], task['den']
            if detailed:
                text = f"Разбор по шагам.\n\nСмешанное число {i} {n}/{d} — это целая часть {i} плюс дробная часть {n}/{d}. Чтобы записать в виде одной дроби: целую часть представляем в дробях со знаменателем {d}: {i} = {i*d}/{d}. Тогда {i} {n}/{d} = {i*d}/{d} + {n}/{d} = {i*d}+{n}/{d} = {i*d+n}/{d}. Итого: {i*d+n}/{d}."
                alt_text = f"Формула: a b/c = (a×c + b)/c. Здесь: {i} {n}/{d} = ({i}×{d}+{n})/{d} = {i*d+n}/{d}."
            else:
                text = f"{i} {n}/{d} = {i}×{d}+{n} в числителе, знаменатель {d} = {i*d+n}/{d}."
                alt_text = f"Целая часть {i} = {i*d}/{d}. Плюс дробная {n}/{d}. Итого: {i*d+n}/{d}."
        else:
            num, den = task['num'], task['den']
            if detailed:
                text = f"Разбор по шагам.\n\nНеправильная дробь {num}/{den} нужно представить в виде смешанного числа. Делим числитель на знаменатель с остатком: {num} ÷ {den} = {correct['int_part']} (целое частное) и остаток {correct['num']}. Значит {num}/{den} = {correct['int_part']} + {correct['num']}/{den} = {correct['int_part']} {correct['num']}/{den}. Ответ: {correct['int_part']} {correct['num']}/{den}."
                alt_text = f"Разделите числитель на знаменатель уголком: {num} = {correct['int_part']}×{den} + {correct['num']}. Поэтому {num}/{den} = {correct['int_part']} {correct['num']}/{den}."
            else:
                text = f"{num} ÷ {den} = {correct['int_part']} и остаток {correct['num']}. Ответ: {correct['int_part']} {correct['num']}/{den}."
                alt_text = f"{num}/{den} = {num//den} + {num%den}/{den} = {correct['int_part']} {correct['num']}/{correct['den']}."
    elif operation == 'add_subtract_same_den':
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        is_subtract = task.get('op_sym') in ('−', '-', 'subtract')
        op_sym = '−' if is_subtract else '+'
        raw = num1 - num2 if op_sym == '−' else num1 + num2
        g = gcd(abs(raw), den1)
        if g == 1:
            text = f"При одинаковых знаменателях {'вычитаем' if op_sym == '−' else 'складываем'} только числители: {num1} {op_sym} {num2} = {raw}. Знаменатель {den1} не меняем. Ответ: {correct['result_num']}/{correct['result_den']}. НОД = 1 — сокращать не нужно."
            alt_text = f"{num1}/{den1} {op_sym} {num2}/{den1} = {raw}/{den1} = {correct['result_num']}/{correct['result_den']}."
        else:
            text = f"Числители: {num1} {op_sym} {num2} = {raw}. Получаем {raw}/{den1}. Сокращаем на НОД = {g}. Ответ: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"Дроби с одинаковым знаменателем: числители {'вычитаем' if op_sym == '−' else 'складываем'}, знаменатель тот же. {raw}/{den1} после сокращения: {correct['result_num']}/{correct['result_den']}."
    elif operation == 'natural_div_fraction':
        nat, num, den = task['natural'], task['num'], task['den']
        text = f"Деление на дробь — умножение на обратную: {nat} ÷ {num}/{den} = {nat} × {den}/{num} = {nat*den}/{num}. После сокращения: {correct['result_num']}/{correct['result_den']}."
        alt_text = f"Правило: a ÷ (b/c) = a × (c/b). {nat} × {den}/{num} = {correct['result_num']}/{correct['result_den']}."
    elif operation == 'mixed_numbers':
        direction = task.get('convert_direction', 'mixed_to_improper')
        if direction == 'mixed_to_improper':
            i, n, d = task['int_part'], task['num'], task['den']
            text = f"Смешанное число: {i} {n}/{d} = {i}×{d}+{n} в числителе, знаменатель {d}. Ответ: {correct['result_num']}/{correct['result_den']}."
            alt_text = f"{i} {n}/{d} = ({i}×{d}+{n})/{d} = {i*d+n}/{d}."
        else:
            num, den = task['num'], task['den']
            text = f"{num} ÷ {den} = {correct['int_part']} и остаток {correct['num']}. Ответ: {correct['int_part']} {correct['num']}/{den}."
            alt_text = f"{num}/{den} = {correct['int_part']} {correct['num']}/{den}."
    elif operation == 'add_subtract_mixed':
        is_subtract = task.get('op_sym') in ('−', '-', 'subtract')
        text = f"Смешанные числа приведены к дробям и выполнено {'вычитание' if is_subtract else 'сложение'}. Правильный ответ: {correct['result_num']}/{correct['result_den']}."
        alt_text = f"Переведите смешанные в неправильные дроби, приведите к общему знаменателю, выполните действие. Ответ: {correct['result_num']}/{correct['result_den']}."
    elif operation == 'basic_property':
        num, den = task['num'], task['den']
        target = task['target_den']
        k = target // den
        text = f"Основное свойство дроби: числитель и знаменатель умножаем на одно и то же число. {num}/{den} = {num}×{k}/{den}×{k} = {correct['result_num']}/{correct['result_den']}."
        alt_text = f"Чтобы получить знаменатель {target}, домножаем на {k}. {num}/{den} = {correct['result_num']}/{correct['result_den']}."
    elif operation == 'common_denominator':
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        common = correct['common_den']
        text = f"НОК({den1}, {den2}) = {common}. Дополнительный множитель для {num1}/{den1}: {common}//{den1} = {common//den1}. Для {num2}/{den2}: {common//den2}. Получаем {correct['new_num1']}/{common} и {correct['new_num2']}/{common}."
        alt_text = f"Общий знаменатель: {common}. {num1}/{den1} = {correct['new_num1']}/{common}, {num2}/{den2} = {correct['new_num2']}/{common}."
    elif operation == 'compare_add_subtract':
        real = task.get('real_operation', 'add')
        if real == 'compare':
            a, b, c, d = task['num1'], task['den1'], task['num2'], task['den2']
            text = f"Сравнение: {a}×{d} = {a*d}, {c}×{b} = {c*b}. Знак: {correct['comparison']}."
            alt_text = f"{a}/{b} {correct['comparison']} {c}/{d}."
        else:
            a, b, c, d = task['num1'], task['den1'], task['num2'], task['den2']
            op_sym = '−' if real == 'subtract' else '+'
            text = f"Общий знаменатель {correct['common_den']}, числители после приведения: {correct['new_num1']} и {correct['new_num2']}. {'Разность' if real == 'subtract' else 'Сумма'} = {correct['result_num']}/{correct['result_den']}."
            alt_text = f"Приведение к общему знаменателю, затем {'вычитание' if real == 'subtract' else 'сложение'} числителей. Ответ: {correct['result_num']}/{correct['result_den']}."
    elif operation == 'fraction_of_number':
        num, den = task['num'], task['den']
        whole = task['whole']
        text = f"Дробь от числа: умножаем число на дробь. {whole} × {num}/{den} = {whole*num}/{den} = {correct['result_num']}/{correct['result_den']}."
        alt_text = f"Чтобы найти {num}/{den} от {whole}: {whole} × {num}/{den} = {correct['result_num']}/{correct['result_den']}."
    elif operation == 'whole_from_part':
        num, den = task['num'], task['den']
        part = task['part']
        text = f"Если {num}/{den} числа = {part}, то число = {part} ÷ {num}/{den} = {part} × {den}/{num} = {correct['result_num']}/{correct['result_den']}."
        alt_text = f"Целое = часть ÷ дробь. {part} × {den}/{num} = {correct['result_num']}/{correct['result_den']}."
    elif operation == 'decimal_add':
        a_str, b_str = task.get('a_str', ''), task.get('b_str', '')
        err_hint = _decimal_result_error_hint(errors)
        base = f"Сложение: уравняйте знаки после запятой и складывайте по разрядам (целые с целыми, десятые с десятыми). {a_str} + {b_str} = {correct.get('result_str', '')}."
        text = err_hint + base
        alt_text = f"Уравняйте количество знаков после запятой нулями, затем сложите числа как натуральные; в ответе запятую ставим так, чтобы разряды совпадали с слагаемыми. Правильный ответ: {correct.get('result_str', '')}."
    elif operation == 'decimal_subtract':
        a_str, b_str = task.get('a_str', ''), task.get('b_str', '')
        err_hint = _decimal_result_error_hint(errors)
        base = f"Вычитание: уравняйте знаки после запятой и вычитайте по разрядам. {a_str} − {b_str} = {correct.get('result_str', '')}."
        text = err_hint + base
        alt_text = f"Уравняйте количество знаков после запятой, вычитайте как натуральные по разрядам. Правильный ответ: {correct.get('result_str', '')}."
    elif operation == 'decimal_multiply':
        a_str, b_str = task.get('a_str', ''), task.get('b_str', '')
        err_hint = _decimal_result_error_hint(errors)
        base = f"Умножение: перемножаем числа без запятой, в ответе отделяем запятой столько знаков, сколько после запятой в обоих множителях. {a_str} × {b_str} = {correct.get('result_str', '')}."
        text = err_hint + base
        alt_text = f"Число знаков после запятой в ответе = сумма знаков после запятой в множителях. Правильный ответ: {correct.get('result_str', '')}."
    elif operation == 'decimal_divide':
        a_str, b_str = task.get('a_str', ''), task.get('b_str', '')
        err_hint = _decimal_result_error_hint(errors)
        base = f"Деление: {a_str} : {b_str} = {correct.get('result_str', '')}. Сделайте делитель целым, перенеся запятую вправо, затем столько же перенесите в делимом."
        text = err_hint + base
        alt_text = f"Деление на десятичную сводится к делению на натуральное. Правильный ответ: {correct.get('result_str', '')}."
    elif operation == 'decimal_compare':
        a_str, b_str = task.get('a_str', ''), task.get('b_str', '')
        text = f"Сравнение поразрядно: {a_str} и {b_str}. Правильный знак: {correct.get('comparison', '')}."
        alt_text = f"Сравнивайте целые части, затем десятые, сотые и т.д."
    elif operation == 'decimal_to_common':
        text = f"В числителе — число без запятой, в знаменателе — 10 в степени (число знаков после запятой). Сократите. Ответ: {correct.get('result_str', '')}."
        alt_text = f"Например 0,75 = 75/100 = 3/4."
    elif operation == 'common_to_decimal':
        num, den = task['num'], task['den']
        err_hint = _decimal_result_error_hint(errors)
        base = f"Разделите числитель на знаменатель уголком. {num}/{den} = {correct.get('result_str', '')}."
        text = err_hint + base
        alt_text = f"В частном ставьте запятую, когда заканчивается деление целой части. Правильный ответ: {correct.get('result_str', '')}."
    elif operation == 'decimal_round':
        dec_str = task.get('decimal_str', '')
        to_places = task.get('to_places', 1)
        err_hint = _decimal_result_error_hint(errors)
        base = f"Округление до {to_places} знака(ов) после запятой: {dec_str} ≈ {correct.get('result_str', '')}. Если следующая цифра ≥ 5, увеличиваем предыдущую на 1."
        text = err_hint + base
        alt_text = f"Смотрите на цифру справа от нужного разряда. Правильный ответ: {correct.get('result_str', '')}."
    return text, alt_text


def build_visualization(operation, task, correct):
    """Универсальная структура визуализации для фронта."""
    viz = {'operation': operation}
    if operation in ('add', 'subtract', 'multiply', 'divide', 'compare'):
        viz['original'] = {'num1': task['num1'], 'den1': task['den1'], 'num2': task['num2'], 'den2': task['den2']}
    if operation == 'compare' and 'comparison' in correct:
        viz['comparison'] = correct['comparison']
    if operation in ('add', 'subtract'):
        viz['correct_common_den'] = correct['common_den']
        viz['correct_new_nums'] = [correct['new_num1'], correct['new_num2']]
    if 'result_num' in correct:
        viz['correct_result'] = {'num': correct['result_num'], 'den': correct['result_den']}
    if operation == 'add_subtract_same_den':
        viz['operation'] = 'subtract' if task.get('op_sym') in ('−', '-', 'subtract') else 'add'
        viz['original'] = {'num1': task['num1'], 'den1': task['den1'], 'num2': task['num2'], 'den2': task['den2']}
        viz['correct_common_den'] = task['den1']
        viz['correct_new_nums'] = [task['num1'], task['num2']]
        viz['correct_result'] = {'num': correct['result_num'], 'den': correct['result_den']}
    elif operation == 'add_subtract_mixed':
        viz['operation'] = 'subtract' if task.get('op_sym') in ('−', '-', 'subtract') else 'add'
        viz['original'] = {'num1': task['num1'], 'den1': task['den1'], 'num2': task['num2'], 'den2': task['den2']}
        viz['correct_common_den'] = correct['common_den']
        viz['correct_new_nums'] = [correct['new_num1'], correct['new_num2']]
        viz['correct_result'] = {'num': correct['result_num'], 'den': correct['result_den']}
    elif operation == 'compare_add_subtract':
        real = task.get('real_operation', 'add')
        viz['operation'] = real
        viz['original'] = {'num1': task['num1'], 'den1': task['den1'], 'num2': task['num2'], 'den2': task['den2']}
        if real == 'compare' and 'comparison' in correct:
            viz['comparison'] = correct['comparison']
        elif real != 'compare':
            viz['correct_common_den'] = correct['common_den']
            viz['correct_new_nums'] = [correct['new_num1'], correct['new_num2']]
            viz['correct_result'] = {'num': correct['result_num'], 'den': correct['result_den']}
    elif operation == 'mixed_numbers':
        viz['operation'] = 'convert'
        viz['task'] = task
        viz['correct_result'] = correct
    elif operation in ('natural_div_fraction', 'basic_property', 'fraction_of_number', 'whole_from_part') and 'result_num' in correct:
        viz['correct_result'] = {'num': correct['result_num'], 'den': correct['result_den']}
    if operation == 'power':
        viz['original'] = {'num1': task['num'], 'den1': task['den'], 'num2': task['exponent'], 'den2': 1}
    if operation == 'reduce':
        viz['original'] = {'num1': task['num'], 'den1': task['den'], 'num2': 0, 'den2': 1}
    if operation == 'convert':
        viz['task'] = task
        viz['correct_result'] = correct
    if operation.startswith('decimal_'):
        viz['operation'] = operation
        if 'result_str' in correct:
            viz['correct_result'] = viz.get('correct_result') or {'result_str': correct['result_str']}
        if 'comparison' in correct:
            viz['comparison'] = correct['comparison']
    if 'before_reduce' in correct:
        viz['before_reduce'] = correct['before_reduce']
    return viz


@app.route('/api/check', methods=['POST'])
def check():
    data = request.get_json()
    task = data['task']
    user = data['user_answers']
    operation = task.get('operation', 'add')

    def _to_int(v):
        if v is None: return None
        try: return int(v)
        except (TypeError, ValueError): return None

    is_correct = False
    errors = {}

    if operation in ('add', 'subtract'):
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        correct = compute_add_subtract(num1, den1, num2, den2, operation)
        err_common = user.get('common_den') != correct['common_den']
        err_n1 = user.get('new_num1') != correct['new_num1']
        err_n2 = user.get('new_num2') != correct['new_num2']
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        err_result = not res_ok
        errors = {'common_den': err_common, 'new_num1': err_n1, 'new_num2': err_n2, 'result': err_result}
        is_correct = not any(errors.values())

    elif operation == 'multiply':
        correct = compute_multiply(task['num1'], task['den1'], task['num2'], task['den2'])
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = not errors['result']

    elif operation == 'divide':
        correct = compute_divide(task['num1'], task['den1'], task['num2'], task['den2'])
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = not errors['result']

    elif operation == 'power':
        correct = compute_power(task['num'], task['den'], task['exponent'])
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = not errors['result']

    elif operation == 'compare':
        correct = compute_compare(task['num1'], task['den1'], task['num2'], task['den2'])
        user_comp = (user.get('comparison') or '').strip()
        if user_comp not in ('<', '=', '>'):
            user_comp = None
        res_ok = user_comp == correct['comparison']
        errors = {'comparison': not res_ok}
        is_correct = not errors['comparison']

    elif operation == 'reduce':
        correct = compute_reduce(task['num'], task['den'])
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = not errors['result']

    elif operation == 'convert':
        direction = task.get('convert_direction', 'mixed_to_improper')
        if direction == 'mixed_to_improper':
            correct = mixed_to_improper(task['int_part'], task['num'], task['den'])
            parsed = parse_result(user.get('result', ''))
            res_ok = _result_matches(parsed, correct)
            errors = {'result': not res_ok}
        else:
            correct = improper_to_mixed(task['num'], task['den'])
            ui, un, ud = _to_int(user.get('int_part')), _to_int(user.get('num')), _to_int(user.get('den'))
            errors = {'int_part': ui != correct['int_part'], 'num': un != correct['num'], 'den': ud != correct['den']}
            res_ok = not any(errors.values())
        is_correct = res_ok

    elif operation == 'add_subtract_same_den':
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        op_sym = task.get('op_sym', '+')
        real_op = 'subtract' if op_sym in ('−', '-', 'subtract') else 'add'
        correct = compute_add_subtract(num1, den1, num2, den2, real_op)
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'natural_div_fraction':
        correct = {'result_num': task['natural'] * task['den'], 'result_den': task['num']}
        g = gcd(correct['result_num'], correct['result_den'])
        correct['result_num'] //= g
        correct['result_den'] //= g
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'mixed_numbers':
        direction = task.get('convert_direction', 'mixed_to_improper')
        if direction == 'mixed_to_improper':
            correct = mixed_to_improper(task['int_part'], task['num'], task['den'])
            parsed = parse_result(user.get('result', ''))
            res_ok = _result_matches(parsed, correct)
            errors = {'result': not res_ok}
        else:
            correct = improper_to_mixed(task['num'], task['den'])
            ui, un, ud = _to_int(user.get('int_part')), _to_int(user.get('num')), _to_int(user.get('den'))
            errors = {'int_part': ui != correct['int_part'], 'num': un != correct['num'], 'den': ud != correct['den']}
            res_ok = not any(errors.values())
        is_correct = res_ok

    elif operation == 'add_subtract_mixed':
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        real_op = 'subtract' if task.get('op_sym') in ('−', '-', 'subtract') else 'add'
        correct = compute_add_subtract(num1, den1, num2, den2, real_op)
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'basic_property':
        correct = {'result_num': task['num'] * (task['target_den'] // task['den']), 'result_den': task['target_den']}
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'common_denominator':
        den1, den2 = task['den1'], task['den2']
        num1, num2 = task['num1'], task['num2']
        common = lcm(den1, den2)
        new_n1 = num1 * (common // den1)
        new_n2 = num2 * (common // den2)
        correct = {'common_den': common, 'new_num1': new_n1, 'new_num2': new_n2}
        err_common = user.get('common_den') != correct['common_den']
        err_n1 = user.get('new_num1') != correct['new_num1']
        err_n2 = user.get('new_num2') != correct['new_num2']
        errors = {'common_den': err_common, 'new_num1': err_n1, 'new_num2': err_n2}
        is_correct = not any(errors.values())

    elif operation == 'compare_add_subtract':
        real = task.get('real_operation', 'add')
        num1, den1 = task['num1'], task['den1']
        num2, den2 = task['num2'], task['den2']
        if real == 'compare':
            correct = compute_compare(num1, den1, num2, den2)
            user_comp = (user.get('comparison') or '').strip()
            res_ok = user_comp in ('<', '=', '>') and user_comp == correct['comparison']
            errors = {'comparison': not res_ok}
        else:
            correct = compute_add_subtract(num1, den1, num2, den2, real)
            err_common = user.get('common_den') != correct['common_den']
            err_n1 = user.get('new_num1') != correct['new_num1']
            err_n2 = user.get('new_num2') != correct['new_num2']
            parsed = parse_result(user.get('result', ''))
            res_ok = _result_matches(parsed, correct)
            errors = {'common_den': err_common, 'new_num1': err_n1, 'new_num2': err_n2, 'result': not res_ok}
        is_correct = res_ok if real == 'compare' else (not any(errors.values()))

    elif operation == 'fraction_of_number':
        correct = {'result_num': task['whole'] * task['num'], 'result_den': task['den']}
        g = gcd(correct['result_num'], correct['result_den'])
        correct['result_num'] //= g
        correct['result_den'] //= g
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'whole_from_part':
        correct = {'result_num': task['part'] * task['den'], 'result_den': task['num']}
        g = gcd(correct['result_num'], correct['result_den'])
        correct['result_num'] //= g
        correct['result_den'] //= g
        parsed = parse_result(user.get('result', ''))
        res_ok = _result_matches(parsed, correct)
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'decimal_add':
        a_num, a_den = task['a_num'], task['a_den']
        b_num, b_den = task['b_num'], task['b_den']
        common = a_den * b_den // gcd(a_den, b_den)
        r_num = a_num * (common // a_den) + b_num * (common // b_den)
        r_den = common
        correct = {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        res_ok = _decimal_equals((user.get('result') or '').strip(), r_num, r_den)
        errors = {'result': not res_ok}
        if not res_ok:
            err_int, err_frac = _decimal_error_parts((user.get('result') or '').strip(), r_num, r_den)
            errors['result_integer'] = err_int
            errors['result_fractional'] = err_frac
        is_correct = res_ok

    elif operation == 'decimal_subtract':
        a_num, a_den = task['a_num'], task['a_den']
        b_num, b_den = task['b_num'], task['b_den']
        common = a_den * b_den // gcd(a_den, b_den)
        r_num = a_num * (common // a_den) - b_num * (common // b_den)
        r_den = common
        correct = {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        res_ok = _decimal_equals((user.get('result') or '').strip(), r_num, r_den)
        errors = {'result': not res_ok}
        if not res_ok:
            err_int, err_frac = _decimal_error_parts((user.get('result') or '').strip(), r_num, r_den)
            errors['result_integer'] = err_int
            errors['result_fractional'] = err_frac
        is_correct = res_ok

    elif operation == 'decimal_multiply':
        a_num, a_den = task['a_num'], task['a_den']
        b_num, b_den = task['b_num'], task['b_den']
        r_num = a_num * b_num
        r_den = a_den * b_den
        g = gcd(r_num, r_den)
        r_num, r_den = r_num // g, r_den // g
        correct = {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        res_ok = _decimal_equals((user.get('result') or '').strip(), r_num, r_den)
        errors = {'result': not res_ok}
        if not res_ok:
            err_int, err_frac = _decimal_error_parts((user.get('result') or '').strip(), r_num, r_den)
            errors['result_integer'] = err_int
            errors['result_fractional'] = err_frac
        is_correct = res_ok

    elif operation == 'decimal_divide':
        if task.get('b_int'):
            a_num, a_den = task['a_num'], task['a_den']
            b = task['b_int']
            r_num = a_num
            r_den = a_den * b
            g = gcd(r_num, r_den)
            r_num, r_den = r_num // g, r_den // g
        else:
            a_num, a_den = task['a_num'], task['a_den']
            b_num, b_den = task['b_num'], task['b_den']
            r_num = a_num * b_den
            r_den = a_den * b_num
            g = gcd(r_num, r_den)
            r_num, r_den = r_num // g, r_den // g
        correct = {'result_num': r_num, 'result_den': r_den, 'result_str': _decimal_to_str(r_num, r_den)}
        res_ok = _decimal_equals((user.get('result') or '').strip(), r_num, r_den)
        errors = {'result': not res_ok}
        if not res_ok:
            err_int, err_frac = _decimal_error_parts((user.get('result') or '').strip(), r_num, r_den)
            errors['result_integer'] = err_int
            errors['result_fractional'] = err_frac
        is_correct = res_ok

    elif operation == 'decimal_compare':
        a_num, a_den = task['a_num'], task['a_den']
        b_num, b_den = task['b_num'], task['b_den']
        left = a_num * b_den
        right = b_num * a_den
        if left < right:
            comp = '<'
        elif left > right:
            comp = '>'
        else:
            comp = '='
        correct = {'comparison': comp}
        user_comp = (user.get('comparison') or '').strip()
        if user_comp not in ('<', '=', '>'):
            user_comp = None
        res_ok = user_comp == comp
        errors = {'comparison': not res_ok}
        is_correct = res_ok

    if operation == 'decimal_to_common':
        num, den = task['num'], task['den']
        g = gcd(num, den)
        correct = {'result_num': num // g, 'result_den': den // g,
                   'result_str': f"{num // g}/{den // g}"}
        parsed = parse_result((user.get('result') or '').strip())
        res_ok = parsed and parsed[0] == correct['result_num'] and parsed[1] == correct['result_den']
        errors = {'result': not res_ok}
        is_correct = res_ok

    elif operation == 'common_to_decimal':
        num, den = task['num'], task['den']
        result_num = num * (10 ** 4) // den
        result_den = 10 ** 4
        while result_den > 1 and result_num % 10 == 0:
            result_num //= 10
            result_den //= 10
        correct = {'result_num': result_num, 'result_den': result_den,
                   'result_str': _decimal_to_str(result_num, result_den)}
        res_ok = _decimal_equals((user.get('result') or '').strip(), result_num, result_den)
        errors = {'result': not res_ok}
        if not res_ok:
            err_int, err_frac = _decimal_error_parts((user.get('result') or '').strip(), result_num, result_den)
            errors['result_integer'] = err_int
            errors['result_fractional'] = err_frac
        is_correct = res_ok

    elif operation == 'decimal_round':
        num, den = task['num'], task['den']
        to_places = task['to_places']
        d = Decimal(num) / Decimal(den)
        rounded = d.quantize(Decimal(10) ** -to_places, rounding=ROUND_HALF_UP)
        r_num = int(rounded * (10 ** to_places))
        r_den = 10 ** to_places
        correct = {'result_str': _decimal_to_str(r_num, r_den), 'result_num': r_num, 'result_den': r_den}
        res_ok = _decimal_equals((user.get('result') or '').strip(), r_num, r_den)
        errors = {'result': not res_ok}
        if not res_ok:
            err_int, err_frac = _decimal_error_parts((user.get('result') or '').strip(), r_num, r_den)
            errors['result_integer'] = err_int
            errors['result_fractional'] = err_frac
        is_correct = res_ok

    section = data.get('section', '')
    detailed = (section == 'grade5')
    text, alt_text = build_analysis(operation, is_correct, errors, task, correct, user, detailed=detailed)
    visualization = build_visualization(operation, task, correct)

    current_user = get_current_user()
    user_id = current_user.id if current_user else None

    # Повторная проверка той же задачи: не засчитывать правильный ответ
    def _task_params_match(a, b):
        if a is None or b is None:
            return a == b
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    is_duplicate_correct = False
    if is_correct and user_id:
        dup = Attempt.query.filter_by(user_id=user_id, operation=operation, is_correct=True).all()
        for a in dup:
            if _task_params_match(a.task_params, task):
                is_duplicate_correct = True
                break

    if is_duplicate_correct:
        stats = UserStats.query.filter_by(user_id=user_id).first()
        gamification = None
        if stats:
            from gamification import STATUS_NAMES
            gamification = {
                'total_stars': stats.total_stars,
                'lifetime_stars': stats.lifetime_stars or 0,
                'current_streak': stats.current_streak,
                'best_streak': stats.best_streak,
                'status': stats.status,
                'status_name': STATUS_NAMES.get(stats.status, stats.status),
                'new_chest': 0,
                'chests_available': stats.chests_available,
            }
        response_data = {
            'is_correct': True,
            'errors': {},
            'analysis': {'text': text, 'alt_text': alt_text},
            'visualization': visualization,
        }
        if gamification:
            response_data['gamification'] = gamification
        return jsonify(response_data)

    attempt = Attempt(
        user_id=user_id,
        operation=operation,
        task_params=task,
        user_answers=user,
        correct_result=correct,
        is_correct=is_correct,
        errors=errors
    )
    db.session.add(attempt)
    db.session.flush()
    ev = EventLog(
        user_id=user_id,
        event_type='attempt',
        payload={'attempt_id': attempt.id, 'operation': operation, 'is_correct': is_correct}
    )
    db.session.add(ev)
    if not is_correct:
        detected = detect_error_type(operation, errors)
        if detected:
            expl = ai_service.generate_explanation(
                attempt, detected['error_type'],
                hint_short=detected['hint_short'],
                hint_long=detected['hint_long']
            )
            label = ErrorLabel(
                attempt_id=attempt.id,
                error_type=detected['error_type'],
                hint_short=detected['hint_short'],
                hint_long=detected['hint_long'],
                ai_explanation=expl['long']
            )
            db.session.add(label)
    db.session.commit()

    gamification = None
    if current_user:
        gamification = update_gamification(
            db.session, current_user.id, operation, is_correct,
            Topic, UserStats, UserTopicProgress, EventLog
        )
        db.session.commit()

    response_data = {
        'is_correct': is_correct,
        'errors': errors,
        'analysis': {'text': text, 'alt_text': alt_text},
        'visualization': visualization
    }
    if gamification is not None:
        response_data['gamification'] = gamification
    return jsonify(response_data)


def open_browser():
    """Открыть браузер при локальном запуске. При деплое пользователи заходят по своему URL (/, /app)."""
    webbrowser.open('http://127.0.0.1:5000/')


def init_db():
    """Create tables and seed topics from VALID_OPERATIONS."""
    with app.app_context():
        db.create_all()
        # Добавить колонки профиля в users, если их ещё нет (миграция для существующих БД)
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                for col, spec in [('school', 'VARCHAR(255)'), ('school_class', 'VARCHAR(64)')]:
                    try:
                        conn.execute(text(f'ALTER TABLE users ADD COLUMN {col} {spec}'))
                        conn.commit()
                    except Exception:
                        pass
                try:
                    conn.execute(text('ALTER TABLE user_stats ADD COLUMN lifetime_stars INTEGER DEFAULT 0'))
                    conn.commit()
                except Exception:
                    pass
        except Exception:
            pass
        if Topic.query.count() == 0:
            sections = {
                'add': 'ordinary', 'subtract': 'ordinary', 'multiply': 'ordinary', 'divide': 'ordinary',
                'power': 'ordinary', 'compare': 'ordinary', 'reduce': 'ordinary', 'convert': 'ordinary',
                'add_subtract_same_den': 'grade5', 'natural_div_fraction': 'grade5', 'mixed_numbers': 'grade5',
                'add_subtract_mixed': 'grade5', 'basic_property': 'grade5', 'common_denominator': 'grade5',
                'compare_add_subtract': 'grade5', 'fraction_of_number': 'grade5', 'whole_from_part': 'grade5',
                'decimal_add': 'decimal', 'decimal_subtract': 'decimal', 'decimal_multiply': 'decimal',
                'decimal_divide': 'decimal', 'decimal_compare': 'decimal', 'decimal_to_common': 'decimal',
                'common_to_decimal': 'decimal', 'decimal_round': 'decimal',
            }
            names = {
                'add': 'Сложение обыкновенных дробей',
                'subtract': 'Вычитание обыкновенных дробей',
                'multiply': 'Умножение дробей',
                'divide': 'Деление дробей',
                'power': 'Степень дроби',
                'compare': 'Сравнение дробей',
                'reduce': 'Сокращение дробей',
                'convert': 'Смешанные и неправильные дроби',
                'add_subtract_same_den': 'Сложение и вычитание с одинаковым знаменателем',
                'natural_div_fraction': 'Деление натурального на дробь',
                'mixed_numbers': 'Смешанные числа',
                'add_subtract_mixed': 'Сложение и вычитание смешанных',
                'basic_property': 'Основное свойство дроби',
                'common_denominator': 'Приведение к общему знаменателю',
                'compare_add_subtract': 'Сравнение, сложение и вычитание',
                'fraction_of_number': 'Дробь от числа',
                'whole_from_part': 'Число по его дроби',
                'decimal_add': 'Сложение десятичных',
                'decimal_subtract': 'Вычитание десятичных',
                'decimal_multiply': 'Умножение десятичных',
                'decimal_divide': 'Деление десятичных',
                'decimal_compare': 'Сравнение десятичных',
                'decimal_to_common': 'Десятичная в обыкновенную',
                'common_to_decimal': 'Обыкновенная в десятичную',
                'decimal_round': 'Округление десятичных',
            }
            for op in VALID_OPERATIONS:
                t = Topic(name=names.get(op, op), section=sections.get(op, 'other'), operation=op)
                db.session.add(t)
            db.session.commit()


if __name__ == '__main__':
    init_db()
    threading.Timer(1.0, open_browser).start()
    app.run(debug=True, port=5000)
else:
    # При запуске через gunicorn (Render и т.д.) создаём таблицы и темы при импорте
    init_db()

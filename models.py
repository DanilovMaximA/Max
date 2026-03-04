# -*- coding: utf-8 -*-
"""SQLAlchemy models for Matema tutor: users, roles, progress, attempts, logs."""
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import relationship

db = SQLAlchemy()

# Role constants
ROLE_STUDENT = 'student'
ROLE_TEACHER = 'teacher'
ROLE_PARENT = 'parent'
ROLE_ADMIN = 'admin'
ROLES = [ROLE_STUDENT, ROLE_TEACHER, ROLE_PARENT, ROLE_ADMIN]


class User(db.Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # null if auth via messenger
    name = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False, default=ROLE_STUDENT)
    school = Column(String(255), nullable=True)
    school_class = Column(String(64), nullable=True)  # например 5А, 6
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # For parents/teachers: link to students
    parent_of = relationship('UserStudentLink', foreign_keys='UserStudentLink.parent_id', backref='parent')
    teacher_of = relationship('UserStudentLink', foreign_keys='UserStudentLink.teacher_id', backref='teacher')
    attempts = relationship('Attempt', backref='user', lazy='dynamic')
    topic_progress = relationship('UserTopicProgress', backref='user', lazy='dynamic')
    events = relationship('EventLog', backref='user', lazy='dynamic')
    stats = relationship('UserStats', backref='user', uselist=False)


class UserStudentLink(db.Model):
    """Связь родитель/учитель — ученик."""
    __tablename__ = 'user_student_links'
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    teacher_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    student_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Topic(db.Model):
    """Темы (например «Обыкновенные дроби: сложение с одинаковыми знаменателями»)."""
    __tablename__ = 'topics'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    section = Column(String(64), nullable=True)  # 'ordinary', 'grade5', 'decimal'
    operation = Column(String(64), nullable=False, unique=True)  # add, subtract, ...
    created_at = Column(DateTime, default=datetime.utcnow)
    progress = relationship('UserTopicProgress', backref='topic', lazy='dynamic')


class UserTopicProgress(db.Model):
    """Прогресс пользователя по теме: % освоения, серия, последняя активность."""
    __tablename__ = 'user_topic_progress'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    topic_id = Column(Integer, ForeignKey('topics.id'), nullable=False)
    total_attempts = Column(Integer, default=0)
    correct_attempts = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)
    last_activity_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'topic_id', name='uq_user_topic'),)


class Attempt(db.Model):
    """Попытка решения задачи."""
    __tablename__ = 'attempts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # null = anonymous
    operation = Column(String(64), nullable=False)
    task_params = Column(JSON, nullable=True)   # сгенерированные параметры задачи
    user_answers = Column(JSON, nullable=True)
    correct_result = Column(JSON, nullable=True)
    is_correct = Column(Boolean, nullable=False)
    errors = Column(JSON, nullable=True)        # флаги по полям
    created_at = Column(DateTime, default=datetime.utcnow)
    error_label = relationship('ErrorLabel', backref='attempt', uselist=False)


class ErrorLabel(db.Model):
    """Результат анализа ошибки (тип, подсказки, связка с attempt)."""
    __tablename__ = 'error_labels'
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey('attempts.id'), nullable=False)
    error_type = Column(String(128), nullable=True)   # код типа ошибки
    hint_short = Column(Text, nullable=True)
    hint_long = Column(Text, nullable=True)
    ai_explanation = Column(Text, nullable=True)     # текст от ИИ если есть
    created_at = Column(DateTime, default=datetime.utcnow)


class EventLog(db.Model):
    """Лог действий: вход/выход, смена темы, награда и т.д."""
    __tablename__ = 'event_log'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    event_type = Column(String(64), nullable=False)  # login, logout, topic_switch, reward, ...
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserStats(db.Model):
    """Геймификация: звёзды, серия, статус, сундуки."""
    __tablename__ = 'user_stats'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)
    total_stars = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)
    status = Column(String(64), default='concentration_qi')  # concentration_qi, base, core, embryo, god
    chests_available = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserReward(db.Model):
    """Открытые награды (аватарки/стикеры из сундуков)."""
    __tablename__ = 'user_rewards'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    reward_type = Column(String(64), nullable=False)  # avatar, sticker
    reward_id = Column(String(64), nullable=False)    # идентификатор награды
    opened_at = Column(DateTime, default=datetime.utcnow)

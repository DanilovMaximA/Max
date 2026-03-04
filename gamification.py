# -*- coding: utf-8 -*-
"""Gamification: stars, streaks, statuses, chests, topic progress."""
from datetime import datetime

# Status progression: концентрация ци -> основа -> ядро -> зародыш -> бог
STATUS_LEVELS = [
    (0, 'concentration_qi'),
    (10, 'base'),
    (50, 'core'),
    (100, 'embryo'),
    (200, 'god'),
]
STATUS_NAMES = {
    'concentration_qi': 'Концентрация ци',
    'base': 'Основа',
    'core': 'Ядро',
    'embryo': 'Зародыш',
    'god': 'Бог',
}

CHEST_EVERY_N_CORRECT = 10  # grant 1 chest every N correct answers (total)


def stars_for_attempt(is_correct, first_try=True):
    """Stars for this attempt: 1 if correct, 0 if wrong. Can extend for steps."""
    return 1 if is_correct else 0


def status_for_stars(total_stars):
    """Return status code from total stars."""
    for threshold, code in reversed(STATUS_LEVELS):
        if total_stars >= threshold:
            return code
    return 'concentration_qi'


def update_gamification(db_session, user_id, operation, is_correct, Topic, UserStats, UserTopicProgress, EventLog):
    """
    Update UserStats and UserTopicProgress after an attempt.
    Returns dict: stars_earned, total_stars, current_streak, best_streak, status, new_chest, topic_progress_pct.
    """
    if not user_id:
        return None
    stats = UserStats.query.filter_by(user_id=user_id).first()
    if not stats:
        stats = UserStats(user_id=user_id)
        db_session.add(stats)
        db_session.flush()
    stars_earned = stars_for_attempt(is_correct)
    if is_correct:
        stats.total_stars += stars_earned
        stats.current_streak += 1
        if stats.current_streak > stats.best_streak:
            stats.best_streak = stats.current_streak
        stats.status = status_for_stars(stats.total_stars)
        # Chest every N correct
        prev_total = stats.total_stars - stars_earned
        new_chest = (stats.total_stars // CHEST_EVERY_N_CORRECT) - (prev_total // CHEST_EVERY_N_CORRECT)
        if new_chest > 0:
            stats.chests_available += new_chest
            ev = EventLog(user_id=user_id, event_type='chest_earned', payload={'count': new_chest})
            db_session.add(ev)
    else:
        stats.current_streak = 0
        new_chest = 0

    topic = Topic.query.filter_by(operation=operation).first()
    topic_pct = None
    if topic:
        prog = UserTopicProgress.query.filter_by(user_id=user_id, topic_id=topic.id).first()
        if not prog:
            prog = UserTopicProgress(user_id=user_id, topic_id=topic.id)
            db_session.add(prog)
            db_session.flush()
        prog.total_attempts += 1
        if is_correct:
            prog.correct_attempts += 1
            if stats.current_streak > prog.best_streak:
                prog.best_streak = stats.current_streak
        prog.last_activity_at = datetime.utcnow()
        topic_pct = round(100 * prog.correct_attempts / max(1, prog.total_attempts))

    return {
        'stars_earned': stars_earned,
        'total_stars': stats.total_stars,
        'current_streak': stats.current_streak,
        'best_streak': stats.best_streak,
        'status': stats.status,
        'status_name': STATUS_NAMES.get(stats.status, stats.status),
        'new_chest': new_chest if is_correct else 0,
        'chests_available': stats.chests_available,
        'topic_progress_pct': topic_pct,
    }

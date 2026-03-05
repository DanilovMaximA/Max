# -*- coding: utf-8 -*-
"""Gamification: stars earned by streaks, chests from 3 stars, statuses by lifetime stars."""
from datetime import datetime

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

STAR_STREAK_THRESHOLDS = [3, 5, 10]
STARS_PER_CHEST = 3


def status_for_stars(lifetime_stars):
    """Return status code from lifetime (all-time) stars."""
    for threshold, code in reversed(STATUS_LEVELS):
        if lifetime_stars >= threshold:
            return code
    return 'concentration_qi'


def _stars_earned_for_streak(prev_streak, new_streak):
    """How many stars earned when streak goes from prev_streak to new_streak."""
    earned = 0
    for t in STAR_STREAK_THRESHOLDS:
        if prev_streak < t <= new_streak:
            earned += 1
    return earned


def update_gamification(db_session, user_id, operation, is_correct, Topic, UserStats, UserTopicProgress, EventLog):
    """
    Update UserStats and UserTopicProgress after an attempt.
    total_stars: current stars toward next chest (0-2, resets to 0 on chest).
    lifetime_stars: all-time stars (for status progression).
    """
    if not user_id:
        return None
    stats = UserStats.query.filter_by(user_id=user_id).first()
    if not stats:
        stats = UserStats(user_id=user_id, total_stars=0, lifetime_stars=0, chests_available=0)
        db_session.add(stats)
        db_session.flush()

    stars_earned = 0
    new_chest = 0

    if is_correct:
        prev_streak = stats.current_streak
        stats.current_streak += 1
        if stats.current_streak > stats.best_streak:
            stats.best_streak = stats.current_streak

        stars_earned = _stars_earned_for_streak(prev_streak, stats.current_streak)
        if stars_earned > 0:
            stats.total_stars += stars_earned
            stats.lifetime_stars = (stats.lifetime_stars or 0) + stars_earned
            stats.status = status_for_stars(stats.lifetime_stars or 0)

        if stats.total_stars >= STARS_PER_CHEST:
            new_chest = stats.total_stars // STARS_PER_CHEST
            stats.total_stars = stats.total_stars % STARS_PER_CHEST
            stats.chests_available += new_chest
            ev = EventLog(user_id=user_id, event_type='chest_earned', payload={'count': new_chest})
            db_session.add(ev)
    else:
        stats.current_streak = 0

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
        'lifetime_stars': stats.lifetime_stars or 0,
        'current_streak': stats.current_streak,
        'best_streak': stats.best_streak,
        'status': stats.status,
        'status_name': STATUS_NAMES.get(stats.status, stats.status),
        'new_chest': new_chest,
        'chests_available': stats.chests_available,
        'topic_progress_pct': topic_pct,
    }

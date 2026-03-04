# -*- coding: utf-8 -*-
"""
Auth provider abstraction for current user resolution.
Allows swapping session-based auth for messenger (Telegram/WhatsApp) without changing app logic.
"""
from abc import ABC, abstractmethod


class AuthProvider(ABC):
    """Abstract: resolve current user id and set/clear session."""

    @abstractmethod
    def get_current_user_id(self):
        """Return user id for current request or None."""
        pass

    def set_user(self, user_id):
        """After login: associate current request with user_id."""
        pass

    def clear_user(self):
        """After logout: clear association."""
        pass


class SessionAuthProvider(AuthProvider):
    """Uses Flask session (cookie). Default for web."""

    def __init__(self, session):
        self._session = session

    def get_current_user_id(self):
        return self._session.get('user_id')

    def set_user(self, user_id):
        self._session['user_id'] = user_id

    def clear_user(self):
        self._session.pop('user_id', None)
        self._session.clear()


class MessengerAuthProvider(AuthProvider):
    """
    Future: validate token from header (e.g. X-Messenger-Token) or query,
    resolve messenger_id to User (via user_messenger_links table or User.messenger_id),
    return user_id. Does not use Flask session; each request carries token.
    Example:
        def get_current_user_id(self):
            token = request.headers.get('X-Messenger-Token') or request.args.get('token')
            if not token: return None
            # verify token with Telegram/WhatsApp API, get messenger_user_id
            # link = UserMessengerLink.query.filter_by(provider='telegram', messenger_user_id=...).first()
            # return link.user_id if link else None
            return None
    """

    def get_current_user_id(self):
        return None

    def set_user(self, user_id):
        pass

    def clear_user(self):
        pass

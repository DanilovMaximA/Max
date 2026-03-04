# -*- coding: utf-8 -*-
"""
AiService: abstraction for error analysis and explanation generation.
Currently rule-based; later can plug in LLM (OpenAI, Gemini) without changing callers.
"""
from error_detector import detect_error_type as rule_based_detect_error_type


class AiService:
    """Analyzes attempts and generates explanations. Replaceable backend for LLM."""

    def detect_error_type(self, attempt):
        """
        Analyze attempt and return error type + hints.
        attempt: object with .operation, .errors (dict).
        Returns: dict with keys error_type, hint_short, hint_long or None.
        """
        if not attempt or not getattr(attempt, 'errors', None):
            return None
        return rule_based_detect_error_type(attempt.operation, attempt.errors)

    def generate_explanation(self, attempt, error_type, hint_short=None, hint_long=None):
        """
        Generate short and long explanation for the error.
        attempt: object with .operation, .user_answers, .task_params, .correct_result.
        error_type: str code from detect_error_type.
        hint_short, hint_long: optional precomputed hints (e.g. from ErrorLabel).
        Returns: dict with 'short', 'long'. Later can call LLM when hint_* are None.
        """
        short = hint_short or 'Допущена ошибка в решении.'
        long_ = hint_long or 'Проверьте шаги решения и сравните с правильным ответом.'
        # Future: if hint_short is None and config has LLM, call LLM here
        return {'short': short, 'long': long_}

    def analyze_attempt(self, attempt):
        """
        Full analysis: error type + explanation. Single entry point for future LLM.
        attempt: ORM Attempt with .operation, .errors, .error_label (optional).
        Returns: dict with error_type, hint_short, hint_long, explanation_short, explanation_long.
        """
        detected = self.detect_error_type(attempt)
        if not detected:
            return None
        err_type = detected['error_type']
        hint_short = detected.get('hint_short')
        hint_long = detected.get('hint_long')
        # Use existing ErrorLabel if already saved (e.g. from check())
        if getattr(attempt, 'error_label', None) and attempt.error_label:
            hint_short = hint_short or attempt.error_label.hint_short
            hint_long = hint_long or attempt.error_label.hint_long
        expl = self.generate_explanation(attempt, err_type, hint_short=hint_short, hint_long=hint_long)
        return {
            'error_type': err_type,
            'hint_short': hint_short,
            'hint_long': hint_long,
            'explanation_short': expl['short'],
            'explanation_long': expl['long'],
        }


# Singleton for app use
ai_service = AiService()

# -*- coding: utf-8 -*-
"""Formalized error types from step checks (no external AI)."""

# Map (operation, error_key) -> (error_type_code, hint_short, hint_long)
ERROR_TYPE_MAP = {
    ('*', 'common_den'): (
        'wrong_common_denominator',
        'Неверный общий знаменатель.',
        'Общий знаменатель — это НОК двух знаменателей. Проверьте вычисление НОК и приведение дробей.'
    ),
    ('*', 'new_num1'): (
        'wrong_additional_factor_first',
        'Ошибка в дополнительном множителе для первой дроби.',
        'Числитель после приведения = старый числитель × (общий_знаменатель ÷ старый_знаменатель).'
    ),
    ('*', 'new_num2'): (
        'wrong_additional_factor_second',
        'Ошибка в дополнительном множителе для второй дроби.',
        'Числитель после приведения = старый числитель × (общий_знаменатель ÷ старый_знаменатель).'
    ),
    ('*', 'result'): (
        'wrong_numerators_action',
        'Ошибка в действии с числителями или в результате.',
        'После приведения к общему знаменателю складываем или вычитаем числители; знаменатель не меняется. Не забудьте сократить результат.'
    ),
    ('*', 'comparison'): (
        'wrong_comparison',
        'Неверный знак сравнения.',
        'Приведите дроби к общему знаменателю и сравните числители, либо сравните произведения a×d и b×c.'
    ),
    ('*', 'result_integer'): (
        'wrong_decimal_integer_part',
        'Ошибка в целой части результата.',
        'Проверьте поразрядное сложение/вычитание целой части и перенос запятой.'
    ),
    ('*', 'result_fractional'): (
        'wrong_decimal_fractional_part',
        'Ошибка в дробной части результата.',
        'Уравняйте количество знаков после запятой нулями и проверьте поразрядные действия.'
    ),
    ('*', 'int_part'): (
        'wrong_integer_part_mixed',
        'Неверная целая часть смешанного числа.',
        'Целая часть = числитель ÷ знаменатель (целочисленное деление).'
    ),
    ('*', 'num'): (
        'wrong_numerator_mixed',
        'Неверный числитель дробной части.',
        'Числитель дробной части = остаток от деления числителя на знаменатель.'
    ),
    ('*', 'den'): (
        'wrong_denominator_mixed',
        'Знаменатель дробной части должен совпадать со знаменателем исходной дроби.',
        'При переводе неправильной дроби в смешанную знаменатель дробной части не меняется.'
    ),
}


def detect_error_type(operation, errors):
    """
    Return primary error type and hints from errors dict.
    Returns dict: error_type, hint_short, hint_long.
    If no errors or unknown, returns None.
    """
    if not errors or all(not v for v in errors.values()):
        return None
    for key, is_err in errors.items():
        if not is_err:
            continue
        if key in ('result_integer', 'result_fractional'):
            entry = ERROR_TYPE_MAP.get(('*', key))
        elif key == 'comparison':
            entry = ERROR_TYPE_MAP.get(('*', 'comparison'))
        elif key in ('int_part', 'num', 'den'):
            entry = ERROR_TYPE_MAP.get(('*', key))
        elif key in ('common_den', 'new_num1', 'new_num2', 'result'):
            entry = ERROR_TYPE_MAP.get(('*', key))
        else:
            entry = None
        if entry:
            code, short, long_ = entry
        else:
            code, short, long_ = f'error_{key}', 'Ошибка в ответе.', 'Проверьте решение по шагам.'
        return {'error_type': code, 'hint_short': short, 'hint_long': long_}
    return None

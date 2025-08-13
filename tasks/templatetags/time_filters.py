from django import template

register = template.Library()

@register.filter
def float_to_time(value):
    try:
        total_minutes = round (float (value) / 60)  # Переводим часы в минуты и округляем
        hours = total_minutes // 60
        minutes = total_minutes % 60

        parts = []
        if hours > 0:
            # Правильное склонение для часов
            hour_word = "час" if hours == 1 else "часа" if 2 <= hours <= 4 else "часов"
            parts.append (f"{hours} {hour_word}")

        if minutes > 0 or not parts:  # Добавляем минуты, если нет часов или они есть
            # Правильное склонение для минут
            minute_word = "минута" if minutes == 1 else "минуты" if 2 <= minutes <= 4 else "минут"
            parts.append (f"{minutes} {minute_word}")

        return " ".join (parts) if parts else "0 минут"

    except (ValueError, TypeError):
        return str (value)  # Возвращаем как есть, если не число

@register.filter
def format_seconds(value):
    """Конвертирует секунды в формат HH:MM:SS"""
    try:
        seconds = int(value)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "00:00:00"

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
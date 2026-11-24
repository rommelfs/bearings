"""Explicit UI timezone; database, scheduling and UTC evidence remain unchanged."""

from datetime import datetime
from zoneinfo import ZoneInfo
from django import template
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

register = template.Library()


@register.simple_tag
def display_timezone():
    return settings.DISPLAY_TIME_ZONE


@register.filter
def display_time(value):
    if isinstance(value, str):
        try:
            value = parse_datetime(value) or value
        except ValueError:
            return value
    if not isinstance(value, datetime):
        return value or "Not recorded"
    if timezone.is_naive(value):
        value = timezone.make_aware(value, ZoneInfo("UTC"))
    return timezone.localtime(value, ZoneInfo(settings.DISPLAY_TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S %Z")

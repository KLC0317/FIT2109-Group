"""Text helpers for names (moved from textfmt.py)."""


def display_name(name, upper=False):
    return name.upper() if upper else name


def initials(name):
    return "".join(part[0] for part in name.split())

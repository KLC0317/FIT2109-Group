"""Text helpers for names."""


def display_name(name, upper=False):
    return name.upper() if upper else name


def initials(name, limit=None):
    return "".join(part[0] for part in name.split()[:limit])

"""Text helpers for names."""


def display_name(name, upper=False, suffix=""):
    return (name.upper() if upper else name) + suffix


def initials(name):
    return "".join(part[0] for part in name.split())

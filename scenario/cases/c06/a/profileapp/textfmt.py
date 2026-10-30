"""Text helpers for names."""


def display_name(name):
    return name


def initials(name):
    return "".join(part[0] for part in name.split())

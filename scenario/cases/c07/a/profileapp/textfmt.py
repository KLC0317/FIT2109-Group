"""Text helpers for names."""


def display_name(name, uppercase=False):
    return name.upper() if uppercase else name


def initials(name):
    return "".join(part[0] for part in name.split())

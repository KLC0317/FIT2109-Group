"""Text helpers for names."""


def display_name(name, upper=False):
    return name.upper() if upper else name


def initials(name):
    return "".join(part[0] for part in name.split())


def title_line(name):
    return display_name(name, upper=True) + " (" + initials(name) + ")"

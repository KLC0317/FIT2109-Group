"""Labels built with a caller-supplied formatter."""

from profileapp.users import get_user


def label(user_id, initials):
    return initials(get_user(user_id)["name"])

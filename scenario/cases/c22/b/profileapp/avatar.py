"""Avatar placeholder text."""

from profileapp.textfmt import initials
from profileapp.users import get_user


def avatar_text(user_id):
    return initials(get_user(user_id)["name"])

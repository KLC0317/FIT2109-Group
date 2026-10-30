"""Avatar placeholder text."""

from profileapp import textfmt
from profileapp.users import get_user


def avatar_text(user_id):
    return textfmt.initials(get_user(user_id)["name"])

"""Avatar placeholder text."""

from profileapp.textfmt import initials as ini
from profileapp.users import get_user


def avatar_text(user_id):
    return ini(get_user(user_id)["name"])

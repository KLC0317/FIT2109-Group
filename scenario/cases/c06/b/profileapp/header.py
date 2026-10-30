"""Page header text."""

from profileapp.textfmt import display_name
from profileapp.users import get_user


def header(user_id):
    return display_name(get_user(user_id)["name"], True)

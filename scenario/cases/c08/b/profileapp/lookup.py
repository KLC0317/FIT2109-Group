"""Lookup by keyword, as used by the admin page."""

from profileapp.users import get_user


def name_of(user_id):
    return get_user(user_id=user_id)["name"]

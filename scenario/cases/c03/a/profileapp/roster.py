"""Team roster output."""

from profileapp.data import USERS
from profileapp.users import get_user


def roster_line(user_id):
    user = get_user(user_id)
    return f"{user['id']}: {user['name']}"


def roster():
    return [roster_line(user_id) for user_id in sorted(USERS)]

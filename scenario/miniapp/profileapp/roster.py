"""Team roster output."""

from profileapp.users import get_user, list_users


def roster_line(user_id):
    user = get_user(user_id)
    return f"{user['id']}: {user['name']}"


def roster():
    return [roster_line(user["id"]) for user in list_users()]

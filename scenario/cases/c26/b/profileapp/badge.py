"""Badge text for the profile page."""

from profileapp.users import get_user


def badge_line(user_id):
    user = get_user(user_id)
    return f"#{user['id']} {user['name']}"

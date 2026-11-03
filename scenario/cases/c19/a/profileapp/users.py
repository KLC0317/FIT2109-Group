"""User lookup."""

from profileapp.data import USERS


class UnknownUser(LookupError):
    """Raised when a user id is not in the data set."""


def get_user(user_id, *, include_email=False):
    try:
        record = USERS[user_id]
    except KeyError:
        raise UnknownUser(user_id) from None
    user = {"id": record["id"], "name": record["name"]}
    if include_email:
        user["email"] = record["email"]
    return user


def list_users():
    return [get_user(user_id) for user_id in sorted(USERS)]

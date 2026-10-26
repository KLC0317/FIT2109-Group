"""User lookup."""

from profileapp.data import USERS


class UnknownUser(LookupError):
    """Raised when a user id is not in the data set."""


def fetch_user(user_id):
    try:
        record = USERS[user_id]
    except KeyError:
        raise UnknownUser(user_id) from None
    return {"id": record["id"], "name": record["name"]}


def list_users():
    return [fetch_user(user_id) for user_id in sorted(USERS)]

"""Team summary."""

from profileapp.users import list_users


def headcount():
    return len(list_users())

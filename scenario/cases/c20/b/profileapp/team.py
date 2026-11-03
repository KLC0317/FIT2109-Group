"""Members of one team."""

from profileapp.data import USERS


def members(team):
    def list_users():
        return [record for record in USERS.values() if record["team"] == team]

    return [record["name"] for record in list_users()]

"""Team statistics."""

from .data import USERS


def team_sizes():
    sizes = {}
    for record in USERS.values():
        sizes[record["team"]] = sizes.get(record["team"], 0) + 1
    return sizes

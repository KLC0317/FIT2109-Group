"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.roster import roster_names

assert roster_names()[0] == "Alice Chen"

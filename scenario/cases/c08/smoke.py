"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.lookup import name_of

assert name_of(1) == "Alice Chen"

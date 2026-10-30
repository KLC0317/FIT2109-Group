"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.summary import headcount

assert headcount() == 3

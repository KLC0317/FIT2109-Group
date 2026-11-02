"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.header import header

assert header(1) == "ALICE CHEN", header(1)

"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.textfmt import title_line

assert title_line("Alice Chen") == "ALICE CHEN (AC)"

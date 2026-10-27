"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.badge import badge_line

assert badge_line(1) == "1: Alice Chen", badge_line(1)

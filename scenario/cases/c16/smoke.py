"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.labels import label

assert label(1, lambda name: name[:1]) == "A"

"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.export import export_csv

assert export_csv().splitlines()[1] == "1,Alice Chen"

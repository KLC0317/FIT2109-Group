"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.team import members

assert members("core") == ["Alice Chen", "Chloe Tan"]

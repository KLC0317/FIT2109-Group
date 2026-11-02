"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.stats import team_sizes

assert team_sizes() == {"core": 2, "ops": 1}

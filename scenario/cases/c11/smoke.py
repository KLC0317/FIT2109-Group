"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.card import card

assert card(1) == "[AC] Alice Chen", card(1)

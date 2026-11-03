"""Ground-truth smoke assertion (not visible to the checker or the baseline)."""

from profileapp.textfmt import initials
from profileapp.users import get_user

assert initials("alice chen") == "AC"
assert get_user(1)["name"] == "Alice Chen"

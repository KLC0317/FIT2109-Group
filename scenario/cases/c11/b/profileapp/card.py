"""Profile card text."""

import profileapp.textfmt as tf
from profileapp.users import get_user


def card(user_id):
    name = get_user(user_id)["name"]
    return f"[{tf.initials(name)}] {tf.display_name(name)}"

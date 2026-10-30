"""Label helper kept for a retired report.

Pre-existing defect used by the base-defect fixtures: get_user() has never
accepted a verbose keyword, so this call fails on the base commit already.
Nothing imports this module, so the existing tests do not notice.
"""

from profileapp.users import get_user


def legacy_label(user_id):
    return get_user(user_id, verbose=True)["name"]

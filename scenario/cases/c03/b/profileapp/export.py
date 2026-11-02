"""CSV export of all users."""

import profileapp.users


def export_csv():
    rows = ["id,name"]
    for user in profileapp.users.list_users():
        rows.append(f"{user['id']},{user['name']}")
    return "\n".join(rows)

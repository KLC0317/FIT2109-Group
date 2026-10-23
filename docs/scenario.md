# Scenario and fixtures

## User and pain point

A developer reviewing two Python feature branches in a small team. One branch
changes a shared API; the other adds a caller in a different file. Git merges
the branches without a textual conflict, both branches pass their own tests,
and the merged program fails only when the new caller runs.

## MiniApp

`scenario/miniapp/` is a small profile service with synthetic data. It is the
base commit of every fixture.

| File | Contents |
|---|---|
| `profileapp/users.py` | `get_user(user_id)`, `list_users()`, `UnknownUser` |
| `profileapp/roster.py` | `roster_line(user_id)`, `roster()` |
| `profileapp/textfmt.py` | `display_name(name, upper=False)`, `initials(name)` |
| `profileapp/data.py` | `USERS`, three synthetic records |
| `profileapp/cli.py`, `main.py` | `python main.py show --id 1` |
| `tests/` | unittest suite for users and roster only |

## Fixture specification

Every fixture is a branch pair created from the same MiniApp base commit:
branch A (Developer A) and branch B (Developer B). A fixture directory holds
the overlay files each branch writes, the files it deletes, its label and a
smoke assertion.

Labels: `break` (silent break: both branches work, Git merges cleanly, the
merged program fails), `safe` (merged program works) and `conflict` (Git
reports a textual conflict).

30 labelled pairs: 12 silent breaks (four per rule), 12 safe pairs and six
text conflicts. 12 are for development; 18 form the holdout, which is frozen
before any tuning (six breaks, eight safe pairs, four conflicts).

In half of the break fixtures the existing tests exercise the affected caller
(B adds a test), so the baseline is not built to fail. Three safe and three
break fixtures also contain a defect already present on the base commit
(`profileapp/legacy.py`, an invalid keyword argument), to measure how many
findings a reviewer must triage.

### Development set

| Case | Label | Rule | Branch A | Branch B | Tests cover caller |
|---|---|---|---|---|---|
| c01 | break | R1 | renames `get_user` to `fetch_user` | `badge.py`: `import profileapp.users as users`; `users.get_user()` | no |
| c02 | break | R1 | removes `textfmt.initials` | `avatar.py`: `from profileapp import textfmt`; `textfmt.initials()` | yes |
| c05 | break | R2 | `include_email` becomes required | `badge.py`: `get_user(user_id)` | no |
| c06 | break | R2 | removes `upper` from `display_name` | `display_name(name, True)` | yes |
| c09 | break | R3 | moves users.py to directory.py | `from profileapp.users import get_user` | no |
| c10 | break | R3 | moves `list_users` into roster.py | `from profileapp.users import list_users` | yes |
| c13 | safe | | adds optional `include_email=False` | `get_user(user_id)` | |
| c14 | safe | | adds optional `suffix=""` to `display_name` | keyword call `display_name(name=..., upper=True)` | |
| c15 | safe | | adds optional `sep=""` to `initials` | `from ... import initials as ini` | |
| c16 | safe | | removes `textfmt.initials` | parameter named `initials` shadows it | |
| c25 | conflict | | edits `get_user` return value | edits the same lines | |
| c26 | conflict | | adds `badge.py` | adds a different `badge.py` | |

### Holdout set

| Case | Label | Rule | Branch A | Branch B | Tests cover caller | Base defect |
|---|---|---|---|---|---|---|
| c03 | break | R1 | removes `list_users` | `import profileapp.users`; `profileapp.users.list_users()` | no | yes |
| c04 | break | R1 | removes `display_name` | same-module call in textfmt.py | yes | |
| c07 | break | R2 | renames `upper` to `uppercase` | `display_name(name, upper=True)` | no | yes |
| c08 | break | R2 | `get_user(user_id, /)` | `get_user(user_id=...)` | yes | |
| c11 | break | R3 | deletes textfmt.py (moved to strings.py) | `import profileapp.textfmt as tf` | no | |
| c12 | break | R3 | deletes data.py (moved to store.py) | `from .data import USERS` | yes | yes |
| c17 | safe | | adds `badge.py` | adds the identical `badge.py` | | |
| c18 | safe | | adds a user record | edits `textfmt` | | |
| c19 | safe | | adds keyword-only `include_email=False` | `get_user(user_id)` | | yes |
| c20 | safe | | removes `list_users` | local variable `list_users` shadows it | | yes |
| c21 | safe | | adds optional `sep=" "` to `initials` | `import profileapp.textfmt as tf` | | yes |
| c22 | safe | | removes `display_name` (unused) | calls `initials` from the same module | | |
| c23 | safe | | moves data.py to store.py | new roster function using `get_user` | | |
| c24 | safe | | `get_user(user_id, /)` | positional call | | |
| c27 | conflict | | deletes textfmt.py | edits textfmt.py | | |
| c28 | conflict | | edits Alice's record | edits Alice's record differently | | |
| c29 | conflict | | changes `roster_line` format | changes it differently | | |
| c30 | conflict | | required `include_email` | default `include_email=True` on the same line | | |

## Labelling protocol

M3 writes each fixture, its label and a smoke assertion that exercises the
new caller. M1 reviews labels against actual Python behaviour before M2 sees
any holdout result. Smoke assertions are the ground truth; neither the
checker nor the baseline may read them.

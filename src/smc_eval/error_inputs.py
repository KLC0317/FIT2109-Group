"""Error and unsupported inputs (proposal Section 5: at least eight).

Each builder creates a small repository under <directory>/<id> and returns
an ErrorInput describing how to call the checker and what it must report.
Every one of them must end with exit code 3 and never with SAFE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smc_eval.gitrepo import Repo, isolated_env

USERS = "def get_user(user_id):\n    return {'id': user_id}\n"
USERS_REQUIRED = "def get_user(user_id, include_email):\n    return {'id': user_id}\n"


@dataclass
class ErrorInput:
    id: str
    description: str
    repo: Path
    refs: tuple[str, str] = ("a", "b")
    args: list[str] = field(default_factory=list)
    expected_status: str = "INCONCLUSIVE"  # or ERROR
    expected_text: str = ""  # must appear in the report's error or unsupported reasons
    env: dict = field(default_factory=dict)  # extra environment for the checker run


def _pair(repo: Repo, base: dict, a: dict, b: dict, a_delete=(), b_delete=()) -> None:
    repo.write(base)
    repo.commit("base")
    repo.branch("a")
    repo.write(a)
    repo.delete(*a_delete)
    repo.commit("a", "a")
    repo.branch("b", "main")
    repo.write(b)
    repo.delete(*b_delete)
    repo.commit("b", "b")
    repo.checkout("main")


def _signature_change(repo: Repo, caller: str, extra_base: dict | None = None) -> None:
    """A changes get_user's signature; B adds a caller written in an unsupported way."""
    base = {"pkg/__init__.py": "", "pkg/users.py": USERS, **(extra_base or {})}
    _pair(repo, base, {"pkg/users.py": USERS_REQUIRED}, {"pkg/caller.py": caller})


def build_all(directory: Path) -> list[ErrorInput]:
    directory = Path(directory)
    env = isolated_env(directory / ".empty-gitconfig")
    inputs: list[ErrorInput] = []

    def repo(name: str) -> Repo:
        return Repo(directory / name, env)

    # E01 unknown reference
    r = repo("e01-unknown-ref")
    _pair(r, {"m.py": "x = 1\n"}, {"m.py": "x = 2\n"}, {"n.py": "y = 1\n"})
    inputs.append(ErrorInput("e01", "unknown branch reference", r.path, ("a", "no-such-branch"),
                             expected_status="ERROR", expected_text="cannot resolve"))

    # E02 not a Git repository
    plain = directory / "e02-not-a-repo"
    plain.mkdir(parents=True, exist_ok=True)
    (plain / "m.py").write_text("x = 1\n")
    # The scratch area may itself sit inside a repository (out/ of this
    # project), so stop Git from searching parent directories.
    inputs.append(ErrorInput("e02", "directory is not a Git repository", plain,
                             expected_status="ERROR", expected_text="not a Git repository",
                             env={"GIT_CEILING_DIRECTORIES": str(directory.resolve())}))

    # E03 source root escaping the repository
    r = repo("e03-source-root-escape")
    _pair(r, {"m.py": "x = 1\n"}, {"m.py": "x = 2\n"}, {"n.py": "y = 1\n"})
    inputs.append(ErrorInput("e03", "source root outside the repository", r.path, args=["--source-root", "../elsewhere"],
                             expected_status="ERROR", expected_text="source root"))

    # E04 source root that exists in no branch
    inputs.append(ErrorInput("e04", "source root missing from every branch", r.path, args=["--source-root", "src"],
                             expected_status="ERROR", expected_text="does not exist"))

    # E05 unrelated histories
    r = repo("e05-unrelated")
    r.write({"m.py": "x = 1\n"})
    r.commit("first root")
    r.branch("a")
    r.git("checkout", "-q", "--orphan", "b")
    r.git("rm", "-q", "-rf", "--cached", ".")
    r.write({"n.py": "y = 1\n"})
    r.commit("second root", "b")
    r.checkout("main")
    inputs.append(ErrorInput("e05", "branches with no common ancestor", r.path,
                             expected_status="ERROR", expected_text="no common ancestor"))

    # E06 criss-cross history: two merge bases
    r = repo("e06-criss-cross")
    r.write({"m.py": "x = 1\n"})
    r.commit("base")
    r.branch("a")
    r.write({"a.py": "a = 1\n"})
    a1 = r.commit("a1", "a")
    r.branch("b", "main")
    r.write({"b.py": "b = 1\n"})
    b1 = r.commit("b1", "b")
    r.checkout("a")
    r.merge(b1, "a")
    r.checkout("b")
    r.merge(a1, "b")
    r.checkout("main")
    inputs.append(ErrorInput("e06", "criss-cross history with two merge bases", r.path,
                             expected_text="merge bases"))

    # E07 submodule (gitlink) in a branch
    r = repo("e07-submodule")
    r.write({"m.py": "x = 1\n"})
    base = r.commit("base")
    r.branch("a")
    r.git("update-index", "--add", "--cacheinfo", f"160000,{base},vendor/lib")
    r.commit_index("add submodule", "a")
    r.branch("b", "main")
    r.write({"n.py": "y = 1\n"})
    r.commit("b", "b")
    r.checkout("main")
    inputs.append(ErrorInput("e07", "submodule in one branch", r.path, expected_text="submodules"))

    # E08 custom merge driver
    r = repo("e08-merge-driver")
    _pair(r, {".gitattributes": "*.py merge=ours-wins\n", "m.py": "x = 1\n"},
          {"m.py": "x = 2\n"}, {"n.py": "y = 1\n"})
    inputs.append(ErrorInput("e08", "custom merge driver in .gitattributes", r.path,
                             expected_text="custom merge driver"))

    # E09 syntax error on one branch
    r = repo("e09-syntax-error")
    _pair(r, {"pkg/__init__.py": "", "pkg/users.py": USERS},
          {"pkg/users.py": USERS_REQUIRED}, {"pkg/broken.py": "def oops(:\n    pass\n"})
    inputs.append(ErrorInput("e09", "syntax error in a branch", r.path, expected_text="SyntaxError"))

    # E10 wildcard import hiding the changed function
    r = repo("e10-wildcard")
    _signature_change(r, "from pkg.users import *\n\n\ndef label(u):\n    return get_user(u)\n")
    inputs.append(ErrorInput("e10", "wildcard import of the changed module", r.path,
                             expected_text="wildcard import"))

    # E11 dynamic import of a module the other branch deletes
    r = repo("e11-dynamic-import")
    _pair(r, {"pkg/__init__.py": "", "pkg/users.py": USERS, "pkg/textfmt.py": "def up(s):\n    return s\n"},
          {"pkg/strings.py": "def up(s):\n    return s.upper()\n"},
          {"pkg/plugin.py": "import importlib\n\n\ndef load():\n    return importlib.import_module('pkg.textfmt')\n"},
          a_delete=("pkg/textfmt.py",))
    inputs.append(ErrorInput("e11", "dynamic import of a deleted module", r.path, expected_text="dynamic import"))

    # E12 unpacked arguments to the changed function
    r = repo("e12-star-args")
    _signature_change(r, "from pkg.users import get_user\n\n\ndef label(args):\n    return get_user(*args)\n")
    inputs.append(ErrorInput("e12", "call with *args to the changed function", r.path, expected_text="*args"))

    # E13 behaviour-altering decorator on the changed function
    r = repo("e13-decorator")
    deco = "import functools\n\n\ndef logged(fn):\n    @functools.wraps(fn)\n    def inner(*a, **k):\n        return fn(*a, **k)\n    return inner\n"
    _pair(r, {"pkg/__init__.py": "", "pkg/deco.py": deco,
              "pkg/users.py": "from pkg.deco import logged\n\n\n@logged\ndef get_user(user_id):\n    return user_id\n"},
          {"pkg/users.py": "from pkg.deco import logged\n\n\n@logged\ndef get_user(user_id, include_email):\n    return user_id\n"},
          {"pkg/caller.py": "from pkg.users import get_user\n\n\ndef label(u):\n    return get_user(u)\n"})
    inputs.append(ErrorInput("e13", "decorated function whose signature changed", r.path, expected_text="decorator"))

    # E14 call through a package re-export
    r = repo("e14-reexport")
    _signature_change(r, "from pkg import get_user\n\n\ndef label(u):\n    return get_user(u)\n",
                      extra_base={"pkg/__init__.py": "from pkg.users import get_user\n"})
    inputs.append(ErrorInput("e14", "call through a package re-export", r.path, expected_text="re-export"))

    return inputs

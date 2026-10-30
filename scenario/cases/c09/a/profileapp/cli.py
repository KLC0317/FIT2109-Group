"""Command-line interface: python main.py show --id 1"""

import argparse

from profileapp.directory import UnknownUser, get_user


def main(argv=None):
    parser = argparse.ArgumentParser(prog="miniapp")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="show one user")
    show.add_argument("--id", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        user = get_user(args.id)
    except UnknownUser:
        print(f"No user with ID {args.id}")
        return 1
    print(f"Loads user {user['name']} (ID {user['id']})")
    return 0

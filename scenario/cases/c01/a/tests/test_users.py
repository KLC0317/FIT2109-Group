import unittest

from profileapp.users import UnknownUser, fetch_user, list_users


class FetchUserTests(unittest.TestCase):
    def test_known_user(self):
        self.assertEqual(fetch_user(1)["name"], "Alice Chen")

    def test_unknown_user(self):
        with self.assertRaises(UnknownUser):
            fetch_user(99)

    def test_list_users(self):
        self.assertEqual([user["id"] for user in list_users()], [1, 2, 3])

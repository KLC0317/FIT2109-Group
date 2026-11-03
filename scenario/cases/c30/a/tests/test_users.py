import unittest

from profileapp.users import UnknownUser, get_user, list_users


class GetUserTests(unittest.TestCase):
    def test_known_user(self):
        self.assertEqual(get_user(1, include_email=False)["name"], "Alice Chen")

    def test_unknown_user(self):
        with self.assertRaises(UnknownUser):
            get_user(99, include_email=False)

    def test_list_users(self):
        self.assertEqual([user["id"] for user in list_users()], [1, 2, 3])

    def test_include_email(self):
        self.assertEqual(get_user(1, include_email=True)["email"], "alice@example.com")

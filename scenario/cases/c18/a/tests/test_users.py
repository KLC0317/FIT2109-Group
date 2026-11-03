import unittest

from profileapp.users import UnknownUser, get_user, list_users


class GetUserTests(unittest.TestCase):
    def test_known_user(self):
        self.assertEqual(get_user(1)["name"], "Alice Chen")

    def test_unknown_user(self):
        with self.assertRaises(UnknownUser):
            get_user(99)

    def test_list_users(self):
        self.assertEqual([user["id"] for user in list_users()], [1, 2, 3, 4])

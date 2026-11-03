import unittest

from profileapp.users import UnknownUser, get_user


class GetUserTests(unittest.TestCase):
    def test_known_user(self):
        self.assertEqual(get_user(1)["name"], "Alice Chen")

    def test_unknown_user(self):
        with self.assertRaises(UnknownUser):
            get_user(99)

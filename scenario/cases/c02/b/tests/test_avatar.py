import unittest

from profileapp.avatar import avatar_text


class AvatarTests(unittest.TestCase):
    def test_avatar_text(self):
        self.assertEqual(avatar_text(1), "AC")

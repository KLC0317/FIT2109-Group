import unittest

from profileapp.lookup import name_of


class LookupTests(unittest.TestCase):
    def test_name_of(self):
        self.assertEqual(name_of(1), "Alice Chen")

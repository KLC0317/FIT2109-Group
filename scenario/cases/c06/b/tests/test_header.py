import unittest

from profileapp.header import header


class HeaderTests(unittest.TestCase):
    def test_header(self):
        self.assertEqual(header(1), "ALICE CHEN")

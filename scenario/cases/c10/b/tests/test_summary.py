import unittest

from profileapp.summary import headcount


class SummaryTests(unittest.TestCase):
    def test_headcount(self):
        self.assertEqual(headcount(), 3)

import unittest

from profileapp.roster import roster, roster_line


class RosterTests(unittest.TestCase):
    def test_roster_line(self):
        self.assertEqual(roster_line(2), "2: Bilal Rahman")

    def test_roster(self):
        self.assertEqual(len(roster()), 3)

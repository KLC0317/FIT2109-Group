import unittest

from profileapp.stats import team_sizes


class StatsTests(unittest.TestCase):
    def test_team_sizes(self):
        self.assertEqual(team_sizes(), {"core": 2, "ops": 1})

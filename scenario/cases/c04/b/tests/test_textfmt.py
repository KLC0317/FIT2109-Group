import unittest

from profileapp.textfmt import title_line


class TitleLineTests(unittest.TestCase):
    def test_title_line(self):
        self.assertEqual(title_line("Alice Chen"), "ALICE CHEN (AC)")

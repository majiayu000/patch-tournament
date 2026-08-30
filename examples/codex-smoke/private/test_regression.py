import unittest

from clamp import clamp


class ClampRegressionTests(unittest.TestCase):
    def test_values_outside_both_bounds(self):
        self.assertEqual(clamp(-1, 0, 10), 0)
        self.assertEqual(clamp(11, 0, 10), 10)
        self.assertEqual(clamp(5, 0, 10), 5)

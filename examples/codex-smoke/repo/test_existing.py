import unittest

from clamp import clamp


class ExistingTests(unittest.TestCase):
    def test_value_inside_bounds_is_unchanged(self):
        self.assertEqual(clamp(5, 0, 10), 5)

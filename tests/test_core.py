import unittest
import argparse

from libgipsync import core

class test_core(unittest.TestCase):

    def setUp(self):
        pass

    def test_read_args(self):
        ret = core.read_args()
        self.assertIsInstance(ret, argparse.Namespace)


class test_Configuration(unittest.TestCase):

    def setUp(self):
        pass

    def test_constructor(self):
        # Either zero or one arguments work:
        c = core.Configuration()
        c = core.Configuration(".")


if __name__ == "__main__":
    unittest.main()

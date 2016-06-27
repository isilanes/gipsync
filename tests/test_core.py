import mock
import unittest
import argparse

from libgipsync import core

class test_core(unittest.TestCase):

    def setUp(self):
        pass

    def test_read_args(self):
        ret = core.read_args()
        self.assertIsInstance(ret, argparse.Namespace)

    def test_collect_sizes_default(self):

        def mysize(arg):
            return len(arg)

        def mymtime(arg):
            arg = arg.replace("y", "fiuuun")
            return len(arg) * 2


        values = [
            [ "path1/data", [], [ "yiley", "file2bc" ] ],
            [ "path2/data", [], [ "myfile1", "myfile2bc" ] ],
        ]

        with mock.patch("os.walk") as mock_walk:
            mock_walk.return_value.__iter__.return_value = iter(values)
            with mock.patch("os.path.getsize", side_effect=mysize):
                with mock.patch("os.path.getmtime", side_effect=mymtime):
                    ret = core.collect_sizes(None) # argument unused
                    self.assertEqual([ x[0] for x in ret ], [36, 46, 50, 52])
                    self.assertEqual([ x[2] for x in ret ], [18, 18, 20, 16])
                    
    def test_collect_sizes_not_data(self):

        values = [
            [ "path1/dato", [], [ "yiley", "file2bc" ] ],
            [ "path2/pata", [], [ "myfile1", "myfile2bc" ] ],
        ]

        with mock.patch("os.walk") as mock_walk:
            mock_walk.return_value.__iter__.return_value = iter(values)
            ret = core.collect_sizes(None) # argument unused
            self.assertEqual(ret, [])
                    
    def test_collect_sizes_no_files(self):

        values = []

        with mock.patch("os.walk") as mock_walk:
            mock_walk.return_value.__iter__.return_value = iter(values)
            ret = core.collect_sizes(None) # argument unused
            self.assertEqual(ret, [])
                    
    def test_since_epoch(self):
        # Change this every 6 months:
        ref = 1467324000.0 # 2016-07-01
        dta = 15552000.0   # ~ 6 months' worth of seconds

        self.assertLess(abs(core.since_epoch() - ref), dta)


class test_Configuration(unittest.TestCase):

    def setUp(self):
        pass

    def test_constructor(self):
        # Either zero or one arguments work:
        c = core.Configuration()
        c = core.Configuration(".")


if __name__ == "__main__":
    unittest.main()

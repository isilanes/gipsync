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

    def test_bytes2size_default(self):
        cases = [
            [1024, "1024 B"],
            [1025, "1.00 kB"],
            [2*1024*1024, "2.00 MB"],
            [10**3, "1000 B"],
            [10**5, "97.66 kB"],
            [10**7, "9.54 MB"],
            [10**9, "953.67 MB"],
            [10**11, "93.13 GB"],
            [1024**4, "1024.00 GB"],
        ]

        for bytes,string in cases:
            self.assertEqual(core.bytes2size(bytes), string)

    def test_bytes2size_handles_large(self):
        self.assertEqual(core.bytes2size(1024**5), "1048576.00 GB")

    def test_bytes2size_zero_and_negatives_left_alone(self):
        cases = [
            [0, "0 B"],
            [-1, "-1 B"],
            [-10**6, "-1000000 B"],
        ]

        for bytes,string in cases:
            self.assertEqual(core.bytes2size(bytes), string)


class test_Configuration(unittest.TestCase):

    def setUp(self):
        pass

    def test_constructor(self):
        # Either zero or one arguments work:
        c = core.Configuration()
        c = core.Configuration(".")


if __name__ == "__main__":
    unittest.main()

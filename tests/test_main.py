import mock
import unittest
import argparse
from StringIO import StringIO

import gipsync

class test_gipsync(unittest.TestCase):
    """Test gipsync.py, the main program."""

    def setUp(self):
        self.ldir = "whatever"
        self.all_args = [ "pos1", "pos2" ]

    def test_gipsinc_deletion(self):
        with mock.patch("os.path.isdir", return_value=True):
            with mock.patch("libgipsync.core.read_args") as mock_args:
                with mock.patch("libgipsync.core.Configuration") as mock_conf:
                    mock_conf().conf = { 'LOCALDIR': self.ldir }
                    mock_args.return_value = argparse.Namespace(positional=[], delete=True)
                    with mock.patch("libgipsync.core.perform_deletion") as mock_deletion:
                        gipsync.main()
                        mock_deletion.assert_called_once()

    def test_gipsync_normal(self):
        with mock.patch("libgipsync.classes.RemoteRepo"):
            with mock.patch("libgipsync.classes.LocalRepo"):
                with mock.patch("os.path.isdir", return_value=True):
                    with mock.patch("libgipsync.core.Configuration") as mock_conf:
                        mock_conf().conf = { 'LOCALDIR': self.ldir }
                        with mock.patch("libgipsync.core.read_args") as mock_args:
                            mock_args.return_value = argparse.Namespace(positional=self.all_args, delete=False)
                            ret = gipsync.main()
                            self.assertIsNone(ret)
                            for arg in self.all_args:
                                mock_conf().read_conf.assert_any_call(arg)

    def test_gipsync_normal_with_all(self):
        with mock.patch("libgipsync.classes.RemoteRepo"):
            with mock.patch("libgipsync.classes.LocalRepo"):
                with mock.patch("os.path.isdir", return_value=True):
                    with mock.patch("libgipsync.core.Configuration") as mock_conf:
                        mock_conf().prefs = { 'ALL': self.all_args }
                        mock_conf().conf = { 'LOCALDIR': self.ldir }
                        with mock.patch("libgipsync.core.read_args") as mock_args:
                            mock_args.return_value = argparse.Namespace(positional=["all"], delete=False)
                            ret = gipsync.main()
                            self.assertIsNone(ret)
                            for arg in self.all_args:
                                mock_conf().read_conf.assert_any_call(arg)

    def test_gipsync_missing_ldir(self):
        with mock.patch("os.path.isdir", return_value=False):
            with mock.patch("libgipsync.core.read_args") as mock_args:
                mock_args.return_value = argparse.Namespace(positional=["all"], delete=False)
                with mock.patch("os.path.isdir", return_value=False):
                    with mock.patch("sys.stdout", new_callable=StringIO) as mock_print:
                        ret = gipsync.main()
                        self.assertIsNone(ret)
                        self.assertIn("ERROR", mock_print.getvalue())


if __name__ == "__main__":
    unittest.main()

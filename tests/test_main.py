import mock
import unittest
import argparse

import gipsync

class test_gipsync(unittest.TestCase):
    """Test gipsync.py, the main program."""

    def setUp(self):
        pass


    @mock.patch("os.path.isdir")
    @mock.patch("libgipsync.core.read_args")
    @mock.patch("libgipsync.classes.LocalRepo")
    @mock.patch("libgipsync.classes.RemoteRepo")
    @mock.patch("libgipsync.core.Configuration")
    def test_main(self, mock_conf, mock_rr, mock_lr, mock_args, mock_isdir):
        """main() function in gipsync.py"""
        
        # Variables:
        ldir = "whatever"
        all_args = [ "pos1", "pos2" ]

        # Configure mocks:
        mock_isdir.return_value = True
        mock_conf().conf = { 'LOCALDIR': ldir }

        # Deletion works:
        mock_args.return_value = argparse.Namespace(positional=[], delete=True)
        with mock.patch("libgipsync.core.perform_deletion") as mock_deletion:
            with mock.patch("sys.exit") as mock_exit:
                gipsync.main()
                mock_exit.assert_called_once()
                mock_deletion.assert_called_once()

        # Normal execution:
        mock_args.return_value = argparse.Namespace(positional=all_args, delete=False)
        ret = gipsync.main()
        self.assertIsNone(ret)
        for arg in all_args:
            mock_conf().read_conf.assert_any_call(arg)

        # Normal execution, called with "all":
        mock_conf.reset_mock()
        args = [ "pos1", "pos2" ]
        mock_conf().prefs = { 'ALL': args }
        mock_args.return_value = argparse.Namespace(positional=["all"], delete=False)
        ret = gipsync.main()
        self.assertIsNone(ret)
        for arg in all_args:
            mock_conf().read_conf.assert_any_call(arg)

        # If ldir does not exist:
        mock_conf.reset_mock()
        mock_args.return_value = argparse.Namespace(positional=["all"], delete=False)
        mock_isdir.return_value = False
        with mock.patch("sys.exit") as mock_exit:
            with mock.patch("sys.stdout"):
                ret = gipsync.main()
                self.assertIsNone(ret)
                self.assertEqual(mock_exit.call_count, len(all_args))


if __name__ == "__main__":
    unittest.main()

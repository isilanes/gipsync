import os
import mock
import unittest

from libgipsync import core
from libgipsync import classes

class test_FileItem(unittest.TestCase):

    def setUp(self):
        self.name = "whatever.jpg"
        self.basedir = "mybasedir"
        self.fullpath = os.path.join(self.basedir, self.name)
        self.cfg = core.Configuration()
        self.cfg.conf["LOCALDIR"] = self.basedir
        self.F = classes.FileItem(self.name, self.cfg)

    def test_fileitem_constructor(self):
        self.assertEqual(self.F.name, self.name)
        self.assertEqual(self.F.cfg, self.cfg)
        self.assertIsInstance(self.F.size, int)
        self.assertIsInstance(self.F.mtime, int)
        self.assertIsNone(self.F.hash)

    def test_fileitem_fullpath(self):
        self.assertEqual(self.F.fullpath, self.fullpath)

    def test_fileitem_get_hash(self):
        with mock.patch("libgipsync.core.hashof", return_value=666):
            self.assertEqual(self.F.get_hash(), 666)

    def test_fileitem_get_size(self):
        with mock.patch("os.path.getsize", return_value="large"):
            self.assertEqual(self.F.get_size(), "large")


class test_Repo(unittest.TestCase):

    def setUp(self):
        self.what = "something"
        self.cfg = core.Configuration()
        self.R = classes.Repo(self.what, self.cfg)

    def test_constructor(self):
        self.assertEqual(self.R.what, self.what)
        self.assertEqual(self.R.cfg, self.cfg)
        self.assertIsInstance(self.R.walked, int)
        self.assertIsInstance(self.R.hashed, int)
        self.assertIsInstance(self.R.files["actual"], dict)
        self.assertIsInstance(self.R.files["read"], dict)


class test_RemoteRepo(unittest.TestCase):

    def setUp(self):
        pass

    def test_constructor(self):
        pass


class test_LocalRepo(unittest.TestCase):

    def setUp(self):
        pass

    def test_constructor(self):
        pass


if __name__ == "__main__":
    unittest.main()

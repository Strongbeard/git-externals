#!/bin/python3

from pathlib import Path
import subprocess
import tempfile
import unittest

from .context import git_externals

class GitExternalsTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._temp_dir_ctx = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp_dir_ctx.name)
        self.svn_dir = self.temp_dir.joinpath('svn')
        subprocess.run(['svnadmin', 'create', self.svn_dir], check=True)

    def tearDown(self):
        super().tearDown()
        self._temp_dir_ctx.cleanup()

    def test_single_svn_external(self):
        git_dir = self.temp_dir.joinpath('git')
        git_dir.mkdir()
        subprocess.run(['git', 'init'], cwd=git_dir, check=True)

if __name__ == '__main__':
    unittest.main()

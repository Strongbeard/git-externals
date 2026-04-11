#!/bin/python3

from collections import namedtuple
from pathlib import Path
import subprocess
import os
import tempfile
import textwrap
import unittest
from urllib.parse import urlunparse

from .context import git_externals

def svn_create_proj_std_layout(proj_root_dir, comment):
    svn_proj_trunk_dir = proj_root_dir.joinpath('trunk')
    svn_proj_branches_dir = proj_root_dir.joinpath('branches')
    svn_proj_tags_dir = proj_root_dir.joinpath('tags')
    subprocess.run([
        'svn',
        'mkdir',
        f'file://{svn_proj_trunk_dir}',
        f'file://{svn_proj_branches_dir}',
        f'file://{svn_proj_tags_dir}',
        '-m',
        comment,
        '--parents'
    ], check=True)
    return (svn_proj_trunk_dir, svn_proj_branches_dir, svn_proj_tags_dir)

class GitExternalsTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._temp_dir_ctx = tempfile.TemporaryDirectory()
        # self._temp_dir_ctx = tempfile.TemporaryDirectory(delete=False)
        self.temp_dir = Path(self._temp_dir_ctx.name)
        self.svn_remote_dir = self.temp_dir.joinpath('svn_remote')
        subprocess.run(['svnadmin', 'create', self.svn_remote_dir], check=True)

    def tearDown(self):
        super().tearDown()
        print(self.temp_dir)
        # self._temp_dir_ctx.cleanup()

    def test_single_svn_external(self):
        # Setup single svn project with 1 file in trunk
        svn_remote_proj_root_dir = self.svn_remote_dir.joinpath('svn_proj')
        (svn_remote_proj_trunk_dir, _, _) = \
            svn_create_proj_std_layout(svn_remote_proj_root_dir, 'Init svn_proj')

        svn_local_proj_1_dir = self.temp_dir.joinpath('svn_local_proj_1')
        subprocess.run([
            'svn',
            'checkout',
            f'file://{svn_remote_proj_trunk_dir}',
            str(svn_local_proj_1_dir)
        ], check=True)
        svn_local_proj_1_file_1 = svn_local_proj_1_dir.joinpath('file_1.txt')
        svn_local_proj_1_file_1.touch()
        subprocess.run([
            'svn', 'add', str(svn_local_proj_1_file_1.name)
        ], cwd=svn_local_proj_1_dir, check=True)
        subprocess.run([
            'svn', 'commit', '--message', 'First File'
        ], cwd=svn_local_proj_1_dir, check=True)

        # Setup git dir
        git_dir = self.temp_dir.joinpath('git')
        git_dir.mkdir()
        subprocess.run(['git', 'init'], cwd=git_dir, check=True)

        # Test GitExternals function call to link external svn repo
        git_external = git_externals.GitExternal(git_dir)
        git_external.add_external(f'file://{svn_remote_proj_trunk_dir!s}', 'svn_proj', vcs="svn")
        externals_file_path = git_dir.joinpath(".gitexternals")
        self.assertTrue(externals_file_path.exists(), f".gitexternals is missing from {git_dir!s}")
        entry=textwrap.dedent(f"""
            [external "svn_proj"]
            \tpath = svn_proj
            \turl = file://{self.temp_dir}/svn_remote/svn_proj/trunk
            \tbranch = master
            \tvcs = svn
        """).strip()
        with open(externals_file_path, encoding="utf-8") as externals_fd:
            self.assertIn(entry, externals_fd.read())
        gitignore_file_path = git_dir.joinpath(".gitignore")
        self.assertTrue(gitignore_file_path.exists(), f".gitignore is missing from {git_dir!s}")
        with open(gitignore_file_path, encoding="utf-8") as gitignore_fd:
            self.assertIn("/svn_proj", gitignore_fd.read())

        git_external.cmd_update(namedtuple(
                'Args',
                ['recursive', 'automatic', 'external', 'only']
            )(True, False, None, "clone")
        )
        self.assertTrue(git_dir.joinpath("svn_proj/file_1.txt").exists())
        self.assertTrue(git_dir.joinpath("svn_proj/.svn").exists())

if __name__ == '__main__':
    unittest.main()

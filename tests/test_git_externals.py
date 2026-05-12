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

def svn_create_proj_std_layout(proj_root_dir: Path, comment):
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

def svn_add_externals(proj_dir: Path, subdir: Path,  external_dir: Path):
    try:
        subdir = subdir.relative_to(proj_dir)
    except ValueError:
        pass
    subprocess.run([
            'svn', 'propset', 'svn:externals',
            f"{subdir!s} file://{external_dir.absolute()!s}", '.'
        ],
        cwd=proj_dir,
        check=True)
    subprocess.run(['svn', 'update'], cwd=proj_dir, check=True)
    subprocess.run([
        'svn', 'commit', '--message', f"Make file://{external_dir} an svn:external of {proj_dir}"
    ], cwd=proj_dir, check=True)

class BaseGitExternalsTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._temp_dir_ctx = tempfile.TemporaryDirectory()
        # self._temp_dir_ctx = tempfile.TemporaryDirectory(delete=False)
        self.temp_dir = Path(self._temp_dir_ctx.name)
        self.svn_remote_dir = self.temp_dir.joinpath('svn_remote')
        self.svn_local_dir = self.temp_dir.joinpath('svn_local')
        self.svn_local_dir.mkdir()
        self.git_parent_dir = self.temp_dir.joinpath('git')
        self.git_parent_dir.mkdir()
        subprocess.run(['svnadmin', 'create', self.svn_remote_dir], check=True)

    def tearDown(self):
        super().tearDown()
        print(self.temp_dir)
        # self._temp_dir_ctx.cleanup()

    def svn_create_proj_with_one_file(self, name: str):
        # Setup single svn project with 1 file in trunk
        (svn_remote_proj_trunk_dir,
         svn_remote_proj_branch_dir,
         svn_remote_proj_tags_dir) = \
            svn_create_proj_std_layout(self.svn_remote_dir.joinpath(name), f"Init {name}")

        svn_local_proj_dir = self.svn_local_dir.joinpath(name)
        subprocess.run([
            'svn',
            'checkout',
            f'file://{svn_remote_proj_trunk_dir}',
            str(svn_local_proj_dir)
        ], check=True)
        svn_local_proj_file = svn_local_proj_dir.joinpath(f"{name}.txt")
        svn_local_proj_file.touch()
        subprocess.run([
            'svn', 'add', str(svn_local_proj_file.name)
        ], cwd=svn_local_proj_dir, check=True)
        subprocess.run([
            'svn', 'commit', '--message', 'First File'
        ], cwd=svn_local_proj_dir, check=True)
        return (
            svn_remote_proj_trunk_dir,
            svn_remote_proj_branch_dir,
            svn_remote_proj_tags_dir,
            svn_local_proj_dir,
            svn_local_proj_file
        )

    def git_init(self, name: str):
        git_dir = self.git_parent_dir.joinpath(name)
        git_dir.mkdir()
        subprocess.run(['git', 'init'], cwd=git_dir, check=True)
        return git_dir


class GitExternalsTestCase(BaseGitExternalsTestCase):
    def test_single_svn_external(self):
        '''
        Test git externals referencing an svn repo
        '''
        # Setup single svn project with 1 file in trunk
        (svn_remote_proj_trunk_dir, _, _, svn_local_dir, _) = \
            self.svn_create_proj_with_one_file('svn_proj')

        # Setup git dir & add svn external to it
        git_dir = self.git_init('git')
        git_external = git_externals.GitExternal(git_dir)
        git_external.add_external(f'file://{svn_remote_proj_trunk_dir!s}', svn_local_dir.name, vcs="svn")

        # Assert GitExternals properly linked to external svn repo
        externals_file_path = git_dir.joinpath(".gitexternals")
        self.assertTrue(externals_file_path.exists(), f".gitexternals is missing from {git_dir!s}")
        entry=textwrap.dedent(f"""
            [external "{svn_local_dir.name}"]
            \tpath = svn_proj
            \turl = file://{svn_remote_proj_trunk_dir}
            \tbranch = master
            \tvcs = svn
        """).strip()
        with open(externals_file_path, encoding="utf-8") as externals_fd:
            self.assertIn(entry, externals_fd.read())
        gitignore_file_path = git_dir.joinpath(".gitignore")
        self.assertTrue(gitignore_file_path.exists(), f".gitignore is missing from {git_dir!s}")
        with open(gitignore_file_path, encoding="utf-8") as gitignore_fd:
            self.assertIn(f"/{svn_local_dir.name}", gitignore_fd.read())

        # Assert externals files exist in git on update call
        git_external.cmd_update(namedtuple(
                'Args',
                ['recursive', 'automatic', 'external', 'only']
            )(True, False, None, "clone")
        )
        self.assertTrue(git_dir.joinpath("svn_proj/svn_proj.txt").exists())
        self.assertTrue(git_dir.joinpath("svn_proj/.svn").exists())

    def test_recursive_svn_externals(self):
        '''
        Test git externals referencing an svn repo that has its own svn:externals
        '''
        # Setup 2 svn projects, one as an external in the other
        svn_remote_outer_proj_trunk_dir, _, _, svn_local_outer_proj_dir, _ = \
            self.svn_create_proj_with_one_file('svn_outer_proj')
        svn_remote_inner_proj_trunk_dir, _, _, svn_local_inner_proj_dir, _ = \
            self.svn_create_proj_with_one_file('svn_inner_proj')
        svn_add_externals(
            svn_local_outer_proj_dir,
            svn_local_outer_proj_dir.joinpath(svn_local_inner_proj_dir.name),
            svn_remote_inner_proj_trunk_dir
        )

        # Setup git dir & add svn external to it
        git_dir = self.git_init('git')
        git_external = git_externals.GitExternal(git_dir)
        git_external.add_external(f'file://{svn_remote_outer_proj_trunk_dir!s}', svn_local_outer_proj_dir.name, vcs="svn")

        # Assert GitExternals properly linked to external svn repo
        externals_file_path = git_dir.joinpath(".gitexternals")
        self.assertTrue(externals_file_path.exists(), f".gitexternals is missing from {git_dir!s}")
        entry=textwrap.dedent(f"""
            [external "{svn_local_outer_proj_dir.name}"]
            \tpath = {svn_local_outer_proj_dir.name}
            \turl = file://{svn_remote_outer_proj_trunk_dir!s}
            \tbranch = master
            \tvcs = svn
        """).strip()
        with open(externals_file_path, encoding="utf-8") as externals_fd:
            self.assertIn(entry, externals_fd.read())
        gitignore_file_path = git_dir.joinpath(".gitignore")
        self.assertTrue(gitignore_file_path.exists(), f".gitignore is missing from {git_dir!s}")
        with open(gitignore_file_path, encoding="utf-8") as gitignore_fd:
            self.assertIn(f"/{svn_local_outer_proj_dir.name!s}", gitignore_fd.read())

        # Assert externals files exist in git on update call
        git_external.cmd_update(namedtuple(
                'Args',
                ['recursive', 'automatic', 'external', 'only']
            )(True, False, None, "clone")
        )
        self.assertTrue(git_dir.joinpath(f"{svn_local_outer_proj_dir.name}/{svn_local_outer_proj_dir.name}.txt").exists())
        self.assertTrue(git_dir.joinpath(f"{svn_local_outer_proj_dir.name}/{svn_local_inner_proj_dir.name}/{svn_local_inner_proj_dir.name}.txt").exists())
        self.assertTrue(git_dir.joinpath(f"{svn_local_outer_proj_dir.name}/.svn").exists())

if __name__ == '__main__':
    unittest.main()

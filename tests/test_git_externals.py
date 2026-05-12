#!/bin/python3

from collections import namedtuple
from contextlib import chdir

import textwrap
import unittest

from .context import git_externals
from .fixture import BaseGitExternalsTestCase, svn_add_externals

class GitExternalsTestCase(BaseGitExternalsTestCase):
    def test_show(self):
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
        git_external.add_external(
            f'file://{svn_remote_outer_proj_trunk_dir!s}',
            svn_local_outer_proj_dir.name,
            vcs="svn"
        )

        with chdir(git_dir):
            git_externals._main("clone", '-r')
            print("===== git show output start =====")
            git_externals._main("show", "--recursive")
            print("===== git show output end =====")

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
        with chdir(git_dir):
            git_externals._main("clone")
        # git_external.cmd_update(namedtuple(
        #         'Args',
        #         ['recursive', 'automatic', 'external', 'only']
        #     )(True, False, None, "clone")
        # )
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
        with chdir(git_dir):
            git_externals._main("clone")
        # git_external.cmd_update(namedtuple(
        #         'Args',
        #         ['recursive', 'automatic', 'external', 'only']
        #     )(True, False, None, "clone")
        # )
        self.assertTrue(git_dir.joinpath(f"{svn_local_outer_proj_dir.name}/{svn_local_outer_proj_dir.name}.txt").exists())
        self.assertTrue(git_dir.joinpath(f"{svn_local_outer_proj_dir.name}/{svn_local_inner_proj_dir.name}/{svn_local_inner_proj_dir.name}.txt").exists())
        self.assertTrue(git_dir.joinpath(f"{svn_local_outer_proj_dir.name}/.svn").exists())

if __name__ == '__main__':
    unittest.main()

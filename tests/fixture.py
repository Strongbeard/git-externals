# Copyright (C) 2026 Kevin Mahon
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of  MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.

from pathlib import Path
import subprocess
import tempfile
import unittest


def svn_create_proj_std_layout(proj_root_dir: Path, comment):
    svn_proj_trunk_dir = proj_root_dir.joinpath("trunk")
    svn_proj_branches_dir = proj_root_dir.joinpath("branches")
    svn_proj_tags_dir = proj_root_dir.joinpath("tags")
    subprocess.run(
        [
            "svn",
            "mkdir",
            f"file://{svn_proj_trunk_dir}",
            f"file://{svn_proj_branches_dir}",
            f"file://{svn_proj_tags_dir}",
            "-m",
            comment,
            "--parents",
        ],
        check=True,
    )
    return (svn_proj_trunk_dir, svn_proj_branches_dir, svn_proj_tags_dir)


def svn_add_externals(proj_dir: Path, subdir: Path, external_dir: Path):
    try:
        subdir = subdir.relative_to(proj_dir)
    except ValueError:
        pass
    subprocess.run(
        [
            "svn",
            "propset",
            "svn:externals",
            f"{subdir!s} file://{external_dir.absolute()!s}",
            ".",
        ],
        cwd=proj_dir,
        check=True,
    )
    subprocess.run(["svn", "update"], cwd=proj_dir, check=True)
    subprocess.run(
        [
            "svn",
            "commit",
            "--message",
            f"Make file://{external_dir} an svn:external of {proj_dir}",
        ],
        cwd=proj_dir,
        check=True,
    )


class BaseGitExternalsTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._temp_dir_ctx = tempfile.TemporaryDirectory()
        # self._temp_dir_ctx = tempfile.TemporaryDirectory(delete=False)
        self.temp_dir = Path(self._temp_dir_ctx.name)
        self.svn_remote_dir = self.temp_dir.joinpath("svn_remote")
        self.svn_local_dir = self.temp_dir.joinpath("svn_local")
        self.svn_local_dir.mkdir()
        self.git_parent_dir = self.temp_dir.joinpath("git")
        self.git_parent_dir.mkdir()
        subprocess.run(["svnadmin", "create", self.svn_remote_dir], check=True)

    def tearDown(self):
        super().tearDown()
        print(self.temp_dir)
        # self._temp_dir_ctx.cleanup()

    def svn_create_proj_with_one_file(self, name: str):
        # Setup single svn project with 1 file in trunk
        (
            svn_remote_proj_trunk_dir,
            svn_remote_proj_branch_dir,
            svn_remote_proj_tags_dir,
        ) = svn_create_proj_std_layout(
            self.svn_remote_dir.joinpath(name), f"Init {name}"
        )

        svn_local_proj_dir = self.svn_local_dir.joinpath(name)
        subprocess.run(
            [
                "svn",
                "checkout",
                f"file://{svn_remote_proj_trunk_dir}",
                str(svn_local_proj_dir),
            ],
            check=True,
        )
        svn_local_proj_file = svn_local_proj_dir.joinpath(f"{name}.txt")
        svn_local_proj_file.touch()
        subprocess.run(
            ["svn", "add", str(svn_local_proj_file.name)],
            cwd=svn_local_proj_dir,
            check=True,
        )
        subprocess.run(
            ["svn", "commit", "--message", "First File"],
            cwd=svn_local_proj_dir,
            check=True,
        )
        return (
            svn_remote_proj_trunk_dir,
            svn_remote_proj_branch_dir,
            svn_remote_proj_tags_dir,
            svn_local_proj_dir,
            svn_local_proj_file,
        )

    def git_init(self, name: str):
        git_dir = self.git_parent_dir.joinpath(name)
        git_dir.mkdir()
        subprocess.run(["git", "init"], cwd=git_dir, check=True)
        return git_dir

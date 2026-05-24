#!/usr/bin/env python3
"""Add other Git directories as externals (subfolders)."""

# Copyright (C) 2017-2024 Christian Dietrich
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

import collections
import fnmatch
import logging
import os
import pathlib
import re
import stat
import string
import subprocess as subp
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typing

    try:
        from _typeshed import StrPath  # , StrOrBytesPath
    except ImportError:
        StrPath: typing.TypeAlias = typing.Union[str, os.PathLike[str]]
        # StrOrBytesPath: typing.TypeAlias = typing.Union[
        #     str, bytes, 'os.PathLike[str]', 'os.PathLike[bytes]']

try:
    import coloredlogs

    colors = coloredlogs.parse_encoded_styles(
        "debug=green;info=green;warning=yellow,bold;error=red;critical=red,bold"
    )
    fields = coloredlogs.parse_encoded_styles("name=blue;levelname=white,bold")
    coloredlogs.install(
        fmt="[%(name)s] %(levelname)s: %(message)s",
        level_styles=colors,
        field_styles=fields,
    )
except ImportError:
    logging.basicConfig(level=logging.INFO)


log = logging.getLogger("git-external")

self_path = os.path.relpath(os.path.abspath(sys.argv[0]), ".")
if "/" not in self_path:
    self_path = "./" + self_path


def get_git_config(file=None, path: "StrPath" = ".") -> dict:
    """Return the git configuration as retrieved in the current directory as a
    dictionary.

    If file is given, git configuration is read only from this file.
    """
    file_cmd = []
    if file:
        file_cmd = ["-f", file]
    config = collections.defaultdict(dict)
    lines = subp.check_output(["git", "config", "-l"] + file_cmd, cwd=path)
    lines = lines.decode("utf-8").split("\n")
    for line in lines:
        m = re.match(r"external\.([^=]+)\.([^=.]+)=(.*)", line)
        if m:
            config[m.group(1)][m.group(2)] = m.group(3)
        m = re.match(r"external\.([^.]+)=(.*)", line)
        if m:
            config["external"][m.group(1)] = m.group(2)
    return config


def get_args(config, option):
    """Parse a config[option] as argument list"""
    option = option.lower()
    if option in config:
        opts = config.get(option).strip().split()
        return [x for x in opts if x]
    return []


def create_symlink(src: "StrPath", dst: "StrPath"):
    src = pathlib.Path(src)
    dst = pathlib.Path(dst)
    src = src.expanduser()
    if dst.exists():
        if not dst.is_symlink():
            raise RuntimeError(f"Cannot create symlink at {src}->{dst}")
        if src.resolve() != dst.resolve():
            dst.unlink()
        else:
            return False
    src.symlink_to(dst)
    return True


class GitExternal:
    updated_paths: "set[pathlib.Path]" = set()

    def __init__(self, path: "StrPath" = "."):
        try:
            _rootdir = subp.check_output(
                ["git", "rev-parse", "--show-toplevel"], cwd=path
            )
            _rootdir = _rootdir.decode("utf-8").strip()
            self.rootdir = pathlib.Path(_rootdir)
        except subp.CalledProcessError as e:
            log.critical("Not a git directory", exc_info=e)
            sys.exit(1)

        self.externals_file = self.rootdir.joinpath(".gitexternals")
        self.ignore_file = self.rootdir.joinpath(".gitignore")
        self.configurations = collections.defaultdict(dict)
        self.path = pathlib.Path(path)

    def is_git_svn(self, path: "StrPath|None" = None):
        """Check if path is a git svn repository."""
        if path is None:
            path = self.rootdir
        else:
            path = pathlib.Path(path)

        # call to 'git svn info' causes git to create an .git/svn (empty)
        # repository, so everyone thinks it is actually a git svn repo (except
        # 'git svn info' itself), so check that before
        if not path.joinpath(".git", "svn").exists():
            return False
        return (
            subp.call(
                ["git", "svn", "info"],
                stdout=subp.DEVNULL,
                stderr=subp.DEVNULL,
                cwd=path,
            )
            == 0
        )

    def get_git_svn_externals(self):
        if not self.is_git_svn(path=self.path):
            return collections.defaultdict(dict)
        exts = subp.check_output(
            ["git", "svn", "show-externals"], cwd=self.path
        ).decode()

        # git svn is strange here, sometimes the url is the second group,
        # sometimes it is part of the first group and the external name is the
        # second group.
        #
        #  ,----[git-svn show-externals]----
        # |# /path/to/
        # |/path/to/svn+ssh://git@host.de/repo external1
        # |
        # |# /other/path/to/
        # |/other/path/to/external2 https://host.de/repo
        # `----

        externals = collections.defaultdict(dict)
        prefix = ""
        for line in exts.split("\n"):
            m = re.match(r"^# (.*)", line)
            if m:
                prefix = m.group(1)
            elif line.startswith(prefix):
                m = re.match(r"(.*) (.*)", line[len(prefix) :])
                if m:
                    if "://" in m.group(2):
                        path, url = 1, 2
                    else:
                        path, url = 2, 1

                    externals[prefix + m.group(path)] = {
                        "path": prefix[1:] + m.group(path),
                        "url": m.group(url),
                        "vcs": "git-svn",
                    }
        return externals

    def merge_externals(self, new_externals):
        """Merge the given new externals into the already existing externals in
        self.configurations.

        If a path in new_externals dominates an already existing external, the
        existing one will be overwritten.
        """
        # make a mapping [(repo_url, key), ...]
        new_paths = [(new_externals[x]["path"], x) for x in new_externals]

        for path, repo in new_paths:
            matches = [
                x
                for x in self.configurations
                if self.configurations[x]["path"].startswith(path)
            ]
            for match in matches:
                del self.configurations[match]
                log.warning("External '%s' is masking '%s'", repo, match)
            self.configurations[repo] = new_externals[repo]

    def load_configuration(self):
        """Load the configuration from ./.gitexternals and git configuration.

        Matching values from git configuration override values specified in
        ./.gitexternals.
        """
        self.configurations = self.get_git_svn_externals()

        if self.externals_file.exists():
            self.merge_externals(get_git_config(file=self.externals_file))

        # Overrides from global config
        override = get_git_config(path=self.path)

        # Expand ${}
        for repo in self.configurations.values():
            for k, v in repo.items():
                if "$" in v:
                    tmpl = string.Template(v)
                    v = tmpl.substitute(override["external"])
                    repo[k] = v

        # We inspect all override configurations and match them up
        # with the externals from this repository by match-*
        # attribute. The corresponding attribute is globbed against
        # match-attribute.
        for name, config in override.items():
            for repo in self.configurations:
                matches = False
                for key in list(config.keys()):
                    if not key.startswith("match-"):
                        continue
                    pattern = config[key].strip()
                    key = key[len("match-") :]
                    if key not in self.configurations[repo]:
                        continue
                    attribute = self.configurations[repo][key].strip()
                    if pattern and attribute and fnmatch.fnmatch(attribute, pattern):
                        matches = True
                if matches:
                    self.configurations[repo].update(
                        {
                            k: v
                            for (k, v) in config.items()
                            if not k.startswith("match-")
                        }
                    )

    def add_external(
        self, url, path: "StrPath", branch="master", vcs="git", script=None
    ):
        """Adding an external by writing it to .gitexternals.

        Arguments:
        url  -- URL of the external (source location)
        path -- Path of the external relative to git project dir (target directory)

        Keyword arguments:
        branch -- Which branch should be cloned/pulled.
        vcs    -- Which vcs to use (git, svn, or git-svn).
        script -- Script to run after cloning the external.
        """
        config = ["git", "config", "-f", str(self.externals_file), "--replace-all"]
        path = self.rootdir.joinpath(path).relative_to(self.rootdir)
        subp.check_call(config + [f"external.{path!s}.path", path], cwd=self.rootdir)
        subp.check_call(config + [f"external.{path!s}.url", url], cwd=self.rootdir)
        subp.check_call(
            config + [f"external.{path!s}.branch", branch], cwd=self.rootdir
        )
        subp.check_call(config + [f"external.{path!s}.vcs", vcs], cwd=self.rootdir)
        if script:
            subp.check_call(
                config + [f"external.{path!s}.script", script], cwd=self.rootdir
            )

        # Add path to ignore file
        found = False
        # Prepend newline if file does not end with one
        prefix = ""
        if self.ignore_file.exists():
            # check if directory is already ignored
            with open(self.ignore_file, "r", encoding="utf-8") as fd:
                for line in fd:
                    prefix = "" if line.endswith("\n") else "\n"
                    if line.strip() in (path, "./" + str(path), "/" + str(path)):
                        found = True
                        break
        # append to .gitignore
        if not found:
            with open(self.ignore_file, "a+", encoding="utf-8") as fd:
                fd.write(prefix + "/" + str(path) + "\n")

        subp.check_call(["git", "add", str(self.externals_file)], cwd=self.rootdir)
        subp.check_call(["git", "add", str(self.ignore_file)], cwd=self.rootdir)

        log.warning("Added external %s\n  Don't forget to call init", path)

    def is_repository(self, path: "StrPath") -> bool:
        """Check if path is a git or SVN repository."""
        path = pathlib.Path(path)
        return any(path.joinpath(x).exists() for x in (".git", ".svn"))

    def get_branch_name(self, path: "StrPath"):
        """Returns the current branch name or 'DETACHED'"""
        cur_branch = subp.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=path,
            stdout=subp.PIPE,
            stderr=subp.PIPE,
            check=True,
        )
        ret = cur_branch.stdout.decode().strip()
        return ret or None

    def update_sparse_checkout(self, repo, path, config):
        """Updates the current set of sparse checkouts"""
        sparse_checkout = get_args(config, "sparseCheckout")
        cur_dir = os.curdir
        os.chdir(path)
        if sparse_checkout:
            log.info("[%s] Setting sparse-checkout to %s", repo, sparse_checkout)
            cmd = ["git", "sparse-checkout", "set"] + sparse_checkout
        else:
            log.info("[%s] Sparse checkout not in use, disabled", repo)
            cmd = ["git", "sparse-checkout", "disable"]
        subp.check_call(cmd)
        os.chdir(cur_dir)

    def init_or_update(self, recursive=True, only=None, external=None):
        """Init or update all repositories in self.configurations.

        Keyword arguments:
        recursive -- checkout/clone externals in externals
        only      -- values could be "clone" and/or "update". If "clone" is
                     given, init the repository. If "update" is given, update
                     the repository. Default is "clone" and "update".
        external  -- specify that only one external should be cloned or updated
        """
        if external and external not in self.configurations:
            raise RuntimeError(f"External '{external}' not found")

        for repo, config in self.configurations.items():
            path = self.rootdir.joinpath(config["path"])
            vcs = config.get("vcs", "git").lower()

            # Handle only a single external
            if external and external not in (repo, config["path"]):
                continue

            # Determine which commands to perform
            if only:
                repo_only = only
            elif "only" in config:
                repo_only = config["only"]
            else:
                repo_only = ("clone", "update")

            if "update" in repo_only and self.is_repository(path):
                realpath = path.resolve(True)
                # Update that external
                if realpath in GitExternal.updated_paths:
                    log.info("[%s] Already updated. Skipping.", repo)
                    return
                GitExternal.updated_paths.add(realpath)

                if vcs == "git-svn":
                    log.info("[%s] Updating GIT-SVN external", repo)
                    subp.check_call(["git", "svn", "rebase"], cwd=path)
                elif vcs == "svn":
                    log.info("[%s] Updating Git SVN external", repo)
                    subp.check_call(["svn", "up"], cwd=path)
                else:
                    cur_branch = self.get_branch_name(path)
                    branch = config.get("branch") or "master"
                    if branch == cur_branch:
                        opts = get_args(config, "updateArgs")
                        log.info("[%s] Updating Git external, %s", repo, opts)
                        subp.check_call(["git", "pull", "--ff-only"] + opts, cwd=path)
                        self.update_sparse_checkout(repo, path, config)
                    elif cur_branch is None:
                        log.warning("[%s] Skipping update, detached HEAD", repo)
                    else:
                        log.warning(
                            "[%s] Skipping update, different branch: %s != %s",
                            repo,
                            branch,
                            cur_branch,
                        )
            elif "clone" in repo_only and not self.is_repository(path):
                # If an external is non-auto, then we skip it, if it
                # is not explicitly mentioned as an argument.
                auto_values = dict(true=True, t=True, yes=True)
                auto = auto_values.get(config.get("auto", "true").lower())
                if not auto and not external:
                    continue

                if config.get("symlink"):
                    if create_symlink(config.get("symlink"), path):
                        log.info("Cloning symlinked external: %s", repo)
                        return

                if vcs == "none":
                    if create_symlink(config.get("url"), path):
                        log.info("Cloning symlinked external: %s", repo)
                    else:
                        log.info("[%s] VCS=none; skipping clone/update", repo)
                elif vcs == "git-svn":
                    log.info("[%s] Cloning Git SVN external", repo)
                    subp.check_call(
                        ["git", "svn", "clone", config["url"], path, "-r", "HEAD"]
                    )
                elif vcs == "svn":
                    log.info("[%s] Cloning SVN external", repo)
                    subp.check_call(
                        [
                            "svn",
                            "checkout",
                            config["url"],
                            path,
                        ]
                    )
                else:
                    branch = config.get("branch", "master")
                    opts = get_args(config, "cloneArgs")
                    log.info("[%s] Cloning Git external, %s", repo, opts)
                    cmd = ["git", "clone"] + opts + [config["url"], str(path)]
                    print(" ".join(cmd))
                    subp.check_call(cmd)
                    self.update_sparse_checkout(repo, path, config)
                    cur_branch = self.get_branch_name(path)
                    branch = config.get("branch") or "master"
                    if cur_branch != branch:
                        log.info(
                            "[%s] Switching branch %s -> %s", repo, cur_branch, branch
                        )
                        subp.check_call(["git", "checkout", branch], cwd=path)

            elif "clone" in repo_only and self.is_repository(path):
                if vcs == "git":
                    cur_branch = self.get_branch_name(path)
                    branch = config.get("branch") or "master"
                    if cur_branch != branch:
                        log.info(
                            "[%s] Switching branch %s -> %s", repo, cur_branch, branch
                        )
                        subp.check_call(["git", "checkout", branch], cwd=path)

            # recursively call for externals
            if (
                recursive
                and vcs in ["git", "git-svn"]
                and set(repo_only) & set(["clone", "update"])
            ):
                log.info("[%s] Updating recursive externals", repo)
                ext = GitExternal(path=path)
                ext.update(True, False, None, None)

            # Run the script if it exists
            script = config.get("script")
            if script:
                script_path = os.path.join(self.rootdir, script)
                if os.path.exists(script_path):
                    log.info("[%s] Running script: %s", repo, script_path)
                    # Ensure the script is executable
                    st = os.stat(script_path)
                    os.chmod(script_path, st.st_mode | stat.S_IEXEC)
                    subp.call([script_path], cwd=self.rootdir)
                else:
                    log.error(
                        "[%s] Script '%s' not found at: %s", repo, script, script_path
                    )

            if config.get("run-init", "").lower() == "true":
                init = os.path.join(path, "init")
                log.info("Running init: %s", init)
                if os.path.exists(init):
                    subp.call(init, cwd=path)

    def install_hook(self):
        """Install the script into git hooks, so it is executed every
        merge/pull.
        """
        hook_dir = subp.check_output(["git", "rev-parse", "--git-path", "hooks"])
        hook_dir = hook_dir.decode().strip()
        hook = os.path.join(hook_dir, "post-merge")
        if os.path.exists(hook_dir) and not os.path.exists(hook):
            with open(hook, "w+") as fd:
                fd.write("#!/bin/sh\n\n")
                fd.write(f"{self_path}\n")
            os.chmod(hook, int("755", 8))

    def update(
        self, recursive: bool, automatic: bool, external: "str|None", only: "tuple|None"
    ):
        """Update/clone all externals."""
        self.load_configuration()
        self.init_or_update(external=external, recursive=recursive, only=only)
        if automatic:
            self.install_hook()

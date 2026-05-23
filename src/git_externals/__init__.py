import argparse
import pathlib
import subprocess
import sys

from .git_externals import GitExternal

def _cmd_update(git_external: GitExternal, **kwargs):
    """Update/clone all externals."""
    git_external.update(**kwargs)

def _cmd_add(git_external: GitExternal, **kwargs):
    """Add an external.

    Arguments:
    args   -- arguments retrieved with argparse
    """
    git_external.add_external(
        kwargs['URL'],
        kwargs['PATH'],
        vcs=kwargs['vcs'],
        branch=kwargs['branch'],
        script=kwargs['script']
    )

def _cmd_show(git_external: GitExternal, **kwargs):
    """Show all externals."""
    git_external.load_configuration()
    for repo, config in git_external.configurations.items():
        print(f'[external "{repo}"]')
        for key, value in config.items():
            print(f'  {key} = {value}')
        if kwargs['recursive'] and pathlib.Path(config['path']).joinpath('.gitexternals').exists():
            x = subprocess.check_output(['./init', 'show'], cwd=config['path'])
            print((b"\t"+x.replace(b"\n", b"\n\t")).decode())

def _main(*args):
    git_external = GitExternal()

    parser = argparse.ArgumentParser(
        prog=args[0],
        description=sys.modules[__name__].__doc__
    )
    subparsers = parser.add_subparsers(help='sub-command help')

    # subcommand UPDATE
    parser_update = subparsers.add_parser('update')
    parser_update.set_defaults(func=_cmd_update, git_external=git_external, only=None)
    parser_update.add_argument("-r", "--not-recursive", action="store_false",
                            dest="recursive",
                            help="Do not clone externals in externals.")
    parser_update.add_argument("-a", "--not-automatic", action="store_false",
                            dest="automatic",
                            help="Do not update externals on every pull.")

    parser_update.add_argument("external", nargs='?', default=None,
                            help="Name of external to update")

    # subcommand CLONE
    parser_clone = subparsers.add_parser('clone')
    parser_clone.set_defaults(func=_cmd_update, git_external=git_external, only=('clone',))
    parser_clone.add_argument("-r", "--not-recursive", action="store_false",
                            dest="recursive",
                            help="Do not clone externals in externals.")
    parser_clone.add_argument("-a", "--not-automatic", action="store_false",
                            dest="automatic",
                            help="Do not update externals on every pull.")
    parser_clone.add_argument("external", nargs='?', default=None,
                            help="Name of external to update")

    # subcommand ADD
    parser_add = subparsers.add_parser('add')
    parser_add.set_defaults(func=_cmd_add, git_external=git_external)
    parser_add.add_argument("URL", help="Url of the external")
    parser_add.add_argument("PATH", help="Path where to clone the external")
    parser_add.add_argument(
        "-b", "--branch", default="master",
        help="Branch that should be used")
    parser_add.add_argument(
        "--script", default=None,
        help="Script to run after cloning the external")
    parser_add_vcs_group = parser_add.add_mutually_exclusive_group()
    parser_add_vcs_group.add_argument(
        "-s", "--svn", action='store_const',
        dest='vcs', const='svn', default='git',
        help="Use 'svn' for handling the external")
    parser_add_vcs_group.add_argument(
        "-g", "--git-svn", action='store_const',
        dest='vcs', const='git-svn', default='git',
        help="Use 'git-svn' for handling the external")

    # subcommand SHOW
    parser_show = subparsers.add_parser('show')
    parser_show.set_defaults(func=_cmd_show, git_external=git_external)
    parser_show.add_argument(
        "-r",
        "--recursive",
        default=False,
        action='store_true',
        help="Show externals recursive"
    )

    # default action: recursive update
    parser.set_defaults(
        func=_cmd_update,
        git_external=git_external,
        recursive=True,
        automatic=True,
        external=None,
        only=None
    )

    parsed_args = parser.parse_args(args)
    parsed_args_dict = vars(parsed_args)
    func = parsed_args_dict.pop('func')
    func(**parsed_args_dict)

def main():
    return _main(*sys.argv)

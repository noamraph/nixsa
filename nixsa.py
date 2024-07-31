#!/usr/bin/env python3

"""
Usage:
nixsa [-h] [-v] [cmd [arg [arg ...]]

Run a command in the nixsa (Nix Standalone) environment.

Assuming realpath(argv[0]) is $NIXSA/bin/nixsa, will use bwrap to run the command with $NIXSA/nix
binded to /nix.

If run as a symlink, the symlink will be used as the command. So, if $NIXSA/bin/nix is a symlink to `nixsa`,
Running `$NIXSA/bin/nix --help` is the same as running `$NIXSA/bin/nixsa nix --help`.

If no arguments are given, and not run as a symlink, will run use $SHELL as the command.

After running the command, the entries in the $NIXSA/bin directories will be updated
with symlinks to `nixsa` according to the entries in $NIXSA/state/nix/profile/bin.
The mtime of the $NIXSA/bin directory will be set to the mtime of the $NIXSA/state/nix/profile
symlink. This allows to skip the update if the profile wasn't updated.

options:
  -h, --help     show this help message and exit
  -v, --verbose  show the commands which are run
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from shlex import quote
from subprocess import call


def _set_env(name: str, value: str | Path | None) -> str:
    """Get a bash command to set an environment variable"""
    if value is not None:
        return f'export {name}={quote(str(value))}'
    else:
        return f'unset {name}'


def _get_bwrap_prefix(nixpath: Path | str) -> list[str]:
    args = ['bwrap', '--bind', str(nixpath), '/nix', '--proc', '/proc', '--dev', '/dev']
    for root_dir in sorted(Path('/').iterdir()):
        if root_dir.name not in ('dev', 'proc', 'nix') and root_dir.exists():
            args.extend(['--bind', str(root_dir), str(root_dir)])
    return args


def _get_bash_c(basepath: Path, cmd: str) -> str:
    """Get the bash script to pass to `bash -c`"""
    # Hack: We set $HOME and $XDG_STATE_HOME (and then restore them) because that's how nix.sh constructs $NIX_LINK.
    home = os.environ.get('HOME')
    xdg_state_home = os.environ.get('XDG_STATE_HOME')
    tmp_home = basepath
    tmp_xdg_state_home = basepath / 'state'
    before = f'{_set_env("HOME", tmp_home)} && {_set_env("XDG_STATE_HOME", tmp_xdg_state_home)}'
    after = f'{_set_env("HOME", home)} && {_set_env("XDG_STATE_HOME", xdg_state_home)}'
    nix_sh = basepath / 'state/nix/profile/etc/profile.d/nix.sh'
    return f'{before} && source {quote(str(nix_sh))} && {after} && exec {quote(cmd)} "$@"'


def nixsa(basepath: Path, cmd: str, args: list[str], is_verbose: bool) -> int:
    nixpath = basepath / 'nix'
    bwrap_prefix = _get_bwrap_prefix(nixpath)
    bash_c = _get_bash_c(basepath, cmd)
    args1 = bwrap_prefix + ['bash', '-c', bash_c, '--'] + args
    if is_verbose:
        print(' '.join(map(quote, args1)), file=sys.stderr)
    rc = call(args1)
    # TODO: update bin directory
    return rc


def main(argv: list[str]) -> int:
    argv0 = Path(argv[0])
    mydir = argv0.resolve().parent
    if mydir.name != 'bin':
        raise RuntimeError(f"The nixsa executable must be in a directory called 'bin', is {mydir.name}")
    basepath = mydir.parent
    nixpath = basepath / 'nix'
    if not nixpath.is_dir():
        raise RuntimeError(f"{nixpath} doesn't exist or is not a directory")
    profile_path = basepath / 'state/nix/profile'
    if not profile_path.is_symlink():
        raise RuntimeError(f'{profile_path} is not a symlink')
    if argv0.is_symlink():
        # TODO: just use the last jump, and only if it's in the same directory as nixsa
        cmd = argv0.name
        args = argv[1:]
        verbose = False
    else:
        if len(argv) > 1 and argv[1] in ('-h', '--help'):
            print(__doc__)
            return 0

        if len(argv) > 1 and argv[1] in ('-v', '--verbose'):
            verbose = True
            argv = [argv[0]] + argv[2:]
        else:
            verbose = False

        if len(argv) == 1:
            argv = [argv[0], os.environ['SHELL']]

        cmd = argv[1]
        args = argv[2:]

    rc = nixsa(basepath, cmd, args, verbose)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))

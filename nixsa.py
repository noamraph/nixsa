#!/usr/bin/env python3

"""
Usage:
nixsa [--nix=/path/to/nix] [--no-nix-sh] [-v] [cmd] [arg, [arg, ...]]

If --nix is not given, use $base/nix (assuming nixsa is at $base/bin/nixsa).
If --no-nix-sh is given, will just run the command without sourcing $base/state/nix/profile/etc/profile.d/nix.sh

If run as a symlink, and the final symlink linking to `nixsa` is a simple name in the same directory,
use the name of the symlink as CMD.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from shlex import quote
from subprocess import call


def nix_user_chroot(nixpath: Path, source_nix_sh: bool, cmdargs: list[str], is_verbose: bool) -> int:
    nixpath = nixpath.absolute()
    args = ['bwrap', '--bind', str(nixpath), '/nix', '--proc', '/proc', '--dev', '/dev']
    for root_dir in sorted(Path('/').glob('*')):
        if root_dir.name not in ('dev', 'proc', 'nix') and root_dir.resolve().exists():
            args.extend(['--bind', str(root_dir), str(root_dir)])
    if source_nix_sh:
        # Hack: We set $HOME and $XDG_STATE_HOME (and then restore them) because that's how nix.sh constructs $NIX_LINK.
        home0 = os.environ.get('HOME', '')
        xdg_state_home0 = os.environ.get('XDG_STATE_HOME', '')
        home = nixpath.parent
        xdg_state_home = home / 'state'
        nix_sh = home / 'state/nix/profile/etc/profile.d/nix.sh'
        bash_src = f'export HOME={home} XDG_STATE_HOME={xdg_state_home} && source "{nix_sh}" && export HOME={home0} XDG_STATE_HOME={xdg_state_home0} && exec "{cmdargs[0]}" "$@"'
        args.extend(['bash', '-c', bash_src, '--'] + cmdargs[1:])
    else:
        args.extend(cmdargs)
    if is_verbose:
        print(' '.join(map(quote, args)), file=sys.stderr)
    return call(args)


def main() -> int:
    from argparse import REMAINDER, ArgumentParser

    parser = ArgumentParser(description='Use bwrap to run a command where /nix is binded to another directory')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument(
        '--nixpath', type=Path, help='Path to a nix directory. If not given, will find it based on the executable path.'
    )
    parser.add_argument('--no-nix-sh', action='store_true', help="Don't source a nix.sh file.")
    parser.add_argument('cmdargs', nargs=REMAINDER)

    argv0 = Path(sys.argv[0])
    realpath = argv0.resolve()
    basepath = realpath.parent.parent
    if argv0.is_symlink():
        # TODO: just use the last jump, and verify it's in the same directory as nixsa
        cmdargs = [argv0.name] + sys.argv[1:]
        nixpath = None
        source_nix_sh = True
        verbose = False
    else:
        args = parser.parse_args()
        cmdargs = args.cmdargs
        if len(cmdargs) == 0:
            cmdargs = [os.environ['SHELL']]

        nixpath = args.nixpath
        source_nix_sh = not args.no_nix_sh
        verbose = args.verbose

    if nixpath is None:
        nixpath = basepath.joinpath('nix')
        if not nixpath.is_dir():
            raise RuntimeError(f"--nix not given, and {nixpath} doesn't exist")

    rc = nix_user_chroot(nixpath, source_nix_sh, cmdargs, verbose)
    return rc


if __name__ == '__main__':
    sys.exit(main())

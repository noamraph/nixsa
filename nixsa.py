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
with symlinks to `nixsa` according to the entries in $NIXSA/state/profile/bin.
The mtime of the $NIXSA/bin directory will be set to the mtime of the $NIXSA/state/profile
symlink. This allows to skip the update if the profile wasn't updated.

options:
  -h, --help     show this help message and exit
  -v, --verbose  show the commands which are run
"""

from __future__ import annotations

import logging
import os
import sys
from logging import info
from pathlib import Path
from shlex import quote
from subprocess import call


def _get_bwrap_prefix(nixpath: Path | str) -> list[str]:
    args = ['bwrap', '--bind', str(nixpath), '/nix', '--proc', '/proc', '--dev', '/dev']
    for root_dir in sorted(Path('/').iterdir()):
        if root_dir.name not in ('dev', 'proc', 'nix') and root_dir.exists():
            args.extend(['--bind', str(root_dir), str(root_dir)])
    return args


def get_real_profile_bin_dir(basepath: Path) -> Path:
    profiles_dir = basepath / 'state/profiles'
    cur_profile_base = profiles_dir.joinpath('profile').readlink()
    cur_profile = profiles_dir / cur_profile_base
    cur_profile_nix = os.readlink(cur_profile)
    if not cur_profile_nix.startswith('/nix/'):
        raise RuntimeError(f"Expecting profile link to start with '/nix/', is {cur_profile_nix!r}")
    cur_profile_real = basepath.joinpath(cur_profile_nix[1:])
    cur_profile_bin = cur_profile_real / 'bin'
    if cur_profile_bin.is_symlink():
        cur_profile_bin_nix = os.readlink(cur_profile_bin)
        if not cur_profile_bin_nix.startswith('/nix'):
            raise RuntimeError(f"Expecting profile/bin link to start with '/nix', is {cur_profile_bin_nix!r}")
        cur_profile_bin_real = basepath.joinpath(cur_profile_bin_nix[1:])
    else:
        cur_profile_bin_real = cur_profile_bin
    if not cur_profile_bin_real.is_dir():
        raise RuntimeError(f'{cur_profile_bin_real!r} is not a directory')
    return cur_profile_bin_real


def update_bin_dir(profile_bin_dir: Path, nixsa_bin_dir: Path) -> None:
    profile_bin_mtime = int(profile_bin_dir.stat().st_mtime)
    nixsa_bin_mtime = int(nixsa_bin_dir.stat().st_mtime)
    if profile_bin_mtime == nixsa_bin_mtime:
        info('profile/bin and nixsa/bin dirs have the same mtime, skipping symlink sync.')
        return
    src_names = set(p.name for p in profile_bin_dir.iterdir())
    dst_names = set()
    for p in nixsa_bin_dir.iterdir():
        if p.name != 'nixsa':
            if not p.is_symlink():
                raise RuntimeError(f'Expecting all items in bin dir to be symlinks, {p} is not a symlink')
            if os.readlink(p) != 'nixsa':
                raise RuntimeError(f"Expecting all items in bin dir to be symlinks to 'nixsa', {p} is not.")
            dst_names.add(p.name)
    if src_names == dst_names:
        info('nixsa/bin directory is up to date with profile/bin directory.')
    else:
        for name in dst_names - src_names:
            p = nixsa_bin_dir / name
            info(f'Removing symlink {p}')
            p.unlink()
        for name in src_names - dst_names:
            p = nixsa_bin_dir / name
            info(f'Creating symlink {p} -> nixsa')
            p.symlink_to('nixsa')
    os.utime(nixsa_bin_dir, (profile_bin_mtime, profile_bin_mtime))


def nixsa(basepath: Path, cmd: str, args: list[str]) -> int:
    nixpath = basepath / 'nix'
    bwrap_prefix = _get_bwrap_prefix(nixpath)
    nix_sh = basepath / 'state/profile/etc/profile.d/nix.sh'
    bash_c = f'source {quote(str(nix_sh))} && exec {quote(cmd)} "$@"'
    args1 = bwrap_prefix + ['bash', '-c', bash_c, '--'] + args
    info(' '.join(map(quote, args1)))
    extra_env = {
        'NIX_USER_CONF_FILES': basepath / 'config/nix.conf',
        'NIX_CACHE_HOME': basepath / 'cache',
        'NIX_CONFIG_HOME': basepath / 'config',
        'NIX_DATA_HOME': basepath / 'share',
        'NIX_STATE_HOME': basepath / 'state',
    }
    env = os.environ.copy()
    env.update({k: str(v) for k, v in extra_env.items()})
    rc = call(args1, env=env)
    profile_bin_dir = get_real_profile_bin_dir(basepath)
    update_bin_dir(profile_bin_dir, basepath / 'bin')
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
    profile_path = basepath / 'state/profile'
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

    logging.basicConfig(format='nixsa: %(message)s', level=logging.INFO if verbose else logging.WARNING)

    rc = nixsa(basepath, cmd, args)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))

#!/usr/bin/env python

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from shlex import quote
from subprocess import PIPE, Popen, check_call


def sh(args: list[str | Path]) -> None:
    print(' '.join(quote(str(arg)) for arg in args), file=sys.stderr)
    check_call(args)


def nixsa_build(nix_archive: Path, nixsa_src: Path, outdir: Path) -> None:
    if not nix_archive.exists():
        raise RuntimeError(f"{nix_archive} doesn't exist")
    if outdir.exists():
        raise RuntimeError(f'{outdir} must not exist before the call')
    outdir = outdir.absolute()
    outdir.mkdir()
    sh(['tar', '-C', outdir, '-xf', nix_archive])
    children = list(outdir.iterdir())
    if len(children) != 1:
        raise RuntimeError('Expecting one main directory in archive')
    (extracted,) = children
    assert extracted.is_dir()
    nix_dir = outdir / 'nix'
    nix_dir.mkdir()
    store_dir = nix_dir / 'store'
    extracted.joinpath('store').rename(store_dir)
    nix_dir.joinpath('var').mkdir()
    nix_dir.joinpath('var/nix').mkdir()
    install_script = extracted.joinpath('install').read_text()
    (nix_inst,) = re.findall(r'nix="([^"]+)"', install_script)
    (_cacert,) = re.findall(r'cacert="([^"]+)"', install_script)
    bin_dir = outdir / 'bin'
    bin_dir.mkdir()
    nixsa = bin_dir / 'nixsa'
    nixsa_s = nixsa_src.read_bytes()
    nixsa.write_bytes(nixsa_s)
    nixsa.chmod(0o555)

    reginfo = extracted.joinpath('.reginfo').read_bytes()
    with Popen([nixsa, '--no-nix-sh', f'{nix_inst}/bin/nix-store', '--load-db'], stdin=PIPE) as subp:
        subp.communicate(reginfo)

    state_dir = outdir / 'state'
    state_dir.mkdir()
    state_dir.joinpath('nix').mkdir()
    os.environ['NIX_PROFILE'] = str(state_dir / 'nix/profile')
    sh(
        [
            bin_dir / 'nixsa',
            '-v',
            '--no-nix-sh',
            f'{nix_inst}/bin/nix-env',
            '-i',
            nix_inst,
        ]
    )


def main() -> None:
    from argparse import ArgumentParser

    parser = ArgumentParser(description='build the nixsa directory')
    parser.add_argument('nix_archive', type=Path, help='path to nix installer archive (.tar.xz)')
    parser.add_argument('nixsa_src', type=Path, help='path to the nixsa executable')
    parser.add_argument('outdir', type=Path)
    args = parser.parse_args()

    nixsa_build(args.nix_archive, args.nixsa_src, args.outdir)


if __name__ == '__main__':
    main()

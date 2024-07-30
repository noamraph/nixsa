#!/usr/bin/env python

from __future__ import annotations

from pathlib import Path
from subprocess import check_call
from logging import info
from shlex import quote
import re
from shutil import copy2

def sh(args):
    info(' '.join(quote(arg)) for arg in args)
    check_call(args)

def nixsa_build(nix_archive: Path, nixsa_src: Path, outdir: Path) -> None:
    if not nix_archive.exists():
        raise RuntimeError(f"{nix_archive} doesn't exist")
    if outdir.exists():
        raise RuntimeError(f"{outdir} must not exist before the call")
    outdir.mkdir()
    sh(['tar', '-C', outdir, '-xf', nix_archive])
    children = list(outdir.iterdir())
    if len(children) != 1:
        raise RuntimeError("Expecting one main directory in archive")
    extracted, = children
    assert extracted.is_dir()
    nix_dir = outdir / 'nix'
    nix_dir.mkdir()
    store_dir = nix_dir / 'store'
    extracted.joinpath('store').rename(store_dir)
    nix_dir.joinpath('var').mkdir()
    nix_dir.joinpath('var/nix').mkdir()
    install_script = extracted.joinpath('install').read_text()
    nix_inst, = re.findall(r'nix="([^"]+)"', install_script)
    cacert, = re.findall(r'cacert="([^"]+)"', install_script)
    bin_dir = outdir / 'bin'
    bin_dir.mkdir()
    nixsa = bin_dir / 'nixsa'
    copy2(nixsa_src, nixsa)


def main():
    from argparse import ArgumentParser

    parser = ArgumentParser(description="build the nixsa directory")
    parser.add_argument("nix_archive", type=Path, help="path to nix installer archive (.tar.xz)")
    parser.add_argument("nixsa_src", type=Path, help="path to the nixsa executable")
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()

    nixsa_build(args.nix_archive, args.nixsa_src, args.outdir)

if __name__ == '__main__':
    main()

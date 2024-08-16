#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import check_call, check_output
from tempfile import mkdtemp


def sh(args: str) -> None:
    print(args, file=sys.stderr)
    check_call(args, shell=True)


def sh_output(args: str) -> str:
    print(args, file=sys.stderr)
    return check_output(args, shell=True, text=True)


def check_tarball(tarball: Path) -> None:
    tmpdir = Path(mkdtemp(prefix='check-tarball-', dir='.'))
    sh(f'tar -C {tmpdir} -xf {tarball}')
    (out,) = list(tmpdir.iterdir())
    assert not (out / 'bin/hello').exists()
    sh(f"{out}/bin/nix profile install 'nixpkgs#hello'")
    hello_out = sh_output(f'{out}/bin/hello')
    assert hello_out.strip() == 'Hello, world!'
    sh(f'{out}/bin/nix profile remove hello')
    assert not (out / 'bin/hello').exists()

    sh(f'chmod -R u+w {tmpdir}')
    sh(f'rm -rf {tmpdir}')


def main() -> None:
    from argparse import ArgumentParser

    parser = ArgumentParser(description='check a built nixsa tarball')
    parser.add_argument('tarball', type=Path)
    args = parser.parse_args()

    check_tarball(args.tarball)


if __name__ == '__main__':
    main()

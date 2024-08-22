#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import PIPE, check_call, check_output, run
from tempfile import mkdtemp


def sh(args: str) -> None:
    print(args, file=sys.stderr)
    check_call(args, shell=True)


def sh_output(args: str) -> str:
    print(args, file=sys.stderr)
    return check_output(args, shell=True, text=True)


def check_tarball(tarball: Path) -> None:
    # Untar into tmpdir
    tmpdir = Path(mkdtemp(prefix='check-tarball-', dir='.'))
    sh(f'tar -C {tmpdir} -xf {tarball}')
    (out,) = list(tmpdir.iterdir())
    # Install `hello` and make sure it works when called directly
    assert not (out / 'bin/hello').exists()
    sh(f"{out}/bin/nix profile install 'nixpkgs#hello'")
    hello_out = sh_output(f'{out}/bin/hello')
    assert hello_out.strip() == 'Hello, world!'
    # Make sure `hello` can be called when adding nixsa/bin to PATH
    status = run('hello', shell=True, check=False, stderr=PIPE)
    assert status.returncode != 0, 'Expecting the `hello` command not to be installed'
    hello_out2 = sh_output(f'export PATH={out}/bin:$PATH && hello')
    assert hello_out2.strip() == 'Hello, world!'
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

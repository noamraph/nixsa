# Nixsa - Nix Standalone Environment

Nixsa lets you experience Nix without any installation. Just extract the tarball and you're ready to go!

```bash
wget https://github.com/noamraph/nixsa/releases/download/v0.1.0/nixsa-0.1.0-x86_64-linux.tar.xz
tar -xf nixsa-0.1.0-x86_64-linux.tar.xz
nixsa/bin/nix profile install nixpkgs#ponysay
nixsa/bin/ponysay 'Hi Nixsa!'
```

Important note: Nixsa currently uses a patched version of Nix, which supports environment variables like NIX_STATE_HOME. Upvote the PR so Nixsa could use a regular Nix version.

[![asciicast](https://asciinema.org/a/672617.svg)](https://asciinema.org/a/672617)


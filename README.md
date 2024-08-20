# Nixsa - Nix Standalone Environment

Nixsa lets you use Nix without any installation. Just extract the tarball and you're ready to go!

```bash
# Download the Nixsa tarball
wget https://github.com/noamraph/nixsa/releases/download/v0.1.0/nixsa-0.1.0-x86_64-linux.tar.xz

# Extract
tar -xf nixsa-0.1.0-x86_64-linux.tar.xz

# Install a package
nixsa/bin/nix profile install nixpkgs#ponysay

# Use it
nixsa/bin/ponysay 'Hi Nixsa!'
```

Important note: Nixsa currently uses a patched version of Nix, which supports environment variables like NIX_STATE_HOME. Upvote the PR so Nixsa could use a regular Nix version.

[![asciicast](https://github.com/user-attachments/assets/f8e1919f-0f63-4ef1-8a54-57b385b1b6de)](https://asciinema.org/a/672617)

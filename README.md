# Nixsa - Nix Standalone Environment

Nixsa lets you use Nix without any installation. Just extract the tarball and you're ready to go! All state and configuration remains within the `nixsa` folder.

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

[![asciicast](https://github.com/user-attachments/assets/f8e1919f-0f63-4ef1-8a54-57b385b1b6de)](https://asciinema.org/a/672748)

One more feature: run `nixsa/bin/nixsa` to start a shell where `/nix` is binded to `nixsa/nix`, and where all the commands in the Nix profile (in `nixsa/state/profile`) are in the PATH.

## How does it work?

Nixsa uses [Bubblewrap](https://github.com/containers/bubblewrap), a sandboxing tool, to run the commands in an environment where `/nix` is binded to the `nix` subfolder of the `nixsa` folder.

All commands in `nixsa/bin` are symlinks to the `nixsa` executable, a statically-linked executable written in Rust. If the `nixsa` executable is called as a symlink, it uses the symlink name as the command to run. So running `nixsa/bin/ponysay hello` does the same thing as running `nixsa/bin/nixsa ponysay hello`.

We can add `-v` to see the command being run. If we run `nixsa-dir/bin/nixsa -v ponysay hello`, we see that Nixsa runs something like this:

```bash
NIX_USER_CONF_FILES=/home/noamraph/nixsa-dir/config/nix.conf \
NIX_CACHE_HOME=/home/noamraph/nixsa-dir/cache \
NIX_CONFIG_HOME=/home/noamraph/nixsa-dir/config \
NIX_DATA_HOME=/home/noamraph/nixsa-dir/share \
NIX_STATE_HOME=/home/noamraph/nixsa-dir/state \
bwrap \
  --bind /home/noamraph/nixsa-dir/nix /nix \
  --proc /proc \
  --dev /dev \
  --bind /home /home \
  ...
  bash -c 'source /home/noamraph/nixsa-dir/state/profile/etc/profile.d/nix.sh && exec ponysay "$@"' -- hello
```

This command:
1. Sets environment variables so Nix will use configuration and state files from the `nixsa-dir` folder.
2. Asks Bubblewrap to bind `/nix` in the environment to `nixsa-dir/nix`, and bind all other folders under `/` to the actual folders.
3. Runs a bash command which sources the `nix.sh` file in the active profile, and then executes the `ponysay` command with the argument `hello`.

In addition, after the command finishes, the `nixsa` executable looks at the current Nix profile, and updates the symlinks in the `nixsa-dir/bin` folder accordingly. For example, after running `nixsa-dir/bin/nix install nixpkgs#ponysay`, the symlink `nixsa-dir/bin/ponysay` will be created, linking to `nixsa-dir/bin/nixsa`.

In order to allow upgrades of the `nixsa` executable itself, `nixsa-dir/bin/nixsa` is a symlink to `../nix/store/HASH-nixsa-bin-VERSION/bin/nixsa`. If you update the `nixsa-bin` package in the profile, Nixsa will update the `nixsa-dir/bin/nixsa` symlink accordingly.

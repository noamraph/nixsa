# Nixsa - A Nix Standalone Environment

Nixsa lets you use Nix without any installation. Just extract the tarball and you're ready to go! All state and configuration remain within the `nixsa` folder.

```bash
# Download the Nixsa tarball
wget https://github.com/noamraph/nixsa/releases/download/v0.2.0/nixsa-0.2.0-x86_64-linux.tar.xz

# Extract
tar -xf nixsa-0.2.0-x86_64-linux.tar.xz

# Install a package
nixsa/bin/nix profile install nixpkgs#ponysay

# Use it
nixsa/bin/ponysay 'Hi Nixsa!'
```

[![asciicast](https://github.com/user-attachments/assets/f8e1919f-0f63-4ef1-8a54-57b385b1b6de)](https://asciinema.org/a/672748)

One more feature: run `nixsa/bin/nixsa` to start a shell where `/nix` is binded to `nixsa/nix`, and where all the commands in the Nix profile (in `nixsa/state/profile`) are in the PATH.

Tip: You can add the `nixsa/bin` folder to your `$PATH`, to have the installed Nix packages readily available.

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
  bash -c 'source /home/noamraph/nixsa-dir/state/profile/etc/profile.d/nix.sh &&
           exec ponysay "$@"' \
  -- hello
```

This command:
1. Sets environment variables so Nix will use configuration and state files from the `nixsa-dir` folder.
2. Asks Bubblewrap to bind `/nix` in the environment to `nixsa-dir/nix`, and bind all other folders under `/` to the actual folders.
3. Runs a bash command which sources the `nix.sh` file in the active profile, and then executes the `ponysay` command with the argument `hello`.

In addition, after the command finishes, the `nixsa` executable looks at the current Nix profile, and updates the symlinks in the `nixsa-dir/bin` folder accordingly. For example, after running `nixsa-dir/bin/nix install nixpkgs#ponysay`, the symlink `nixsa-dir/bin/ponysay` will be created, linking to `nixsa-dir/bin/nixsa`.

In order to allow upgrades of the `nixsa` executable itself, `nixsa-dir/bin/nixsa` is a symlink to `../nix/store/HASH-nixsa-bin-VERSION/bin/nixsa`. If you update the `nixsa-bin` package in the profile, Nixsa will update the `nixsa-dir/bin/nixsa` symlink accordingly.

## Comparison to other tools

Nixsa is very similar in its purpose to [nix-portable](https://github.com/DavHau/nix-portable). The main differences that I see are:
* nix-portable doesn't support managing Nix profiles via `nix-env` or `nix-profile`, and doesn't support managing Nix channels via `nix-channel`. Nixsa does support those.
* nix-portable stores state and configuration in per-user directories, such as `~/.nix-portable`. Nixsa keeps all state and configuration in the extracted directory, so you can have multiple Nixsa environments at once.
* Nixsa uses Bubblewrap to virtualize the `/nix` directory. nix-portable has multiple available runtimes to do this, Bubblewrap being one of them. It is probably possible to add more runtimes alternatives to Nixsa, if the need arises.

Another tool which allows using Nix without root is [nix-user-chroot](https://github.com/nix-community/nix-user-chroot). It is a lower-level tool, which just runs a subprocess in an environment in which `/nix` is binded to another directory. So, in order to run a command installed by Nix, you either have to enter a shell by running `nix-user-chroot ~/.nix bash -l`, or create a script which calls `nix-user-chroot` in order to run the command.

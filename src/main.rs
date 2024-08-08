use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use shell_quote::{Bash, QuoteRefExt};
use std::collections::HashSet;
use std::os::unix::{fs::symlink, process::ExitStatusExt};
use std::process::{Command, ExitCode};
use std::{env, fs};
use tracing::{info, warn, Level};
use tracing_subscriber::FmtSubscriber;

const DESCRIPTION: &str = "\
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
";

fn get_bwrap_prefix(nixpath: &Utf8Path) -> Result<Vec<String>> {
    let mut args: Vec<String> = vec!["bwrap".into(), "--bind".into(), nixpath.to_string(), "/nix".into()];
    args.extend(["--proc".into(), "/proc".into(), "--dev".into(), "/dev".into()]);
    for root_dir in Utf8PathBuf::from("/").read_dir_utf8()?.flatten() {
        let root_dir = root_dir.path();
        let file_name = root_dir.file_name().unwrap_or_default();
        if file_name != "dev" && file_name != "proc" && file_name != "nix" && root_dir.exists() {
            args.extend(["--bind".into(), root_dir.to_string(), root_dir.to_string()]);
        }
    }
    Ok(args)
}

/// Get the real path to the 'bin' dir in the active profile, resolving `/nix` symlinks
fn get_real_profile_bin_dir(basepath: &Utf8Path) -> Result<Utf8PathBuf> {
    let profiles_dir = basepath.join("state/profiles");
    let cur_profile_base = profiles_dir.join("profile").read_link_utf8()?;
    let cur_profile = profiles_dir.join(cur_profile_base);
    let cur_profile_nix = cur_profile.read_link_utf8()?;
    let cur_profile_nix_stripped = cur_profile_nix.strip_prefix("/nix/")?;
    let cur_profile_real = basepath.join("nix").join(cur_profile_nix_stripped);
    let cur_profile_bin = cur_profile_real.join("bin");
    let cur_profile_bin_real = if cur_profile_bin.is_symlink() {
        let cur_profile_bin_nix = cur_profile_bin.read_link_utf8()?;
        let cur_profile_bin_nix_stripped = cur_profile_bin_nix.strip_prefix("/nix/")?;
        basepath.join("nix").join(cur_profile_bin_nix_stripped)
    } else {
        cur_profile_bin
    };
    if !cur_profile_bin_real.is_dir() {
        bail!("{:?} is not a directory", cur_profile_bin_real);
    }
    Ok(cur_profile_bin_real)
}

/// Update the symlinks in the nixsa/bin directory based on the profile bin directory
fn update_bin_dir(basepath: &Utf8Path) -> Result<()> {
    let profiles_dir = basepath.join("state/profiles");
    let profiles_mtime = profiles_dir.metadata()?.modified()?;
    let nixsa_bin_dir = basepath.join("bin");
    let nixsa_bin_mtime = nixsa_bin_dir.metadata()?.modified()?;
    if nixsa_bin_mtime >= profiles_mtime {
        info!("bin dir modification time is later than the state/profiles mtime, skipping symlink sync.");
        return Ok(());
    }

    let profile_bin_dir = get_real_profile_bin_dir(basepath)?;
    let mut src_names = HashSet::<String>::new();
    for entry in profile_bin_dir.read_dir_utf8()? {
        src_names.insert(entry?.file_name().into());
    }
    let src_names = src_names;
    let mut dst_names = HashSet::<String>::new();
    for entry in nixsa_bin_dir.read_dir_utf8()? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name();
        if name != "nixsa" {
            if !path.is_symlink() {
                bail!("Expecting all items in bin dir to be symlinks, {:?} is not a symlink", path);
            }
            if path.read_link_utf8()?.as_str() != "nixsa" {
                bail!("Expecting all items in bin dir to be symlinks to 'nixsa', {:?} is not", path);
            }
            dst_names.insert(name.into());
        }
    }
    let dst_names = dst_names;
    if src_names == dst_names {
        info!("nixsa/bin directory is up to date with profile/bin directory.");
    } else {
        for name in dst_names.difference(&src_names) {
            let path = nixsa_bin_dir.join(name);
            info!("Removing symlink {:?}", path);
            fs::remove_file(path)?;
        }
        for name in src_names.difference(&dst_names) {
            let path = nixsa_bin_dir.join(name);
            info!("Creating symlink {:?} -> nixsa", path);
            symlink("nixsa", path)?;
        }
    }
    Ok(())
}

fn quote(s: &str) -> String {
    s.quoted(Bash)
}

fn nixsa(basepath: &Utf8Path, cmd: &str, args: &[String]) -> Result<ExitCode> {
    let nixpath = basepath.join("nix");
    let bwrap_prefix = get_bwrap_prefix(&nixpath)?;
    let nix_sh = basepath.join("state/profile/etc/profile.d/nix.sh");
    let bash_c = format!("source {} && exec {} \"$@\"", quote(nix_sh.as_str()), quote(cmd));

    let mut args1 = bwrap_prefix;
    args1.extend(["bash".into(), "-c".into(), bash_c, "--".into()]);
    args1.extend(args.iter().map(String::clone));

    let extra_env = [
        ("NIX_USER_CONF_FILES", basepath.join("config/nix.conf")),
        ("NIX_CACHE_HOME", basepath.join("cache")),
        ("NIX_CONFIG_HOME", basepath.join("config")),
        ("NIX_DATA_HOME", basepath.join("share")),
        ("NIX_STATE_HOME", basepath.join("state")),
    ];

    info!(
        "{} {}",
        extra_env.iter().map(|(name, val)| format!("{}={}", name, val)).collect::<Vec<String>>().join(" "),
        args1.iter().map(|s| quote(s)).collect::<Vec<String>>().join(" ")
    );

    let status = Command::new(&args1[0]).args(&args1[1..]).envs(extra_env).status()?;
    update_bin_dir(basepath)?;
    let code = u8::try_from(match status.code() {
        Some(code) => code,
        None => {
            let signal = status.signal().expect("signal should not be None if code is None");
            warn!("Subprocess killed with signal {}", signal);
            signal
        }
    })
    .expect("Code should fit u8");
    Ok(ExitCode::from(code))
}
enum ParsedArgs {
    Help,
    Run { basepath: Utf8PathBuf, cmd: String, args: Vec<String>, verbose: bool },
}

fn parse_args(args: Vec<String>) -> Result<ParsedArgs> {
    let argv0 = Utf8PathBuf::from(args[0].clone());
    let resolved = argv0.canonicalize_utf8()?;
    let mydir = resolved.parent().expect("Expecting resolved executable to have a parent");
    if mydir.file_name() != Some("bin") {
        bail!("The nixsa executable must be in a directory called 'bin', is {:?}", mydir);
    }
    let basepath = mydir.parent().context("The nixsa executable should be under at least two dirs")?;
    let nixpath = basepath.join("nix");
    if !nixpath.is_dir() {
        bail!("{:?} doesn't exist or is not a directory", nixpath);
    }
    let profile_path = basepath.join("state/profile");
    if !profile_path.is_symlink() {
        bail!("{:?} is not a symlink", profile_path);
    }
    if argv0.is_symlink() {
        // TODO: It's better to use just the last redirection, since it allows to symlink to the symlink
        // without preserving the name.
        let cmd: String = argv0.file_name().expect("The symlink should have a file_name").to_owned();
        Ok(ParsedArgs::Run { basepath: basepath.into(), cmd, args: args[1..].into(), verbose: false })
    } else {
        if args.len() > 1 && (args[1] == "-h" || args[1] == "--help") {
            return Ok(ParsedArgs::Help);
        }

        let mut args = args;
        let verbose: bool;
        if args.len() > 1 && (args[1] == "-v" || args[1] == "--verbose") {
            verbose = true;
            args.remove(1);
        } else {
            verbose = false;
        }

        if args.len() == 1 {
            args.push(env::var("SHELL")?);
        }

        Ok(ParsedArgs::Run { basepath: basepath.into(), cmd: args[1].clone(), args: args[2..].into(), verbose })
    }
}

fn main() -> Result<ExitCode> {
    let args0: Vec<String> = env::args().collect();
    let args = parse_args(args0)?;
    match args {
        ParsedArgs::Help => {
            print!("{}", DESCRIPTION);
            Ok(ExitCode::from(0))
        }
        ParsedArgs::Run { basepath, cmd, args, verbose } => {
            let max_level = if verbose { Level::INFO } else { Level::WARN };
            let subscriber = FmtSubscriber::builder().with_max_level(max_level).without_time().finish();
            tracing::subscriber::set_global_default(subscriber)?;

            nixsa(&basepath, &cmd, &args)
        }
    }
}

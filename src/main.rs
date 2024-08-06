use anyhow::{bail, Context, Result};
use std::collections::HashSet;
use std::ffi::{OsStr, OsString};
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::UNIX_EPOCH;
use std::{env, fmt, fs};
use tracing::{info, Level};
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

fn get_bwrap_prefix(nixpath: &Path) -> Result<Vec<OsString>> {
    let mut args: Vec<OsString> = vec!["bwrap".into(), "--bind".into(), nixpath.into(), "/nix".into()];
    args.extend(["--proc".into(), "/proc".into(), "--dev".into(), "/dev".into()]);
    for root_dir in PathBuf::from("/").read_dir()?.flatten() {
        let root_dir = root_dir.path();
        let file_name = root_dir.file_name().unwrap_or_default();
        if file_name != "dev" && file_name != "proc" && file_name != "nix" && root_dir.exists() {
            args.extend(["--bind".into(), root_dir.clone().into(), root_dir.clone().into()]);
        }
    }
    Ok(args)
}

/// Get the real path to the 'bin' dir in the active profile, resolving `/nix` symlinks
fn get_real_profile_bin_dir(basepath: &Path) -> Result<PathBuf> {
    let profiles_dir = basepath.join("state/profiles");
    let cur_profile_base = profiles_dir.join("profile").read_link()?;
    let cur_profile = profiles_dir.join(cur_profile_base);
    let cur_profile_nix = cur_profile.read_link()?;
    let cur_profile_nix_stripped = cur_profile_nix.strip_prefix("/nix/")?;
    let cur_profile_real = basepath.join("nix").join(cur_profile_nix_stripped);
    let cur_profile_bin = cur_profile_real.join("bin");
    let cur_profile_bin_real = if cur_profile_bin.is_symlink() {
        let cur_profile_bin_nix = cur_profile_bin.read_link()?;
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
fn update_bin_dir(profile_bin_dir: &Path, nixsa_bin_dir: &Path) -> Result<()> {
    let profile_bin_mtime = profile_bin_dir.metadata()?.modified()?;
    let nixsa_bin_mtime = profile_bin_dir.metadata()?.modified()?;
    if profile_bin_mtime.duration_since(UNIX_EPOCH)?.as_secs() == nixsa_bin_mtime.duration_since(UNIX_EPOCH)?.as_secs()
    {
        info!("profile/bin and nixsa/bin dirs have the same mtime, skipping symlink sync.");
        return Ok(());
    }
    let mut src_names = HashSet::<OsString>::new();
    for entry in profile_bin_dir.read_dir()? {
        src_names.insert(entry?.file_name());
    }
    let src_names = src_names;
    let mut dst_names = HashSet::<OsString>::new();
    for entry in nixsa_bin_dir.read_dir()? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name();
        if name != "nixsa" {
            if !path.is_symlink() {
                bail!("Expecting all items in bin dir to be symlinks, {:?} is not a symlink", path);
            }
            if path.read_link()? != PathBuf::from("nixsa") {
                bail!("Expecting all items in bin dir to be symlinks to 'nixsa', {:?} is not", path);
            }
            dst_names.insert(name);
        }
    }
    let dst_names = dst_names;
    if src_names == dst_names {
        info!("nixsa/bin directory is up to date with profile/bin directory.");
    } else {
        for name in dst_names.difference(&src_names) {
            let path = nixsa_bin_dir.join(name);
            info!("Removing symlink {:?}", path);
            fs::remove_file(path);
        }
        for name in src_names.difference(&dst_names) {
            let path = nixsa_bin_dir.join(name);
            info!("Creating symlink {:?} -> nixsa", path);
            symlink("nixsa", path);
        }
    }
    fs::File::open(nixsa_bin_dir)?.set_modified(profile_bin_mtime);
    Ok(())
}

fn nixsa(basepath: &Path, cmd: &OsStr, args: &[OsString]) -> Result<ExitCode> {
    let nixpath = basepath.join("nix");
    let bwrap_prefix = get_bwrap_prefix(&nixpath)?;
    let nix_sh = basepath.join("state/profile/etc/profile.d/nix.sh");
    let bash_c = fmt!("source {} && exec {} \"@\"", nix_sa, cmd);
    todo!()
}
enum ParsedArgs {
    Help,
    Run { basepath: PathBuf, cmd: OsString, args: Vec<OsString>, verbose: bool },
}

fn parse_args(args: &[OsString]) -> Result<ParsedArgs> {
    let argv0 = PathBuf::from(args[0].clone());
    let resolved = fs::canonicalize(&argv0)?;
    let mydir = resolved.parent().expect("Expecting resolved executable to have a parent");
    if mydir.file_name() != Some(OsStr::new("bin")) {
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
        let cmd: OsString = argv0.file_name().expect("The symlink should have a file_name").to_owned();
        Ok(ParsedArgs::Run { basepath: basepath.into(), cmd, args: args[1..].into(), verbose: false })
    } else {
        if args.len() > 1 && (args[1] == "-h" || args[1] == "--help") {
            return Ok(ParsedArgs::Help);
        }
        todo!()
    }
}

fn main() -> Result<()> {
    println!("Hello, world!");
    let args0: Vec<OsString> = env::args_os().collect();
    let args = parse_args(&args0)?;
    match args {
        ParsedArgs::Help => {
            print!("{}", DESCRIPTION);
        }
        ParsedArgs::Run { basepath, cmd, args, verbose } => {
            let max_level = if verbose { Level::INFO } else { Level::WARN };
            let subscriber = FmtSubscriber::builder().with_max_level(max_level).finish();
            tracing::subscriber::set_global_default(subscriber)?;
            todo!()
        }
    }
    Ok(())
}

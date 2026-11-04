//! Explicit restricted-process packet/Core fixture. No Wintun or host network
//! configuration is changed. Run only in an elevated disposable environment.
use std::{io, path::PathBuf, process::ExitCode};

fn main() -> ExitCode {
    match arguments().and_then(execute) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("windows-packet-worker-smoke failed: {error}");
            ExitCode::FAILURE
        }
    }
}

fn arguments() -> io::Result<(PathBuf, PathBuf)> {
    let mut args = std::env::args_os().skip(1);
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--disposable-environment"))
        || args.next().as_deref() != Some(std::ffi::OsStr::new("--worker"))
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "requires --disposable-environment --worker <absolute worker.exe> --directory <fresh absolute directory>",
        ));
    }
    let worker = args.next().map(PathBuf::from);
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--directory")) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "missing --directory",
        ));
    }
    let directory = args.next().map(PathBuf::from);
    match (worker, directory, args.next()) {
        (Some(worker), Some(directory), None)
            if worker.is_absolute() && directory.is_absolute() =>
        {
            Ok((worker, directory))
        }
        _ => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid fixture paths/arguments",
        )),
    }
}

#[cfg(not(windows))]
fn execute(_: (PathBuf, PathBuf)) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "Windows only; no process or network operation attempted",
    ))
}

#[cfg(windows)]
fn execute(paths: (PathBuf, PathBuf)) -> io::Result<()> {
    windows::run(paths.0, paths.1)
}

#[cfg(windows)]
#[path = "support/packet_worker_fixture.rs"]
mod windows;

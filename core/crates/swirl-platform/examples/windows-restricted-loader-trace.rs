//! Optional disposable diagnosis; never replaces the required A/B startup gate.
use std::{io, path::PathBuf, process::ExitCode};

fn arguments() -> io::Result<(PathBuf, PathBuf)> {
    let mut args = std::env::args_os().skip(1);
    let deny = || {
        io::Error::new(
            io::ErrorKind::PermissionDenied,
            "requires --disposable-environment --probe <absolute windows-headless-worker-probe.exe> --directory <fresh absolute directory>",
        )
    };
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--disposable-environment"))
        || args.next().as_deref() != Some(std::ffi::OsStr::new("--probe"))
    {
        return Err(deny());
    }
    let probe = args.next().map(PathBuf::from).ok_or_else(deny)?;
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--directory")) {
        return Err(deny());
    }
    let directory = args.next().map(PathBuf::from).ok_or_else(deny)?;
    if args.next().is_some()
        || !probe.is_absolute()
        || !directory.is_absolute()
        || probe.file_name() != Some(std::ffi::OsStr::new("windows-headless-worker-probe.exe"))
    {
        return Err(deny());
    }
    Ok((probe, directory))
}

#[cfg(not(windows))]
fn execute(_: (PathBuf, PathBuf)) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "Windows only; no operation attempted",
    ))
}

#[cfg(windows)]
fn execute((probe, directory): (PathBuf, PathBuf)) -> io::Result<()> {
    use sha2::{Digest, Sha256};
    use std::{
        fs::OpenOptions,
        path::{Component, Prefix},
    };
    use swirl_platform::windows_restricted_worker::{
        current_token_profile, trace_headless_startup,
    };
    let profile = current_token_profile()?;
    if !profile.elevated || !profile.admin_enabled {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "explicit elevated disposable environment required; no process launched",
        ));
    }
    for path in [&probe, &directory] {
        if !matches!(path.components().next(), Some(Component::Prefix(prefix)) if matches!(prefix.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)))
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "fixture paths must be on a local drive",
            ));
        }
    }
    let source = std::fs::canonicalize(probe)?;
    if !std::fs::metadata(&source)?.is_file()
        || std::fs::metadata(&source)?.len() > 64 * 1024 * 1024
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "probe is not a bounded executable file",
        ));
    }
    std::fs::create_dir(&directory)?;
    let copied = directory.join("windows-headless-worker-probe.exe");
    let original_bytes = std::fs::read(&source)?;
    let original_hash = format!("{:x}", Sha256::digest(&original_bytes));
    let mut image = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&copied)?;
    std::io::Write::write_all(&mut image, &original_bytes)?;
    image.sync_all()?;
    drop(image);
    let copied_hash = format!("{:x}", Sha256::digest(std::fs::read(&copied)?));
    if copied_hash != original_hash {
        return Err(io::Error::other("copied probe image hash mismatch"));
    }
    let mut receipt = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(directory.join("probe-image.json"))?;
    std::io::Write::write_all(
        &mut receipt,
        &serde_json::to_vec_pretty(
            &serde_json::json!({"source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unrecorded"),"original_sha256":original_hash,"copied_sha256":copied_hash,"purpose":"optional loader diagnosis only"}),
        )?,
    )?;
    receipt.sync_all()?;
    let journal = OpenOptions::new()
        .create_new(true)
        .read(true)
        .write(true)
        .open(directory.join("delegated-fake-ip.dat"))?;
    let mut result = trace_headless_startup(&copied, &journal, &directory)?;
    result["probe_image_sha256"] = serde_json::json!(copied_hash);
    std::fs::write(
        directory.join("loader-result.json"),
        serde_json::to_vec_pretty(&result)?,
    )?;
    println!("{result}");
    Ok(())
}

fn main() -> ExitCode {
    match arguments().and_then(execute) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("restricted loader diagnostic failed: {error}");
            ExitCode::FAILURE
        }
    }
}

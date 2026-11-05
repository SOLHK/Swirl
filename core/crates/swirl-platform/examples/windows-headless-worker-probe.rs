//! Diagnostic child for the explicitly acknowledged restricted-worker smoke.
//! No desktop, service, Core, driver, socket or network configuration operation.

#[cfg(not(windows))]
fn main() {
    eprintln!("WindowsRequired");
    std::process::exit(2);
}

#[cfg(windows)]
fn main() {
    eprintln!("SWIRL_HEADLESS_WORKER_MAIN_ENTERED");
    if let Err(error) = run() {
        eprintln!("headless worker probe failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(windows)]
fn run() -> std::io::Result<()> {
    use std::io::{self, BufRead, Read, Write};
    use swirl_platform::windows_restricted_worker::current_token_profile;

    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    if arguments != ["--headless-pipe-probe"] {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "requires the internal --headless-pipe-probe argument",
        ));
    }
    let profile = current_token_profile()?;
    if profile.elevated
        || !profile.restricted
        || profile.admin_enabled
        || !profile.admin_deny_only
        || profile.integrity_rid != 0x1000
        || profile.unexpected_enabled_privileges != 0
        || profile.enabled_privileges > 1
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "headless worker token violated the low restricted launch contract",
        ));
    }
    // The owning smoke applies the same finite process/job deadline as its
    // original child. Bound bytes before allocation; never consume other frames.
    let mut input = Vec::with_capacity(17);
    io::stdin().lock().take(17).read_until(b'\n', &mut input)?;
    if input.len() > 16 || input != b"ping\n" {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "headless worker stdin frame differs",
        ));
    }
    let result = serde_json::json!({
        "ok":true,
        "evidence":"headless restricted-worker loader diagnostic",
        "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),
        "profile":profile,
        "stdio_reply":"pong",
        "desktop_identity_verified":false,
        "product_broker_integrated":false,
        "network_modified":false,
    });
    let stdout = io::stdout();
    let mut output = stdout.lock();
    writeln!(output, "{result}")?;
    output.flush()
}

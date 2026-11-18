//! Internal experimental low-token endpoint; never a public network RPC server.
fn main() {
    #[cfg(windows)]
    let result = if std::env::args().skip(1).collect::<Vec<_>>() == ["--internal-packet-worker"] {
        eprintln!("SWIRL_PACKET_WORKER_MAIN_ENTERED");
        swirl_api::native_packet_worker::run()
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "PacketWorkerInternalOnly",
        ))
    };
    #[cfg(not(windows))]
    let result: std::io::Result<()> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "PacketWorkerWindowsRequired",
    ));
    if let Err(error) = result {
        eprintln!("packet worker failed: {error}");
        std::process::exit(1);
    }
}

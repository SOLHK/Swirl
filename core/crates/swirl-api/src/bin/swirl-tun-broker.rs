//! Product entry point: authentication completes before a helper may recover
//! or change network configuration. No experimental packet worker is used.
fn main() {
    if std::env::args().skip(1).collect::<Vec<_>>() == ["--build-info"] {
        let mut identity = swirl_api::build_info();
        identity["role"] = serde_json::json!("swirl_tun_broker");
        println!("{identity}");
        return;
    }
    #[cfg(windows)]
    let result = swirl_api::native_tun_broker::run(std::env::args().skip(1).collect());
    #[cfg(not(windows))]
    let result: std::io::Result<()> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "BrokerWindowsRequired",
    ));
    if result.is_err() {
        // OS errors and input frames can contain private paths or config.
        eprintln!("Swirl native TUN broker stopped; activation was not confirmed.");
        std::process::exit(1);
    }
}

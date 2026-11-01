//! Explicit disposable-runner WFP enforcement test. Never run on a user's host.
#[cfg(not(windows))]
fn main() {
    eprintln!("WindowsRequired: this is an explicit Windows-only network mutation command");
    std::process::exit(2);
}

#[cfg(windows)]
fn main() {
    if let Err(error) = smoke::run() {
        eprintln!("scoped WFP smoke failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(windows)]
mod smoke {
    use std::{
        fs::{File, OpenOptions},
        io::{self, Read, Write},
        net::{SocketAddr, TcpListener, TcpStream, UdpSocket},
        path::PathBuf,
        process::Command,
        sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        },
        thread,
        time::{Duration, SystemTime, UNIX_EPOCH},
    };
    use swirl_platform::windows_wfp::{Action, Engine, Protocol, ScopedPolicy, ScopedRule};

    const TIMEOUT: Duration = Duration::from_secs(1);

    fn require(value: bool, message: &str) -> io::Result<()> {
        if value {
            Ok(())
        } else {
            Err(io::Error::other(message))
        }
    }

    #[allow(unsafe_code)]
    fn elevated() -> io::Result<bool> {
        use windows_sys::Win32::{
            Foundation::CloseHandle,
            Security::{GetTokenInformation, TOKEN_ELEVATION, TOKEN_QUERY, TokenElevation},
            System::Threading::{GetCurrentProcess, OpenProcessToken},
        };
        let mut token = std::ptr::null_mut();
        // SAFETY: current-process pseudo handle and writable output are valid.
        if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut value = TOKEN_ELEVATION::default();
        let mut bytes = 0;
        // SAFETY: live token, correctly sized output and returned length. Close
        // the token on both success and failure before returning.
        let result = unsafe {
            GetTokenInformation(
                token,
                TokenElevation,
                (&mut value as *mut TOKEN_ELEVATION).cast(),
                std::mem::size_of_val(&value) as u32,
                &mut bytes,
            )
        };
        let error = (result == 0).then(io::Error::last_os_error);
        // SAFETY: unique token handle obtained above, no outstanding borrowers.
        unsafe { CloseHandle(token) };
        if let Some(error) = error {
            return Err(error);
        }
        require(
            bytes as usize == std::mem::size_of_val(&value),
            "invalid token elevation readback",
        )?;
        Ok(value.TokenIsElevated != 0)
    }

    struct Peers {
        endpoints: Vec<(Protocol, SocketAddr)>,
        stop: Arc<AtomicBool>,
        threads: Vec<thread::JoinHandle<io::Result<()>>>,
    }

    impl Peers {
        fn new() -> io::Result<Self> {
            let mut peers = Self {
                endpoints: Vec::new(),
                stop: Arc::new(AtomicBool::new(false)),
                threads: Vec::new(),
            };
            for host in ["127.0.0.1:0", "[::1]:0"] {
                let listener = TcpListener::bind(host)?;
                listener.set_nonblocking(true)?;
                peers
                    .endpoints
                    .push((Protocol::Tcp, listener.local_addr()?));
                let stop = peers.stop.clone();
                peers.threads.push(thread::spawn(move || {
                    let mut streams: Vec<TcpStream> = Vec::new();
                    while !stop.load(Ordering::Acquire) {
                        match listener.accept() {
                            Ok((stream, _)) => {
                                stream.set_nonblocking(true)?;
                                streams.push(stream);
                            }
                            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {}
                            Err(e) => return Err(e),
                        }
                        let mut i = 0;
                        while i < streams.len() {
                            let mut byte = [0];
                            match streams[i].read(&mut byte) {
                                Ok(0) => {
                                    streams.swap_remove(i);
                                    continue;
                                }
                                Ok(_) => streams[i].write_all(&byte)?,
                                Err(e) if e.kind() == io::ErrorKind::WouldBlock => {}
                                Err(_) => {
                                    streams.swap_remove(i);
                                    continue;
                                }
                            }
                            i += 1;
                        }
                        thread::sleep(Duration::from_millis(1));
                    }
                    Ok(())
                }));
                let udp = UdpSocket::bind(host)?;
                udp.set_nonblocking(true)?;
                peers.endpoints.push((Protocol::Udp, udp.local_addr()?));
                let stop = peers.stop.clone();
                peers.threads.push(thread::spawn(move || {
                    while !stop.load(Ordering::Acquire) {
                        let mut data = [0; 8];
                        match udp.recv_from(&mut data) {
                            Ok((length, sender)) => {
                                udp.send_to(&data[..length], sender)?;
                            }
                            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {}
                            Err(e) => return Err(e),
                        }
                        thread::sleep(Duration::from_millis(1));
                    }
                    Ok(())
                }));
            }
            Ok(peers)
        }

        fn finish(&mut self) -> io::Result<()> {
            self.stop.store(true, Ordering::Release);
            let mut first_error = None;
            for thread in self.threads.drain(..) {
                let result = thread
                    .join()
                    .unwrap_or_else(|_| Err(io::Error::other("scoped WFP peer thread panicked")));
                if let Err(error) = result {
                    first_error.get_or_insert(error);
                }
            }
            first_error.map_or(Ok(()), Err)
        }
    }

    impl Drop for Peers {
        fn drop(&mut self) {
            if let Err(error) = self.finish() {
                eprintln!("scoped WFP peer failed during cleanup: {error}");
            }
        }
    }

    fn tcp(endpoint: SocketAddr) -> io::Result<TcpStream> {
        let stream = TcpStream::connect_timeout(&endpoint, TIMEOUT)?;
        stream.set_read_timeout(Some(TIMEOUT))?;
        stream.set_write_timeout(Some(TIMEOUT))?;
        Ok(stream)
    }

    fn tcp_echo(stream: &mut TcpStream) -> io::Result<()> {
        stream.write_all(b"q")?;
        let mut byte = [0];
        stream.read_exact(&mut byte)?;
        require(byte == *b"q", "TCP peer content mismatch")
    }

    fn udp(endpoint: SocketAddr) -> io::Result<UdpSocket> {
        let socket = UdpSocket::bind(if endpoint.is_ipv6() {
            "[::1]:0"
        } else {
            "127.0.0.1:0"
        })?;
        socket.set_read_timeout(Some(TIMEOUT))?;
        socket.set_write_timeout(Some(TIMEOUT))?;
        socket.connect(endpoint)?;
        Ok(socket)
    }

    fn udp_echo(socket: &UdpSocket) -> io::Result<()> {
        socket.send(b"q")?;
        let mut byte = [0; 8];
        let length = socket.recv(&mut byte)?;
        require(&byte[..length] == b"q", "UDP peer content mismatch")
    }

    fn probe(protocol: Protocol, endpoint: SocketAddr) -> io::Result<()> {
        match protocol {
            Protocol::Tcp => tcp_echo(&mut tcp(endpoint)?),
            Protocol::Udp => udp_echo(&udp(endpoint)?),
        }
    }

    fn recover(receipt_path: PathBuf) -> io::Result<()> {
        require(receipt_path.is_absolute(), "receipt path must be absolute")?;
        let mut bytes = Vec::new();
        File::open(receipt_path)?
            .take(16 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        require(
            bytes.len() <= 16 * 1024,
            "receipt exceeds the scoped policy bound",
        )?;
        let policy: ScopedPolicy = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
        let mut engine = Engine::open()?;
        let mut transaction = engine.begin()?;
        transaction.remove(&policy)?;
        transaction.commit()?;
        require(
            engine.absent(&policy)?,
            "explicit recovery readback is not absent",
        )?;
        println!(
            "{}",
            serde_json::json!({"ok":true,"owned_policy_removed":true,
            "evidence":"explicit scoped WFP receipt recovery","system_kill_switch_acceptance":false})
        );
        Ok(())
    }

    pub fn run() -> io::Result<()> {
        let args = std::env::args().skip(1).collect::<Vec<_>>();
        if args.len() == 3 && args[0] == "--peer-probe" {
            let protocol = match args[1].as_str() {
                "tcp" => Protocol::Tcp,
                "udp" => Protocol::Udp,
                _ => return Err(io::Error::other("invalid probe protocol")),
            };
            return probe(protocol, args[2].parse().map_err(io::Error::other)?);
        }
        if args.len() == 4
            && args[0] == "--disposable-network"
            && args[1] == "--recover"
            && args[2] == "--receipt"
        {
            require(
                elevated()?,
                "recovery requires an independently elevated disposable runner",
            )?;
            return recover(PathBuf::from(&args[3]));
        }
        require(
            args.len() == 3 && args[0] == "--disposable-network" && args[1] == "--receipt",
            "requires --disposable-network --receipt <fresh absolute path>; no mutation attempted",
        )?;
        require(
            elevated()?,
            "requires an independently elevated disposable Windows runner",
        )?;
        let receipt_path = PathBuf::from(&args[2]);
        require(receipt_path.is_absolute(), "receipt path must be absolute")?;
        let mut peers = Peers::new()?;
        let mut control = Peers::new()?;
        let ticks = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let policy = ScopedPolicy {
            schema: 1,
            owner: ticks.to_be_bytes(),
            application: std::env::current_exe()?,
            rules: peers
                .endpoints
                .iter()
                .map(|&(protocol, endpoint)| ScopedRule {
                    endpoint,
                    protocol,
                    action: Action::Block,
                })
                .collect(),
        };
        let mut receipt = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&receipt_path)?;
        receipt.write_all(&serde_json::to_vec_pretty(&policy).map_err(io::Error::other)?)?;
        receipt.sync_all()?;
        drop(receipt);
        let mut engine = Engine::open()?;
        require(
            engine.absent(&policy)?,
            "another WFP owner already exists; refusing takeover",
        )?;
        // Exercise a real BFE error after successful staged writes. A poisoned
        // commit must abort all staged objects, including provider/sublayer.
        let mut failed = engine.begin()?;
        failed.install(&policy)?;
        require(
            failed.install(&policy).is_err(),
            "duplicate provider unexpectedly adopted",
        )?;
        require(failed.commit().is_err(), "poisoned transaction committed")?;
        require(
            engine.absent(&policy)?,
            "failed transaction left staged WFP objects",
        )?;
        let mut existing_tcp = Vec::new();
        let mut existing_udp = Vec::new();
        for &(protocol, endpoint) in &peers.endpoints {
            probe(protocol, endpoint)?;
            match protocol {
                Protocol::Tcp => {
                    let mut stream = tcp(endpoint)?;
                    tcp_echo(&mut stream)?;
                    existing_tcp.push(stream);
                }
                Protocol::Udp => {
                    let socket = udp(endpoint)?;
                    udp_echo(&socket)?;
                    existing_udp.push(socket);
                }
            }
        }
        let mut transaction = engine.begin()?;
        transaction.install(&policy)?;
        transaction.commit()?;
        // From here every ordinary Result failure still runs exact cleanup.
        let result = (|| -> io::Result<serde_json::Value> {
            engine.verify(&policy)?;
            for &(protocol, endpoint) in &peers.endpoints {
                require(
                    probe(protocol, endpoint).is_err(),
                    "new flow escaped scoped WFP block",
                )?;
            }
            let tcp_after = existing_tcp
                .iter_mut()
                .map(|stream| tcp_echo(stream).is_ok())
                .collect::<Vec<_>>();
            let udp_after = existing_udp
                .iter()
                .map(|socket| udp_echo(socket).is_ok())
                .collect::<Vec<_>>();
            for &(protocol, endpoint) in &control.endpoints {
                probe(protocol, endpoint)?;
            }
            let mut wrong_owner = policy.clone();
            wrong_owner.owner[0] ^= 1;
            let mut removal = engine.begin()?;
            require(
                removal.remove(&wrong_owner).is_err(),
                "foreign nonce deleted policy",
            )?;
            require(
                removal.commit().is_err(),
                "foreign nonce transaction committed",
            )?;
            engine.verify(&policy)?;
            engine.close()?;
            let mut reopened = Engine::open()?;
            reopened.verify(&policy)?;
            for &(protocol, endpoint) in &peers.endpoints {
                require(
                    probe(protocol, endpoint).is_err(),
                    "closing engine implicitly unlocked persistent policy",
                )?;
            }
            // Same binary at a distinct path has a distinct WFP application ID.
            let other = receipt_path.with_extension("other-app.exe");
            require(!other.exists(), "other-application fixture already exists")?;
            std::fs::copy(&policy.application, &other)?;
            let other_result = (|| {
                for &(protocol, endpoint) in &peers.endpoints {
                    let status = Command::new(&other)
                        .args([
                            "--peer-probe",
                            match protocol {
                                Protocol::Tcp => "tcp",
                                Protocol::Udp => "udp",
                            },
                            &endpoint.to_string(),
                        ])
                        .status()?;
                    require(
                        status.success(),
                        "application-scoped rule affected another executable",
                    )?;
                }
                Ok::<_, io::Error>(())
            })();
            let removed = std::fs::remove_file(&other);
            other_result?;
            removed?;
            Ok(
                serde_json::json!({"existing_tcp_echo_after_commit":tcp_after,"existing_udp_echo_after_commit":udp_after}),
            )
        })();
        let cleanup = (|| {
            let mut engine = Engine::open()?;
            let mut transaction = engine.begin()?;
            transaction.remove(&policy)?;
            transaction.commit()?;
            require(
                engine.absent(&policy)?,
                "WFP cleanup readback is not absent",
            )?;
            for &(protocol, endpoint) in &peers.endpoints {
                probe(protocol, endpoint)?;
            }
            Ok::<_, io::Error>(())
        })();
        // WFP restoration/probes precede peer shutdown. Evaluate both joins
        // before propagating either error, so success cannot hide a failed
        // fixture and one failing group cannot leave another group unjoined.
        let peers_finished = peers.finish();
        let control_finished = control.finish();
        if let Err(error) = cleanup {
            return Err(io::Error::other(format!(
                "WFP cleanup failed; retain receipt {}: {error}",
                receipt_path.display()
            )));
        }
        let observations = result?;
        peers_finished?;
        control_finished?;
        println!(
            "{}",
            serde_json::json!({"ok":true,"evidence":"scoped WFP application loopback transaction smoke",
            "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),
            "rules":policy.rules.len(),"transaction_error_rollback":true,"nonce_conflict_refused":true,
            "persistent_across_engine_reopen":true,"control_endpoints_unchanged":true,"other_application_unchanged":true,
            "owned_policy_removed":true,"new_flow_block_ipv4_ipv6_tcp_udp":true,"observations":observations,
            "system_kill_switch_acceptance":false,"boot_acceptance":false,"existing_flow_revocation_guarantee":false})
        );
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::sync::mpsc;

        #[test]
        fn peer_error_or_panic_is_reported_only_after_all_threads_are_joined() {
            for panic in [false, true] {
                let stop = Arc::new(AtomicBool::new(false));
                let (blocked, block_seen) = mpsc::channel();
                let (release, released) = mpsc::channel();
                let (complete, completed) = mpsc::channel();
                let observed_stop = stop.clone();
                let mut peers = Peers {
                    endpoints: Vec::new(),
                    stop,
                    threads: vec![
                        thread::spawn(move || {
                            assert!(!panic, "injected peer panic");
                            Err(io::Error::from(io::ErrorKind::BrokenPipe))
                        }),
                        thread::spawn(move || {
                            while !observed_stop.load(Ordering::Acquire) {
                                thread::yield_now();
                            }
                            blocked.send(()).unwrap();
                            released.recv().unwrap();
                            Ok(())
                        }),
                    ],
                };
                let finisher = thread::spawn(move || {
                    let result = peers.finish();
                    assert!(peers.threads.is_empty());
                    // Explicit finish consumes all handles; Drop is idempotent.
                    peers.finish().unwrap();
                    complete.send(result).unwrap();
                });
                block_seen.recv_timeout(Duration::from_secs(2)).unwrap();
                let premature = completed.recv_timeout(Duration::from_millis(30));
                // Always release/join before asserting to keep regressions from
                // leaving the test's deliberately blocked fixture detached.
                release.send(()).unwrap();
                let (waited, result) = match premature {
                    Err(mpsc::RecvTimeoutError::Timeout) => (
                        true,
                        completed.recv_timeout(Duration::from_secs(2)).unwrap(),
                    ),
                    Ok(result) => (false, result),
                    Err(error) => panic!("finisher disconnected: {error}"),
                };
                finisher.join().unwrap();
                assert!(waited, "a failed first peer bypassed joining another peer");
                let error = result.unwrap_err();
                assert_eq!(
                    error.kind(),
                    if panic {
                        io::ErrorKind::Other
                    } else {
                        io::ErrorKind::BrokenPipe
                    }
                );
            }
        }
    }
}

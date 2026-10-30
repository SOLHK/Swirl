//! Real Windows socket assumptions used by the disposable Wintun peer fixture.
//! No driver, system proxy, address, route, DNS or firewall state is changed.
#![cfg(windows)]

#[path = "../examples/support/nonblocking_fixture_socket.rs"]
mod fixture_socket;

use std::{
    io::{self, Read, Write},
    net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr, TcpListener, TcpStream, UdpSocket},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

// These deadlines release a mistakenly blocking syscall. They do not measure
// performance: even a late result passes if the actual syscall was WouldBlock.
const START_WAIT: Duration = Duration::from_secs(5);
const ESCAPE_AFTER: Duration = Duration::from_secs(2);
const REAP_WAIT: Duration = Duration::from_secs(5);

#[derive(Debug)]
struct Observation {
    result: io::Result<()>,
    elapsed: Duration,
}

fn require_would_block<W>(
    label: &str,
    operation: impl FnOnce() -> io::Result<()> + Send + 'static,
    wake: impl FnOnce() -> io::Result<W>,
) {
    let (started, ready) = mpsc::sync_channel(1);
    let (completed, result) = mpsc::sync_channel(1);
    let worker = thread::spawn(move || {
        let _ = started.send(());
        let now = Instant::now();
        let observation = Observation {
            result: operation(),
            elapsed: now.elapsed(),
        };
        let _ = completed.send(observation);
    });
    let startup = ready.recv_timeout(START_WAIT);
    let first = result.recv_timeout(ESCAPE_AFTER);
    // Keep the wake socket/stream alive until the probed syscall has returned.
    // A blocking recv consumes the wake byte; a blocking accept accepts this
    // connection. Both are a failed WouldBlock contract, never a retry.
    let escape = matches!(first, Err(mpsc::RecvTimeoutError::Timeout)).then(wake);
    let observation = match first {
        Ok(value) => Ok(value),
        Err(mpsc::RecvTimeoutError::Timeout) => result.recv_timeout(REAP_WAIT),
        Err(error) => Err(error),
    };
    let join_deadline = Instant::now() + REAP_WAIT;
    while !worker.is_finished() && Instant::now() < join_deadline {
        thread::sleep(Duration::from_millis(1));
    }
    let joined = if worker.is_finished() {
        Some(worker.join())
    } else {
        // An OS failure must fail this bounded test rather than hanging the
        // entire suite in join(). Normal blocking probes are released above.
        drop(worker);
        None
    };
    let wake_error = escape.as_ref().and_then(|result| result.as_ref().err());
    assert!(
        matches!(joined, Some(Ok(()))),
        "{label}: socket probe did not finish; startup={startup:?}, observation={observation:?}, wake_error={wake_error:?}"
    );
    let observation = observation.unwrap_or_else(|error| {
        panic!("{label}: no socket result after owned loopback wake: {error}; wake_error={wake_error:?}")
    });
    assert!(
        matches!(&observation.result, Err(error) if error.kind() == io::ErrorKind::WouldBlock),
        "{label}: expected WouldBlock from the actual socket; result={:?}, elapsed={:?}, wake_used={}, wake_error={wake_error:?}",
        observation.result,
        observation.elapsed,
        escape.is_some(),
    );
    eprintln!(
        "Windows fixture socket PASS: {label}; WouldBlock; syscall_elapsed={:?}; escape_used={}",
        observation.elapsed,
        escape.is_some()
    );
}

fn udp_clone(ip: IpAddr) {
    let original = UdpSocket::bind(SocketAddr::new(ip, 0)).unwrap();
    original.set_nonblocking(true).unwrap();
    assert_eq!(
        original.recv_from(&mut [0; 1]).unwrap_err().kind(),
        io::ErrorKind::WouldBlock
    );
    let cloned = fixture_socket::clone_udp_for_tokio(&original).unwrap();
    let address = cloned.local_addr().unwrap();
    assert_eq!(address, original.local_addr().unwrap());
    require_would_block(
        &format!("{ip} cloned UDP empty receive"),
        move || cloned.recv_from(&mut [0; 1]).map(|_| ()),
        move || {
            let wake = UdpSocket::bind(SocketAddr::new(ip, 0))?;
            wake.set_write_timeout(Some(REAP_WAIT))?;
            if wake.send_to(&[0xa7], address)? != 1 {
                return Err(io::Error::new(io::ErrorKind::WriteZero, "short UDP wake"));
            }
            Ok(wake)
        },
    );
    drop(original);
}

fn tcp_clone_and_accepted_stream(ip: IpAddr) {
    let original = TcpListener::bind(SocketAddr::new(ip, 0)).unwrap();
    original.set_nonblocking(true).unwrap();
    assert_eq!(
        original.accept().unwrap_err().kind(),
        io::ErrorKind::WouldBlock
    );
    let cloned = fixture_socket::clone_listener_for_tokio(&original).unwrap();
    let address = cloned.local_addr().unwrap();
    assert_eq!(address, original.local_addr().unwrap());
    require_would_block(
        &format!("{ip} cloned TCP listener empty accept"),
        move || cloned.accept().map(|_| ()),
        move || TcpStream::connect_timeout(&address, REAP_WAIT),
    );
    drop(original);

    // Mio's Windows accept path relies on inheritance from this very listener;
    // it does not explicitly set the accepted stream to nonblocking mode.
    // Use a new owned listener so a late WouldBlock result in the first probe
    // cannot leave its escape connection queued for this independent probe.
    let original = TcpListener::bind(SocketAddr::new(ip, 0)).unwrap();
    original.set_nonblocking(true).unwrap();
    let cloned = fixture_socket::clone_listener_for_tokio(&original).unwrap();
    let address = cloned.local_addr().unwrap();
    let mut peer = TcpStream::connect_timeout(&address, REAP_WAIT).unwrap();
    peer.set_write_timeout(Some(REAP_WAIT)).unwrap();
    let deadline = Instant::now() + REAP_WAIT;
    let (mut accepted, source) = loop {
        match cloned.accept() {
            Ok(connection) => break connection,
            Err(error)
                if error.kind() == io::ErrorKind::WouldBlock && Instant::now() < deadline =>
            {
                thread::sleep(Duration::from_millis(1));
            }
            Err(error) => panic!("{ip}: owned TCP peer setup failed: {error}"),
        }
    };
    assert_eq!(source, peer.local_addr().unwrap());
    require_would_block(
        &format!("{ip} accepted TCP stream empty read"),
        move || accepted.read(&mut [0; 1]).map(|_| ()),
        move || {
            peer.write_all(&[0xa7])?;
            Ok(peer)
        },
    );
    drop(original);
}

#[test]
fn ipv4_udp_fixture_clone_retains_nonblocking_receive() {
    udp_clone(Ipv4Addr::LOCALHOST.into());
}

#[test]
fn ipv6_udp_fixture_clone_retains_nonblocking_receive() {
    udp_clone(Ipv6Addr::LOCALHOST.into());
}

#[test]
fn ipv4_tcp_fixture_clone_and_accepted_stream_retain_nonblocking() {
    tcp_clone_and_accepted_stream(Ipv4Addr::LOCALHOST.into());
}

#[test]
fn ipv6_tcp_fixture_clone_and_accepted_stream_retain_nonblocking() {
    tcp_clone_and_accepted_stream(Ipv6Addr::LOCALHOST.into());
}

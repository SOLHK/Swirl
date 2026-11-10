//! Test-only ownership of loopback TCP/UDP pairs. No host configuration writes.
//!
//! Match tools/tests/loopback_ports.py: Windows TCP and UDP exclusion ranges
//! are independent, so TCP bind(0) is not proof that UDP can use the same port.
//! Filter known reservations, keep owners bound, and never retry an unexplained
//! access denial as if it were an ordinary address collision.
//! https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-bind
use std::{
    collections::HashSet,
    io,
    net::{Ipv4Addr, TcpListener, UdpSocket},
};

fn parse_exclusions(output: &str) -> io::Result<HashSet<u16>> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidData, "InvalidPortExclusionTable");
    let mut ports = HashSet::new();
    let mut table = false;
    for line in output.lines().map(str::trim) {
        let columns: Vec<_> = line.split_whitespace().collect();
        if columns.len() == 2
            && columns
                .iter()
                .all(|column| column.bytes().all(|byte| byte == b'-'))
        {
            table = true;
            continue;
        }
        if !table || line.is_empty() || line.starts_with("* -") {
            continue;
        }
        let row = line.strip_suffix('*').unwrap_or(line).trim_end();
        let columns: Vec<_> = row.split_whitespace().collect();
        if columns.len() != 2
            || !columns
                .iter()
                .all(|column| column.bytes().all(|byte| byte.is_ascii_digit()))
        {
            return Err(invalid());
        }
        let first: u16 = columns[0].parse().map_err(|_| invalid())?;
        let last: u16 = columns[1].parse().map_err(|_| invalid())?;
        if first == 0 || last < first {
            return Err(invalid());
        }
        ports.extend(first..=last);
    }
    if !table {
        return Err(invalid());
    }
    Ok(ports)
}

#[cfg(windows)]
fn exclusion_query(protocol: &str) -> io::Result<Vec<u8>> {
    use std::{
        io::Read,
        process::{Command, Stdio},
        thread,
        time::{Duration, Instant},
    };
    let mut child = Command::new("netsh")
        .args(["interface", "ipv4", "show", "excludedportrange", protocol])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let stdout = child.stdout.take().expect("piped netsh stdout");
    // Drain while waiting: a valid table can exceed the Windows pipe buffer.
    // Only this fixed, read-only netsh command runs; it does not launch peers.
    let reader = match thread::Builder::new()
        .name("fixture-netsh-output".into())
        .spawn(move || {
            let mut output = Vec::new();
            stdout.take(1_048_577).read_to_end(&mut output)?;
            Ok::<_, io::Error>(output)
        }) {
        Ok(reader) => reader,
        Err(error) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    let deadline = Instant::now() + Duration::from_secs(10);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(10)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "PortExclusionQueryTimeout",
                ));
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(error);
            }
        }
    };
    let output = reader
        .join()
        .map_err(|_| io::Error::other("PortExclusionReaderFailed"))??;
    if !status?.success() || output.len() > 1_048_576 {
        return Err(io::Error::other("PortExclusionQueryFailed"));
    }
    Ok(output)
}

#[cfg(windows)]
fn windows_exclusions() -> &'static HashSet<u16> {
    use std::sync::OnceLock;
    static EXCLUSIONS: OnceLock<HashSet<u16>> = OnceLock::new();
    EXCLUSIONS.get_or_init(|| {
        let mut ports = HashSet::new();
        for protocol in ["protocol=tcp", "protocol=udp"] {
            let result = exclusion_query(protocol)
                .expect("read-only Windows fixture port exclusion query failed");
            let output = String::from_utf8_lossy(&result);
            eprintln!("DNS fixture reservation snapshot: ipv4 {protocol}\n{output}");
            ports.extend(
                parse_exclusions(&output).expect("unrecognized Windows port exclusion table"),
            );
        }
        ports
    })
}

fn reserve_pair<T, U>(
    exclusions: &HashSet<u16>,
    mut tcp: impl FnMut() -> io::Result<(T, u16)>,
    mut udp: impl FnMut(u16) -> io::Result<U>,
) -> io::Result<(T, U)> {
    if exclusions.len() == usize::from(u16::MAX) {
        return Err(io::Error::new(
            io::ErrorKind::AddrNotAvailable,
            "NoUnexcludedFixturePort",
        ));
    }
    let mut held = Vec::new();
    let mut filtered = HashSet::new();
    let mut collisions = 0;
    loop {
        let (owner, port) = tcp()?;
        if exclusions.contains(&port) {
            // This finite precheck is separate from actual bind retries. Hold
            // every rejected owner so a sequential allocator can traverse an
            // entire exclusion block without choosing the same port again.
            if !filtered.insert(port) {
                return Err(io::Error::other("FixtureAllocatorReusedHeldPort"));
            }
            held.push(owner);
            continue;
        }
        match udp(port) {
            Ok(socket) => return Ok((owner, socket)),
            Err(error) => {
                eprintln!(
                    "DNS fixture UDP bind failed: port={port}, kind={:?}, os={:?}",
                    error.kind(),
                    error.raw_os_error()
                );
                if error.kind() != io::ErrorKind::AddrInUse || collisions == 15 {
                    return Err(error);
                }
                collisions += 1;
                held.push(owner);
            }
        }
    }
}

pub(super) fn reserve_tcp_udp() -> io::Result<(TcpListener, UdpSocket)> {
    #[cfg(windows)]
    let exclusions = windows_exclusions();
    #[cfg(not(windows))]
    let exclusions = &HashSet::new();
    reserve_pair(
        exclusions,
        || {
            let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
            let port = listener.local_addr()?.port();
            Ok((listener, port))
        },
        |port| UdpSocket::bind((Ipv4Addr::LOCALHOST, port)),
    )
}

#[test]
fn localized_exclusion_tables_are_numeric_and_fail_closed() {
    let ports = parse_exclusions("协议 udp 端口排除范围\n起始端口 结束端口\n---------- ----------\n50000 50031\n51000 51001 *\n\n* - 管理的端口排除。\n").unwrap();
    assert_eq!(ports.len(), 34);
    assert!(ports.contains(&50031) && ports.contains(&51001));
    assert!(!ports.contains(&50032));
    assert_eq!(
        parse_exclusions("--- ---\n51000 51001*\n").unwrap(),
        (51000..=51001).collect()
    );
    assert!(
        parse_exclusions("heading\n----- -----\n")
            .unwrap()
            .is_empty()
    );
    for invalid in [
        "",
        "1 10",
        "--- ---\n0 10",
        "--- ---\n2 1",
        "--- ---\n1 65536",
        "--- ---\n1 2 extra",
        "--- ---\n+1 2",
        "--- ---\n1 +2",
        "--- ---\n1 2**",
        "--- ---\nunrecognized data",
    ] {
        assert!(parse_exclusions(invalid).is_err(), "accepted {invalid:?}");
    }
}

#[test]
fn a_whole_exclusion_block_is_filtered_without_releasing_owners() {
    use std::{cell::Cell, rc::Rc};
    struct Owner(Rc<Cell<usize>>);
    impl Drop for Owner {
        fn drop(&mut self) {
            self.0.set(self.0.get() - 1);
        }
    }
    let live = Rc::new(Cell::new(0));
    let mut next = 50000;
    let exclusions = (50000..50032).collect();
    let (owner, ()) = reserve_pair(
        &exclusions,
        || {
            assert_eq!(live.get(), usize::from(next - 50000));
            live.set(live.get() + 1);
            let port = next;
            next += 1;
            Ok((Owner(live.clone()), port))
        },
        |port| {
            assert_eq!(port, 50032, "attempted UDP in the known excluded block");
            Ok(())
        },
    )
    .unwrap();
    assert_eq!(next, 50033);
    assert_eq!(live.get(), 1);
    drop(owner);
    assert_eq!(live.get(), 0);
}

#[test]
fn an_unknown_access_denial_is_fatal_even_after_a_collision() {
    let mut attempts = 0;
    let mut next = 50000;
    let result = reserve_pair(
        &HashSet::new(),
        || {
            next += 1;
            Ok(((), next))
        },
        |_| {
            attempts += 1;
            Err::<(), _>(io::Error::from(if attempts == 1 {
                io::ErrorKind::AddrInUse
            } else {
                io::ErrorKind::PermissionDenied
            }))
        },
    );
    assert_eq!(result.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
    assert_eq!(attempts, 2);
}

#[test]
fn real_pair_owns_both_protocols_for_the_same_loopback_port() {
    let (tcp, udp) = reserve_tcp_udp().unwrap();
    let address = tcp.local_addr().unwrap();
    assert_eq!(address, udp.local_addr().unwrap());
    assert!(address.ip().is_loopback() && address.port() != 0);
    assert!(TcpListener::bind(address).is_err());
    assert!(UdpSocket::bind(address).is_err());
}

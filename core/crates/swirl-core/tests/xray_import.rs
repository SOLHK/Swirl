//! Source JSON -> archive -> native Config -> Core -> independent proxy -> target.
//! All endpoints/credentials are synthetic and every socket stays on loopback.
//! These tests are not TLS/REALITY, public-network, or provider verification.
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{Ipv4Addr, Shutdown, SocketAddr, TcpListener, TcpStream},
    thread,
    time::{Duration, Instant},
};
use swirl_core::Core;
use swirl_subscription::{
    Config,
    xray::{
        InputSource,
        convert::{ConvertedDocument, NativeStatus, Protocol, import_document},
    },
};

const UUID: &str = "00112233-4455-6677-8899-aabbccddeeff";
const UUID_BYTES: [u8; 16] = [
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
];
const DEADLINE: Duration = Duration::from_secs(5);
const REMOTE_NAME: &str = "origin.fixture.invalid";
const TAIL: &[u8] = b"AFTER_UPLOAD_EOF\0\x80\xff";

#[derive(Clone, Copy)]
enum PeerProtocol {
    Http,
    Socks5,
    Vless,
    Socks4,
    Socks4a,
}

fn payloads() -> (Vec<u8>, Vec<u8>) {
    let upload = (0..32_785).map(|i| (i % 251) as u8).collect();
    let mut download: Vec<u8> = (0..16_403).map(|i| ((i * 13) % 256) as u8).collect();
    download.extend(TAIL);
    (upload, download)
}
fn socket_limits(stream: &TcpStream) {
    stream.set_read_timeout(Some(DEADLINE)).unwrap();
    stream.set_write_timeout(Some(DEADLINE)).unwrap();
}
fn accept(listener: &TcpListener) -> TcpStream {
    listener.set_nonblocking(true).unwrap();
    let deadline = Instant::now() + DEADLINE;
    loop {
        match listener.accept() {
            Ok((stream, _)) => {
                stream.set_nonblocking(false).unwrap();
                socket_limits(&stream);
                return stream;
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(Instant::now() < deadline, "fixture accept deadline");
                thread::sleep(Duration::from_millis(2));
            }
            Err(error) => panic!("fixture accept failed: {error}"),
        }
    }
}
fn no_extra_connection(listener: &TcpListener) {
    listener.set_nonblocking(true).unwrap();
    assert_eq!(
        listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}
fn read<const N: usize>(stream: &mut TcpStream) -> [u8; N] {
    let mut bytes = [0; N];
    stream.read_exact(&mut bytes).unwrap();
    bytes
}
fn eof(stream: &mut TcpStream) {
    assert_eq!(
        stream.read(&mut [0]).unwrap(),
        0,
        "expected exact half-close boundary"
    );
}
fn header(stream: &mut TcpStream) -> Vec<u8> {
    let mut bytes = Vec::new();
    while !bytes.ends_with(b"\r\n\r\n") {
        assert!(bytes.len() < 8192, "bounded fixture HTTP header");
        bytes.push(read::<1>(stream)[0]);
    }
    bytes
}
fn terminated(stream: &mut TcpStream) -> Vec<u8> {
    let mut bytes = Vec::new();
    loop {
        let next = read::<1>(stream)[0];
        if next == 0 {
            return bytes;
        }
        assert!(bytes.len() < 255, "bounded fixture SOCKS4 string");
        bytes.push(next);
    }
}
fn write_fragments(stream: &mut TcpStream, bytes: &[u8]) {
    for chunk in bytes.chunks(997) {
        stream.write_all(chunk).unwrap();
    }
}

fn upstream_request(stream: &mut TcpStream, protocol: PeerProtocol, origin: SocketAddr) {
    match protocol {
        PeerProtocol::Http => {
            let bytes = header(stream);
            let text = std::str::from_utf8(&bytes).unwrap();
            let mut first = text.lines().next().unwrap().split_ascii_whitespace();
            assert_eq!(first.next(), Some("CONNECT"));
            assert_eq!(first.next().unwrap().parse::<SocketAddr>().unwrap(), origin);
            assert_eq!(first.next(), Some("HTTP/1.1"));
            assert_eq!(first.next(), None);
            // Independent expected RFC 7617 bytes for the selected "u":"p".
            assert_eq!(
                text.lines()
                    .filter(|line| line.starts_with("Proxy-Authorization:"))
                    .collect::<Vec<_>>(),
                ["Proxy-Authorization: Basic dTpw"]
            );
            assert!(text.lines().any(|line| line == format!("Host: {origin}")));
        }
        PeerProtocol::Socks5 => {
            // Password authentication must be offered exclusively; it cannot
            // silently negotiate noauth when the imported account is present.
            assert_eq!(read::<3>(stream), [5, 1, 2]);
            stream.write_all(&[5, 2]).unwrap();
            assert_eq!(read::<2>(stream), [1, 1]);
            assert_eq!(read::<1>(stream), *b"u");
            assert_eq!(read::<2>(stream), [1, b'p']);
            stream.write_all(&[1, 0]).unwrap();
            assert_eq!(read::<4>(stream), [5, 1, 0, 1]);
            let address = Ipv4Addr::from(read::<4>(stream));
            let port = u16::from_be_bytes(read::<2>(stream));
            assert_eq!(SocketAddr::from((address, port)), origin);
        }
        PeerProtocol::Vless => {
            assert_eq!(read::<1>(stream), [0]);
            assert_eq!(read::<16>(stream), UUID_BYTES);
            assert_eq!(read::<2>(stream), [0, 1]); // no addons, TCP command
            let port = u16::from_be_bytes(read::<2>(stream));
            assert_eq!(read::<1>(stream), [1]); // IPv4
            let address = Ipv4Addr::from(read::<4>(stream));
            assert_eq!(SocketAddr::from((address, port)), origin);
        }
        PeerProtocol::Socks4 | PeerProtocol::Socks4a => {
            assert_eq!(read::<2>(stream), [4, 1]);
            let port = u16::from_be_bytes(read::<2>(stream));
            let address = Ipv4Addr::from(read::<4>(stream));
            let user_id = terminated(stream);
            assert_eq!(port, origin.port());
            if matches!(protocol, PeerProtocol::Socks4a) {
                assert_eq!(address, Ipv4Addr::new(0, 0, 0, 1));
                assert_eq!(user_id, b"fixture-user-id");
                assert_eq!(terminated(stream), REMOTE_NAME.as_bytes());
            } else {
                assert_eq!(SocketAddr::from((address, port)), origin);
                // An explicit empty account has the upstream empty USERID.
                assert_eq!(user_id, b"");
            }
        }
    }
}
fn response_prefix(stream: &mut TcpStream, protocol: PeerProtocol) {
    let bytes: &[u8] = match protocol {
        PeerProtocol::Http => b"HTTP/1.1 200 Connection Established\r\n\r\n",
        PeerProtocol::Socks5 => &[5, 0, 0, 1, 127, 0, 0, 1, 0, 0],
        PeerProtocol::Vless => &[0, 0],
        PeerProtocol::Socks4 | PeerProtocol::Socks4a => &[0, 90, 0, 0, 0, 0, 0, 0],
    };
    // Exercise response-prefix reads across separately written fragments.
    for chunk in bytes.chunks(1) {
        stream.write_all(chunk).unwrap();
    }
}

fn source(protocol: PeerProtocol, port: u16, unused_port: u16) -> (Value, usize) {
    let stream = json!({"network":"tcp","security":"none"});
    match protocol {
        PeerProtocol::Vless => (
            json!({"protocol":"vless","settings":{"vnext":[{
                "address":"127.0.0.1","port":port,
                "users":[{"id":"ffffffff-ffff-ffff-ffff-ffffffffffff","encryption":"none"},
                    {"id":UUID,"encryption":"none"}]
            }]},"streamSettings":stream}),
            1,
        ),
        PeerProtocol::Http | PeerProtocol::Socks5 => (
            json!({"protocol":if matches!(protocol,PeerProtocol::Http) {"http"} else {"socks"},
                "settings":{"servers":[
                    {"address":"127.0.0.1","port":unused_port,"users":[{"user":"unused","pass":"unused"}]},
                    {"address":"127.0.0.1","port":port,"users":[
                        {"user":"unused","pass":"unused"},{"user":"u","pass":"p"}]}
                ]},"streamSettings":stream}),
            2,
        ),
        PeerProtocol::Socks4 | PeerProtocol::Socks4a => (
            json!({"protocol":"socks","settings":{
                "version":if matches!(protocol,PeerProtocol::Socks4a) {"4A"} else {"4"},
                "servers":[{"address":"127.0.0.1","port":port,"users":[
                    if matches!(protocol,PeerProtocol::Socks4a) {json!({"user":"fixture-user-id"})} else {json!({})}
                ]}]},"streamSettings":stream}),
            0,
        ),
    }
}

fn roundtrip_runtime(protocol: PeerProtocol) {
    let origin = TcpListener::bind("127.0.0.1:0").unwrap();
    let origin_address = origin.local_addr().unwrap();
    let peer = TcpListener::bind("127.0.0.1:0").unwrap();
    let unused = TcpListener::bind("127.0.0.1:0").unwrap();
    let (document, selected) = source(
        protocol,
        peer.local_addr().unwrap().port(),
        unused.local_addr().unwrap().port(),
    );
    let original = serde_json::to_vec_pretty(&document).unwrap();
    let imported = import_document(&original, InputSource::File).unwrap();
    let restored = ConvertedDocument::restore(&imported.save().unwrap()).unwrap();
    assert_eq!(restored.raw_json(), original);
    let chosen = &restored.nodes()[selected];
    assert_eq!(
        chosen.native_status(),
        NativeStatus::Executable,
        "{:?}",
        chosen.diagnostics()
    );
    assert!(chosen.native_outbound().is_some());
    assert!(!chosen.network_verified());
    if matches!(protocol, PeerProtocol::Http | PeerProtocol::Socks5) {
        assert_eq!(chosen.source().server_index, Some(1));
        assert_eq!(chosen.source().user_index, Some(1));
    }
    let config = restored
        .native_config(selected, SocketAddr::from(([127, 0, 0, 1], 0)))
        .unwrap();
    // This is the same serialized standard Config boundary used by Core/FFI.
    let config = Config::parse(&serde_json::to_vec(&config).unwrap()).unwrap();
    let mut core = Core::start(config).unwrap();

    let origin_listener = origin.try_clone().unwrap();
    let origin_task = thread::spawn(move || {
        let mut stream = accept(&origin_listener);
        let connected_from = stream.peer_addr().unwrap();
        let (upload, download) = payloads();
        let mut received = vec![0; upload.len()];
        stream.read_exact(&mut received).unwrap();
        assert_eq!(received, upload);
        // The reply is impossible until the caller's write-half close arrived.
        eof(&mut stream);
        write_fragments(&mut stream, &download);
        stream.shutdown(Shutdown::Write).unwrap();
        connected_from
    });
    let peer_listener = peer.try_clone().unwrap();
    let peer_task = thread::spawn(move || {
        let mut stream = accept(&peer_listener);
        upstream_request(&mut stream, protocol, origin_address);
        // The only fixture permitted to open the origin socket is this peer,
        // after independently verifying destination and authentication bytes.
        let mut destination = TcpStream::connect_timeout(&origin_address, DEADLINE).unwrap();
        socket_limits(&destination);
        let connected_from = destination.local_addr().unwrap();
        response_prefix(&mut stream, protocol);
        let (upload, download) = payloads();
        let mut observed_upload = vec![0; upload.len()];
        stream.read_exact(&mut observed_upload).unwrap();
        assert_eq!(observed_upload, upload);
        eof(&mut stream);
        write_fragments(&mut destination, &observed_upload);
        destination.shutdown(Shutdown::Write).unwrap();
        let mut observed_download = vec![0; download.len()];
        destination.read_exact(&mut observed_download).unwrap();
        assert_eq!(observed_download, download);
        eof(&mut destination);
        write_fragments(&mut stream, &observed_download);
        stream.shutdown(Shutdown::Write).unwrap();
        connected_from
    });

    let mut client = TcpStream::connect_timeout(&core.address(), DEADLINE).unwrap();
    socket_limits(&client);
    let target = if matches!(protocol, PeerProtocol::Socks4a) {
        // No resolver is needed: the independent SOCKS4a peer validates this
        // name and connects only to its previously bound loopback origin.
        format!("{REMOTE_NAME}:{}", origin_address.port())
    } else {
        origin_address.to_string()
    };
    write!(
        client,
        "CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n"
    )
    .unwrap();
    assert_eq!(
        header(&mut client),
        b"HTTP/1.1 200 Connection Established\r\n\r\n"
    );
    let (upload, download) = payloads();
    write_fragments(&mut client, &upload);
    client.shutdown(Shutdown::Write).unwrap();
    let mut response = vec![0; download.len()];
    client.read_exact(&mut response).unwrap();
    assert_eq!(response, download);
    assert!(response.ends_with(TAIL));
    eof(&mut client);
    drop(client);
    // Exact source-port equality proves the origin's connection came through
    // our independently observed peer, rather than a direct fallback.
    assert_eq!(peer_task.join().unwrap(), origin_task.join().unwrap());
    let deadline = Instant::now() + DEADLINE;
    loop {
        let state = core.snapshot().unwrap();
        if state.active == 0 {
            assert_eq!(state.accepted, 1);
            assert_eq!(state.failed, 0, "{}", state.last_error);
            assert_eq!(state.upload, upload.len() as u64);
            assert_eq!(state.download, download.len() as u64);
            break;
        }
        assert!(Instant::now() < deadline, "native connection did not close");
        thread::sleep(Duration::from_millis(2));
    }
    core.stop();
    no_extra_connection(&unused);
    no_extra_connection(&peer);
    no_extra_connection(&origin);
    // Observations are evidence for this synthetic test, not an import flag.
    assert!(!restored.nodes()[selected].network_verified());
}

#[test]
fn xray_http_selected_account_survives_archive_and_halfclose_to_origin() {
    roundtrip_runtime(PeerProtocol::Http);
}
#[test]
fn xray_socks5_selected_server_and_account_halfclose_to_origin() {
    roundtrip_runtime(PeerProtocol::Socks5);
}
#[test]
fn xray_vless_selected_uuid_survives_archive_and_halfclose_to_origin() {
    roundtrip_runtime(PeerProtocol::Vless);
}
#[test]
fn xray_socks4_empty_account_survives_archive_and_halfclose_to_origin() {
    roundtrip_runtime(PeerProtocol::Socks4);
}
#[test]
fn xray_socks4a_case_alias_preserves_remote_name_and_userid_to_origin() {
    roundtrip_runtime(PeerProtocol::Socks4a);
}
#[test]
fn vmess_and_unsupported_transport_never_produce_a_runtime_or_socket() {
    let peer = TcpListener::bind("127.0.0.1:0").unwrap();
    for (protocol, network) in [("vmess", "tcp"), ("vless", "grpc")] {
        let user = if protocol == "vmess" {
            json!({"id":UUID,"alterId":16,"security":"none"})
        } else {
            json!({"id":UUID,"encryption":"none"})
        };
        let original = serde_json::to_vec(&json!({
            "protocol":protocol,"settings":{"vnext":[{
                "address":"127.0.0.1","port":peer.local_addr().unwrap().port(),"users":[user]
            }]},"streamSettings":{"network":network,"security":"none"}
        }))
        .unwrap();
        let document = import_document(&original, InputSource::File).unwrap();
        let document = ConvertedDocument::restore(&document.save().unwrap()).unwrap();
        assert_eq!(
            document.nodes()[0].protocol(),
            if protocol == "vmess" {
                Protocol::Vmess
            } else {
                Protocol::Vless
            }
        );
        assert_eq!(document.nodes()[0].native_status(), NativeStatus::Blocked);
        assert!(document.nodes()[0].native_outbound().is_none());
        assert!(
            document
                .native_config(0, SocketAddr::from(([127, 0, 0, 1], 0)))
                .is_err()
        );
        no_extra_connection(&peer);
    }
}

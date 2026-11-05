//! Real UDP socket regressions for SS2022 egress. The Windows-only guard lives
//! in this integration process; no test installs routes, DNS settings or TUN.
use aes::cipher::{BlockDecrypt, BlockEncrypt, KeyInit};
use base64::{Engine, engine::general_purpose::STANDARD};
use ring::aead;
use std::{
    io,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use swirl_dns::Resolver;
use swirl_protocol::{Target, ss2022::UdpAssociation};
use tokio::{net::UdpSocket, sync::Mutex, time::timeout};

const WAIT: Duration = Duration::from_secs(5);
static TEST_GUARD: Mutex<()> = Mutex::const_new(());

fn clock() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs()
}

fn header(master: &[u8], bytes: [u8; 16], decrypt: bool) -> [u8; 16] {
    let mut block = aes::Block::from(bytes);
    match (master.len(), decrypt) {
        (16, false) => aes::Aes128::new_from_slice(master)
            .unwrap()
            .encrypt_block(&mut block),
        (16, true) => aes::Aes128::new_from_slice(master)
            .unwrap()
            .decrypt_block(&mut block),
        (32, false) => aes::Aes256::new_from_slice(master)
            .unwrap()
            .encrypt_block(&mut block),
        (32, true) => aes::Aes256::new_from_slice(master)
            .unwrap()
            .decrypt_block(&mut block),
        _ => panic!("unsupported fixture key"),
    }
    block.into()
}

fn packet_key(master: &[u8], session: &[u8]) -> aead::LessSafeKey {
    let material = [master, session].concat();
    let derived = blake3::derive_key("shadowsocks 2022 session subkey", &material);
    let algorithm = if master.len() == 16 {
        &aead::AES_128_GCM
    } else {
        &aead::AES_256_GCM
    };
    aead::LessSafeKey::new(aead::UnboundKey::new(algorithm, &derived[..master.len()]).unwrap())
}

// Bounded SIP022 peer fixture, using the raw crypto primitives rather than the
// production UdpSession encoder/decoder. This checks actual encrypted packets;
// the existing official shadowsocks-rust suite remains the interop authority.
fn reply(master: &[u8], wire: &[u8], packet_id: u64, expected: &[u8], response: &[u8]) -> Vec<u8> {
    assert!(wire.len() >= 16 + 11 + 16);
    let request_header = header(master, wire[..16].try_into().unwrap(), true);
    assert_eq!(
        u64::from_be_bytes(request_header[8..].try_into().unwrap()),
        packet_id
    );
    let mut body = wire[16..].to_vec();
    let plain = packet_key(master, &request_header[..8])
        .open_in_place(
            aead::Nonce::assume_unique_for_key(request_header[4..].try_into().unwrap()),
            aead::Aad::empty(),
            &mut body,
        )
        .unwrap();
    assert_eq!(plain[0], 0);
    assert!(clock().abs_diff(u64::from_be_bytes(plain[1..9].try_into().unwrap())) <= 30);
    let padding = usize::from(u16::from_be_bytes([plain[9], plain[10]]));
    assert_eq!(&plain[11 + padding..], expected);

    let mut response_header = request_header;
    for byte in &mut response_header[..8] {
        *byte ^= 0x80;
    }
    let mut body = vec![1];
    body.extend_from_slice(&clock().to_be_bytes());
    body.extend_from_slice(&request_header[..8]);
    body.extend_from_slice(&[0, 0]);
    body.extend_from_slice(response);
    packet_key(master, &response_header[..8])
        .seal_in_place_append_tag(
            aead::Nonce::assume_unique_for_key(response_header[4..].try_into().unwrap()),
            aead::Aad::empty(),
            &mut body,
        )
        .unwrap();
    [header(master, response_header, false).as_slice(), &body].concat()
}

async fn loopback_roundtrips() {
    for (cipher, key_len) in [
        ("2022-blake3-aes-128-gcm", 16),
        ("2022-blake3-aes-256-gcm", 32),
    ] {
        let master = vec![73; key_len];
        for bind in ["127.0.0.1:0", "[::1]:0"] {
            let peer = UdpSocket::bind(bind).await.unwrap();
            let address = peer.local_addr().unwrap();
            let mut association = UdpAssociation::connect(
                &address.ip().to_string(),
                address.port(),
                &STANDARD.encode(&master),
                cipher,
                &Resolver::default(),
                WAIT,
            )
            .await
            .unwrap();
            // UDP connect only selects a peer; the constructor emits no packet.
            assert_eq!(
                peer.try_recv(&mut [0; 1]).unwrap_err().kind(),
                io::ErrorKind::WouldBlock
            );
            let target = Target {
                host: "udp.fixture.invalid".into(),
                port: 5353,
            };
            let mut encoded = vec![3, target.host.len() as u8];
            encoded.extend_from_slice(target.host.as_bytes());
            encoded.extend_from_slice(&target.port.to_be_bytes());
            for (packet_id, payload) in [vec![], vec![0x5a; 1200]].into_iter().enumerate() {
                association.send(&target, &payload).await.unwrap();
                let mut buffer = [0; 2048];
                let (size, source) = timeout(WAIT, peer.recv_from(&mut buffer))
                    .await
                    .unwrap()
                    .unwrap();
                assert!(source.ip().is_loopback());
                assert_eq!(source.is_ipv6(), address.is_ipv6());
                let expected = [encoded.as_slice(), &payload].concat();
                let response = [encoded.as_slice(), b"peer:", &payload].concat();
                let wire = reply(
                    &master,
                    &buffer[..size],
                    packet_id as u64,
                    &expected,
                    &response,
                );
                assert_eq!(peer.send_to(&wire, source).await.unwrap(), wire.len());
                let (returned, body) = timeout(WAIT, association.recv()).await.unwrap().unwrap();
                assert_eq!(
                    (returned.host, returned.port),
                    (target.host.clone(), target.port)
                );
                assert_eq!(body, [b"peer:".as_slice(), &payload].concat());
            }
        }
    }
}

#[tokio::test]
async fn ss2022_udp_keeps_authenticated_empty_and_full_ipv4_ipv6_datagrams() {
    let _guard = TEST_GUARD.lock().await;
    loopback_roundtrips().await;
}

#[cfg(windows)]
#[tokio::test]
async fn suspended_ss2022_rejects_external_peers_and_keeps_explicit_loopback() {
    use swirl_transport::egress::EgressLease;

    let _guard = TEST_GUARD.lock().await;
    let lease = EgressLease::acquire_suspended().unwrap();
    for host in ["192.0.2.1", "2001:db8::1"] {
        let result = UdpAssociation::connect(
            host,
            5353,
            &STANDARD.encode([73; 16]),
            "2022-blake3-aes-128-gcm",
            &Resolver::default(),
            WAIT,
        )
        .await;
        assert!(
            matches!(result, Err("Ss2022UdpConnect")),
            "suspended external UDP must not acquire an unbound socket"
        );
    }
    loopback_roundtrips().await;
    lease.release_after_routes_restored().unwrap();
}

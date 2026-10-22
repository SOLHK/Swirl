use super::*;
use std::io::{Cursor, Read, Write};
use x25519_dalek::{PublicKey, StaticSecret};

fn client() -> TlsClient {
    let public = *PublicKey::from(&StaticSecret::from([0x42; 32])).as_bytes();
    let parameters =
        ClientParameters::new("reality.test", public, &[0xab, 0xcd], [26, 10, 19]).unwrap();
    TlsClient::new(&parameters, 1_792_353_600, &[b"h2".to_vec()]).unwrap()
}

fn drain(client: &mut TlsClient) -> Vec<u8> {
    let mut output = Vec::new();
    for _ in 0..16 {
        if !client.wants_write() {
            return output;
        }
        assert!(client.write_tls(&mut output).unwrap() > 0);
    }
    panic!("bounded test output did not drain")
}

fn record(kind: u8, payload: &[u8]) -> Vec<u8> {
    let mut out = vec![kind, 3, 3];
    out.extend_from_slice(&(payload.len() as u16).to_be_bytes());
    out.extend_from_slice(payload);
    out
}

fn server_hello(client_flight: &[u8]) -> Vec<u8> {
    let client_hello = &client_flight[5..];
    let key = PublicKey::from(&StaticSecret::from([0x24; 32]));
    let mut extensions = vec![0, 43, 0, 2, 3, 4, 0, 51, 0, 36, 0, 29, 0, 32];
    extensions.extend_from_slice(key.as_bytes());
    let mut body = vec![3, 3];
    body.extend_from_slice(&[0x99; 32]);
    body.push(32);
    body.extend_from_slice(&client_hello[hello::SESSION_ID]);
    body.extend_from_slice(&[0x13, 1, 0]);
    body.extend_from_slice(&(extensions.len() as u16).to_be_bytes());
    body.extend_from_slice(&extensions);
    let mut out = vec![2];
    out.extend_from_slice(&(body.len() as u32).to_be_bytes()[1..]);
    out.extend_from_slice(&body);
    out
}

fn feed(client: &mut TlsClient, bytes: &[u8]) -> io::Result<()> {
    let mut input = Cursor::new(bytes);
    for _ in 0..bytes.len() + 1 {
        if input.position() as usize == bytes.len() {
            return Ok(());
        }
        drain(client);
        let read = client.read_tls(&mut input)?;
        assert!(read > 0);
    }
    panic!("bounded test input did not drain")
}

#[test]
fn no_application_or_negotiated_success_before_finished() {
    let mut client = client();
    assert!(client.is_handshaking());
    assert!(!client.wants_read());
    assert_eq!(
        client.read_plaintext(&mut [0; 16]).unwrap_err().kind(),
        io::ErrorKind::WouldBlock
    );
    assert_eq!(
        client
            .write_plaintext(b"secret application")
            .unwrap_err()
            .kind(),
        io::ErrorKind::WouldBlock
    );
    assert_eq!(
        client.send_close_notify().unwrap_err().kind(),
        io::ErrorKind::WouldBlock
    );
    assert!(client.negotiated_cipher_suite().is_none());
    assert!(client.negotiated_group().is_none());
    assert!(client.alpn_protocol().is_none());
    let flight = drain(&mut client);
    let hello = server_hello(&flight);
    feed(&mut client, &record(22, &hello)).unwrap();
    assert!(client.is_handshaking());
    assert!(client.negotiated_cipher_suite().is_none());
    assert_eq!(
        client
            .write_plaintext(b"still unauthenticated")
            .unwrap_err()
            .kind(),
        io::ErrorKind::WouldBlock
    );
}

#[test]
fn server_hello_record_fragmentation_preserves_the_exact_message() {
    for split in [1, 2, 3, 4, 38, 39, 70, 71, 100] {
        let mut client = client();
        let hello = server_hello(&drain(&mut client));
        let parts = [record(22, &hello[..split]), record(22, &hello[split..])].concat();
        for byte in parts {
            feed(&mut client, &[byte]).unwrap();
        }
        assert!(client.first_server_hello.is_none());
        assert!(client.is_handshaking());
    }
}

#[test]
fn server_hello_input_never_consumes_bytes_from_the_next_record() {
    let mut client = client();
    let hello = server_hello(&drain(&mut client));
    let first = record(22, &hello);
    let mut input = Cursor::new([first.as_slice(), b"untouched-next-record"].concat());
    assert_eq!(client.read_tls(&mut input).unwrap(), 5);
    assert_eq!(client.read_tls(&mut input).unwrap(), hello.len());
    assert_eq!(input.position() as usize, first.len());
    let mut untouched = Vec::new();
    input.read_to_end(&mut untouched).unwrap();
    assert_eq!(untouched, b"untouched-next-record");
}

#[test]
fn invalid_session_echo_fails_before_backend_and_poison_is_sticky() {
    let mut client = client();
    let mut hello = server_hello(&drain(&mut client));
    hello[39] ^= 1;
    assert_eq!(
        feed(&mut client, &record(22, &hello))
            .unwrap_err()
            .to_string(),
        "RealitySessionIdEcho"
    );
    assert!(client.first_server_hello.is_some());
    assert!(!client.wants_write());
    assert!(!client.wants_read());
    assert_eq!(
        client
            .write_plaintext(b"must not escape")
            .unwrap_err()
            .to_string(),
        "RealityConnectionFailed"
    );
    assert_eq!(
        client.read_plaintext(&mut [0; 1]).unwrap_err().to_string(),
        "RealityConnectionFailed"
    );
}

#[test]
fn hrr_is_rejected_without_emitting_a_second_clienthello() {
    let mut client = client();
    let mut hello = server_hello(&drain(&mut client));
    hello[6..38].copy_from_slice(&[
        0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65, 0xb8,
        0x91, 0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2, 0xc8, 0xa8,
        0x33, 0x9c,
    ]);
    assert_eq!(
        feed(&mut client, &record(22, &hello))
            .unwrap_err()
            .to_string(),
        "RealityHelloRetryUnsupported"
    );
    assert!(!client.wants_write());
}

#[test]
fn malformed_record_headers_fail_before_payload_allocation() {
    for header in [
        [22, 3, 1, 0, 1],
        [22, 3, 3, 0, 0],
        [22, 3, 3, 64, 1],
        [23, 3, 3, 65, 1],
        [24, 3, 3, 0, 1],
        [20, 3, 3, 0, 2],
        [21, 3, 3, 0, 3],
        [22, 3, 3, 255, 255],
    ] {
        let mut client = client();
        drain(&mut client);
        assert!(feed(&mut client, &header).is_err(), "{header:?}");
        assert_eq!(client.record.len(), 5);
        assert!(client.failed);
    }
}

#[test]
fn fragmented_record_and_handshake_eof_are_failures() {
    for length in 0..10 {
        let mut client = client();
        let flight = drain(&mut client);
        let input = record(22, &server_hello(&flight));
        feed(&mut client, &input[..length]).unwrap();
        assert_eq!(
            client.read_tls(&mut io::empty()).unwrap_err().kind(),
            io::ErrorKind::UnexpectedEof
        );
        assert!(client.failed);
    }
}

#[test]
fn first_flight_budgets_and_trailing_plaintext_are_rejected() {
    let mut client = client();
    drain(&mut client);
    // Declare an unfinished 256-byte SH and exhaust the bounded record budget.
    feed(&mut client, &record(22, &[2, 0, 1, 0])).unwrap();
    for _ in 1..64 {
        feed(&mut client, &record(22, &[0])).unwrap();
    }
    assert_eq!(
        feed(&mut client, &record(22, &[0]))
            .unwrap_err()
            .to_string(),
        "RealityFirstFlightRecordLimit"
    );
    let mut client = self::client();
    let mut hello = server_hello(&drain(&mut client));
    hello.push(0);
    assert!(feed(&mut client, &record(22, &hello)).is_err());
}

#[test]
fn first_flight_does_not_treat_ccs_or_ciphertext_as_authenticated_data() {
    for bytes in [
        record(20, &[2]),
        record(23, &[1]),
        record(21, &[2, 40]),
        [record(20, &[1]), record(20, &[1])].concat(),
    ] {
        let mut client = client();
        drain(&mut client);
        assert!(feed(&mut client, &bytes).is_err());
        assert_eq!(
            client.read_plaintext(&mut [0; 16]).unwrap_err().to_string(),
            "RealityConnectionFailed"
        );
    }
}

struct ShortWriter {
    bytes: Vec<u8>,
    block: bool,
}
impl Write for ShortWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.block {
            self.block = false;
            return Err(io::ErrorKind::WouldBlock.into());
        }
        let n = bytes.len().min(3);
        self.bytes.extend_from_slice(&bytes[..n]);
        self.block = true;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn initial_flight_partial_and_blocked_writes_preserve_all_bytes() {
    let mut client = client();
    let expected = client.first_flight.get_ref().clone();
    let mut writer = ShortWriter {
        bytes: Vec::new(),
        block: true,
    };
    for _ in 0..expected.len() * 2 {
        if !client.wants_write() {
            break;
        }
        if let Err(error) = client.write_tls(&mut writer) {
            assert_eq!(error.kind(), io::ErrorKind::WouldBlock);
        }
    }
    assert!(!client.wants_write());
    assert_eq!(writer.bytes, expected);
    assert!(client.wants_read());
}

struct BlockedReader;
impl Read for BlockedReader {
    fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
        Err(io::ErrorKind::WouldBlock.into())
    }
}

#[test]
fn a_blocked_partial_record_is_resumable_without_reauthentication() {
    let mut client = client();
    let hello = server_hello(&drain(&mut client));
    let input = record(22, &hello);
    feed(&mut client, &input[..7]).unwrap();
    let filled = client.filled;
    assert_eq!(
        client.read_tls(&mut BlockedReader).unwrap_err().kind(),
        io::ErrorKind::WouldBlock
    );
    assert_eq!(client.filled, filled);
    assert!(!client.failed);
    feed(&mut client, &input[7..]).unwrap();
    assert!(client.first_server_hello.is_none());
}

struct FailedIo(io::ErrorKind);

impl Read for FailedIo {
    fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
        Err(io::Error::new(self.0, "original transport failure"))
    }
}

impl Write for FailedIo {
    fn write(&mut self, _: &[u8]) -> io::Result<usize> {
        Err(io::Error::new(self.0, "original transport failure"))
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn fatal_read_and_write_errors_preserve_the_first_error_and_end_the_attempt() {
    for writing in [false, true] {
        let mut client = client();
        let mut transport = FailedIo(io::ErrorKind::ConnectionReset);
        let error = if writing {
            client.write_tls(&mut transport).unwrap_err()
        } else {
            let hello = server_hello(&drain(&mut client));
            feed(&mut client, &record(22, &hello)[..7]).unwrap();
            client.read_tls(&mut transport).unwrap_err()
        };
        assert_eq!(error.kind(), io::ErrorKind::ConnectionReset);
        assert_eq!(error.to_string(), "original transport failure");
        assert!(client.failed);
        assert!(!client.wants_write());
        assert!(!client.wants_read());
        assert_eq!(
            client.write_tls(&mut Vec::new()).unwrap_err().to_string(),
            "RealityConnectionFailed"
        );
    }
}

#[test]
fn interrupted_read_and_write_remain_resumable() {
    let mut client = client();
    let expected = client.first_flight.get_ref().clone();
    let mut transport = FailedIo(io::ErrorKind::Interrupted);
    assert_eq!(
        client.write_tls(&mut transport).unwrap_err().kind(),
        io::ErrorKind::Interrupted
    );
    assert_eq!(client.first_flight.position(), 0);
    assert!(!client.failed);
    assert_eq!(drain(&mut client), expected);
    let input = record(22, &server_hello(&expected));
    feed(&mut client, &input[..7]).unwrap();
    assert_eq!(
        client.read_tls(&mut transport).unwrap_err().kind(),
        io::ErrorKind::Interrupted
    );
    assert_eq!(client.filled, 7);
    assert!(!client.failed);
    feed(&mut client, &input[7..]).unwrap();
    assert!(client.first_server_hello.is_none());
}

#[test]
fn zero_write_with_pending_flight_fails_instead_of_spinning() {
    let mut client = client();
    let mut no_capacity = &mut [][..];
    let error = client.write_tls(&mut no_capacity).unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::WriteZero);
    assert_eq!(error.to_string(), "RealityTlsWriteNoProgress");
    assert_eq!(client.first_flight.position(), 0);
    assert!(client.failed);
    assert!(!client.wants_write());
}

#[test]
fn debug_output_contains_no_keys_session_or_server_identity() {
    let client = client();
    let output = format!("{client:?}");
    assert!(output.contains("TlsClient"));
    assert!(!output.contains("reality.test"));
    assert!(!output.contains("authentication_key"));
    assert!(!output.contains("first_flight"));
}

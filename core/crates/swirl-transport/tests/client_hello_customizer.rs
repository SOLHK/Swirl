//! Contract tests exercise the real rustls constructor and wire output. No
//! socket, certificate bypass or independent shadow encoder is involved.
use std::{
    io::Cursor,
    sync::{Arc, Mutex},
};
use tokio_rustls::rustls::{
    self, ClientConfig, ClientConnection, Error, RootCertStore,
    client::{ClientHelloCustomizer, Resumption},
};

#[derive(Debug)]
struct Edit {
    edit: fn(&mut Vec<u8>),
    emitted: Arc<Mutex<Vec<u8>>>,
}
impl ClientHelloCustomizer for Edit {
    fn customize(&self, hello: &[u8]) -> Result<Vec<u8>, Error> {
        let mut result = hello.to_vec();
        (self.edit)(&mut result);
        *self.emitted.lock().unwrap() = result.clone();
        Ok(result)
    }
}
fn config() -> ClientConfig {
    let mut config =
        ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
            .with_protocol_versions(&[&rustls::version::TLS13])
            .unwrap()
            .with_root_certificates(RootCertStore::empty())
            .with_no_client_auth();
    config.resumption = Resumption::disabled();
    config.alpn_protocols = vec![b"h2".to_vec(), b"http/1.1".to_vec()];
    config.cert_decompressors = vec![rustls::compress::BROTLI_DECOMPRESSOR];
    config
}
fn with_edit(edit: fn(&mut Vec<u8>)) -> (ClientConfig, Arc<Mutex<Vec<u8>>>) {
    let mut config = config();
    let emitted = Arc::new(Mutex::new(Vec::new()));
    config.client_hello_customizer = Some(Arc::new(Edit {
        edit,
        emitted: emitted.clone(),
    }));
    (config, emitted)
}
fn connect(config: ClientConfig) -> Result<ClientConnection, Error> {
    ClientConnection::new(Arc::new(config), "reality.test".try_into().unwrap())
}
fn first_flight(connection: &mut ClientConnection) -> Vec<u8> {
    let mut records = Vec::new();
    connection.write_tls(&mut records).unwrap();
    assert_eq!(records[0], 22);
    let length = u16::from_be_bytes([records[3], records[4]]) as usize;
    assert_eq!(records.len(), length + 5);
    records[5..].to_vec()
}
fn extension_vector(hello: &[u8]) -> usize {
    let mut at = 39 + usize::from(hello[38]);
    at += 2 + usize::from(u16::from_be_bytes([hello[at], hello[at + 1]]));
    at += 1 + usize::from(hello[at]);
    at
}
fn extension(hello: &[u8], wanted: u16) -> (usize, usize) {
    let mut at = extension_vector(hello) + 2;
    while at < hello.len() {
        let kind = u16::from_be_bytes([hello[at], hello[at + 1]]);
        let length = u16::from_be_bytes([hello[at + 2], hello[at + 3]]) as usize;
        if kind == wanted {
            return (at + 4, length);
        }
        at += 4 + length;
    }
    panic!("test extension absent: {wanted}");
}
fn append(hello: &mut Vec<u8>, kind: u16, body: &[u8]) {
    let at = extension_vector(hello);
    hello.extend_from_slice(&kind.to_be_bytes());
    hello.extend_from_slice(&(body.len() as u16).to_be_bytes());
    hello.extend_from_slice(body);
    let extension_len = (hello.len() - at - 2) as u16;
    hello[at..at + 2].copy_from_slice(&extension_len.to_be_bytes());
    let message_len = (hello.len() - 4) as u32;
    hello[1..4].copy_from_slice(&message_len.to_be_bytes()[1..]);
}
fn invalid(edit: fn(&mut Vec<u8>)) {
    let (config, _) = with_edit(edit);
    let error = connect(config).unwrap_err();
    assert!(
        matches!(error, Error::General(ref e) if e == "CustomClientHelloInvalid"),
        "{error:?}"
    );
}

#[test]
fn unconfigured_client_keeps_upstream_constructor() {
    let config = config();
    assert!(config.client_hello_customizer.is_none());
    assert!(connect(config).is_ok());
}
#[test]
fn unchanged_callback_sends_the_exact_transcript_input() {
    let (config, emitted) = with_edit(|_| {});
    let mut client = connect(config).unwrap();
    assert_eq!(first_flight(&mut client), *emitted.lock().unwrap());
}
#[test]
fn unknown_grease_is_preserved_in_the_actual_wire_encoding() {
    let (config, emitted) = with_edit(|hello| append(hello, 0x3a3a, &[]));
    let mut client = connect(config).unwrap();
    let wire = first_flight(&mut client);
    assert_eq!(wire, *emitted.lock().unwrap());
    assert_eq!(extension(&wire, 0x3a3a).1, 0);
}
#[test]
fn callback_cannot_replace_fresh_random_session_id_or_key_material() {
    invalid(|hello| hello[6] ^= 1);
    invalid(|hello| hello[39] ^= 1);
    invalid(|hello| {
        let (at, length) = extension(hello, 51);
        hello[at + length - 1] ^= 1;
    });
}
#[test]
fn callback_cannot_change_configured_identity_application_or_decompression() {
    invalid(|hello| {
        let (at, length) = extension(hello, 0);
        hello[at + length - 1] ^= 1;
    });
    invalid(|hello| {
        let (at, length) = extension(hello, 16);
        hello[at + length - 1] ^= 1;
    });
    invalid(|hello| {
        let (at, length) = extension(hello, 27);
        hello[at + length - 1] ^= 1;
    });
}
#[test]
fn callback_rejects_malformed_oversize_duplicate_and_protocol_state_extensions() {
    invalid(|hello| {
        hello.pop();
    });
    invalid(|hello| hello.resize(16 * 1024 + 1, 0));
    invalid(|hello| append(hello, 0, &[]));
    invalid(|hello| append(hello, 0x1234, &[]));
    invalid(|hello| append(hello, 41, &[]));
    invalid(|hello| append(hello, 42, &[]));
    invalid(|hello| append(hello, 44, &[]));
    invalid(|hello| append(hello, 0xfe0d, &[1]));
    invalid(|hello| append(hello, 35, &[1]));
}
#[test]
fn callback_rejects_tls12_engine_and_early_data_before_running() {
    let (mut early, emitted) = with_edit(|_| {});
    early.enable_early_data = true;
    assert!(
        matches!(connect(early), Err(Error::General(e)) if e == "CustomClientHelloContextUnsupported")
    );
    assert!(emitted.lock().unwrap().is_empty());
    let mut mixed =
        ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
            .with_safe_default_protocol_versions()
            .unwrap()
            .with_root_certificates(RootCertStore::empty())
            .with_no_client_auth();
    mixed.client_hello_customizer = Some(Arc::new(Edit {
        edit: |_| {},
        emitted: emitted.clone(),
    }));
    assert!(
        matches!(connect(mixed), Err(Error::General(e)) if e == "CustomClientHelloContextUnsupported")
    );
    assert!(emitted.lock().unwrap().is_empty());
}
#[test]
fn hello_retry_request_never_runs_a_second_customization() {
    let (config, emitted) = with_edit(|_| {});
    let mut client = connect(config).unwrap();
    let hello = first_flight(&mut client);
    let original = emitted.lock().unwrap().clone();
    let mut body = vec![3, 3];
    body.extend_from_slice(&[
        0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65, 0xb8,
        0x91, 0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2, 0xc8, 0xa8,
        0x33, 0x9c,
    ]);
    body.push(32);
    body.extend_from_slice(&hello[39..71]);
    body.extend_from_slice(&[0x13, 0x01, 0, 0, 12, 0, 43, 0, 2, 3, 4, 0, 51, 0, 2, 0, 23]);
    let mut hrr = vec![2];
    hrr.extend_from_slice(&(body.len() as u32).to_be_bytes()[1..]);
    hrr.extend_from_slice(&body);
    let mut record = vec![22, 3, 3];
    record.extend_from_slice(&(hrr.len() as u16).to_be_bytes());
    record.extend_from_slice(&hrr);
    client.read_tls(&mut Cursor::new(record)).unwrap();
    let error = client.process_new_packets().unwrap_err();
    assert!(
        matches!(error, Error::General(ref e) if e == "CustomClientHelloContextUnsupported"),
        "{error:?}"
    );
    assert_eq!(*emitted.lock().unwrap(), original);
}
#[test]
fn advertised_brotli_is_real_and_enforces_exact_output_length() {
    let input = b"certificate compression compatibility".repeat(100);
    let compressed = rustls::compress::BROTLI_COMPRESSOR
        .compress(
            input.clone(),
            rustls::compress::CompressionLevel::Interactive,
        )
        .unwrap();
    let mut output = vec![0; input.len()];
    rustls::compress::BROTLI_DECOMPRESSOR
        .decompress(&compressed, &mut output)
        .unwrap();
    assert_eq!(output, input);
    for wrong_len in [input.len() - 1, input.len() + 1] {
        assert!(
            rustls::compress::BROTLI_DECOMPRESSOR
                .decompress(&compressed, &mut vec![0; wrong_len])
                .is_err()
        );
    }
    let mut trailing = compressed;
    trailing.push(0);
    assert!(
        rustls::compress::BROTLI_DECOMPRESSOR
            .decompress(&trailing, &mut output)
            .is_err()
    );
}

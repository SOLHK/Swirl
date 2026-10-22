use super::{UrlTestStage, health_probe, url_test_head};
use base64::Engine;
use std::{net::IpAddr, sync::Arc};
use swirl_dns::Resolver;
use swirl_subscription::{HealthProbe, HostMapping, Outbound, Tls};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    sync::oneshot,
    time::{Duration, timeout},
};
use tokio_rustls::{
    TlsAcceptor,
    rustls::{
        ServerConfig,
        pki_types::{CertificateDer, PrivatePkcs8KeyDer},
    },
};

fn options(port: u16) -> HealthProbe {
    HealthProbe {
        url: format!("http://127.0.0.1:{port}/check?case=header"),
        interval_ms: 10_000,
        timeout_ms: 5_000,
        expected_status: 204,
        tolerance_ms: 0,
        tls: None,
    }
}

fn tls_fixture() -> (Vec<u8>, TlsAcceptor) {
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../../swirl-transport/tests/fixtures/reality_auth.json"
    ))
    .unwrap();
    let certificate = &fixture["certificate"];
    let hex = |key: &str| {
        certificate[key]
            .as_str()
            .unwrap()
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect::<Vec<_>>()
    };
    let der = hex("ordinary_self_signed_der_hex");
    let key = hex("ed25519_pkcs8_der_hex");
    let config = ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(
            vec![CertificateDer::from(der.clone())],
            PrivatePkcs8KeyDer::from(key).into(),
        )
        .unwrap();
    (der, TlsAcceptor::from(Arc::new(config)))
}

fn https_options(port: u16, trust_anchor: Option<&[u8]>) -> HealthProbe {
    HealthProbe {
        url: format!("https://reality.test:{port}/check?case=tls"),
        tls: Some(Tls {
            server_name: "reality.test".into(),
            alpn: vec!["http/1.1".into()],
            ca_der_base64: trust_anchor
                .map(|der| base64::engine::general_purpose::STANDARD.encode(der)),
        }),
        ..options(port)
    }
}

fn https_resolver() -> Resolver {
    Resolver::default().with_hosts(&[HostMapping {
        name: "reality.test".into(),
        address: IpAddr::V4(std::net::Ipv4Addr::LOCALHOST),
    }])
}

async fn request_headers<R: AsyncRead + Unpin>(socket: &mut R) -> Vec<u8> {
    let mut request = Vec::new();
    loop {
        let mut block = [0; 128];
        let count = socket.read(&mut block).await.unwrap();
        assert!(count > 0, "probe closed before sending request headers");
        request.extend_from_slice(&block[..count]);
        assert!(
            request.len() <= 2048,
            "probe request exceeded fixture limit"
        );
        if request.windows(4).any(|part| part == b"\r\n\r\n") {
            return request;
        }
    }
}

#[tokio::test]
async fn url_test_head_returns_before_peer_body_or_close() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let probe = options(listener.local_addr().unwrap().port());
    // The policy default is 204, but the manual URL test accepts any 2xx.
    let (release, held) = oneshot::channel::<()>();
    let peer = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let request = request_headers(&mut socket).await;
        assert!(request.starts_with(b"HEAD /check?case=header HTTP/1.1\r\n"));
        socket
            .write_all(b"HTTP/1.1 103 Early Hints\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n")
            .await
            .unwrap();
        // The socket remains open with the advertised body delayed until the
        // probe returns. A post-release write may race with the dropped stream.
        let _ = held.await;
        let _ = socket.write_all(b"late body byte").await;
    });
    let result = timeout(
        Duration::from_secs(3),
        url_test_head(&Outbound::Direct {}, &probe, &Resolver::default(), None),
    )
    .await
    .expect("HEAD probe waited for body or peer close")
    .unwrap();
    assert_eq!(result.http_status, 200);
    assert!(result.origin_tls_ms.is_none());
    assert!(result.outbound_connect_ms <= result.response_headers_ms);
    release.send(()).unwrap();
    peer.await.unwrap();
}

#[tokio::test]
async fn url_test_head_reports_http_status_failure_without_latency() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let probe = options(listener.local_addr().unwrap().port());
    let peer = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let request = request_headers(&mut socket).await;
        assert!(request.starts_with(b"HEAD /check?case=header HTTP/1.1\r\n"));
        socket
            .write_all(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
            .await
            .unwrap();
    });
    let failure = url_test_head(&Outbound::Direct {}, &probe, &Resolver::default(), None)
        .await
        .unwrap_err();
    assert_eq!(failure.stage, UrlTestStage::HttpStatus);
    assert_eq!(failure.http_status, Some(503));
    assert_eq!(failure.code, "UrlTestStatus");
    peer.await.unwrap();
}

#[tokio::test]
async fn url_test_head_reports_truncated_headers_as_response_failure() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let probe = options(listener.local_addr().unwrap().port());
    let peer = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let request = request_headers(&mut socket).await;
        assert!(request.starts_with(b"HEAD /check?case=header HTTP/1.1\r\n"));
        socket
            .write_all(b"HTTP/1.1 204 No Content\r\n")
            .await
            .unwrap();
    });
    let failure = url_test_head(&Outbound::Direct {}, &probe, &Resolver::default(), None)
        .await
        .unwrap_err();
    assert_eq!(failure.stage, UrlTestStage::ResponseHeaders);
    assert_eq!(failure.http_status, None);
    assert_eq!(failure.code, "UrlTestRead");
    peer.await.unwrap();
}

#[tokio::test]
async fn url_test_head_optional_expected_status_is_exact() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let probe = options(listener.local_addr().unwrap().port());
    let peer = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let request = request_headers(&mut socket).await;
        assert!(request.starts_with(b"HEAD /check?case=header HTTP/1.1\r\n"));
        socket
            .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            .await
            .unwrap();
    });
    let failure = url_test_head(
        &Outbound::Direct {},
        &probe,
        &Resolver::default(),
        Some(204),
    )
    .await
    .unwrap_err();
    assert_eq!(failure.stage, UrlTestStage::HttpStatus);
    assert_eq!(failure.http_status, Some(200));
    assert_eq!(failure.code, "UrlTestStatus");
    peer.await.unwrap();
}

#[tokio::test]
async fn url_test_head_authenticates_https_and_reports_origin_tls_phase() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let (certificate, acceptor) = tls_fixture();
    let probe = https_options(listener.local_addr().unwrap().port(), Some(&certificate));
    let resolver = https_resolver();
    let (release, held) = oneshot::channel::<()>();
    let peer = tokio::spawn(async move {
        let (socket, _) = listener.accept().await.unwrap();
        let mut tls = acceptor.accept(socket).await.unwrap();
        let request = request_headers(&mut tls).await;
        assert!(request.starts_with(b"HEAD /check?case=tls HTTP/1.1\r\n"));
        assert!(
            request
                .windows(b"Host: reality.test:".len())
                .any(|part| part == b"Host: reality.test:")
        );
        tls.write_all(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")
            .await
            .unwrap();
        // The peer remains open: neither body nor TLS shutdown is in the metric.
        let _ = held.await;
    });
    let metrics = timeout(
        Duration::from_secs(3),
        url_test_head(&Outbound::Direct {}, &probe, &resolver, None),
    )
    .await
    .expect("HTTPS HEAD probe waited for peer close")
    .unwrap();
    assert_eq!(metrics.http_status, 204);
    assert!(metrics.origin_tls_ms.is_some());
    assert!(metrics.outbound_connect_ms <= metrics.response_headers_ms);
    release.send(()).unwrap();
    peer.await.unwrap();
}

#[tokio::test]
async fn url_test_head_rejects_untrusted_https_certificate_at_origin_tls() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let (_, acceptor) = tls_fixture();
    let probe = https_options(listener.local_addr().unwrap().port(), None);
    let resolver = https_resolver();
    let peer = tokio::spawn(async move {
        let (socket, _) = listener.accept().await.unwrap();
        let _ = acceptor.accept(socket).await;
    });
    let failure = timeout(
        Duration::from_secs(3),
        url_test_head(&Outbound::Direct {}, &probe, &resolver, None),
    )
    .await
    .expect("untrusted HTTPS certificate hung the probe")
    .unwrap_err();
    assert_eq!(failure.stage, UrlTestStage::OriginTls);
    assert_eq!(failure.code, "TlsVerificationOrHandshake");
    assert_eq!(failure.http_status, None);
    peer.await.unwrap();
}

#[tokio::test]
async fn health_probe_preserves_get_request_and_header_timing() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let probe = options(listener.local_addr().unwrap().port());
    let (release, held) = oneshot::channel::<()>();
    let peer = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let request = request_headers(&mut socket).await;
        assert!(request.starts_with(b"GET /check?case=header HTTP/1.1\r\n"));
        socket
            .write_all(b"HTTP/1.1 204 No Content\r\nContent-Length: 1000000\r\n\r\n")
            .await
            .unwrap();
        let _ = held.await;
    });
    timeout(
        Duration::from_secs(3),
        health_probe(&Outbound::Direct {}, &probe, &Resolver::default()),
    )
    .await
    .expect("existing GET probe waited for body or peer close")
    .unwrap();
    release.send(()).unwrap();
    peer.await.unwrap();
}

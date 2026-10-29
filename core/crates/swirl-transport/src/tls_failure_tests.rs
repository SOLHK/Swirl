use super::*;
use std::{
    pin::Pin,
    task::{Context, Poll},
};
use tokio::io::ReadBuf;
use tokio_rustls::rustls::{
    CertificateError, Error,
    pki_types::{ServerName, UnixTime},
};

#[test]
fn certificate_context_is_classified_without_exporting_private_names_or_messages() {
    let instant = UnixTime::since_unix_epoch(std::time::Duration::from_secs(1));
    for (certificate, expected) in [
        (CertificateError::Expired, "TlsCertificateExpired"),
        (
            CertificateError::ExpiredContext {
                time: instant,
                not_after: instant,
            },
            "TlsCertificateExpired",
        ),
        (CertificateError::NotValidYet, "TlsCertificateNotValidYet"),
        (
            CertificateError::NotValidYetContext {
                time: instant,
                not_before: instant,
            },
            "TlsCertificateNotValidYet",
        ),
        (
            CertificateError::NotValidForName,
            "TlsCertificateNameMismatch",
        ),
        (
            CertificateError::NotValidForNameContext {
                expected: ServerName::try_from("private-expected.invalid").unwrap(),
                presented: vec!["private-presented.invalid".into()],
            },
            "TlsCertificateNameMismatch",
        ),
        (
            CertificateError::UnknownIssuer,
            "TlsCertificateUnknownIssuer",
        ),
        (CertificateError::Revoked, "TlsCertificateRevoked"),
        (CertificateError::BadSignature, "TlsCertificateInvalid"),
    ] {
        let error = io::Error::new(
            io::ErrorKind::InvalidData,
            Error::InvalidCertificate(certificate),
        );
        assert_eq!(tls_failure_code(&error), expected);
    }
    let missing = io::Error::new(io::ErrorKind::InvalidData, Error::NoCertificatesPresented);
    assert_eq!(tls_failure_code(&missing), "TlsCertificateMissing");
    let unknown = io::Error::new(
        io::ErrorKind::InvalidData,
        Error::General("private-message UnknownIssuer Expired".into()),
    );
    assert_eq!(tls_failure_code(&unknown), "TlsVerificationOrHandshake");
    let untyped = io::Error::new(
        io::ErrorKind::InvalidData,
        "Expired NotValidForName private-name.invalid",
    );
    assert_eq!(tls_failure_code(&untyped), "TlsVerificationOrHandshake");
}

struct FailingRead(io::ErrorKind);
impl AsyncRead for FailingRead {
    fn poll_read(
        self: Pin<&mut Self>,
        _: &mut Context<'_>,
        _: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Poll::Ready(Err(io::Error::new(
            self.0,
            "private-server.invalid:443 private-password",
        )))
    }
}
impl AsyncWrite for FailingRead {
    fn poll_write(
        self: Pin<&mut Self>,
        _: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        Poll::Ready(Ok(bytes.len()))
    }
    fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
    fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
}

#[tokio::test]
async fn secure_preserves_typed_transport_failures_instead_of_claiming_bad_certificates() {
    let tls = swirl_subscription::Tls {
        server_name: "fixture.invalid".into(),
        alpn: vec![],
        ca_der_base64: None,
    };
    for (kind, expected) in [
        (io::ErrorKind::UnexpectedEof, "TlsHandshakeEof"),
        (io::ErrorKind::ConnectionReset, "TlsConnectionReset"),
        (io::ErrorKind::ConnectionAborted, "TlsConnectionAborted"),
        (io::ErrorKind::ConnectionRefused, "TlsConnectionRefused"),
        (io::ErrorKind::TimedOut, "TlsHandshakeIoTimeout"),
        (io::ErrorKind::BrokenPipe, "TlsHandshakeBrokenPipe"),
        (io::ErrorKind::Other, "TlsVerificationOrHandshake"),
    ] {
        assert!(matches!(secure(FailingRead(kind), &tls).await, Err(code) if code == expected));
    }
}

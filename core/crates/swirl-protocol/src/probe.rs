//! Explicit health requests run through the selected native outbound. The
//! measured interval ends at validated final response headers, not at a TCP
//! connect or an unrelated direct request. No application traffic is replayed.
use crate::{Result, Target, Transport};
use std::time::Instant;
use swirl_dns::Resolver;
use swirl_subscription::{HealthProbe, Outbound};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    time::{Duration, timeout, timeout_at},
};

const HEADER_LIMIT: usize = 8192;
const INFORMATIONAL_LIMIT: usize = 8;

/// The operation that failed. `OutboundConnect` includes the node's DNS,
/// transport, and protocol setup; it is not a pure TCP round trip.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UrlTestStage {
    Input,
    Dns,
    TcpConnect,
    OutboundHandshake,
    OutboundConnect,
    OriginTls,
    RequestWrite,
    ResponseHeaders,
    HttpStatus,
}

/// Fixed, redacted failure code with the stage and optional HTTP status.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct UrlTestFailure {
    pub stage: UrlTestStage,
    pub code: &'static str,
    pub http_status: Option<u16>,
}

impl UrlTestFailure {
    fn at(stage: UrlTestStage, code: &'static str) -> Self {
        Self {
            stage,
            code,
            http_status: None,
        }
    }

    fn outbound(code: &'static str) -> Self {
        let stage = match crate::failure_stage(code) {
            "dns" => UrlTestStage::Dns,
            "tcp_connect" => UrlTestStage::TcpConnect,
            "tls_handshake" | "reality_handshake" | "websocket_upgrade" | "protocol_handshake" => {
                UrlTestStage::OutboundHandshake
            }
            _ => UrlTestStage::OutboundConnect,
        };
        Self::at(stage, code)
    }

    fn input(code: &'static str) -> Self {
        let code = match code {
            "PolicyProbeParameters" => "UrlTestParameters",
            "PolicyProbeUrl" => "UrlTestUrl",
            "PolicyProbeHost" => "UrlTestHost",
            "PolicyProbePort" => "UrlTestPort",
            "PolicyProbeTls" => "UrlTestTls",
            _ => "UrlTestInput",
        };
        Self::at(UrlTestStage::Input, code)
    }

    fn response(code: &'static str) -> Self {
        let code = match code {
            "PolicyProbeHeaderLimit" => "UrlTestHeaderLimit",
            "PolicyProbeInformationalLimit" => "UrlTestInformationalLimit",
            "PolicyProbeHttp" => "UrlTestInvalidHttp",
            "PolicyProbeRead" => "UrlTestRead",
            _ => "UrlTestResponse",
        };
        Self::at(UrlTestStage::ResponseHeaders, code)
    }
}

/// One fresh HEAD request through an explicit native outbound.
/// `outbound_connect_ms` and `response_headers_ms` are cumulative from start;
/// the former includes DNS and node handshake, and the latter ends at validated
/// final headers before body or EOF. `origin_tls_ms` is that phase's duration.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct UrlTestMetrics {
    pub outbound_connect_ms: u64,
    pub origin_tls_ms: Option<u64>,
    pub response_headers_ms: u64,
    pub http_status: u16,
}

fn elapsed_ms(started: Instant) -> u64 {
    started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64
}

/// Measure a fresh native outbound with HEAD, with no redirect, retry, body
/// download, external-core fallback, or implicit change to the selected node.
/// The configured timeout is one shared deadline across every network phase.
/// `expected_status = None` accepts any final 2xx response; `Some(status)`
/// requires that exact 2xx status. Automatic policy health uses `health_probe`.
///
/// # Errors
/// Returns a fixed-code failure tagged with the phase that failed. A response
/// whose status differs from `expected_status` returns the actual status.
pub async fn url_test_head(
    outbound: &Outbound,
    options: &HealthProbe,
    resolver: &Resolver,
    expected_status: Option<u16>,
) -> std::result::Result<UrlTestMetrics, UrlTestFailure> {
    url_test_head_selected(outbound, options, resolver, expected_status, None).await
}

/// Run the same bounded HEAD probe through an explicit native transport. The
/// node and its transport remain fixed for the entire probe, with no fallback.
pub async fn url_test_head_with_transport(
    outbound: &Outbound,
    options: &HealthProbe,
    resolver: &Resolver,
    expected_status: Option<u16>,
    transport: &Transport,
) -> std::result::Result<UrlTestMetrics, UrlTestFailure> {
    url_test_head_selected(
        outbound,
        options,
        resolver,
        expected_status,
        Some(transport),
    )
    .await
}

async fn url_test_head_selected(
    outbound: &Outbound,
    options: &HealthProbe,
    resolver: &Resolver,
    expected_status: Option<u16>,
    transport: Option<&Transport>,
) -> std::result::Result<UrlTestMetrics, UrlTestFailure> {
    if expected_status.is_some_and(|status| !(200..=299).contains(&status)) {
        return Err(UrlTestFailure::at(
            UrlTestStage::Input,
            "UrlTestExpectedStatus",
        ));
    }
    let target = options.target().map_err(UrlTestFailure::input)?;
    let started = Instant::now();
    let deadline = tokio::time::Instant::now() + Duration::from_millis(options.timeout_ms);
    let mut stream = timeout_at(
        deadline,
        crate::connect_selected(
            outbound,
            &Target {
                host: target.host.clone(),
                port: target.port,
            },
            resolver,
            Duration::from_millis(options.timeout_ms),
            transport,
            false,
        ),
    )
    .await
    .map_err(|_| UrlTestFailure::at(UrlTestStage::OutboundConnect, "UrlTestTimeout"))?
    .map_err(UrlTestFailure::outbound)?;
    let outbound_connect_ms = elapsed_ms(started);

    let origin_tls_ms = if let Some(tls) = target.tls {
        let tls_started = Instant::now();
        stream = timeout_at(deadline, swirl_transport::secure(stream, &tls))
            .await
            .map_err(|_| UrlTestFailure::at(UrlTestStage::OriginTls, "UrlTestTimeout"))?
            .map_err(|code| UrlTestFailure::at(UrlTestStage::OriginTls, code))?;
        Some(elapsed_ms(tls_started))
    } else {
        None
    };
    let request = format!(
        "HEAD {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\nUser-Agent: Swirl-Core-URLTest/1\r\nAccept: */*\r\n\r\n",
        target.path, target.authority
    );
    timeout_at(deadline, async {
        stream.write_all(request.as_bytes()).await?;
        stream.flush().await
    })
    .await
    .map_err(|_| UrlTestFailure::at(UrlTestStage::RequestWrite, "UrlTestTimeout"))?
    .map_err(|_| UrlTestFailure::at(UrlTestStage::RequestWrite, "UrlTestWrite"))?;

    let status = timeout_at(deadline, response_code(&mut stream))
        .await
        .map_err(|_| UrlTestFailure::at(UrlTestStage::ResponseHeaders, "UrlTestTimeout"))?
        .map_err(UrlTestFailure::response)?;
    let response_headers_ms = elapsed_ms(started);
    if !expected_status.map_or((200..=299).contains(&status), |expected| status == expected) {
        return Err(UrlTestFailure {
            stage: UrlTestStage::HttpStatus,
            code: "UrlTestStatus",
            http_status: Some(status),
        });
    }
    // A HEAD response has no body. Drop our owned stream rather than waiting
    // for the peer to close or for a TLS write shutdown after the metric ends.
    drop(stream);
    Ok(UrlTestMetrics {
        outbound_connect_ms,
        origin_tls_ms,
        response_headers_ms,
        http_status: status,
    })
}

pub async fn health_probe(
    outbound: &Outbound,
    options: &HealthProbe,
    resolver: &Resolver,
) -> Result<u64> {
    health_probe_selected(outbound, options, resolver, None).await
}

/// Run an automatic-policy health request through the node's explicit native
/// transport, preserving the existing shared timeout and shutdown semantics.
pub async fn health_probe_with_transport(
    outbound: &Outbound,
    options: &HealthProbe,
    resolver: &Resolver,
    transport: &Transport,
) -> Result<u64> {
    health_probe_selected(outbound, options, resolver, Some(transport)).await
}

async fn health_probe_selected(
    outbound: &Outbound,
    options: &HealthProbe,
    resolver: &Resolver,
    transport: Option<&Transport>,
) -> Result<u64> {
    let target = options.target()?;
    let started = Instant::now();
    // Resolution, proxy negotiation, origin TLS, request, response and write
    // shutdown share a single deadline. Redirects and retries are forbidden.
    timeout(Duration::from_millis(options.timeout_ms), async {
        let mut stream = crate::connect_selected(
            outbound,
            &Target {
                host: target.host.clone(),
                port: target.port,
            },
            resolver,
            Duration::from_millis(options.timeout_ms),
            transport,
            false,
        )
        .await?;
        if let Some(tls) = target.tls {
            stream = swirl_transport::secure(stream, &tls).await?;
        }
        let request = format!(
            "GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\nUser-Agent: Swirl-Core-Health/1\r\nAccept: */*\r\n\r\n",
            target.path, target.authority
        );
        stream
            .write_all(request.as_bytes())
            .await
            .map_err(|_| "PolicyProbeWrite")?;
        stream.flush().await.map_err(|_| "PolicyProbeWrite")?;
        response_status(&mut stream, options.expected_status).await?;
        let latency = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
        // No unbounded body download or peer-close wait. TLS close_notify and
        // native outbound write shutdown still use the same overall budget.
        stream
            .shutdown()
            .await
            .map_err(|_| "PolicyProbeShutdown")?;
        Ok(latency)
    })
    .await
    .map_err(|_| "PolicyProbeTimeout")?
}

async fn response_status<R: AsyncRead + Unpin>(stream: &mut R, expected: u16) -> Result<()> {
    if response_code(stream).await? == expected {
        Ok(())
    } else {
        Err("PolicyProbeStatus")
    }
}

async fn response_code<R: AsyncRead + Unpin>(stream: &mut R) -> Result<u16> {
    let mut response = Vec::with_capacity(1024);
    let mut total_headers = 0;
    let mut informational = 0;
    loop {
        if let Some(end) = response.windows(4).position(|w| w == b"\r\n\r\n") {
            let length = end + 4;
            total_headers += length;
            if total_headers > HEADER_LIMIT {
                return Err("PolicyProbeHeaderLimit");
            }
            let mut headers = [httparse::EMPTY_HEADER; 64];
            let mut parsed = httparse::Response::new(&mut headers);
            if !parsed
                .parse(&response[..length])
                .map_err(|_| "PolicyProbeHttp")?
                .is_complete()
                || !matches!(parsed.version, Some(0 | 1))
            {
                return Err("PolicyProbeHttp");
            }
            let status = parsed.code.ok_or("PolicyProbeHttp")?;
            if (100..200).contains(&status) && status != 101 {
                // RFC 9110 permits interim responses. They do not establish
                // health, and cannot reset the byte, count or time budgets.
                informational += 1;
                if informational > INFORMATIONAL_LIMIT {
                    return Err("PolicyProbeInformationalLimit");
                }
                response.drain(..length);
                continue;
            }
            return Ok(status);
        }
        let remaining = HEADER_LIMIT.saturating_sub(total_headers + response.len());
        if remaining == 0 {
            return Err("PolicyProbeHeaderLimit");
        }
        let mut block = [0; 1024];
        let capacity = remaining.min(block.len());
        let count = stream
            .read(&mut block[..capacity])
            .await
            .map_err(|_| "PolicyProbeRead")?;
        if count == 0 {
            return Err("PolicyProbeRead");
        }
        response.extend_from_slice(&block[..count]);
    }
}

#[cfg(test)]
#[path = "probe_tests.rs"]
mod probe_tests;

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn fragmented_interim_responses_require_a_complete_final_status() {
        let (mut read, mut write) = tokio::io::duplex(11);
        let writer = tokio::spawn(async move {
            for piece in b"HTTP/1.1 103 Early Hints\r\nLink: </fixture>\r\n\r\nHTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n".chunks(3) {
                write.write_all(piece).await.unwrap();
            }
        });
        assert_eq!(response_status(&mut read, 204).await, Ok(()));
        writer.await.unwrap();
    }

    #[tokio::test]
    async fn malformed_truncated_redirect_and_upgrade_responses_are_unhealthy() {
        for (bytes, error) in [
            (
                b"HTTP/1.1 302 Found\r\nLocation: http://unused/\r\n\r\n".as_slice(),
                "PolicyProbeStatus",
            ),
            (
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n".as_slice(),
                "PolicyProbeStatus",
            ),
            (b"HTTP/1.1 200 OK\r\n\r\n".as_slice(), "PolicyProbeStatus"),
            (
                b"HTTP/1.1 204 No Content\r\nbad header\r\n\r\n".as_slice(),
                "PolicyProbeHttp",
            ),
            (b"HTTP/1.1 204 No Content\r\n".as_slice(), "PolicyProbeRead"),
            (
                b"HTTP/1.1 103 Early Hints\r\n\r\n".as_slice(),
                "PolicyProbeRead",
            ),
        ] {
            assert_eq!(response_status(&mut &bytes[..], 204).await, Err(error));
        }
    }

    #[tokio::test]
    async fn interim_headers_share_one_total_byte_and_count_budget() {
        let interim = b"HTTP/1.1 103 Early Hints\r\n\r\n";
        let mut too_many = interim.repeat(INFORMATIONAL_LIMIT + 1);
        too_many.extend_from_slice(b"HTTP/1.1 204 No Content\r\n\r\n");
        assert_eq!(
            response_status(&mut too_many.as_slice(), 204).await,
            Err("PolicyProbeInformationalLimit")
        );
        let mut bytes = b"HTTP/1.1 103 Early Hints\r\nX-Fixture: ".to_vec();
        bytes.extend(vec![b'a'; 4100]);
        bytes.extend_from_slice(b"\r\n\r\n");
        let mut too_large = bytes.repeat(2);
        too_large.extend_from_slice(b"HTTP/1.1 204 No Content\r\n\r\n");
        assert_eq!(
            response_status(&mut too_large.as_slice(), 204).await,
            Err("PolicyProbeHeaderLimit")
        );
    }

    #[tokio::test]
    async fn header_completion_does_not_wait_for_a_response_body() {
        let (mut read, mut write) = tokio::io::duplex(128);
        write
            .write_all(b"HTTP/1.0 200 OK\r\nContent-Length: 1000000000\r\n\r\n")
            .await
            .unwrap();
        assert_eq!(
            timeout(Duration::from_millis(100), response_status(&mut read, 200))
                .await
                .unwrap(),
            Ok(())
        );
        // Keeping the writer alive proves that EOF/body completion was not
        // mistaken for receipt of the configured status.
        drop(write);
    }
}

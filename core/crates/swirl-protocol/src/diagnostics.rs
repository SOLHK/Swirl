//! Static failure categories. No server messages, addresses or credentials are
//! included. Ambiguous legacy codes remain unknown rather than guessing a cause.
use serde::Serialize;

/// A closed vocabulary: an OS error can never carry its message into a report.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TcpOutcome {
    Success,
    Refused,
    Timeout,
    Unreachable,
    Other,
    Cancelled,
}

impl TcpOutcome {
    pub(super) fn from_io(error: &std::io::Error) -> Self {
        use std::io::ErrorKind;
        match error.kind() {
            ErrorKind::ConnectionRefused => Self::Refused,
            ErrorKind::TimedOut => Self::Timeout,
            ErrorKind::NetworkUnreachable | ErrorKind::HostUnreachable | ErrorKind::NetworkDown => {
                Self::Unreachable
            }
            _ => Self::Other,
        }
    }
}

/// Ordinals are local to this diagnostic, never hashes of a private endpoint.
#[derive(Clone, Debug, Serialize)]
pub struct TcpAttempt {
    pub ordinal: usize,
    pub family: &'static str,
    /// Monotonic start offset from the beginning of the TCP stage.
    pub started_ms: u64,
    pub elapsed_ms: u64,
    pub outcome: TcpOutcome,
}

/// DNS/TCP evidence only. It cannot establish protocol authentication or HTTPS
/// forwarding. Private hostnames, addresses, ports and credentials have no
/// fields in this type, including in its Debug representation.
#[derive(Clone, Debug, Serialize)]
pub struct TcpDiagnostic {
    pub schema: u32,
    pub engine: &'static str,
    pub scope: &'static str,
    pub ok: bool,
    pub error_code: Option<&'static str>,
    pub failure_stage: Option<&'static str>,
    pub total_budget_ms: u64,
    pub dns_budget_ms: u64,
    pub dns_elapsed_ms: u64,
    pub tcp_elapsed_ms: u64,
    pub total_elapsed_ms: u64,
    /// Distinct addresses admitted by the existing native dialer (at most 16).
    pub address_count: usize,
    pub ipv4_count: usize,
    pub ipv6_count: usize,
    pub attempted_count: usize,
    /// Resolved addresses for which no connect future was started.
    pub remaining_count: usize,
    pub peak_pending: usize,
    pub attempts: Vec<TcpAttempt>,
}

impl TcpDiagnostic {
    pub(super) fn new(total_budget_ms: u64, dns_budget_ms: u64) -> Self {
        Self {
            schema: 1,
            engine: "swirl-rust",
            scope: "dns_tcp_only",
            ok: false,
            error_code: None,
            failure_stage: None,
            total_budget_ms,
            dns_budget_ms,
            dns_elapsed_ms: 0,
            tcp_elapsed_ms: 0,
            total_elapsed_ms: 0,
            address_count: 0,
            ipv4_count: 0,
            ipv6_count: 0,
            attempted_count: 0,
            remaining_count: 0,
            peak_pending: 0,
            attempts: Vec::new(),
        }
    }
}

pub fn failure_stage(code: &str) -> &'static str {
    match code {
        "" => "",
        "UpstreamDnsTimeout" => "dns",
        "UpstreamTcpTimeout" | "UpstreamConnectFailed" | "UpstreamAddressLimit" => "tcp_connect",
        "UpstreamTlsTimeout" => "tls_handshake",
        "ShadowsocksObfsWrite" | "ShadowsocksObfsWriteTimeout" => "http_obfs",
        "UpstreamProtocolTimeout"
        | "UpstreamAuthentication"
        | "UpstreamRejected"
        | "UpstreamHeaderTooLarge"
        | "ShadowsocksSetup"
        | "ShadowsocksHandshakeWrite"
        | "TrojanHandshakeWrite"
        | "VlessHandshakeWrite"
        | "Socks4Rejected" => "protocol_handshake",
        "StreamIo" => "stream_io",
        "HandshakeTimeout" | "InboundClosed" | "InboundAuthentication" | "InboundReply" => {
            "inbound"
        }
        code if code.starts_with("Dns") || code.starts_with("RouteDns") => "dns",
        code if code.starts_with("Tls") => "tls_handshake",
        code if code.starts_with("Reality") => "reality_handshake",
        code if code.starts_with("WebSocketUpgrade") => "websocket_upgrade",
        code if code.starts_with("SocksUpstream") || code.starts_with("HttpUpstream") => {
            "protocol_handshake"
        }
        code if code.starts_with("InitialWrite") => "initial_write",
        code if code.starts_with("Route") || code.starts_with("Policy") => "routing",
        _ => "unknown",
    }
}

//! Static failure categories. No server messages, addresses or credentials are
//! included. Ambiguous legacy codes remain unknown rather than guessing a cause.
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
        code if code.starts_with("WebSocketUpgrade") => "websocket_upgrade",
        code if code.starts_with("SocksUpstream") || code.starts_with("HttpUpstream") => {
            "protocol_handshake"
        }
        code if code.starts_with("InitialWrite") => "initial_write",
        code if code.starts_with("Route") || code.starts_with("Policy") => "routing",
        _ => "unknown",
    }
}

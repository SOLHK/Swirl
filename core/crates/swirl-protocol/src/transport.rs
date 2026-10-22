//! Explicit transport selection at the protocol boundary. Import/conversion is
//! deliberately separate: unsupported settings fail before DNS or socket I/O.
use crate::Result;
use serde::{Deserialize, Serialize};
use swirl_subscription::{Outbound, WebSocket};
use swirl_transport::BoxStream;

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Transport {
    /// Xray `raw` and the historical `tcp` name use the same byte stream.
    #[serde(alias = "raw")]
    Tcp {},
    #[serde(rename = "websocket", alias = "ws")]
    WebSocket {
        settings: WebSocket,
        #[serde(default)]
        headers: Vec<(String, String)>,
    },
    Grpc {
        config: swirl_transport::grpc::Config,
    },
    #[serde(rename = "http2", alias = "h2")]
    Http2 {
        config: swirl_transport::http2::Config,
    },
    #[serde(rename = "httpupgrade")]
    HttpUpgrade {
        config: swirl_transport::httpupgrade::Config,
    },
    #[serde(rename = "xhttp")]
    XHttp {
        config: swirl_transport::xhttp::Config,
    },
}

impl Transport {
    pub(crate) fn required_alpn(&self) -> Option<&'static [u8]> {
        match self {
            Self::Grpc { .. } | Self::Http2 { .. } | Self::XHttp { .. } => Some(b"h2"),
            _ => None,
        }
    }

    pub(crate) async fn wrap(
        &self,
        stream: BoxStream,
        tls: bool,
        remaining: std::time::Duration,
    ) -> Result<BoxStream> {
        match self {
            Self::Tcp {} => Ok(stream),
            Self::WebSocket { settings, headers } => {
                crate::websocket::connect_with_headers(stream, settings, headers).await
            }
            Self::Grpc { config } => {
                swirl_transport::grpc::connect_with_timeout(stream, config, tls, remaining).await
            }
            Self::Http2 { config } => {
                swirl_transport::http2::connect_with_timeout(stream, config, tls, remaining).await
            }
            Self::HttpUpgrade { config } => {
                swirl_transport::httpupgrade::connect_with_timeout(stream, config, remaining).await
            }
            Self::XHttp { config } => {
                swirl_transport::xhttp::connect_with_timeout(stream, config, tls, remaining).await
            }
        }
    }
}

pub(crate) fn validate(outbound: &Outbound, selected: Option<&Transport>) -> Result<()> {
    let (tls, websocket, reality, flow) = match outbound {
        Outbound::Vless {
            tls,
            websocket,
            reality,
            flow,
            ..
        } => (
            tls.as_ref(),
            websocket.as_ref(),
            reality.is_some(),
            flow.as_deref(),
        ),
        Outbound::Trojan { tls, websocket, .. } => (Some(tls), websocket.as_ref(), false, None),
        _ if selected.is_some() => return Err("TransportProtocolUnsupported"),
        _ => return Ok(()),
    };
    if let Some(ws) = websocket {
        ws.validate_tls(tls)?;
        if selected.is_some() {
            return Err("TransportConflict");
        }
    }
    if let Some(selected) = selected {
        if matches!(selected, Transport::Tcp {}) {
            return Ok(());
        }
        if reality {
            return Err("RealityTransportUnsupported");
        }
        if flow.is_some_and(|value| !value.is_empty()) {
            return Err("VisionTransportUnsupported");
        }
        if let Some(required) = selected.required_alpn()
            && tls.is_some_and(|tls| {
                !tls.alpn.is_empty() && !tls.alpn.iter().any(|v| v.as_bytes() == required)
            })
        {
            return Err("TlsAlpnUnsupported");
        }
        match selected {
            Transport::WebSocket { settings, headers } => {
                settings.validate_tls(tls)?;
                crate::websocket::validate_headers(headers)?;
            }
            Transport::Grpc { config } => config.validate()?,
            Transport::Http2 { config } => {
                if tls.is_none() {
                    return Err("Http2TlsRequired");
                }
                config.validate()?;
            }
            Transport::HttpUpgrade { config } => {
                if tls.is_some_and(|tls| !(tls.alpn.is_empty() || tls.alpn == ["http/1.1"])) {
                    return Err("HttpUpgradeAlpnUnsupported");
                }
                config.validate()?;
            }
            Transport::XHttp { config } => config.validate()?,
            Transport::Tcp {} => {}
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn raw_alias_and_unsupported_options_fail_closed() {
        assert!(matches!(
            serde_json::from_str::<Transport>(r#"{"type":"raw"}"#).unwrap(),
            Transport::Tcp {}
        ));
        for input in [
            r#"{"type":"tcp","header":{"type":"http"}}"#,
            r#"{"type":"websocket","settings":{"host":"example.com","path":"/"},"early_data":1024}"#,
            r#"{"type":"xhttp","mode":"auto"}"#,
        ] {
            assert!(serde_json::from_str::<Transport>(input).is_err());
        }
    }
}

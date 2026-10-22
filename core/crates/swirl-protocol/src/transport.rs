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
    /// Validate this selection against an outbound before DNS, sockets or Core
    /// activation. Importers still own strict source-parameter conversion.
    pub fn validate_for(&self, outbound: &Outbound) -> Result<()> {
        validate(outbound, Some(self))
    }

    pub(crate) fn required_alpn(&self) -> Option<&'static [u8]> {
        match self {
            Self::Grpc { .. } | Self::Http2 { .. } | Self::XHttp { .. } => Some(b"h2"),
            _ => None,
        }
    }

    /// Only for an already authenticated REALITY session. Xray's pinned
    /// REALITY server deliberately sets NextProtos=nil, then starts its gRPC
    /// or XHTTP HTTP/2 listener with prior knowledge. An absent selection is
    /// therefore expected there; a present incompatible protocol still fails.
    /// Ordinary certificate-based TLS requires negotiated h2 in `secure_with_alpn`.
    pub(crate) fn validate_reality_alpn(&self, negotiated: Option<&[u8]>) -> Result<()> {
        if let (Some(required), Some(negotiated)) = (self.required_alpn(), negotiated)
            && required != negotiated
        {
            return Err("RealityAlpnNegotiation");
        }
        Ok(())
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
            reality.as_ref(),
            flow.as_deref(),
        ),
        Outbound::Trojan { tls, websocket, .. } => (Some(tls), websocket.as_ref(), None, None),
        Outbound::Vmess { tls, websocket, .. } => (tls.as_ref(), websocket.as_ref(), None, None),
        _ if selected.is_some() => return Err("TransportProtocolUnsupported"),
        _ => return Ok(()),
    };
    if let Some(reality) = reality {
        if tls.is_some() || websocket.is_some() {
            return Err("RealityTransportConflict");
        }
        reality.validate()?;
    }
    if let Some(ws) = websocket {
        ws.validate_tls(tls)?;
        crate::websocket::validate_settings(ws, &[])?;
        if selected.is_some() {
            return Err("TransportConflict");
        }
    }
    if let Some(selected) = selected {
        if matches!(outbound, Outbound::Vmess { .. })
            && !matches!(selected, Transport::Tcp {} | Transport::WebSocket { .. })
        {
            return Err("VmessTransportUnsupported");
        }
        if matches!(selected, Transport::Tcp {}) {
            return Ok(());
        }
        if reality.is_some()
            && !matches!(selected, Transport::Grpc { .. } | Transport::XHttp { .. })
        {
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
        if let Some(required) = selected.required_alpn()
            && reality.is_some_and(|reality| {
                !reality.alpn.is_empty()
                    && !reality
                        .alpn
                        .iter()
                        .any(|value| value.as_bytes() == required)
            })
        {
            return Err("RealityAlpnUnsupported");
        }
        match selected {
            Transport::WebSocket { settings, headers } => {
                settings.validate_tls(tls)?;
                crate::websocket::validate_settings(settings, headers)?;
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

    #[test]
    fn reality_prior_knowledge_does_not_accept_incompatible_alpn() {
        let mut outbound: Outbound = serde_json::from_str(
            r#"{"type":"vless","host":"peer.invalid","port":443,
                "uuid":"00112233-4455-6677-8899-aabbccddeeff","reality":{
                "server_name":"peer.invalid",
                "public_key":"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
                "short_id":"01","fingerprint":"rustls","alpn":[]}}"#,
        )
        .unwrap();
        for input in [
            r#"{"type":"grpc","config":{"authority":"peer.invalid","service_name":"tunnel","mode":"tun"}}"#,
            r#"{"type":"xhttp","config":{"host":"peer.invalid","path":"/tunnel","mode":"stream-one"}}"#,
        ] {
            let selected: Transport = serde_json::from_str(input).unwrap();
            assert_eq!(selected.validate_for(&outbound), Ok(()));
            assert_eq!(selected.validate_reality_alpn(None), Ok(()));
            assert_eq!(selected.validate_reality_alpn(Some(b"h2")), Ok(()));
            assert_eq!(
                selected.validate_reality_alpn(Some(b"http/1.1")),
                Err("RealityAlpnNegotiation")
            );
            let Outbound::Vless { reality, .. } = &mut outbound else {
                unreachable!()
            };
            reality.as_mut().unwrap().alpn = vec!["http/1.1".into()];
            assert_eq!(
                selected.validate_for(&outbound),
                Err("RealityAlpnUnsupported")
            );
            let Outbound::Vless { reality, .. } = &mut outbound else {
                unreachable!()
            };
            reality.as_mut().unwrap().alpn.clear();
        }
    }
}

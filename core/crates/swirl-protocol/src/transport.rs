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
}

impl Transport {
    pub(crate) async fn wrap(&self, stream: BoxStream, _tls: bool) -> Result<BoxStream> {
        match self {
            Self::Tcp {} => Ok(stream),
            Self::WebSocket { settings, headers } => {
                crate::websocket::connect_with_headers(stream, settings, headers).await
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
    if let Some(Transport::WebSocket { settings, headers }) = selected {
        if reality {
            return Err("RealityTransportUnsupported");
        }
        if flow.is_some_and(|value| !value.is_empty()) {
            return Err("VisionTransportUnsupported");
        }
        settings.validate_tls(tls)?;
        crate::websocket::validate_headers(headers)?;
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

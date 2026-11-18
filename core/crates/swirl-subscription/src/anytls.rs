//! AnyTLS parameters and the lifetime of sessions owned by an immutable node.
use crate::{Tls, valid_host};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex, Weak};

pub trait SessionResource: Send + Sync {
    fn close(&self);
    fn is_closed(&self) -> bool;
}

#[derive(Default)]
pub struct SessionOwner(Mutex<Vec<Weak<dyn SessionResource>>>);
impl SessionOwner {
    pub fn register(&self, resource: Weak<dyn SessionResource>) -> Result<(), &'static str> {
        let mut entries = self.0.lock().map_err(|_| "AnyTlsSessionOwner")?;
        entries.retain(|entry| {
            entry
                .upgrade()
                .is_some_and(|resource| !resource.is_closed())
        });
        if entries.len() >= 64 {
            return Err("AnyTlsSessionOwnerLimit");
        }
        entries.push(resource);
        Ok(())
    }
}
impl Drop for SessionOwner {
    fn drop(&mut self) {
        for resource in self
            .0
            .get_mut()
            .unwrap_or_else(|error| error.into_inner())
            .drain(..)
        {
            if let Some(resource) = resource.upgrade() {
                resource.close();
            }
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnyTls {
    pub host: String,
    pub port: u16,
    pub password: String,
    pub tls: Tls,
    #[serde(default = "enabled")]
    pub udp: bool,
    #[serde(default = "idle_timeout")]
    pub idle_session_timeout_seconds: u64,
    #[serde(skip)]
    pub session_owner: Arc<SessionOwner>,
}
fn idle_timeout() -> u64 {
    60
}
fn enabled() -> bool {
    true
}
impl AnyTls {
    pub fn validate(&self) -> Result<(), &'static str> {
        if !valid_host(&self.host)
            || self.port == 0
            || self.password.is_empty()
            || self.password.len() > 1024
            || !valid_host(&self.tls.server_name)
            || !(5..=300).contains(&self.idle_session_timeout_seconds)
        {
            return Err("AnyTlsParameters");
        }
        if self.tls.alpn.len() > 16
            || self
                .tls
                .alpn
                .iter()
                .any(|value| value.is_empty() || value.len() > 255 || !value.is_ascii())
            || self
                .tls
                .ca_der_base64
                .as_ref()
                .is_some_and(|value| value.len() > 65_536)
        {
            return Err("AnyTlsTlsParameters");
        }
        Ok(())
    }
    pub fn from_raw(raw: &serde_json::Value) -> Result<Self, &'static str> {
        use serde_json::Value;
        let object = raw.as_object().ok_or("AnyTlsParameters")?;
        if raw
            .get("type")
            .is_some_and(|value| value.as_str() != Some("anytls"))
        {
            return Err("AnyTlsProtocol");
        }
        if object.keys().any(|key| {
            !matches!(
                key.as_str(),
                "name"
                    | "tag"
                    | "type"
                    | "server"
                    | "port"
                    | "server_port"
                    | "password"
                    | "tls"
                    | "sni"
                    | "servername"
                    | "alpn"
                    | "udp"
                    | "skip-cert-verify"
                    | "tls-verification"
                    | "network"
                    | "pcs"
                    | "raw-uri"
                    | "raw-ini"
            )
        }) {
            return Err("AnyTlsOptionsUnsupported");
        }
        if raw.get("pcs").is_some_and(|v| v.as_str() != Some("")) {
            return Err("AnyTlsCertificatePinsUnsupported");
        }
        if raw
            .get("skip-cert-verify")
            .is_some_and(|v| v != &Value::Bool(false))
            || raw
                .get("tls-verification")
                .is_some_and(|v| v != &Value::Bool(true))
        {
            return Err("CertificateVerificationDisabledUnsupported");
        }
        if raw.get("tls").is_some_and(|v| v != &Value::Bool(true))
            || raw
                .get("network")
                .is_some_and(|v| v.as_str() != Some("tcp"))
        {
            return Err("AnyTlsTransportUnsupported");
        }
        let host = raw
            .get("server")
            .and_then(Value::as_str)
            .ok_or("AnyTlsHost")?
            .to_owned();
        let port = raw
            .get("port")
            .or_else(|| raw.get("server_port"))
            .and_then(Value::as_u64)
            .and_then(|v| u16::try_from(v).ok())
            .ok_or("AnyTlsPort")?;
        if raw
            .get("port")
            .zip(raw.get("server_port"))
            .is_some_and(|(a, b)| a != b)
        {
            return Err("AnyTlsPort");
        }
        if raw
            .get("sni")
            .zip(raw.get("servername"))
            .is_some_and(|(a, b)| a != b)
        {
            return Err("AnyTlsTlsNames");
        }
        let server_name = match raw.get("sni").or_else(|| raw.get("servername")) {
            Some(v) => v.as_str().ok_or("AnyTlsTlsNames")?.to_owned(),
            None => host.clone(),
        };
        let alpn = match raw.get("alpn") {
            None => vec![],
            Some(Value::Array(values)) => values
                .iter()
                .map(|v| v.as_str().map(str::to_owned).ok_or("AnyTlsAlpn"))
                .collect::<Result<Vec<_>, _>>()?,
            _ => return Err("AnyTlsAlpn"),
        };
        let config = Self {
            host,
            port,
            password: raw
                .get("password")
                .and_then(Value::as_str)
                .ok_or("AnyTlsPassword")?
                .to_owned(),
            tls: Tls {
                server_name,
                alpn,
                ca_der_base64: None,
            },
            udp: match raw.get("udp") {
                None => true,
                Some(Value::Bool(value)) => *value,
                _ => return Err("AnyTlsUdp"),
            },
            idle_session_timeout_seconds: idle_timeout(),
            session_owner: Arc::default(),
        };
        config.validate()?;
        Ok(config)
    }
}

#[cfg(test)]
#[path = "anytls_tests.rs"]
mod tests;

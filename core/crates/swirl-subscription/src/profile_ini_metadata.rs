//! Client-only profile metadata is preserved without creating host side effects.
//! The shell must display the returned restrictions and keep the raw document in
//! its encrypted catalog. Embedded URLs never change the subscription source.
use super::{ProfileError, bool_value, fail};
use serde_json::{Map, Value, json};
use std::collections::{BTreeSet, HashSet};

#[derive(Default)]
pub(super) struct Metadata {
    managed: Option<Value>,
    preserved: BTreeSet<String>,
}

fn web_url(text: &str) -> bool {
    text.len() <= 4096
        && !text.contains('\\')
        && !text.chars().any(char::is_control)
        && url::Url::parse(text).is_ok_and(|url| {
            matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.fragment().is_none()
                && url.port() != Some(0)
        })
}

impl Metadata {
    pub(super) fn managed(&mut self, line: &str, first: bool) -> Result<(), ProfileError> {
        if !first || self.managed.is_some() {
            return Err(fail("ProfileManagedHeaderPosition"));
        }
        let mut fields = line.split_whitespace();
        if fields.next() != Some("#!MANAGED-CONFIG") || !fields.next().is_some_and(web_url) {
            return Err(fail("ProfileManagedUrlInvalid"));
        }
        let mut interval = 86400_u64;
        let mut strict = false;
        let mut seen = HashSet::new();
        for field in fields {
            let (key, value) = field
                .split_once('=')
                .ok_or_else(|| fail("ProfileManagedParameter"))?;
            if !seen.insert(key) {
                return Err(fail("ProfileManagedParameter"));
            }
            match key {
                "interval" => {
                    interval = value
                        .parse::<u64>()
                        .ok()
                        .filter(|n| (60..=2592000).contains(n))
                        .ok_or_else(|| fail("ProfileManagedInterval"))?;
                }
                "strict" => strict = bool_value(value)?,
                _ => return Err(fail("ProfileManagedParameter")),
            }
        }
        self.managed = Some(json!({"embeddedUrlPreserved":true,
            "embeddedUrlApplied":false,"intervalSeconds":interval,"strict":strict}));
        Ok(())
    }

    /// Returns false for unknown or traffic-affecting keys. This list is not an
    /// escape hatch: client-only values are type checked and never executed.
    pub(super) fn general(&mut self, key: &str, value: &str) -> Result<bool, ProfileError> {
        let valid = match key {
            "loglevel" => matches!(
                value.to_ascii_lowercase().as_str(),
                "verbose" | "info" | "notify" | "warning" | "error" | "debug"
            ),
            "proxy-test-url" | "internet-test-url" | "network_check_url" | "server_check_url"
            | "profile_img_url" | "group-icon" => web_url(value),
            "test-timeout" => value.parse::<u32>().is_ok_and(|n| (1..=120).contains(&n)),
            "server_check_timeout" => value
                .parse::<u32>()
                .is_ok_and(|n| (100..=30000).contains(&n)),
            "server_check_user_agent" | "doh_user_agent" => {
                !value.is_empty() && value.len() <= 512 && !value.chars().any(char::is_control)
            }
            // Explicit restrictions already satisfied by the fixed loopback
            // listener and lack of a TUN adapter. Never enable either here.
            "allow-wifi-access" => !bool_value(value)?,
            "ipv6-vif" => matches!(value.to_ascii_lowercase().as_str(), "off" | "disabled"),
            _ => return Ok(false),
        };
        if !valid {
            return Err(fail("ProfileIniClientSettingInvalid"));
        }
        self.preserved.insert(key.to_owned());
        Ok(true)
    }

    pub(super) fn finish(self, projected: &mut Value) {
        let mut metadata = Map::new();
        let mut restrictions = Vec::new();
        if let Some(managed) = self.managed {
            metadata.insert("managedConfig".into(), managed);
            restrictions.push("EmbeddedUpdateUsesSwirlSubscription");
        }
        if !self.preserved.is_empty() {
            metadata.insert("preservedGeneral".into(), json!(self.preserved));
            restrictions.push("ClientGeneralSettingsPreserved");
        }
        if !metadata.is_empty() {
            metadata.insert("restrictions".into(), json!(restrictions));
            projected["importMetadata"] = Value::Object(metadata);
        }
    }
}

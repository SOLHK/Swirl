//! Fixed synthetic billing over the same mandatory transport guard. This is
//! not an official provider, billing-lag, freshness or wire-accounting adapter.
use super::{FixtureTls, Grant, Result, key};
use base64::Engine;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{collections::BTreeMap, sync::Arc};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWriteExt};
use tokio_rustls::{
    TlsConnector,
    rustls::{ClientConfig, RootCertStore, client::Resumption, pki_types::CertificateDer},
};

pub(super) const BYTE_LIMIT: u64 = 65536;
const DOMAIN: &str = "swirl-synthetic-billing-v1";
const SERVER_NAME: &str = "swirl-qa.fixture.invalid";
const MAX_HEADER_BYTES: usize = 8192;
const MAX_LINE_BYTES: usize = 1024;
const MAX_COUNTER: u64 = i64::MAX as u64;
const FAILURE: &str = "billing_snapshot_failed";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct BillingGrant {
    schema: u32,
    domain: String,
    authority_id: String,
    account_id: String,
    period_id: String,
    request_nonce: String,
}

impl BillingGrant {
    pub(super) fn validate(&self, nonce: &str) -> Result<()> {
        if self.schema != 1
            || self.domain != DOMAIN
            || self.request_nonce != nonce
            || [
                &self.authority_id,
                &self.account_id,
                &self.period_id,
                &self.request_nonce,
            ]
            .iter()
            .any(|value| key(value).is_none())
        {
            return Err("PrivateWorkerBillingGrant");
        }
        Ok(())
    }
}

pub(super) fn tls_config(tls: &FixtureTls) -> Result<Arc<ClientConfig>> {
    if tls.server_name != SERVER_NAME || tls.ca_der_base64.len() > 8192 {
        return Err("PrivateWorkerTls");
    }
    let der = base64::engine::general_purpose::STANDARD
        .decode(&tls.ca_der_base64)
        .map_err(|_| "PrivateWorkerTls")?;
    if der.is_empty() || base64::engine::general_purpose::STANDARD.encode(&der) != tls.ca_der_base64
    {
        return Err("PrivateWorkerTls");
    }
    // No public/system roots and no verification override. Even a certificate
    // accepted by another process is irrelevant to this one-fixture trust set.
    let mut roots = RootCertStore::empty();
    roots
        .add(CertificateDer::from(der))
        .map_err(|_| "PrivateWorkerTls")?;
    let mut config = ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    config.alpn_protocols = vec![b"http/1.1".to_vec()];
    config.resumption = Resumption::disabled();
    config.enable_early_data = false;
    Ok(Arc::new(config))
}

fn number(value: &str) -> Result<u64> {
    if value.is_empty()
        || !value.bytes().all(|byte| byte.is_ascii_digit())
        || (value.len() > 1 && value.starts_with('0'))
    {
        return Err(FAILURE);
    }
    value
        .parse::<u64>()
        .ok()
        .filter(|value| *value <= MAX_COUNTER)
        .ok_or(FAILURE)
}

fn parse_headers(bytes: &[u8], expected: &BillingGrant) -> Result<Value> {
    if bytes.len() > MAX_HEADER_BYTES
        || !bytes
            .iter()
            .all(|byte| matches!(byte, b' '..=b'~' | b'\r' | b'\n'))
    {
        return Err(FAILURE);
    }
    let text = std::str::from_utf8(bytes).map_err(|_| FAILURE)?;
    let text = text.strip_suffix("\r\n\r\n").ok_or(FAILURE)?;
    let mut lines = text.split("\r\n");
    let status = lines.next().ok_or(FAILURE)?;
    if status.len() + 2 > MAX_LINE_BYTES
        || !status.starts_with("HTTP/1.1 200 ")
        || status.contains(['\r', '\n'])
    {
        return Err(FAILURE);
    }
    let mut headers = BTreeMap::new();
    for line in lines {
        if line.len() + 2 > MAX_LINE_BYTES || line.contains(['\r', '\n']) {
            return Err(FAILURE);
        }
        let (name, value) = line.split_once(": ").ok_or(FAILURE)?;
        let name = name.to_ascii_lowercase();
        if !matches!(
            name.as_str(),
            "content-length"
                | "connection"
                | "subscription-userinfo"
                | "x-swirl-qa-billing-schema"
                | "x-swirl-qa-billing-domain"
                | "x-swirl-qa-billing-authority"
                | "x-swirl-qa-billing-account"
                | "x-swirl-qa-billing-period"
                | "x-swirl-qa-billing-nonce"
                | "x-swirl-qa-billing-revision"
                | "x-swirl-qa-billing-covered-sequence"
        ) || headers.insert(name, value).is_some()
        {
            return Err(FAILURE);
        }
    }
    let get = |name: &str| headers.get(name).copied().ok_or(FAILURE);
    if get("content-length")? != "0"
        || headers
            .get("connection")
            .is_some_and(|value| *value != "close")
        || get("x-swirl-qa-billing-schema")? != "1"
        || get("x-swirl-qa-billing-domain")? != DOMAIN
        || get("x-swirl-qa-billing-authority")? != expected.authority_id
        || get("x-swirl-qa-billing-account")? != expected.account_id
        || get("x-swirl-qa-billing-period")? != expected.period_id
        || get("x-swirl-qa-billing-nonce")? != expected.request_nonce
    {
        return Err(FAILURE);
    }
    let info: Vec<&str> = get("subscription-userinfo")?.split(';').collect();
    if info.len() != 4 {
        return Err(FAILURE);
    }
    let upload = number(info[0].strip_prefix("upload=").ok_or(FAILURE)?)?;
    let download = number(info[1].strip_prefix("download=").ok_or(FAILURE)?)?;
    let total = number(info[2].strip_prefix("total=").ok_or(FAILURE)?)?;
    let expire = number(info[3].strip_prefix("expire=").ok_or(FAILURE)?)?;
    let revision = number(get("x-swirl-qa-billing-revision")?)?;
    let covered_sequence = number(get("x-swirl-qa-billing-covered-sequence")?)?;
    if revision == 0 || total == 0 || upload.checked_add(download).is_none_or(|used| used > total) {
        return Err(FAILURE);
    }
    Ok(json!({"schema":1,"domain":DOMAIN,
        "authority_id":expected.authority_id,"account_id":expected.account_id,
        "period_id":expected.period_id,"request_nonce":expected.request_nonce,
        "revision":revision,"covered_sequence":covered_sequence,
        "upload":upload,"download":download,"total":total,"expire":expire}))
}

async fn read_headers(stream: &mut (impl AsyncRead + Unpin)) -> Result<Vec<u8>> {
    let mut bytes = Vec::with_capacity(MAX_LINE_BYTES);
    let mut line_length = 0;
    while bytes.len() < MAX_HEADER_BYTES {
        let byte = stream.read_u8().await.map_err(|_| FAILURE)?;
        if !matches!(byte, b' '..=b'~' | b'\r' | b'\n') {
            return Err(FAILURE);
        }
        bytes.push(byte);
        line_length += 1;
        if line_length > MAX_LINE_BYTES {
            return Err(FAILURE);
        }
        if bytes.ends_with(b"\r\n\r\n") {
            return Ok(bytes);
        }
        if bytes.ends_with(b"\r\n") {
            line_length = 0;
        }
    }
    Err(FAILURE)
}

pub(super) async fn snapshot(grant: &Grant) -> Result<Value> {
    let expected = grant.billing.as_ref().ok_or(FAILURE)?;
    let tls = tls_config(grant.tls.as_ref().ok_or(FAILURE)?).map_err(|_| FAILURE)?;
    // The IP is immutable and already admitted by install_worker. This is the
    // sole second connection; every TLS/request/response byte crosses TcpQuota.
    let socket = swirl_transport::connect_tcp(grant.endpoint())
        .await
        .map_err(|_| FAILURE)?;
    let mut stream = TlsConnector::from(tls)
        .connect(SERVER_NAME.try_into().map_err(|_| FAILURE)?, socket)
        .await
        .map_err(|_| FAILURE)?;
    if stream.get_ref().1.alpn_protocol() != Some(b"http/1.1") {
        return Err(FAILURE);
    }
    let authorization = base64::engine::general_purpose::STANDARD
        .encode(format!("swirl-private-billing:{}", grant.challenge));
    let request = format!(
        "HEAD /swirl-private-billing/{} HTTP/1.1\r\nHost: {}\r\nAuthorization: Basic {}\r\nConnection: close\r\n\r\n",
        expected.request_nonce, SERVER_NAME, authorization
    );
    stream
        .write_all(request.as_bytes())
        .await
        .map_err(|_| FAILURE)?;
    stream.flush().await.map_err(|_| FAILURE)?;
    let bytes = read_headers(&mut stream).await?;
    let result = parse_headers(&bytes, expected)?;
    // A HEAD response declaring no body still cannot smuggle an application
    // tail. Require authenticated TLS EOF, examining at most one extra byte;
    // never download a subscription body. Deadline/cancel remains authoritative.
    if stream.read(&mut [0u8; 1]).await.map_err(|_| FAILURE)? != 0 {
        return Err(FAILURE);
    }
    let _ = stream.shutdown().await;
    drop(stream);
    Ok(result)
}

#[cfg(test)]
#[path = "billing_tests.rs"]
mod tests;

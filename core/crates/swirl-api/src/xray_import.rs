//! Private Qt projection of the authoritative Xray/V2Ray converter. There is no second
//! JSON parser, protocol converter, or runtime here. Only the diagnostics are
//! suitable for logs; successful responses contain credentials and raw data.
use serde::Serialize;
use std::io::{self, Write};
use swirl_subscription::{
    Outbound,
    xray::{
        Diagnostic, InputSource, MAX_JSON_INPUT,
        convert::{
            Authentication, ConvertedDocument, NodeSource, Protocol, Security, Transport,
            ValidationStatus, import_document,
        },
    },
};

const MAX_OUTPUT: usize = 64 * 1024 * 1024;
const INVALID_BUFFER: isize = -1;
const PANIC: isize = -2;
const INTERNAL_ERROR: isize = -3;
const OUTPUT_LIMIT: isize = -4;

#[derive(Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum AuthenticationView<'a> {
    Vless {
        id: Option<&'a str>,
        encryption: Option<&'a str>,
        flow: Option<&'a str>,
        level: Option<u32>,
        email: Option<&'a str>,
    },
    Vmess {
        id: Option<&'a str>,
        alter_id: Option<u16>,
        security: Option<&'a str>,
        level: Option<u32>,
        email: Option<&'a str>,
    },
    Password {
        password: Option<&'a str>,
        method: Option<&'a str>,
        level: Option<u32>,
        email: Option<&'a str>,
    },
    UserPassword {
        user: Option<&'a str>,
        pass: Option<&'a str>,
        level: Option<u32>,
    },
    None,
    Unknown,
}

impl<'a> From<&'a Authentication> for AuthenticationView<'a> {
    fn from(value: &'a Authentication) -> Self {
        match value {
            Authentication::Vless {
                id,
                encryption,
                flow,
                level,
                email,
            } => Self::Vless {
                id: id.as_deref(),
                encryption: encryption.as_deref(),
                flow: flow.as_deref(),
                level: *level,
                email: email.as_deref(),
            },
            Authentication::Vmess {
                id,
                alter_id,
                security,
                level,
                email,
            } => Self::Vmess {
                id: id.as_deref(),
                alter_id: *alter_id,
                security: security.as_deref(),
                level: *level,
                email: email.as_deref(),
            },
            Authentication::Password {
                password,
                method,
                level,
                email,
            } => Self::Password {
                password: password.as_deref(),
                method: method.as_deref(),
                level: *level,
                email: email.as_deref(),
            },
            Authentication::UserPassword { user, pass, level } => Self::UserPassword {
                user: user.as_deref(),
                pass: pass.as_deref(),
                level: *level,
            },
            Authentication::None => Self::None,
            Authentication::Unknown => Self::Unknown,
        }
    }
}

#[derive(Serialize)]
struct NodeView<'a> {
    index: usize,
    source: &'a NodeSource,
    name: &'a str,
    protocol: Protocol,
    host: Option<&'a str>,
    port: Option<u16>,
    authentication: AuthenticationView<'a>,
    transport: Transport,
    security: Security,
    validation: ValidationStatus,
    diagnostics: &'a [Diagnostic],
    is_remote_node: bool,
    executable: bool,
    native_outbound: Option<&'a Outbound>,
    execution_issues: Vec<&'a str>,
    network_verified: bool,
}

#[derive(Serialize)]
struct Response<'a> {
    schema: u32,
    ok: bool,
    format: &'static str,
    diagnostics: &'a [Diagnostic],
    // A multi-user outbound is retained once rather than copied per account.
    // NodeSource.outbound_index addresses this list; index addresses nodes.
    outbounds: Vec<&'a serde_json::Value>,
    nodes: Vec<NodeView<'a>>,
}

#[derive(Serialize)]
struct ErrorResponse<'a> {
    schema: u32,
    ok: bool,
    format: &'static str,
    error: &'a str,
    diagnostics: [&'a Diagnostic; 1],
}

fn response(document: &ConvertedDocument) -> Result<Response<'_>, isize> {
    let mut outbounds = Vec::new();
    let mut nodes = Vec::with_capacity(document.nodes().len());
    for (index, node) in document.nodes().iter().enumerate() {
        let raw = document.raw_outbound(index).ok_or(INTERNAL_ERROR)?;
        let source = node.source();
        if source.outbound_index > outbounds.len() {
            return Err(INTERNAL_ERROR);
        }
        if source.outbound_index == outbounds.len() {
            outbounds.push(raw);
        }
        let is_remote_node = !matches!(
            raw.get("protocol").and_then(serde_json::Value::as_str),
            Some("freedom" | "blackhole" | "dns" | "loopback")
        );
        let blocked = node
            .diagnostics()
            .iter()
            .find(|issue| matches!(issue.severity.as_str(), "error" | "unsupported"));
        // The authoritative converter owns capability and all late document
        // diagnostics. Its candidate belongs to this expanded server/account,
        // not to the original outbound shared by its siblings.
        let native_outbound = if is_remote_node {
            node.native_outbound()
        } else {
            None
        };
        let issue = if !is_remote_node {
            Some("LocalActionNotRemoteNode")
        } else if native_outbound.is_some() {
            None
        } else if let Some(issue) = blocked {
            Some(issue.code.as_str())
        } else if node.validation() != ValidationStatus::Valid {
            Some("NodeParametersUnverified")
        } else {
            Some("NativeExecutionBlocked")
        };
        nodes.push(NodeView {
            index,
            source,
            name: raw
                .get("tag")
                .and_then(serde_json::Value::as_str)
                .unwrap_or(""),
            protocol: node.protocol(),
            host: node.endpoint().map(|endpoint| endpoint.address.as_str()),
            port: node.endpoint().map(|endpoint| endpoint.port),
            authentication: node.authentication().into(),
            transport: node.transport(),
            security: node.security(),
            validation: node.validation(),
            diagnostics: node.diagnostics(),
            is_remote_node,
            executable: native_outbound.is_some(),
            native_outbound,
            execution_issues: issue.into_iter().collect(),
            network_verified: node.network_verified(),
        });
    }
    Ok(Response {
        schema: 1,
        ok: true,
        format: "xray-v2ray-json",
        diagnostics: document.diagnostics(),
        outbounds,
        nodes,
    })
}

struct BoundedWriter<W> {
    inner: W,
    written: usize,
    exceeded: bool,
    maximum: usize,
}

impl<W: Write> Write for BoundedWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > self.maximum.saturating_sub(self.written) {
            self.exceeded = true;
            return Err(io::Error::other("ImportOutputLimit"));
        }
        let written = self.inner.write(bytes)?;
        self.written += written;
        Ok(written)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}

fn serialize<T: Serialize, W: Write>(value: &T, writer: W, maximum: usize) -> Result<W, isize> {
    let mut bounded = BoundedWriter {
        inner: writer,
        written: 0,
        exceeded: false,
        maximum,
    };
    if serde_json::to_writer(&mut bounded, value).is_err() {
        return Err(if bounded.exceeded {
            OUTPUT_LIMIT
        } else {
            INTERNAL_ERROR
        });
    }
    Ok(bounded.inner)
}

#[derive(Default)]
struct Counter(usize);
impl Write for Counter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0 += bytes.len();
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn encoded_response<T: Serialize>(
    value: &T,
    capacity: usize,
) -> Result<(usize, Option<Vec<u8>>), isize> {
    // The size query allocates no output buffer, and overflow is rejected before
    // constructing one. This also leaves an insufficient caller buffer intact.
    let size = serialize(value, Counter::default(), MAX_OUTPUT)?.0;
    let bytes = if size <= capacity {
        Some(serialize(value, Vec::with_capacity(size), size)?)
    } else {
        None
    };
    Ok((size, bytes))
}

fn import_response(input: &[u8], capacity: usize) -> Result<(usize, Option<Vec<u8>>), isize> {
    match import_document(input, InputSource::Unknown) {
        Ok(document) => encoded_response(&response(&document)?, capacity),
        Err(diagnostic) => encoded_response(
            &ErrorResponse {
                schema: 1,
                ok: false,
                format: "xray-v2ray-json",
                error: &diagnostic.code,
                diagnostics: [&diagnostic],
            },
            capacity,
        ),
    }
}

/// Return the exact bounded UTF-8 response size; write only when capacity is
/// sufficient. `(output = null, capacity = 0)` queries the size. Diagnostics
/// include no input excerpts. Successful responses contain private node data.
///
/// # Safety
/// Non-null input must address input_len initialized bytes. A non-null output
/// must address output_capacity writable bytes. Regions must remain valid,
/// unmodified by other threads and nonoverlapping for the call. Null input is
/// valid only for zero input length; null output only for zero capacity.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_import_xray_v1(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
) -> isize {
    if (input.is_null() && input_len != 0)
        || (output.is_null() && output_capacity != 0)
        || input_len > MAX_JSON_INPUT
        || output_capacity > MAX_OUTPUT
    {
        return INVALID_BUFFER;
    }
    let Some(input_end) = (input as usize).checked_add(input_len) else {
        return INVALID_BUFFER;
    };
    let Some(output_end) = (output as usize).checked_add(output_capacity) else {
        return INVALID_BUFFER;
    };
    if input_len != 0
        && output_capacity != 0
        && (input as usize) < output_end
        && (output as usize) < input_end
    {
        return INVALID_BUFFER;
    }
    std::panic::catch_unwind(|| {
        let input = if input_len == 0 {
            &[]
        } else {
            // SAFETY: ABI caller guarantees initialized immutable input bytes;
            // null, oversized, overflowed and overlapping regions were rejected.
            unsafe { std::slice::from_raw_parts(input, input_len) }
        };
        match import_response(input, output_capacity) {
            Ok((size, bytes)) => {
                if let Some(mut bytes) = bytes {
                    // SAFETY: caller guarantees a writable nonoverlapping region
                    // and serialization has checked its entire required size.
                    unsafe {
                        std::ptr::copy_nonoverlapping(bytes.as_ptr(), output, bytes.len());
                    }
                    // Avoid retaining an extra serialized credential copy.
                    bytes.fill(0);
                }
                size as isize
            }
            Err(code) => code,
        }
    })
    .unwrap_or(PANIC)
}

#[cfg(test)]
#[path = "xray_import_tests.rs"]
mod tests;

//! Shared bounded buffer contract for offline import ABIs. No network I/O.
use serde::Serialize;
use std::io::{self, Write};

pub(crate) const MAX_OUTPUT: usize = 64 * 1024 * 1024;
pub(crate) const INVALID_BUFFER: isize = -1;
const PANIC: isize = -2;
const INTERNAL_ERROR: isize = -3;
pub(crate) const OUTPUT_LIMIT: isize = -4;
type ResponseEncoder = fn(&[u8], usize) -> Result<(usize, Option<Vec<u8>>), isize>;

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

pub(crate) fn serialize<T: Serialize, W: Write>(
    value: &T,
    writer: W,
    maximum: usize,
) -> Result<W, isize> {
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
pub(crate) struct Counter(usize);
impl Write for Counter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0 += bytes.len();
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

pub(crate) fn encoded_response<T: Serialize>(
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

/// Caller guarantees valid initialized input and writable output regions.
/// Pointer arithmetic, overlap, nullness and all allocation budgets are checked.
pub(crate) unsafe fn call(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
    input_limit: usize,
    response: ResponseEncoder,
) -> isize {
    if (input.is_null() && input_len != 0)
        || (output.is_null() && output_capacity != 0)
        || input_len > input_limit
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
        match response(input, output_capacity) {
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

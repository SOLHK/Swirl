//! Blocking packet framing for the two dedicated broker/worker packet pipes.
//! Control JSON, stop and heartbeat traffic use separate existing handles.
//! This boundary validates framing only; the existing IP stack validates IP.
//! Epoch and sequence checks do not authenticate a peer. The launcher owns
//! private handles and peer authorization; the owner must cancel blocked IO.
//! The broker must authenticate the worker and give it only the intended pipe
//! handles. The epoch binds frames to that launch; it is not authentication.
use std::io::{self, Read, Write};

const MAGIC: &[u8; 4] = b"SWIP";
const VERSION: u8 = 1;
const HEADER_BYTES: usize = 24;

fn validate(epoch: u64, mtu: usize) -> io::Result<()> {
    if epoch == 0 || !(1280..=9000).contains(&mtu) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "packet IPC requires a nonzero epoch and MTU 1280..=9000",
        ));
    }
    Ok(())
}

fn poisoned() -> io::Error {
    io::Error::new(io::ErrorKind::BrokenPipe, "packet IPC endpoint is poisoned")
}

fn exhausted() -> io::Error {
    io::Error::new(
        io::ErrorKind::ConnectionAborted,
        "packet IPC sequence exhausted",
    )
}

/// One direction, bound to the broker-authenticated launch epoch. A malformed,
/// truncated or failed frame permanently closes this reader's framing state.
pub struct PacketReader<R> {
    input: R,
    epoch: u64,
    mtu: usize,
    next_sequence: Option<u64>,
    failed: bool,
    eof: bool,
}

impl<R: Read> PacketReader<R> {
    /// Bind one dedicated packet input to a nonzero launch epoch and an MTU in
    /// `1280..=9000`. The caller supplies the already authenticated pipe handle.
    pub fn new(input: R, epoch: u64, mtu: usize) -> io::Result<Self> {
        validate(epoch, mtu)?;
        Ok(Self {
            input,
            epoch,
            mtu,
            next_sequence: Some(1),
            failed: false,
            eof: false,
        })
    }

    /// `None` means clean EOF before the first byte of a header. It is terminal,
    /// rather than permission to accept another session on the same pipe.
    /// IO and framing errors poison the reader. Blocking reads and cancellation
    /// of the owning pipe/thread remain the lifecycle controller's responsibility.
    pub fn read_packet(&mut self) -> io::Result<Option<Vec<u8>>> {
        if self.failed {
            return Err(poisoned());
        }
        if self.eof {
            return Ok(None);
        }
        self.failed = true;
        let expected = self.next_sequence.ok_or_else(exhausted)?;
        let mut header = [0; HEADER_BYTES];
        loop {
            match self.input.read(&mut header[..1]) {
                Ok(0) => {
                    self.eof = true;
                    self.failed = false;
                    return Ok(None);
                }
                Ok(_) => break,
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error),
            }
        }
        self.input.read_exact(&mut header[1..])?;
        let length = usize::from(u16::from_be_bytes([header[6], header[7]]));
        let epoch = u64::from_be_bytes(header[8..16].try_into().expect("fixed epoch field"));
        let sequence = u64::from_be_bytes(header[16..24].try_into().expect("fixed sequence field"));
        if &header[..4] != MAGIC
            || header[4] != VERSION
            || header[5] != 0
            || !(1..=self.mtu).contains(&length)
            || epoch != self.epoch
            || sequence != expected
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid packet IPC header, epoch or sequence",
            ));
        }
        // Every untrusted header field has been validated before allocation or
        // body reads. Never scan ahead for MAGIC after a framing failure.
        let mut payload = vec![0; length];
        self.input.read_exact(&mut payload)?;
        self.next_sequence = expected.checked_add(1);
        self.failed = false;
        Ok(Some(payload))
    }
}

/// Each direction starts at sequence one independently. Partial IO poisons the
/// carrier; a later packet must not be appended to a half-written frame.
pub struct PacketWriter<W> {
    output: W,
    epoch: u64,
    mtu: usize,
    next_sequence: Option<u64>,
    failed: bool,
}

impl<W: Write> PacketWriter<W> {
    /// Bind one dedicated packet output to a nonzero launch epoch and an MTU in
    /// `1280..=9000`. The caller supplies the already authenticated pipe handle.
    pub fn new(output: W, epoch: u64, mtu: usize) -> io::Result<Self> {
        validate(epoch, mtu)?;
        Ok(Self {
            output,
            epoch,
            mtu,
            next_sequence: Some(1),
            failed: false,
        })
    }

    /// Write one `1..=MTU` packet with `write_all`, without flushing a supplied
    /// buffering adapter. IO failure poisons the writer; invalid input length
    /// writes nothing. Blocking-IO cancellation belongs to the pipe owner.
    pub fn write_packet(&mut self, payload: &[u8]) -> io::Result<()> {
        if self.failed {
            return Err(poisoned());
        }
        if !(1..=self.mtu).contains(&payload.len()) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "packet IPC payload length is outside MTU",
            ));
        }
        self.failed = true;
        let sequence = self.next_sequence.ok_or_else(exhausted)?;
        let mut header = [0; HEADER_BYTES];
        header[..4].copy_from_slice(MAGIC);
        header[4] = VERSION;
        header[6..8].copy_from_slice(&(payload.len() as u16).to_be_bytes());
        header[8..16].copy_from_slice(&self.epoch.to_be_bytes());
        header[16..24].copy_from_slice(&sequence.to_be_bytes());
        self.output.write_all(&header)?;
        self.output.write_all(payload)?;
        self.next_sequence = sequence.checked_add(1);
        self.failed = false;
        Ok(())
    }
}

#[cfg(test)]
#[path = "native_tun_ipc_tests.rs"]
mod tests;

use super::*;
use std::io::Cursor;

const EPOCH: u64 = 0x0102_0304_0506_0708;

// Encode the test peer's contract explicitly, independently of the writer.
fn frame(epoch: u64, sequence: u64, payload: &[u8]) -> Vec<u8> {
    let mut wire = b"SWIP\x01\x00".to_vec();
    wire.extend_from_slice(&(payload.len() as u16).to_be_bytes());
    wire.extend_from_slice(&epoch.to_be_bytes());
    wire.extend_from_slice(&sequence.to_be_bytes());
    wire.extend_from_slice(payload);
    wire
}

struct FragmentedRead {
    bytes: Cursor<Vec<u8>>,
    chunk: usize,
    interrupt: bool,
    fail_at: Option<u64>,
    calls: usize,
}

impl FragmentedRead {
    fn new(bytes: Vec<u8>, chunk: usize) -> Self {
        Self {
            bytes: Cursor::new(bytes),
            chunk,
            interrupt: true,
            fail_at: None,
            calls: 0,
        }
    }
}

impl Read for FragmentedRead {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.calls += 1;
        if self.interrupt {
            self.interrupt = false;
            return Err(io::ErrorKind::Interrupted.into());
        }
        let remaining = match self.fail_at {
            Some(at) if self.bytes.position() >= at => {
                return Err(io::ErrorKind::PermissionDenied.into());
            }
            Some(at) => (at - self.bytes.position()) as usize,
            None => usize::MAX,
        };
        let amount = output.len().min(self.chunk).min(remaining);
        self.bytes.read(&mut output[..amount])
    }
}

struct PartialWrite {
    bytes: Vec<u8>,
    chunk: usize,
    interrupt: bool,
    fail_at: Option<usize>,
    zero_at: Option<usize>,
    calls: usize,
}

impl PartialWrite {
    fn new(chunk: usize) -> Self {
        Self {
            bytes: Vec::new(),
            chunk,
            interrupt: true,
            fail_at: None,
            zero_at: None,
            calls: 0,
        }
    }
}

impl Write for PartialWrite {
    fn write(&mut self, input: &[u8]) -> io::Result<usize> {
        self.calls += 1;
        if self.interrupt {
            self.interrupt = false;
            return Err(io::ErrorKind::Interrupted.into());
        }
        if self.fail_at.is_some_and(|at| self.bytes.len() >= at) {
            return Err(io::ErrorKind::PermissionDenied.into());
        }
        if self.zero_at.is_some_and(|at| self.bytes.len() >= at) {
            return Ok(0);
        }
        let remaining = self
            .fail_at
            .into_iter()
            .chain(self.zero_at)
            .min()
            .map_or(usize::MAX, |at| at - self.bytes.len());
        let amount = input.len().min(self.chunk).min(remaining);
        self.bytes.extend_from_slice(&input[..amount]);
        Ok(amount)
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn constructors_reject_zero_epoch_and_mtu_outside_validated_range() {
    for (epoch, mtu) in [(0, 1280), (EPOCH, 0), (EPOCH, 1279), (EPOCH, 9001)] {
        assert!(PacketReader::new(Cursor::new([]), epoch, mtu).is_err());
        assert!(PacketWriter::new(Vec::new(), epoch, mtu).is_err());
    }
    for mtu in [1280, 9000] {
        assert!(PacketReader::new(Cursor::new([]), EPOCH, mtu).is_ok());
        assert!(PacketWriter::new(Vec::new(), EPOCH, mtu).is_ok());
    }
}

#[test]
fn writer_emits_exact_big_endian_header_and_independent_direction_sequences() {
    let mut upstream = PacketWriter::new(Vec::new(), EPOCH, 1280).unwrap();
    let mut downstream = PacketWriter::new(Vec::new(), EPOCH, 1280).unwrap();
    upstream.write_packet(&[0x45]).unwrap();
    upstream.write_packet(b"second").unwrap();
    downstream.write_packet(&[0x60]).unwrap();
    assert_eq!(
        &upstream.output[..25],
        &[
            b'S', b'W', b'I', b'P', 1, 0, 0, 1, 1, 2, 3, 4, 5, 6, 7, 8, 0, 0, 0, 0, 0, 0, 0, 1,
            0x45,
        ]
    );
    assert_eq!(&upstream.output[25..], frame(EPOCH, 2, b"second"));
    assert_eq!(downstream.output, frame(EPOCH, 1, &[0x60]));
}

#[test]
fn fragmented_reads_and_interrupted_calls_preserve_concatenated_packets() {
    let payload = (0..9000).map(|n| (n % 251) as u8).collect::<Vec<_>>();
    for chunk in [1, 3, 23, 24, 4096] {
        let mut wire = frame(EPOCH, 1, &[0]);
        wire.extend(frame(EPOCH, 2, &payload));
        let mut reader = PacketReader::new(FragmentedRead::new(wire, chunk), EPOCH, 9000).unwrap();
        assert_eq!(reader.read_packet().unwrap(), Some(vec![0]));
        assert_eq!(reader.read_packet().unwrap(), Some(payload.clone()));
        assert_eq!(reader.read_packet().unwrap(), None);
        let calls = reader.input.calls;
        assert_eq!(reader.read_packet().unwrap(), None);
        assert_eq!(reader.input.calls, calls, "clean EOF must be terminal");
    }
}

#[test]
fn invalid_headers_fail_before_body_reads_and_permanently_poison_reader() {
    let valid = frame(EPOCH, 1, b"body-must-not-be-read");
    for changed in [0, 4, 5, 6, 7, 8, 16, 23] {
        let mut wire = valid.clone();
        match changed {
            6 => wire[6..8].copy_from_slice(&9001u16.to_be_bytes()),
            7 => wire[6..8].copy_from_slice(&0u16.to_be_bytes()),
            23 => wire[23] = 0,
            index => wire[index] ^= 0xff,
        }
        let mut input = FragmentedRead::new(wire, 3);
        input.fail_at = Some(24);
        let mut reader = PacketReader::new(input, EPOCH, 9000).unwrap();
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(reader.input.bytes.position(), 24);
        let calls = reader.input.calls;
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
        assert_eq!(
            reader.input.calls, calls,
            "poisoned reader must not resynchronize"
        );
    }
}

#[test]
fn zero_or_previous_launch_epoch_cannot_read_a_body() {
    for epoch in [0, EPOCH - 1, EPOCH + 1] {
        let mut input = FragmentedRead::new(frame(epoch, 1, b"packet"), 5);
        input.fail_at = Some(24);
        let mut reader = PacketReader::new(input, EPOCH, 1280).unwrap();
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(reader.input.bytes.position(), 24);
    }
}

#[test]
fn replay_or_skipped_sequence_cannot_resynchronize_to_later_valid_frame() {
    for sequence in [0, 1, 3] {
        let first = frame(EPOCH, 1, b"first");
        let mut wire = first.clone();
        wire.extend(frame(EPOCH, sequence, b"replay"));
        wire.extend(frame(EPOCH, 2, b"valid-but-unreachable"));
        let mut reader = PacketReader::new(Cursor::new(wire), EPOCH, 1280).unwrap();
        assert_eq!(reader.read_packet().unwrap(), Some(b"first".to_vec()));
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(reader.input.position() as usize, first.len() + 24);
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
        assert_eq!(reader.input.position() as usize, first.len() + 24);
    }
}

#[test]
fn eof_is_clean_only_before_any_header_byte() {
    let wire = frame(EPOCH, 1, b"payload");
    let mut empty = PacketReader::new(Cursor::new([]), EPOCH, 1280).unwrap();
    assert_eq!(empty.read_packet().unwrap(), None);
    for end in 1..24 {
        let mut reader = PacketReader::new(Cursor::new(&wire[..end]), EPOCH, 1280).unwrap();
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::UnexpectedEof
        );
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
    }
}

#[test]
fn every_truncated_body_fails_without_advancing_or_reusing_sequence() {
    let wire = frame(EPOCH, 1, b"payload");
    for end in 24..wire.len() {
        let mut reader = PacketReader::new(Cursor::new(&wire[..end]), EPOCH, 1280).unwrap();
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::UnexpectedEof
        );
        assert_eq!(reader.next_sequence, Some(1));
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
    }
}

#[test]
fn io_failure_before_header_or_during_frame_permanently_poison_reader() {
    for fail_at in [0, 7, 24, 27] {
        let mut input = FragmentedRead::new(frame(EPOCH, 1, b"payload"), 2);
        input.fail_at = Some(fail_at);
        let mut reader = PacketReader::new(input, EPOCH, 1280).unwrap();
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::PermissionDenied
        );
        assert_eq!(reader.input.bytes.position(), fail_at);
        let calls = reader.input.calls;
        assert_eq!(
            reader.read_packet().unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
        assert_eq!(reader.input.calls, calls);
        assert_eq!(reader.next_sequence, Some(1));
    }
}

#[test]
fn partial_and_interrupted_writes_emit_complete_frames_without_duplicate_bytes() {
    for chunk in [1, 3, 23, 4096] {
        let mut writer = PacketWriter::new(PartialWrite::new(chunk), EPOCH, 1280).unwrap();
        writer.write_packet(b"first").unwrap();
        writer.write_packet(&vec![0xab; 1280]).unwrap();
        let mut expected = frame(EPOCH, 1, b"first");
        expected.extend(frame(EPOCH, 2, &vec![0xab; 1280]));
        assert_eq!(writer.output.bytes, expected);
        assert_eq!(writer.next_sequence, Some(3));
    }
}

#[test]
fn failed_or_zero_writes_poison_without_appending_another_packet() {
    for fail_at in [0, 7, 24, 27] {
        for zero in [false, true] {
            let mut output = PartialWrite::new(3);
            if zero {
                output.zero_at = Some(fail_at);
            } else {
                output.fail_at = Some(fail_at);
            }
            let mut writer = PacketWriter::new(output, EPOCH, 1280).unwrap();
            assert_eq!(
                writer.write_packet(b"payload").unwrap_err().kind(),
                if zero {
                    io::ErrorKind::WriteZero
                } else {
                    io::ErrorKind::PermissionDenied
                }
            );
            assert_eq!(writer.output.bytes, frame(EPOCH, 1, b"payload")[..fail_at]);
            let calls = writer.output.calls;
            assert_eq!(
                writer.write_packet(b"next").unwrap_err().kind(),
                io::ErrorKind::BrokenPipe
            );
            assert_eq!(writer.output.calls, calls);
            assert_eq!(writer.next_sequence, Some(1));
        }
    }
}

#[test]
fn invalid_outbound_lengths_write_nothing_and_preserve_first_sequence() {
    let mut writer = PacketWriter::new(Vec::new(), EPOCH, 1280).unwrap();
    for payload in [vec![], vec![0; 1281]] {
        assert_eq!(
            writer.write_packet(&payload).unwrap_err().kind(),
            io::ErrorKind::InvalidInput
        );
        assert!(writer.output.is_empty());
        assert_eq!(writer.next_sequence, Some(1));
    }
    writer.write_packet(b"valid").unwrap();
    assert_eq!(writer.output, frame(EPOCH, 1, b"valid"));
}

#[test]
fn sequence_maximum_is_last_valid_packet_and_never_wraps() {
    let mut writer = PacketWriter::new(Vec::new(), EPOCH, 1280).unwrap();
    writer.next_sequence = Some(u64::MAX);
    writer.write_packet(b"last").unwrap();
    assert_eq!(writer.output, frame(EPOCH, u64::MAX, b"last"));
    assert_eq!(writer.next_sequence, None);
    let written = writer.output.clone();
    assert_eq!(
        writer.write_packet(b"wrap").unwrap_err().kind(),
        io::ErrorKind::ConnectionAborted
    );
    assert_eq!(writer.output, written);
    assert_eq!(
        writer.write_packet(b"wrap").unwrap_err().kind(),
        io::ErrorKind::BrokenPipe
    );

    let mut wire = frame(EPOCH, u64::MAX, b"last");
    wire.extend(frame(EPOCH, 0, b"wrap"));
    let mut reader = PacketReader::new(Cursor::new(wire), EPOCH, 1280).unwrap();
    reader.next_sequence = Some(u64::MAX);
    assert_eq!(reader.read_packet().unwrap(), Some(b"last".to_vec()));
    assert_eq!(
        reader.read_packet().unwrap_err().kind(),
        io::ErrorKind::ConnectionAborted
    );
    assert_eq!(reader.input.position(), 28);
    assert_eq!(
        reader.read_packet().unwrap_err().kind(),
        io::ErrorKind::BrokenPipe
    );
}

use swirl_protocol::vision::{
    Command, Decoder, Encoder, Error, HEADER_LEN, MAX_FRAME_LEN, MAX_PART_LEN, UUID_LEN,
    request_addons,
};

const UUID: [u8; 16] = [
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
];

struct Vector {
    name: &'static str,
    first: bool,
    command: Command,
    content: Vec<u8>,
    padding: Vec<u8>,
    wire: Vec<u8>,
}

fn hex(text: &str) -> Vec<u8> {
    assert_eq!(text.len() % 2, 0);
    text.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| {
            u8::from_str_radix(std::str::from_utf8(pair).expect("ASCII hex"), 16)
                .expect("valid hex")
        })
        .collect()
}

fn vectors() -> Vec<Vector> {
    include_str!("fixtures/vision-v1.txt")
        .lines()
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(|line| {
            let fields: Vec<_> = line.split('|').collect();
            assert_eq!(fields.len(), 6);
            Vector {
                name: fields[0],
                first: match fields[1] {
                    "1" => true,
                    "0" => false,
                    _ => panic!("invalid first marker"),
                },
                command: Command::try_from(fields[2].parse::<u8>().expect("command byte"))
                    .expect("supported command"),
                content: hex(fields[3]),
                padding: hex(fields[4]),
                wire: hex(fields[5]),
            }
        })
        .collect()
}

fn vector(name: &str) -> Vector {
    vectors()
        .into_iter()
        .find(|item| item.name == name)
        .expect("named independent vector")
}

fn prime(decoder: &mut Decoder) {
    let initial = vector("first_empty_continue").wire;
    let step = decoder.decode(&initial).expect("independent first frame");
    assert_eq!(step.consumed, initial.len());
    assert_eq!(step.boundary, Some(Command::Continue));
    assert!(step.payload.is_empty());
}

fn accept_chunks(decoder: &mut Decoder, bytes: &[u8], sizes: &[usize]) -> (Vec<u8>, Vec<Command>) {
    let mut payload = Vec::new();
    let mut boundaries = Vec::new();
    let mut position = 0;
    for &size in sizes {
        let end = position + size;
        assert!(end <= bytes.len());
        while position < end {
            let step = decoder.decode(&bytes[position..end]).expect("valid frame");
            assert!(step.consumed > 0, "nonempty input must make progress");
            assert!(step.consumed <= end - position);
            payload.extend_from_slice(step.payload);
            if let Some(command) = step.boundary {
                boundaries.push(command);
            }
            position += step.consumed;
        }
    }
    assert_eq!(position, bytes.len());
    (payload, boundaries)
}

#[test]
fn encoder_matches_ten_independent_python_wire_vectors() {
    let vectors = vectors();
    assert_eq!(vectors.len(), 10);
    for item in vectors {
        let mut encoder = Encoder::new(UUID);
        if !item.first {
            assert_eq!(
                encoder.frame(Command::Continue, b"", b"").unwrap(),
                vector("first_empty_continue").wire
            );
        }
        assert_eq!(
            encoder
                .frame(item.command, &item.content, &item.padding)
                .unwrap(),
            item.wire,
            "{}",
            item.name
        );
    }
}

#[test]
fn decoder_accepts_independent_vectors_at_every_split_and_bytewise() {
    for item in vectors() {
        for cut in 0..=item.wire.len() {
            let mut decoder = Decoder::new(UUID);
            if !item.first {
                prime(&mut decoder);
            }
            let (payload, boundaries) =
                accept_chunks(&mut decoder, &item.wire, &[cut, item.wire.len() - cut]);
            assert_eq!(payload, item.content, "{} split {cut}", item.name);
            assert_eq!(boundaries, [item.command], "{} split {cut}", item.name);
            decoder.finish().unwrap();
        }
        let mut decoder = Decoder::new(UUID);
        if !item.first {
            prime(&mut decoder);
        }
        let (payload, boundaries) =
            accept_chunks(&mut decoder, &item.wire, &vec![1; item.wire.len()]);
        assert_eq!(payload, item.content, "{} bytewise", item.name);
        assert_eq!(boundaries, [item.command], "{} bytewise", item.name);
        decoder.finish().unwrap();
    }
}

#[test]
fn several_frames_in_one_read_keep_boundaries_and_payload_order() {
    let a = vector("first_continue");
    let b = vector("later_continue");
    let c = vector("later_end");
    let wire = [a.wire, b.wire, c.wire].concat();
    let content = [a.content, b.content, c.content].concat();
    for chunk_size in 1..=wire.len() {
        let sizes: Vec<_> = wire.chunks(chunk_size).map(<[u8]>::len).collect();
        let mut decoder = Decoder::new(UUID);
        let (actual, boundaries) = accept_chunks(&mut decoder, &wire, &sizes);
        assert_eq!(actual, content, "chunk size {chunk_size}");
        assert_eq!(
            boundaries,
            [Command::Continue, Command::Continue, Command::EndPadding]
        );
        decoder.finish().unwrap();
    }
}

#[test]
fn terminal_boundary_does_not_consume_or_forward_pending_transport_bytes() {
    for name in ["first_end", "first_direct_request"] {
        let item = vector(name);
        let tail = b"pending bytes owned by the transport adapter";
        let wire = [item.wire.as_slice(), tail.as_slice()].concat();
        let mut decoder = Decoder::new(UUID);
        let step = decoder.decode(&wire).unwrap();
        assert_eq!(step.payload, item.content);
        assert_eq!(step.boundary, Some(item.command));
        assert_eq!(step.consumed, item.wire.len());
        let consumed = step.consumed;
        assert_eq!(&wire[consumed..], tail);
        assert_eq!(
            decoder.decode(&wire[consumed..]).err(),
            Some(Error::AfterTerminal)
        );
        assert_eq!(
            decoder.decode(b"anything").err(),
            Some(Error::AfterTerminal)
        );
        assert_eq!(decoder.finish(), Err(Error::AfterTerminal));
    }
}

#[test]
fn direct_is_only_an_event_after_all_content_and_padding() {
    let item = vector("first_direct_request");
    let mut decoder = Decoder::new(UUID);
    let before_last = decoder.decode(&item.wire[..item.wire.len() - 1]).unwrap();
    assert_eq!(before_last.payload, item.content);
    assert_eq!(before_last.boundary, None);
    let last = decoder.decode(&item.wire[item.wire.len() - 1..]).unwrap();
    assert!(last.payload.is_empty());
    assert_eq!(last.boundary, Some(Command::DirectRequested));
    assert_eq!(last.consumed, 1);
    // No TLS-version argument, stream extraction or raw-copy permission exists.
    decoder.finish().unwrap();
}

#[test]
fn first_uuid_is_mandatory_and_all_mismatch_positions_poison_decoder() {
    let reference = vector("first_continue").wire;
    for index in 0..UUID_LEN {
        let mut wrong = reference.clone();
        wrong[index] ^= 0x01;
        for split in 0..UUID_LEN {
            let mut decoder = Decoder::new(UUID);
            let first = decoder.decode(&wrong[..split]).unwrap();
            assert!(first.payload.is_empty());
            assert_eq!(first.boundary, None);
            assert_eq!(
                decoder.decode(&wrong[split..]).err(),
                Some(Error::UuidMismatch)
            );
            assert_eq!(decoder.decode(&reference).err(), Some(Error::UuidMismatch));
            assert_eq!(decoder.finish(), Err(Error::UuidMismatch));
        }
    }
    let missing = vector("later_continue").wire;
    let mut decoder = Decoder::new(UUID);
    assert!(decoder.decode(&missing).unwrap().payload.is_empty());
    assert_eq!(decoder.finish(), Err(Error::TruncatedUuid));
}

#[test]
fn every_unknown_command_is_rejected_without_returning_payload() {
    let reference = vector("first_continue").wire;
    for unknown in 3..=u8::MAX {
        let mut wrong = reference.clone();
        wrong[UUID_LEN] = unknown;
        let mut decoder = Decoder::new(UUID);
        assert_eq!(decoder.decode(&wrong).err(), Some(Error::UnknownCommand));
        assert_eq!(
            decoder.decode(&reference).err(),
            Some(Error::UnknownCommand)
        );
        assert_eq!(decoder.finish(), Err(Error::UnknownCommand));
        assert_eq!(Command::try_from(unknown), Err(Error::UnknownCommand));
    }
}

#[test]
fn uuid_and_header_eof_are_distinguished_at_every_partial_offset() {
    let reference = vector("first_continue").wire;
    for size in 1..UUID_LEN + HEADER_LEN {
        let mut decoder = Decoder::new(UUID);
        let step = decoder.decode(&reference[..size]).unwrap();
        assert!(step.payload.is_empty());
        assert_eq!(step.boundary, None);
        let expected = if size < UUID_LEN {
            Error::TruncatedUuid
        } else {
            Error::TruncatedHeader
        };
        assert_eq!(decoder.finish(), Err(expected), "offset {size}");
        assert_eq!(decoder.decode(&reference[size..]).err(), Some(expected));
        assert_eq!(decoder.finish(), Err(expected));
    }
}

#[test]
fn content_and_padding_eof_are_distinguished_at_every_partial_offset() {
    for name in ["first_continue", "first_end", "first_direct_request"] {
        let item = vector(name);
        let content_start = UUID_LEN + HEADER_LEN;
        let padding_start = content_start + item.content.len();
        for size in content_start..item.wire.len() {
            let mut decoder = Decoder::new(UUID);
            let step = decoder.decode(&item.wire[..size]).unwrap();
            let content_received = (size - content_start).min(item.content.len());
            assert_eq!(step.payload, &item.content[..content_received]);
            assert_eq!(step.boundary, None);
            let expected = if size < padding_start {
                Error::TruncatedContent
            } else {
                Error::TruncatedPadding
            };
            assert_eq!(decoder.finish(), Err(expected), "{name} offset {size}");
            assert_eq!(decoder.decode(&item.wire[size..]).err(), Some(expected));
        }
    }
}

#[test]
fn later_partial_headers_are_not_mistaken_for_clean_eof() {
    let item = vector("later_continue");
    for size in 1..HEADER_LEN {
        let mut decoder = Decoder::new(UUID);
        prime(&mut decoder);
        assert!(
            decoder
                .decode(&item.wire[..size])
                .unwrap()
                .payload
                .is_empty()
        );
        assert_eq!(decoder.finish(), Err(Error::TruncatedHeader));
    }
}

#[test]
fn empty_and_complete_frame_eof_are_legal_and_idempotent() {
    let mut decoder = Decoder::new(UUID);
    decoder.finish().unwrap();
    decoder.finish().unwrap();
    assert_eq!(decoder.decode(&[]).err(), Some(Error::AfterEof));
    for name in [
        "first_empty_continue",
        "first_continue",
        "first_end",
        "first_direct_request",
    ] {
        let item = vector(name);
        let mut decoder = Decoder::new(UUID);
        let step = decoder.decode(&item.wire).unwrap();
        assert_eq!(step.boundary, Some(item.command));
        decoder.finish().unwrap();
        decoder.finish().unwrap();
        assert_eq!(decoder.decode(b"more").err(), Some(Error::AfterEof));
        assert_eq!(decoder.finish(), Err(Error::AfterEof));
    }
}

#[test]
fn empty_decode_is_not_an_eof_signal() {
    let item = vector("first_continue");
    let mut decoder = Decoder::new(UUID);
    for part in item.wire.chunks(1) {
        let empty = decoder.decode(b"").unwrap();
        assert_eq!(empty.consumed, 0);
        assert!(empty.payload.is_empty());
        assert_eq!(empty.boundary, None);
        assert_eq!(decoder.decode(part).unwrap().consumed, 1);
    }
    let empty = decoder.decode(b"").unwrap();
    assert_eq!(empty.consumed, 0);
    assert_eq!(empty.boundary, None);
    decoder.finish().unwrap();
}

#[test]
fn encoder_enforces_both_wire_limits_before_changing_first_frame_state() {
    let too_large = vec![0u8; MAX_PART_LEN + 1];
    let mut encoder = Encoder::new(UUID);
    assert_eq!(
        encoder.frame(Command::EndPadding, &too_large, b""),
        Err(Error::ContentTooLarge)
    );
    assert_eq!(
        encoder.frame(Command::DirectRequested, b"", &too_large),
        Err(Error::PaddingTooLarge)
    );
    let item = vector("first_continue");
    assert_eq!(
        encoder
            .frame(item.command, &item.content, &item.padding)
            .unwrap(),
        item.wire
    );
    assert_eq!(
        encoder.frame(Command::Continue, &too_large, b""),
        Err(Error::ContentTooLarge)
    );
    let later = vector("later_end");
    assert_eq!(
        encoder
            .frame(later.command, &later.content, &later.padding)
            .unwrap(),
        later.wire
    );
}

#[test]
fn maximum_content_and_padding_are_accepted_without_decoder_buffering() {
    let content = vec![0x35; MAX_PART_LEN];
    let padding = vec![0xca; MAX_PART_LEN];
    let mut encoder = Encoder::new(UUID);
    let wire = encoder
        .frame(Command::Continue, &content, &padding)
        .unwrap();
    assert_eq!(wire.len(), MAX_FRAME_LEN);
    assert_eq!(
        &wire[UUID_LEN..UUID_LEN + HEADER_LEN],
        &[0, 255, 255, 255, 255]
    );
    let mut decoder = Decoder::new(UUID);
    let mut received = 0;
    let mut events = Vec::new();
    for chunk in wire.chunks(997) {
        let step = decoder.decode(chunk).unwrap();
        assert_eq!(step.consumed, chunk.len());
        assert!(step.payload.iter().all(|&byte| byte == 0x35));
        // Payload is borrowed directly from the current input, including on large frames.
        if !step.payload.is_empty() {
            let start = chunk.as_ptr() as usize;
            let payload_start = step.payload.as_ptr() as usize;
            assert!(payload_start >= start);
            assert!(payload_start + step.payload.len() <= start + chunk.len());
        }
        received += step.payload.len();
        if let Some(event) = step.boundary {
            events.push(event);
        }
    }
    assert_eq!(received, MAX_PART_LEN);
    assert_eq!(events, [Command::Continue]);
    decoder.finish().unwrap();
}

#[test]
fn advertised_maximum_lengths_do_not_require_the_body_to_be_buffered() {
    let mut header = UUID.to_vec();
    header.extend_from_slice(&[0, 255, 255, 255, 255]);
    let mut decoder = Decoder::new(UUID);
    let step = decoder.decode(&header).unwrap();
    assert_eq!(step.consumed, header.len());
    assert!(step.payload.is_empty());
    assert_eq!(step.boundary, None);
    assert_eq!(decoder.finish(), Err(Error::TruncatedContent));

    header[UUID_LEN + 1] = 0;
    header[UUID_LEN + 2] = 0;
    let mut decoder = Decoder::new(UUID);
    assert!(decoder.decode(&header).unwrap().payload.is_empty());
    assert_eq!(decoder.finish(), Err(Error::TruncatedPadding));
}

#[test]
fn encoders_reject_frames_after_either_terminal_command() {
    for command in [Command::EndPadding, Command::DirectRequested] {
        let mut encoder = Encoder::new(UUID);
        encoder.frame(command, b"last", b"pad").unwrap();
        for next in [
            Command::Continue,
            Command::EndPadding,
            Command::DirectRequested,
        ] {
            assert_eq!(
                encoder.frame(next, b"no", b"more"),
                Err(Error::AfterTerminal)
            );
        }
    }
}

#[test]
fn directions_keep_independent_uuid_and_terminal_state() {
    let mut uplink = (Encoder::new(UUID), Decoder::new(UUID));
    let mut downlink = (Encoder::new(UUID), Decoder::new(UUID));
    let up_first = vector("first_end");
    assert_eq!(
        uplink
            .0
            .frame(up_first.command, &up_first.content, &up_first.padding)
            .unwrap(),
        up_first.wire
    );
    assert_eq!(
        uplink.1.decode(&up_first.wire).unwrap().boundary,
        Some(Command::EndPadding)
    );
    assert_eq!(
        uplink.0.frame(Command::Continue, b"", b""),
        Err(Error::AfterTerminal)
    );
    // The opposite direction still starts with its own complete UUID and can continue.
    let down_first = vector("first_continue");
    assert_eq!(
        downlink
            .0
            .frame(down_first.command, &down_first.content, &down_first.padding)
            .unwrap(),
        down_first.wire
    );
    assert_eq!(
        downlink.1.decode(&down_first.wire).unwrap().boundary,
        Some(Command::Continue)
    );
    let down_last = vector("later_direct_request");
    assert_eq!(
        downlink
            .0
            .frame(down_last.command, &down_last.content, &down_last.padding)
            .unwrap(),
        down_last.wire
    );
    assert_eq!(
        downlink.1.decode(&down_last.wire).unwrap().boundary,
        Some(Command::DirectRequested)
    );
    uplink.1.finish().unwrap();
    downlink.1.finish().unwrap();
}

#[test]
fn payload_header_lookalikes_are_never_reinterpreted_as_framing() {
    let content = [UUID.as_slice(), &[2, 0, 0, 0, 0], UUID.as_slice()].concat();
    let mut wire = UUID.to_vec();
    // Independent layout: one Continue frame, length 37, zero padding.
    wire.extend_from_slice(&[0, 0, 37, 0, 0]);
    wire.extend_from_slice(&content);
    let mut decoder = Decoder::new(UUID);
    let (actual, events) = accept_chunks(&mut decoder, &wire, &vec![1; wire.len()]);
    assert_eq!(actual, content);
    assert_eq!(events, [Command::Continue]);
    decoder.finish().unwrap();
}

#[test]
fn padding_only_frames_make_bounded_progress_without_payload_or_extra_events() {
    let first = vector("first_padding_only");
    let later = vector("later_empty_continue");
    let mut wire = first.wire.clone();
    for _ in 0..512 {
        wire.extend_from_slice(&later.wire);
    }
    let mut decoder = Decoder::new(UUID);
    let mut position = 0;
    let mut frames = 0;
    while position < wire.len() {
        let step = decoder.decode(&wire[position..]).unwrap();
        assert!(step.payload.is_empty());
        assert_eq!(step.boundary, Some(Command::Continue));
        assert_eq!(
            step.consumed,
            if frames == 0 {
                first.wire.len()
            } else {
                HEADER_LEN
            }
        );
        position += step.consumed;
        frames += 1;
    }
    assert_eq!(frames, 513);
    decoder.finish().unwrap();
}

#[test]
fn request_addons_match_independent_protobuf_vectors() {
    let mut count = 0;
    for line in include_str!("fixtures/flow-v1.txt").lines() {
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<_> = line.split('|').collect();
        assert_eq!(fields.len(), 4);
        let flow = match fields[1] {
            "none" => None,
            "some" => Some(fields[2]),
            _ => panic!("invalid flow marker"),
        };
        assert_eq!(
            request_addons(flow).unwrap(),
            hex(fields[3]),
            "{}",
            fields[0]
        );
        count += 1;
    }
    assert_eq!(count, 3);
    assert_eq!(request_addons(Some("xtls-rprx-vision")).unwrap().len(), 19);
}

#[test]
fn unknown_flows_cannot_silently_become_empty_addons() {
    for unknown in [
        "xtls-rprx-vision-udp443",
        "xtls-rprx-direct",
        "XTLS-RPRX-VISION",
        " xtls-rprx-vision",
        "xtls-rprx-vision ",
        "xtls-rprx-vision\0",
        " ",
        "none",
        "vision",
        "synthetic-secret-unknown-flow",
    ] {
        let error = request_addons(Some(unknown)).unwrap_err();
        assert_eq!(error, Error::UnsupportedFlow);
        assert!(!error.to_string().contains(unknown));
    }
}

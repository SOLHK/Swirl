use swirl_protocol::vision::tls::{Direction, Eligibility, Ineligible, Inspection};

const CLIENT: Direction = Direction::ClientToServer;
const SERVER: Direction = Direction::ServerToClient;

fn extension(kind: u16, value: &[u8]) -> Vec<u8> {
    [
        kind.to_be_bytes().as_slice(),
        &(value.len() as u16).to_be_bytes(),
        value,
    ]
    .concat()
}

fn hello(direction: Direction, suites: &[u16], extensions: &[u8], session: &[u8]) -> Vec<u8> {
    let mut body = vec![3, 3];
    body.extend([0x5a; 32]);
    body.push(session.len() as u8);
    body.extend(session);
    if direction == CLIENT {
        body.extend(((suites.len() * 2) as u16).to_be_bytes());
        for suite in suites {
            body.extend(suite.to_be_bytes());
        }
        body.extend([1, 0]);
    } else {
        assert_eq!(suites.len(), 1);
        body.extend(suites[0].to_be_bytes());
        body.push(0);
    }
    body.extend((extensions.len() as u16).to_be_bytes());
    body.extend(extensions);
    let mut message = vec![if direction == CLIENT { 1 } else { 2 }];
    message.extend(&(body.len() as u32).to_be_bytes()[1..]);
    message.extend(body);
    message
}

fn record(kind: u8, body: &[u8]) -> Vec<u8> {
    [
        &[kind, 3, 3],
        (body.len() as u16).to_be_bytes().as_slice(),
        body,
    ]
    .concat()
}

fn tls13(direction: Direction, suite: u16) -> Vec<u8> {
    hello(
        direction,
        &[suite],
        &extension(
            43,
            if direction == CLIENT {
                &[2, 3, 4]
            } else {
                &[3, 4]
            },
        ),
        &[0x31; 32],
    )
}

fn inspect(client: &[u8], server: &[u8]) -> Inspection {
    let mut state = Inspection::new();
    state.observe(CLIENT, &record(22, client));
    state.observe(SERVER, &record(22, server));
    state
}

#[test]
fn both_hellos_work_at_every_network_split_and_one_byte_records() {
    let client = tls13(CLIENT, 0x1301);
    let server = tls13(SERVER, 0x1301);
    for record_size in [1, 2, 3, 7, 16, 67, 16384] {
        let client_wire: Vec<_> = client
            .chunks(record_size)
            .flat_map(|part| record(22, part))
            .collect();
        let server_wire: Vec<_> = server
            .chunks(record_size)
            .flat_map(|part| record(22, part))
            .collect();
        for split in 0..=client_wire.len().max(server_wire.len()) {
            let mut state = Inspection::new();
            let client_split = split.min(client_wire.len());
            let server_split = split.min(server_wire.len());
            state.observe(CLIENT, &client_wire[..client_split]);
            state.observe(SERVER, &server_wire[..server_split]);
            state.observe(CLIENT, &client_wire[client_split..]);
            state.observe(SERVER, &server_wire[server_split..]);
            assert_eq!(
                state.eligibility(),
                Eligibility::Candidate {
                    cipher_suite: 0x1301
                }
            );
            assert!(state.at_record_boundary(CLIENT));
            assert!(state.at_record_boundary(SERVER));
            assert_eq!(state.buffered_bytes(), 0);
        }
    }
}

#[test]
fn randomized_bidirectional_slices_preserve_hello_and_record_state() {
    let mut client = record(22, &tls13(CLIENT, 0x1303));
    client.extend(record(20, &[1]));
    client.extend(record(23, &[0x5d; 327]));
    let mut server = record(22, &tls13(SERVER, 0x1303));
    server.extend(record(23, &[0xad; 415]));
    for seed in 0..64u32 {
        let mut random = seed;
        let mut state = Inspection::new();
        let mut positions = [0, 0];
        while positions[0] < client.len() || positions[1] < server.len() {
            for (index, direction, wire) in [(0, CLIENT, &client), (1, SERVER, &server)] {
                random = random.wrapping_mul(1664525).wrapping_add(1013904223);
                let end = (positions[index] + 1 + (random % 53) as usize).min(wire.len());
                state.observe(direction, &wire[positions[index]..end]);
                positions[index] = end;
            }
        }
        assert_eq!(
            state.eligibility(),
            Eligibility::Candidate {
                cipher_suite: 0x1303
            }
        );
        for direction in [CLIENT, SERVER] {
            assert!(state.at_record_boundary(direction));
            assert!(state.application_record_seen(direction));
        }
    }
}

#[test]
fn supported_suites_require_exact_client_offer_and_reject_short_tag_cipher() {
    for suite in 0x1301..=0x1304 {
        assert_eq!(
            inspect(&tls13(CLIENT, suite), &tls13(SERVER, suite)).eligibility(),
            Eligibility::Candidate {
                cipher_suite: suite
            }
        );
    }
    assert_eq!(
        inspect(&tls13(CLIENT, 0x1301), &tls13(SERVER, 0x1302)).eligibility(),
        Eligibility::Ineligible(Ineligible::CipherNotOffered)
    );
    for suite in [0x1305, 0x1306, 0xc02f, 0xffff] {
        assert_eq!(
            inspect(&tls13(CLIENT, suite), &tls13(SERVER, suite)).eligibility(),
            Eligibility::Ineligible(Ineligible::CipherUnsupported)
        );
    }
}

#[test]
fn tls12_and_missing_client_tls13_offer_are_not_candidates() {
    let legacy = hello(CLIENT, &[0x1301], &[], &[0x31; 32]);
    for (client, server) in [
        (legacy.clone(), hello(SERVER, &[0xc02f], &[], &[0x31; 32])),
        (legacy, tls13(SERVER, 0x1301)),
        (
            tls13(CLIENT, 0x1301),
            hello(SERVER, &[0x1301], &[], &[0x31; 32]),
        ),
    ] {
        assert_eq!(
            inspect(&client, &server).eligibility(),
            Eligibility::Ineligible(Ineligible::Version)
        );
    }
}

#[test]
fn random_and_unknown_extension_patterns_cannot_claim_tls13() {
    let fake = extension(0xface, &[0, 43, 0, 2, 3, 4]);
    let server = hello(SERVER, &[0x1301], &fake, &[0x31; 32]);
    assert_eq!(
        inspect(&tls13(CLIENT, 0x1301), &server).eligibility(),
        Eligibility::Ineligible(Ineligible::Version)
    );
    let mut state = Inspection::new();
    state.observe(CLIENT, b"GET / HTTP/1.1\r\n");
    state.observe(CLIENT, &record(22, &tls13(CLIENT, 0x1301)));
    state.observe(SERVER, &record(22, &tls13(SERVER, 0x1301)));
    assert_eq!(
        state.eligibility(),
        Eligibility::Ineligible(Ineligible::NotTls)
    );
    assert_eq!(state.buffered_bytes(), 0);
}

#[test]
fn duplicate_extensions_and_trailing_or_short_lengths_fail_closed() {
    let normal = extension(43, &[3, 4]);
    let mut malformed = vec![
        normal.repeat(2),
        extension(43, &[3]),
        extension(43, &[3, 4, 0]),
    ];
    let mut short = normal.clone();
    short[3] += 1;
    malformed.push(short);
    malformed.push([normal, vec![0]].concat());
    for extensions in malformed {
        let server = hello(SERVER, &[0x1301], &extensions, &[0x31; 32]);
        assert!(matches!(
            inspect(&tls13(CLIENT, 0x1301), &server).eligibility(),
            Eligibility::Ineligible(_)
        ));
    }
    for versions in [&[][..], &[0], &[1, 3], &[2, 3, 4, 0], &[3, 3, 4, 3]] {
        let client = hello(CLIENT, &[0x1301], &extension(43, versions), &[0x31; 32]);
        assert_eq!(
            inspect(&client, &tls13(SERVER, 0x1301)).eligibility(),
            Eligibility::Ineligible(Ineligible::Malformed)
        );
    }
}

#[test]
fn session_id_echo_and_tls13_legacy_fields_are_checked() {
    let wrong_id = hello(SERVER, &[0x1301], &extension(43, &[3, 4]), &[0x32; 32]);
    assert_eq!(
        inspect(&tls13(CLIENT, 0x1301), &wrong_id).eligibility(),
        Eligibility::Ineligible(Ineligible::SessionIdMismatch)
    );
    for index in [5, 4 + 2 + 32 + 1 + 32 + 2] {
        let mut server = tls13(SERVER, 0x1301);
        server[index] = 2;
        assert!(matches!(
            inspect(&tls13(CLIENT, 0x1301), &server).eligibility(),
            Eligibility::Ineligible(_)
        ));
    }
    let oversized_id = hello(CLIENT, &[0x1301], &extension(43, &[2, 3, 4]), &[0x31; 33]);
    assert_eq!(
        inspect(&oversized_id, &tls13(SERVER, 0x1301)).eligibility(),
        Eligibility::Ineligible(Ineligible::Malformed)
    );
}

#[test]
fn hello_retry_request_never_becomes_a_final_server_hello() {
    let mut retry = tls13(SERVER, 0x1301);
    let random = [
        0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65, 0xb8,
        0x91, 0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2, 0xc8, 0xa8,
        0x33, 0x9c,
    ];
    retry[6..38].copy_from_slice(&random);
    let mut state = inspect(&tls13(CLIENT, 0x1301), &retry);
    state.observe(SERVER, &record(22, &tls13(SERVER, 0x1301)));
    assert_eq!(
        state.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
}

fn retry_hello(direction: Direction, group: u16, retry: bool, cookie: Option<&[u8]>) -> Vec<u8> {
    retry_hello_with_extra(direction, group, retry, cookie, &[])
}

fn retry_hello_with_extra(
    direction: Direction,
    group: u16,
    retry: bool,
    cookie: Option<&[u8]>,
    extra: &[u8],
) -> Vec<u8> {
    let mut extensions = extension(
        43,
        if direction == CLIENT {
            &[2, 3, 4]
        } else {
            &[3, 4]
        },
    );
    if direction == CLIENT {
        extensions.extend(extension(10, &[0, 4, 0, 29, 0, 23]));
    }
    let share = if retry {
        group.to_be_bytes().to_vec()
    } else {
        let key = vec![0x25; if group == 29 { 32 } else { 65 }];
        let entry = [
            group.to_be_bytes().as_slice(),
            &(key.len() as u16).to_be_bytes(),
            &key,
        ]
        .concat();
        if direction == CLIENT {
            [(entry.len() as u16).to_be_bytes().as_slice(), &entry].concat()
        } else {
            entry
        }
    };
    extensions.extend(extension(51, &share));
    if let Some(cookie) = cookie {
        extensions.extend(extension(
            44,
            &[(cookie.len() as u16).to_be_bytes().as_slice(), cookie].concat(),
        ));
    }
    extensions.extend(extra);
    let mut result = hello(direction, &[0x1301], &extensions, &[0x31; 32]);
    if retry {
        result[6..38].copy_from_slice(&[
            0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65,
            0xb8, 0x91, 0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2,
            0xc8, 0xa8, 0x33, 0x9c,
        ]);
    }
    result
}

fn requested_retry(cookie: Option<&[u8]>) -> Inspection {
    inspect(
        &retry_hello(CLIENT, 29, false, None),
        &retry_hello(SERVER, 23, true, cookie),
    )
}

#[test]
fn valid_retry_requires_both_complete_second_flight_hellos() {
    let mut state = requested_retry(Some(b"fixture-cookie"));
    assert_eq!(state.eligibility(), Eligibility::Pending);
    state.observe(CLIENT, &record(20, &[1]));
    state.observe(
        CLIENT,
        &record(22, &retry_hello(CLIENT, 23, false, Some(b"fixture-cookie"))),
    );
    assert_eq!(state.eligibility(), Eligibility::Pending);
    state.observe(SERVER, &record(20, &[1]));
    state.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
    assert_eq!(
        state.eligibility(),
        Eligibility::Candidate {
            cipher_suite: 0x1301
        }
    );
    assert!(state.at_record_boundary(CLIENT));
    assert!(state.at_record_boundary(SERVER));
}

#[test]
fn retry_second_flight_and_ccs_are_independent_of_every_read_split() {
    let client = [
        record(20, &[1]),
        record(22, &retry_hello(CLIENT, 23, false, None)),
        record(23, &[0x61; 17]),
    ]
    .concat();
    let server = [
        record(20, &[1]),
        record(22, &retry_hello(SERVER, 23, false, None)),
        record(23, &[0x62; 19]),
    ]
    .concat();
    for split in 0..=client.len().max(server.len()) {
        let mut state = requested_retry(None);
        let c = split.min(client.len());
        let s = split.min(server.len());
        state.observe(CLIENT, &client[..c]);
        state.observe(SERVER, &server[..s]);
        state.observe(CLIENT, &client[c..]);
        state.observe(SERVER, &server[s..]);
        assert_eq!(
            state.eligibility(),
            Eligibility::Candidate {
                cipher_suite: 0x1301
            },
            "split {split}"
        );
        assert!(state.at_record_boundary(CLIENT) && state.at_record_boundary(SERVER));
        assert!(state.application_record_seen(CLIENT) && state.application_record_seen(SERVER));
        assert_eq!(state.buffered_bytes(), 0);
    }
}

#[test]
fn retry_rejects_repeated_retry_and_changed_client_random() {
    let mut repeated = requested_retry(None);
    repeated.observe(CLIENT, &record(22, &retry_hello(CLIENT, 23, false, None)));
    repeated.observe(SERVER, &record(22, &retry_hello(SERVER, 23, true, None)));
    assert_eq!(
        repeated.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
    let mut changed = requested_retry(None);
    let mut client = retry_hello(CLIENT, 23, false, None);
    client[6] ^= 1;
    changed.observe(CLIENT, &record(22, &client));
    changed.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
    assert_eq!(
        changed.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
}

#[test]
fn retry_rejects_unrequested_share_and_missing_or_changed_cookie() {
    for (group, cookie) in [
        (29, Some(&b"fixture-cookie"[..])),
        (23, None),
        (23, Some(&b"changed-cookie"[..])),
    ] {
        let mut state = requested_retry(Some(b"fixture-cookie"));
        state.observe(
            CLIENT,
            &record(22, &retry_hello(CLIENT, group, false, cookie)),
        );
        state.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
        assert_eq!(
            state.eligibility(),
            Eligibility::Ineligible(Ineligible::HelloRetryRequest)
        );
    }
}

#[test]
fn retry_never_changes_the_original_sni_session_or_selected_cipher() {
    for mutation in 0..3 {
        let original = extension(0, b"\0\x05\0\0\x02ok");
        let altered = extension(0, b"\0\x05\0\0\x02no");
        let mut state = inspect(
            &retry_hello_with_extra(CLIENT, 29, false, None, &original),
            &retry_hello(SERVER, 23, true, None),
        );
        let mut client = retry_hello_with_extra(
            CLIENT,
            23,
            false,
            None,
            if mutation == 0 { &altered } else { &original },
        );
        if mutation == 1 {
            client[39] ^= 1;
        } // First byte of legacy_session_id.
        state.observe(CLIENT, &record(22, &client));
        let mut server = retry_hello(SERVER, 23, false, None);
        if mutation == 2 {
            server[72] = 2;
        } // Selected suite: 0x1301 -> 0x1302.
        state.observe(SERVER, &record(22, &server));
        assert_eq!(
            state.eligibility(),
            Eligibility::Ineligible(Ineligible::HelloRetryRequest),
            "mutation {mutation}"
        );
    }
}

#[test]
fn retry_rejects_an_already_sent_share_and_repeated_retry_before_clienthello2() {
    let bad = inspect(
        &retry_hello(CLIENT, 29, false, None),
        &retry_hello(SERVER, 29, true, None),
    );
    assert_eq!(
        bad.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
    let mut repeated = requested_retry(None);
    repeated.observe(SERVER, &record(22, &retry_hello(SERVER, 23, true, None)));
    assert_eq!(
        repeated.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
}

#[test]
fn retry_cookie_only_keeps_the_original_key_share() {
    let cookie = b"fixture-cookie";
    let mut extensions = extension(43, &[3, 4]);
    extensions.extend(extension(
        44,
        &[(cookie.len() as u16).to_be_bytes().as_slice(), cookie].concat(),
    ));
    let mut retry = hello(SERVER, &[0x1301], &extensions, &[0x31; 32]);
    retry[6..38].copy_from_slice(&retry_hello(SERVER, 23, true, None)[6..38]);
    for change_key in [false, true] {
        let mut state = inspect(&retry_hello(CLIENT, 29, false, None), &retry);
        let mut client = retry_hello(CLIENT, 29, false, Some(cookie));
        if change_key {
            let key = client
                .iter()
                .position(|&b| b == 0x25)
                .expect("fixture key share");
            client[key] ^= 1;
        }
        state.observe(CLIENT, &record(22, &client));
        state.observe(SERVER, &record(22, &retry_hello(SERVER, 29, false, None)));
        assert_eq!(
            state.eligibility(),
            if change_key {
                Eligibility::Ineligible(Ineligible::HelloRetryRequest)
            } else {
                Eligibility::Candidate {
                    cipher_suite: 0x1301,
                }
            }
        );
    }
}

#[test]
fn retry_ccs_rejects_bad_values_and_interleaved_hello_fragments() {
    for ccs in [&[2][..], &[1, 1][..]] {
        let mut state = requested_retry(None);
        state.observe(CLIENT, &record(20, ccs));
        assert_eq!(
            state.eligibility(),
            Eligibility::Ineligible(Ineligible::Malformed)
        );
        let server = [
            record(22, &retry_hello(SERVER, 23, true, None)),
            record(20, ccs),
        ]
        .concat();
        let mut combined = Inspection::new();
        combined.observe(CLIENT, &record(22, &retry_hello(CLIENT, 29, false, None)));
        combined.observe(SERVER, &server);
        assert_eq!(
            combined.eligibility(),
            Eligibility::Ineligible(Ineligible::Malformed)
        );
    }
    let mut interleaved = requested_retry(None);
    interleaved.observe(
        CLIENT,
        &record(22, &retry_hello(CLIENT, 23, false, None)[..17]),
    );
    interleaved.observe(CLIENT, &record(20, &[1]));
    assert_eq!(
        interleaved.eligibility(),
        Eligibility::Ineligible(Ineligible::Malformed)
    );
}

#[test]
fn retry_never_grants_direct_eligibility_for_uninspected_psk_updates() {
    let psk = extension(41, &[0, 7, 0, 1, 0x61, 0, 0, 0, 0, 0, 33, 32]);
    let mut first = inspect(
        &retry_hello_with_extra(CLIENT, 29, false, None, &psk),
        &retry_hello(SERVER, 23, true, None),
    );
    first.observe(CLIENT, &record(22, &retry_hello(CLIENT, 23, false, None)));
    first.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
    assert_eq!(
        first.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
    let mut added = requested_retry(None);
    added.observe(
        CLIENT,
        &record(22, &retry_hello_with_extra(CLIENT, 23, false, None, &psk)),
    );
    added.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
    assert_eq!(
        added.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
}

#[test]
fn retry_requires_early_data_to_be_removed_from_clienthello2() {
    for keep_early_data in [false, true] {
        let early = extension(42, &[]);
        let mut state = inspect(
            &retry_hello_with_extra(CLIENT, 29, false, None, &early),
            &retry_hello(SERVER, 23, true, None),
        );
        state.observe(
            CLIENT,
            &record(
                22,
                &retry_hello_with_extra(
                    CLIENT,
                    23,
                    false,
                    None,
                    if keep_early_data { &early } else { &[] },
                ),
            ),
        );
        state.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
        assert_eq!(
            state.eligibility(),
            if keep_early_data {
                Eligibility::Ineligible(Ineligible::HelloRetryRequest)
            } else {
                Eligibility::Candidate {
                    cipher_suite: 0x1301,
                }
            }
        );
    }
}

#[test]
fn repeated_retry_is_rejected_at_every_read_split_and_record_boundary() {
    let retry = retry_hello(SERVER, 23, true, None);
    for wire in [
        record(22, &[retry.clone(), retry.clone()].concat()),
        [record(22, &retry), record(22, &retry)].concat(),
    ] {
        for split in 0..=wire.len() {
            let mut state = Inspection::new();
            state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 29, false, None)));
            state.observe(SERVER, &wire[..split]);
            state.observe(SERVER, &wire[split..]);
            state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 23, false, None)));
            state.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
            assert_eq!(
                state.eligibility(),
                Eligibility::Ineligible(Ineligible::HelloRetryRequest),
                "split {split}"
            );
        }
    }
}

#[test]
fn retry_cannot_share_a_record_with_the_final_serverhello_at_any_read_split() {
    let wire = record(
        22,
        &[
            retry_hello(SERVER, 23, true, None),
            retry_hello(SERVER, 23, false, None),
        ]
        .concat(),
    );
    for split in 0..=wire.len() {
        let mut state = Inspection::new();
        state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 29, false, None)));
        state.observe(SERVER, &wire[..split]);
        state.observe(SERVER, &wire[split..]);
        state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 23, false, None)));
        assert_eq!(
            state.eligibility(),
            Eligibility::Ineligible(Ineligible::HelloRetryRequest),
            "split {split}"
        );
    }
}

#[test]
fn retry_rejects_a_server_psk_without_a_client_psk() {
    let mut state = requested_retry(None);
    state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 23, false, None)));
    state.observe(
        SERVER,
        &record(
            22,
            &retry_hello_with_extra(SERVER, 23, false, None, &extension(41, &[0, 0])),
        ),
    );
    assert_eq!(
        state.eligibility(),
        Eligibility::Ineligible(Ineligible::HelloRetryRequest)
    );
}

#[test]
fn retry_preserves_partial_ccs_header_after_the_first_server_flight() {
    let ccs = record(20, &[1]);
    let mut server = record(22, &retry_hello(SERVER, 23, true, None));
    server.extend(&ccs[..3]);
    let mut state = Inspection::new();
    state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 29, false, None)));
    state.observe(SERVER, &server);
    assert_eq!(state.eligibility(), Eligibility::Pending);
    state.observe(SERVER, &ccs[3..]);
    state.observe(CLIENT, &record(22, &retry_hello(CLIENT, 23, false, None)));
    state.observe(SERVER, &record(22, &retry_hello(SERVER, 23, false, None)));
    assert_eq!(
        state.eligibility(),
        Eligibility::Candidate {
            cipher_suite: 0x1301
        }
    );
    assert!(state.at_record_boundary(SERVER));
}

#[test]
fn encrypted_record_is_complete_only_after_its_last_byte() {
    let mut state = inspect(&tls13(CLIENT, 0x1301), &tls13(SERVER, 0x1301));
    let application = record(23, &[0x41; 113]);
    for (index, byte) in application.iter().enumerate() {
        state.observe(CLIENT, &[*byte]);
        assert_eq!(
            state.at_record_boundary(CLIENT),
            index + 1 == application.len()
        );
        assert_eq!(
            state.application_record_seen(CLIENT),
            index + 1 == application.len()
        );
    }
    // A completed record cannot authorize handoff while another header is partial.
    state.observe(CLIENT, &[23, 3]);
    assert!(!state.at_record_boundary(CLIENT));
}

#[test]
fn incomplete_hellos_never_become_candidates() {
    for direction in [CLIENT, SERVER] {
        let wire = record(22, &tls13(direction, 0x1301));
        for length in 0..wire.len() {
            let mut state = Inspection::new();
            let other = if direction == CLIENT { SERVER } else { CLIENT };
            state.observe(other, &record(22, &tls13(other, 0x1301)));
            state.observe(direction, &wire[..length]);
            assert_eq!(
                state.eligibility(),
                Eligibility::Pending,
                "{direction:?} offset {length}"
            );
            assert!(state.buffered_bytes() <= 64 * 1024);
        }
    }
}

#[test]
fn advertised_limits_reject_without_allocating_untrusted_body() {
    for header in [
        vec![22, 3, 3, 0xff, 0xff],
        record(22, &[1, 0xff, 0xff, 0xff]),
        record(22, &[1, 1, 0, 0]),
    ] {
        let mut state = Inspection::new();
        state.observe(CLIENT, &header);
        assert!(matches!(state.eligibility(), Eligibility::Ineligible(_)));
        assert_eq!(state.buffered_bytes(), 0);
    }
    let excessive_suites = hello(CLIENT, &vec![0x1301; 257], &extension(43, &[2, 3, 4]), &[]);
    assert_eq!(
        inspect(&excessive_suites, &tls13(SERVER, 0x1301)).eligibility(),
        Eligibility::Ineligible(Ineligible::InspectionLimit)
    );
    let extensions: Vec<_> = (1000..1257).flat_map(|kind| extension(kind, &[])).collect();
    let excessive_extensions = hello(CLIENT, &[0x1301], &extensions, &[]);
    assert_eq!(
        inspect(&excessive_extensions, &tls13(SERVER, 0x1301)).eligibility(),
        Eligibility::Ineligible(Ineligible::InspectionLimit)
    );
}

#[test]
fn wrong_message_type_and_mid_hello_non_handshake_record_are_rejected() {
    let mut wrong = tls13(CLIENT, 0x1301);
    wrong[0] = 2;
    assert_eq!(
        inspect(&wrong, &tls13(SERVER, 0x1301)).eligibility(),
        Eligibility::Ineligible(Ineligible::Malformed)
    );
    let message = tls13(CLIENT, 0x1301);
    let mut state = Inspection::new();
    state.observe(CLIENT, &record(22, &message[..17]));
    state.observe(CLIENT, &record(23, &message[17..]));
    assert!(matches!(state.eligibility(), Eligibility::Ineligible(_)));
    assert_eq!(state.buffered_bytes(), 0);
}

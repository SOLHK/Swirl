use super::*;

fn grant() -> BillingGrant {
    BillingGrant {
        schema: 1,
        domain: DOMAIN.into(),
        authority_id: "a".repeat(64),
        account_id: "b".repeat(64),
        period_id: "c".repeat(64),
        request_nonce: "d".repeat(64),
    }
}

fn response() -> String {
    let g = grant();
    format!(
        "HTTP/1.1 200 OK\r\nSubscription-Userinfo: upload=10;download=20;total=200000000000;expire=0\r\nX-Swirl-QA-Billing-Schema: 1\r\nX-Swirl-QA-Billing-Domain: {DOMAIN}\r\nX-Swirl-QA-Billing-Authority: {}\r\nX-Swirl-QA-Billing-Account: {}\r\nX-Swirl-QA-Billing-Period: {}\r\nX-Swirl-QA-Billing-Nonce: {}\r\nX-Swirl-QA-Billing-Revision: 1\r\nX-Swirl-QA-Billing-Covered-Sequence: 0\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        g.authority_id, g.account_id, g.period_id, g.request_nonce
    )
}

fn extra(line: &str) -> String {
    response().replace(
        "Connection: close\r\n",
        &format!("Connection: close\r\n{line}\r\n"),
    )
}

#[test]
fn fixed_billing_receipt_contains_only_validated_bound_fields() {
    let value = parse_headers(response().as_bytes(), &grant()).unwrap();
    assert_eq!(value.as_object().unwrap().len(), 12);
    assert_eq!(value["upload"], 10);
    assert_eq!(value["download"], 20);
    assert_eq!(value["total"], 200000000000u64);
    assert_eq!(value["expire"], 0);
    assert_eq!(value["covered_sequence"], 0);
    assert_eq!(value["request_nonce"], "d".repeat(64));
    assert!(
        parse_headers(
            response().replace("Connection: close\r\n", "").as_bytes(),
            &grant()
        )
        .is_ok()
    );
    assert!(
        parse_headers(
            response()
                .replace("Content-Length", "CONTENT-LENGTH")
                .as_bytes(),
            &grant()
        )
        .is_ok()
    );
}

#[test]
fn integer_syntax_and_signed_database_counter_bounds_are_strict() {
    for good in ["0", "1", "9223372036854775807"] {
        assert!(number(good).is_ok());
    }
    for bad in [
        "",
        "00",
        "01",
        "+1",
        "-1",
        "1.0",
        "1e2",
        " 1",
        "1 ",
        "١",
        "9223372036854775808",
        "18446744073709551616",
    ] {
        assert_eq!(number(bad), Err(FAILURE));
    }
    for (from, to) in [
        ("upload=10", "upload=01"),
        ("download=20", "download=-1"),
        ("total=200000000000", "total=0"),
        ("total=200000000000", "total=29"),
        ("expire=0", "expire=9223372036854775808"),
        ("Revision: 1", "Revision: 0"),
        ("Covered-Sequence: 0", "Covered-Sequence: 00"),
        ("upload=10;download=20", "download=20;upload=10"),
        ("expire=0", "expire=0;unknown=1"),
    ] {
        assert_eq!(
            parse_headers(response().replace(from, to).as_bytes(), &grant()),
            Err(FAILURE)
        );
    }
}

#[test]
fn every_required_header_and_identity_is_bound() {
    for line in response()
        .split("\r\n")
        .filter(|line| line.contains(": ") && !line.starts_with("Connection:"))
    {
        let missing = response().replace(&format!("{line}\r\n"), "");
        assert_eq!(parse_headers(missing.as_bytes(), &grant()), Err(FAILURE));
    }
    for (from, to) in [
        ("Schema: 1".into(), "Schema: 2".into()),
        (DOMAIN.into(), "swirl-live-billing".into()),
        ("a".repeat(64), "e".repeat(64)),
        ("b".repeat(64), "e".repeat(64)),
        ("c".repeat(64), "e".repeat(64)),
        ("d".repeat(64), "e".repeat(64)),
    ] {
        assert_eq!(
            parse_headers(response().replace(&from, &to).as_bytes(), &grant()),
            Err(FAILURE)
        );
    }
}

#[test]
fn status_redirect_transfer_body_and_duplicate_headers_fail_closed() {
    for line in [
        "Location: https://never-follow.fixture.invalid/",
        "Transfer-Encoding: chunked",
        "Content-Length: 0",
        "cOnTeNt-LeNgTh: 0",
        "Subscription-Userinfo: upload=0;download=0;total=1;expire=0",
        "X-Unrecognized: anything",
        "Content-Length : 0",
    ] {
        assert_eq!(
            parse_headers(extra(line).as_bytes(), &grant()),
            Err(FAILURE)
        );
    }
    for (from, to) in [
        ("HTTP/1.1 200 OK", "HTTP/1.0 200 OK"),
        ("HTTP/1.1 200 OK", "HTTP/1.1 302 Found"),
        ("HTTP/1.1 200 OK", "HTTP/1.1 401 Unauthorized"),
        ("HTTP/1.1 200 OK", "HTTP/1.1 2000 OK"),
        ("Content-Length: 0", "Content-Length: 1"),
        ("Content-Length: 0", "Content-Length: 00"),
        ("Connection: close", "Connection: keep-alive"),
        ("upload=10", "upload=10\nInjected: 1"),
        ("upload=10", "upload=\t10"),
    ] {
        assert_eq!(
            parse_headers(response().replace(from, to).as_bytes(), &grant()),
            Err(FAILURE)
        );
    }
    for tail in ["x", "\r\nHTTP/1.1 200 OK\r\n\r\n"] {
        assert_eq!(
            parse_headers((response() + tail).as_bytes(), &grant()),
            Err(FAILURE)
        );
    }
    for byte in [0u8, 127, 128, 255] {
        let mut value = response().into_bytes();
        value[13] = byte;
        assert_eq!(parse_headers(&value, &grant()), Err(FAILURE));
    }
}

#[test]
fn header_line_limit_counts_the_crlf_and_does_not_accept_bare_lf() {
    let prefix = "HTTP/1.1 200 ";
    let longest = prefix.to_owned() + &"x".repeat(MAX_LINE_BYTES - prefix.len() - 2);
    assert!(
        parse_headers(
            response().replace("HTTP/1.1 200 OK", &longest).as_bytes(),
            &grant()
        )
        .is_ok()
    );
    assert_eq!(
        parse_headers(
            response()
                .replace("HTTP/1.1 200 OK", &(longest + "x"))
                .as_bytes(),
            &grant()
        ),
        Err(FAILURE)
    );
    assert_eq!(
        parse_headers(response().replace("\r\n", "\n").as_bytes(), &grant()),
        Err(FAILURE)
    );
}

async fn read_fixture(bytes: Vec<u8>) -> Result<Vec<u8>> {
    let (mut writer, mut reader) = tokio::io::duplex(bytes.len() + 1);
    writer.write_all(&bytes).await.unwrap();
    writer.shutdown().await.unwrap();
    read_headers(&mut reader).await
}

#[tokio::test]
async fn header_reader_stops_at_fixed_limits_without_reading_a_body() {
    let body = b"must-not-read-a-body";
    let mut bytes = response().into_bytes();
    bytes.extend_from_slice(body);
    let (mut writer, mut reader) = tokio::io::duplex(bytes.len() + 1);
    writer.write_all(&bytes).await.unwrap();
    writer.shutdown().await.unwrap();
    assert_eq!(
        read_headers(&mut reader).await.unwrap(),
        response().as_bytes()
    );
    let mut remaining = Vec::new();
    reader.read_to_end(&mut remaining).await.unwrap();
    assert_eq!(remaining, body);
    for size in [MAX_HEADER_BYTES, MAX_HEADER_BYTES + 1] {
        let mut bytes = Vec::new();
        while bytes.len() < size - 2 {
            let line = (size - 2 - bytes.len()).min(MAX_LINE_BYTES);
            bytes.extend(std::iter::repeat_n(b'x', line - 2));
            bytes.extend_from_slice(b"\r\n");
        }
        bytes.extend_from_slice(b"\r\n");
        assert_eq!(read_fixture(bytes).await.is_ok(), size == MAX_HEADER_BYTES);
    }
    assert_eq!(
        read_fixture(vec![b'x'; MAX_LINE_BYTES + 1]).await,
        Err(FAILURE)
    );
    assert_eq!(
        read_fixture(response().trim_end().as_bytes().to_vec()).await,
        Err(FAILURE)
    );
}

#[test]
fn grant_nonce_domain_and_fields_cannot_override_the_fixed_protocol() {
    assert!(grant().validate(&"d".repeat(64)).is_ok());
    assert_eq!(
        grant().validate(&"e".repeat(64)),
        Err("PrivateWorkerBillingGrant")
    );
    let mut g = grant();
    g.authority_id = "A".repeat(64);
    assert_eq!(
        g.validate(&"d".repeat(64)),
        Err("PrivateWorkerBillingGrant")
    );
    let mut value = json!({"schema":1,"domain":DOMAIN,"authority_id":"a".repeat(64),
        "account_id":"b".repeat(64),"period_id":"c".repeat(64),"request_nonce":"d".repeat(64)});
    value["url"] = json!("https://arbitrary.invalid/");
    assert!(serde_json::from_value::<BillingGrant>(value).is_err());
    assert!(
        tls_config(&FixtureTls {
            server_name: "another.fixture.invalid".into(),
            ca_der_base64: String::new()
        })
        .is_err()
    );
}

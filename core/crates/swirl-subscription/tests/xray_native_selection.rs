//! Mixed-validity sources keep every sibling and require an explicit node choice.
//! All hosts, UUIDs, passwords and accounts are synthetic offline fixtures.
use serde_json::{Value, json};
use swirl_subscription::{
    Config, Outbound,
    xray::{
        InputSource,
        convert::{ConvertedDocument, NativeStatus, ValidationStatus, import_document},
    },
};

const FIRST_ID: &str = "00112233-4455-6677-8899-aabbccddeeff";
const LAST_ID: &str = "ffeeddcc-bbaa-9988-7766-554433221100";

fn restored(value: &Value) -> ConvertedDocument {
    let mut raw = b"\xef\xbb\xbf \n".to_vec();
    raw.extend(serde_json::to_vec_pretty(value).unwrap());
    raw.extend(b"\r\n");
    let before = import_document(&raw, InputSource::File).unwrap();
    let after = ConvertedDocument::restore(&before.save().unwrap()).unwrap();
    assert_eq!(after.raw_json(), raw);
    assert_eq!(after.configuration(), value);
    assert_eq!(after.source(), InputSource::File);
    assert_eq!(after.diagnostics(), before.diagnostics());
    assert_eq!(before.nodes().len(), after.nodes().len());
    for (first, reloaded) in before.nodes().iter().zip(after.nodes()) {
        assert_eq!(first.source(), reloaded.source());
        assert_eq!(first.authentication(), reloaded.authentication());
        assert_eq!(first.validation(), reloaded.validation());
        assert_eq!(first.diagnostics(), reloaded.diagnostics());
        assert_eq!(first.native_status(), reloaded.native_status());
        assert_eq!(
            first
                .native_outbound()
                .map(|outbound| serde_json::to_value(outbound).unwrap()),
            reloaded
                .native_outbound()
                .map(|outbound| serde_json::to_value(outbound).unwrap())
        );
        assert!(!first.network_verified() && !reloaded.network_verified());
    }
    after
}

fn selected(doc: &ConvertedDocument, index: usize) -> Config {
    let node = &doc.nodes()[index];
    assert_eq!(node.validation(), ValidationStatus::Valid, "{node:?}");
    assert_eq!(node.native_status(), NativeStatus::Executable, "{node:?}");
    assert!(
        node.diagnostics()
            .iter()
            .all(|d| !matches!(d.severity.as_str(), "error" | "unsupported"))
    );
    let config = doc
        .native_config(index, "127.0.0.1:0".parse().unwrap())
        .unwrap();
    assert_eq!(config.nodes.len(), 1);
    assert_eq!(config.selected, config.nodes[0].id);
    Config::parse(&serde_json::to_vec(&config).unwrap()).unwrap()
}

fn blocked(doc: &ConvertedDocument, index: usize, code: &str, path: &str) {
    let node = &doc.nodes()[index];
    assert_eq!(node.native_status(), NativeStatus::Blocked, "{node:?}");
    assert!(node.native_outbound().is_none());
    assert!(
        node.diagnostics()
            .iter()
            .any(|d| d.code == code && d.path == path)
    );
    assert_eq!(
        doc.native_config(index, "127.0.0.1:0".parse().unwrap())
            .err()
            .unwrap()
            .code,
        "NativeExecutionBlocked"
    );
}

#[test]
fn invalid_uuid_account_stays_blocked_without_contaminating_valid_siblings() {
    let value = json!({"outbounds":[{"protocol":"vless","settings":{"vnext":[{
        "address":"vless.example.invalid","port":443,"users":[
            {"id":FIRST_ID,"encryption":"none"},
            {"id":"00112233-4455-6677-8899-aabbccddeefg","encryption":"none"},
            {"id":LAST_ID,"encryption":"none"}
        ]
    }]}}]});
    let doc = restored(&value);
    assert_eq!(doc.nodes().len(), 3);
    for (index, node) in doc.nodes().iter().enumerate() {
        assert_eq!(node.source().outbound_index, 0);
        assert_eq!(node.source().server_index, Some(0));
        assert_eq!(node.source().user_index, Some(index));
        assert_eq!(
            node.source().user_path.as_deref(),
            Some(format!("outbounds[0].settings.vnext[0].users[{index}]").as_str())
        );
    }
    assert_eq!(doc.nodes()[1].validation(), ValidationStatus::Invalid);
    blocked(
        &doc,
        1,
        "InvalidUuid",
        "outbounds[0].settings.vnext[0].users[1].id",
    );
    for (index, expected_id) in [(0, FIRST_ID), (2, LAST_ID)] {
        let config = selected(&doc, index);
        let Outbound::Vless {
            host, port, uuid, ..
        } = &config.nodes[0].outbound
        else {
            panic!("explicit account selection changed the VLESS protocol");
        };
        assert_eq!(host, "vless.example.invalid");
        assert_eq!(*port, 443);
        assert_eq!(uuid, expected_id);
    }
}

#[test]
fn unsupported_cipher_server_keeps_its_slot_and_does_not_replace_valid_siblings() {
    let value = json!({"outbounds":[{"protocol":"shadowsocks","settings":{"servers":[
        {"address":"first.example.invalid","port":1001,"method":"aes-128-gcm","password":"SYNTHETIC-FIRST"},
        {"address":"blocked.example.invalid","port":1002,"method":"2022-blake3-chacha20-poly1305","password":"QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="},
        {"address":"chosen.example.invalid","port":1003,"method":"chacha20-ietf-poly1305","password":" SYNTHETIC-LAST:密碼 "}
    ]}}]});
    let doc = restored(&value);
    assert_eq!(doc.nodes().len(), 3);
    for (index, node) in doc.nodes().iter().enumerate() {
        assert_eq!(node.source().outbound_index, 0);
        assert_eq!(node.source().server_index, Some(index));
        assert_eq!(node.source().user_index, None);
        assert_eq!(node.source().user_path, None);
        assert_eq!(
            node.source().server_path,
            format!("outbounds[0].settings.servers[{index}]")
        );
    }
    blocked(
        &doc,
        1,
        "ShadowsocksCipherUnsupported",
        "outbounds[0].settings.servers[1].method",
    );
    for (index, host_expected, port_expected, cipher_expected, password_expected) in [
        (
            0,
            "first.example.invalid",
            1001,
            "aes-128-gcm",
            "SYNTHETIC-FIRST",
        ),
        (
            2,
            "chosen.example.invalid",
            1003,
            "chacha20-ietf-poly1305",
            " SYNTHETIC-LAST:密碼 ",
        ),
    ] {
        let config = selected(&doc, index);
        let Outbound::Shadowsocks {
            host,
            port,
            password,
            cipher,
            udp,
            obfs_http,
        } = &config.nodes[0].outbound
        else {
            panic!("explicit server selection changed the Shadowsocks protocol");
        };
        assert_eq!(host, host_expected);
        assert_eq!(*port, port_expected);
        assert_eq!(cipher, cipher_expected);
        assert_eq!(password, password_expected);
        assert!(!udp);
        assert!(obfs_http.is_none());
    }
}

#[test]
fn invalid_http_basic_username_cannot_be_exported_or_disable_sibling_authentication() {
    let value = json!({"outbounds":[{"protocol":"http","settings":{"servers":[{
        "address":"http.example.invalid","port":3128,"users":[
            {"user":"bad:name","pass":"SYNTHETIC-BLOCKED"},
            {"user":"chosen-account","pass":" SYNTHETIC-SELECTED:密碼 "}
        ]
    }]}}]});
    let doc = restored(&value);
    assert_eq!(doc.nodes().len(), 2);
    for (index, node) in doc.nodes().iter().enumerate() {
        assert_eq!(node.source().server_index, Some(0));
        assert_eq!(node.source().user_index, Some(index));
        assert_eq!(
            node.source().user_path.as_deref(),
            Some(format!("outbounds[0].settings.servers[0].users[{index}]").as_str())
        );
    }
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
    blocked(
        &doc,
        0,
        "HttpBasicUsernameColon",
        "outbounds[0].settings.servers[0].users[0].user",
    );
    let config = selected(&doc, 1);
    let Outbound::HttpConnect {
        host,
        port,
        auth: Some(auth),
        tls: None,
    } = &config.nodes[0].outbound
    else {
        panic!("valid HTTP sibling must retain authenticated plain CONNECT");
    };
    assert_eq!(host, "http.example.invalid");
    assert_eq!(*port, 3128);
    assert_eq!(auth.username, "chosen-account");
    assert_eq!(auth.password, " SYNTHETIC-SELECTED:密碼 ");
}

#[test]
fn invalid_server_does_not_shift_cross_outbound_indices_or_authorize_fallback_selection() {
    let value = json!({"outbounds":[
        {"protocol":"vless","settings":{"address":"independent.example.invalid","port":443,"id":FIRST_ID,"encryption":"none"}},
        {"protocol":"socks","settings":{"servers":[
            {"address":"blocked.example.invalid","port":0,"users":[{"user":"blocked","pass":"SYNTHETIC-BLOCKED"}]},
            {"address":"chosen.example.invalid","port":1080,"users":[
                {"user":"first-account","pass":"SYNTHETIC-FIRST"},
                {"user":"chosen-account","pass":"SYNTHETIC-SELECTED"}
            ]}
        ]}}
    ]});
    let doc = restored(&value);
    assert_eq!(doc.nodes().len(), 4);
    assert_eq!(doc.nodes()[1].validation(), ValidationStatus::Invalid);
    blocked(
        &doc,
        1,
        "InvalidServerPort",
        "outbounds[1].settings.servers[0].port",
    );
    for (index, server, user) in [(1, 0, 0), (2, 1, 0), (3, 1, 1)] {
        let source = doc.nodes()[index].source();
        assert_eq!(source.outbound_index, 1);
        assert_eq!(source.outbound_path, "outbounds[1]");
        assert_eq!(source.server_index, Some(server));
        assert_eq!(source.user_index, Some(user));
        assert_eq!(
            source.user_path.as_deref(),
            Some(format!("outbounds[1].settings.servers[{server}].users[{user}]").as_str())
        );
    }
    assert!(matches!(
        selected(&doc, 0).nodes[0].outbound,
        Outbound::Vless { .. }
    ));
    for (index, username, password) in [
        (2, "first-account", "SYNTHETIC-FIRST"),
        (3, "chosen-account", "SYNTHETIC-SELECTED"),
    ] {
        let config = selected(&doc, index);
        let Outbound::Socks5 {
            host,
            port,
            auth: Some(auth),
            tls: None,
            udp: false,
        } = &config.nodes[0].outbound
        else {
            panic!("explicit SOCKS sibling selection lost protocol or authentication");
        };
        assert_eq!(host, "chosen.example.invalid");
        assert_eq!(*port, 1080);
        assert_eq!(auth.username, username);
        assert_eq!(auth.password, password);
    }
    for index in [doc.nodes().len(), usize::MAX] {
        assert_eq!(
            doc.native_config(index, "127.0.0.1:0".parse().unwrap())
                .err()
                .unwrap()
                .code,
            "NativeNodeIndex"
        );
    }
}

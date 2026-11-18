//! Actual system PowerShell IPC, with all network commands replaced by fixtures.
use super::*;
use crate::windows_network_session::NetworkSession;

const TEST_TIMEOUT: Duration = Duration::from_secs(20);

#[test]
fn session_reuses_process_and_keeps_unicode_requests_separate() {
    let mut session = NetworkSession::start(&resource_session_script(
        r#"
$p = $swirlRequest | ConvertFrom-Json
$global:swirlCalls += 1
ConvertTo-Json -InputObject @{pid=$PID;calls=$global:swirlCalls;value=$p.value} -Compress
"#,
    ))
    .unwrap();
    let input = json!({"value":"第一行\nsecond\"line\\path"});
    let first: serde_json::Value = session.request(&input, TEST_TIMEOUT).unwrap();
    assert!(first["pid"].as_u64().is_some_and(|pid| pid > 0));
    assert_eq!(
        first,
        json!({"pid":first["pid"],"calls":1,"value":input["value"]})
    );
    let second: serde_json::Value = session
        .request(&json!({"value":"next"}), TEST_TIMEOUT)
        .unwrap();
    assert_eq!(second, json!({"pid":first["pid"],"calls":2,"value":"next"}));
}

#[test]
fn session_duplicate_response_cannot_satisfy_next_request() {
    let mut session = NetworkSession::start(
        r#"
[void][Console]::In.ReadLine()
[Console]::Out.WriteLine('{"request_id":1,"result":true}')
[Console]::Out.WriteLine('{"request_id":1,"result":true}')
Start-Sleep -Seconds 120
"#,
    )
    .unwrap();
    assert!(session.request::<bool>(&json!({}), TEST_TIMEOUT).unwrap());
    let error = session
        .request::<bool>(&json!({}), TEST_TIMEOUT)
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    assert!(error.to_string().contains("request identity mismatch"));
    assert!(session.request::<bool>(&json!({}), TEST_TIMEOUT).is_err());
}

#[test]
fn session_blocked_stdin_times_out_and_preserves_stderr_context() {
    let mut session = NetworkSession::start(
        r#"
[void][Console]::In.ReadLine()
[Console]::Error.WriteLine('fixture paused before next read')
[Console]::Out.WriteLine('{"request_id":1,"result":true}')
Start-Sleep -Seconds 120
"#,
    )
    .unwrap();
    // A response proves startup has finished. Only then fill the unread pipe.
    assert!(session.request::<bool>(&json!({}), TEST_TIMEOUT).unwrap());
    let start = Instant::now();
    let error = session
        .request::<bool>(
            &json!({"value":"x".repeat(60 * 1024)}),
            Duration::from_millis(100),
        )
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    assert!(error.to_string().contains("timed out"));
    assert!(
        error
            .to_string()
            .contains("fixture paused before next read")
    );
    assert!(
        start.elapsed() < Duration::from_secs(10),
        "pipe owners did not retire"
    );
    assert!(session.request::<bool>(&json!({}), TEST_TIMEOUT).is_err());
}

#[test]
fn session_rejects_oversized_truncated_or_malformed_responses_and_stops() {
    for output in [
        "[Console]::Out.Write(('x' * (1024 * 1024 + 1))); Start-Sleep -Seconds 120",
        "[Console]::Out.Write('{\"request_id\":1,\"result\":true}'); exit 0",
        "[Console]::Out.WriteLine('not-json'); Start-Sleep -Seconds 120",
    ] {
        let mut session =
            NetworkSession::start(&format!("[void][Console]::In.ReadLine(); {output}")).unwrap();
        let error = session
            .request::<bool>(&json!({}), TEST_TIMEOUT)
            .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData, "{error}");
        assert!(session.request::<bool>(&json!({}), TEST_TIMEOUT).is_err());
    }
}

#[test]
fn session_rejects_multiple_script_results_without_publishing_success() {
    let mut session = NetworkSession::start(&resource_session_script("'true'; 'false'")).unwrap();
    let error = session
        .request::<bool>(&json!({}), TEST_TIMEOUT)
        .unwrap_err();
    assert!(
        error.to_string().contains("exactly one JSON result"),
        "{error}"
    );
}

#[test]
fn resource_session_rereads_live_state_and_rejects_changed_interface_ownership() {
    const MOCKS: &str = r#"
$global:swirlReads = 0
function Get-NetAdapter {
  [CmdletBinding()] param([switch]$IncludeHidden)
  $global:swirlReads += 1
  $index = if ($global:swirlReads -le 2) {71} else {72}
  [pscustomobject]@{InterfaceGuid=[guid]'00000000-0000-0000-0000-000000000001';ifIndex=$index;HardwareInterface=$false}
}
function Get-NetIPInterface {
  [CmdletBinding()] param([uint32]$InterfaceIndex,[string]$AddressFamily,[string]$PolicyStore)
  if ($InterfaceIndex -ne 71 -or $AddressFamily -ne 'IPv4' -or $PolicyStore -ne 'ActiveStore') { throw 'Wrong fixture query' }
  [pscustomobject]@{NlMtu=[uint32](1300 + $global:swirlReads * 100)}
}
"#;
    let session = NetworkSession::start(&format!(
        "{MOCKS}\n{}",
        resource_session_script(RESOURCE_SCRIPT)
    ))
    .unwrap();
    let identity = InterfaceIdentity::new(71, 1);
    let mut backend = WindowsNetworkBackend {
        owned: identity.clone(),
        session: Some(session),
    };
    assert_eq!(
        backend
            .read(&identity, &Resource::Mtu { ipv6: false })
            .unwrap(),
        Some(Value::Mtu { mtu: 1400 })
    );
    assert_eq!(
        backend
            .read(&identity, &Resource::Mtu { ipv6: false })
            .unwrap(),
        Some(Value::Mtu { mtu: 1500 })
    );
    let error = backend
        .read(&identity, &Resource::Mtu { ipv6: false })
        .unwrap_err();
    assert!(
        error
            .to_string()
            .contains("TUN interface ownership changed"),
        "{error}"
    );
    assert!(
        backend.session.is_none(),
        "failed session must be discarded before recovery"
    );
}

#[test]
fn resource_session_missing_adapter_returns_typed_none_without_network_commands() {
    let script = format!(
        "function Get-NetAdapter {{ [CmdletBinding()] param([switch]$IncludeHidden) }}\n{}",
        resource_session_script(RESOURCE_SCRIPT)
    );
    let mut session = NetworkSession::start(&script).unwrap();
    let input = json!({"mode":"read","interface":InterfaceIdentity::new(71,1),"resource":Resource::Mtu {ipv6:false}});
    for _ in 0..2 {
        assert_eq!(
            session
                .request::<Option<Value>>(&input, TEST_TIMEOUT)
                .unwrap(),
            None
        );
    }
}

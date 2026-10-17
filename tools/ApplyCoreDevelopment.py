"""One-time, checked source refactoring on the isolated core development branch.

No user configuration, network requests, credentials, or platform settings.
The workflow commits the resulting real source before compiling and testing it.
"""
from pathlib import Path

changes = {}
def read(path):
    return changes.get(path, Path(path).read_text(encoding='utf-8'))
def change(path, old, new):
    text = read(path)
    if text.count(old) != 1:
        raise RuntimeError(f'Unexpected source baseline for {path}: {old[:70]!r}')
    changes[path] = text.replace(old, new, 1)

sub = 'core/crates/swirl-subscription/src/lib.rs'
if '    Socks4 {' not in read(sub):
    change(sub, '    Socks5 {\n        host: String,', '''    Socks4 {
        host: String,
        port: u16,
        #[serde(default)]
        user_id: String,
        #[serde(default = "default_true")]
        remote_dns: bool,
    },
    Socks5 {
        host: String,''')
    change(sub, '            match &node.outbound {\n                Outbound::Vless {', '''            match &node.outbound {
                Outbound::Socks4 { host, port, user_id, .. }
                    if !valid_host(host) || *port == 0 || user_id.len() > 255
                        || user_id.chars().any(char::is_control) => {
                    return Err("Socks4Parameters");
                }
                Outbound::Vless {''')

proto = 'core/crates/swirl-protocol/src/lib.rs'
if 'mod socks4;' not in read(proto):
    change(proto, 'mod shadowsocks;', 'mod shadowsocks;\nmod socks4;')
    change(proto, 'pub enum InboundKind {\n    Socks5,', 'pub enum InboundKind {\n    Socks4,\n    Socks5,')
    change(proto, '    if first == 5 {\n        return accept_socks(stream, auth).await;\n    }', '''    if first == 4 {
        return socks4::accept(stream, auth).await;
    }
    if first == 5 {
        return accept_socks(stream, auth).await;
    }''')
    change(proto, '    let bytes = match kind {\n        InboundKind::Socks5 => {', '''    let bytes = match kind {
        InboundKind::Socks4 => vec![0, if ok {90} else {91}, 0, 0, 0, 0, 0, 0],
        InboundKind::Socks5 => {''')
    change(proto, '        Outbound::Reject {} => return Err("RouteRejected"),', '''        Outbound::Reject {} => return Err("RouteRejected"),
        Outbound::Socks4 { host, port, user_id, remote_dns } => {
            return socks4::connect(host, *port, user_id, *remote_dns, target, resolver).await;
        }''')

dns = 'core/crates/swirl-dns/src/lib.rs'
if 'DoH/Fake-IP are not claimed.' in read(dns):
    change(dns, '//! Bounded system/custom/strict TLS DNS resolver. DoH/Fake-IP are not claimed.',
           '//! Bounded system/custom/DoT/HTTP-1.1 DoH resolver. Fake-IP is not implemented.')

qt = 'src/Swirl.Quick/engine/RustDnsConfiguration.h'
if '// Native DoH and DoT existing-field mapping.' not in read(qt):
    text = read(qt)
    start = text.index('    QJsonArray tlsServers;')
    end = text.index('    QJsonObject result{{"hosts", mapped}', start)
    replacement = r'''    // Native DoH and DoT existing-field mapping.
    QJsonArray tlsServers;
    if (!encrypted.isEmpty()) {
        const QRegularExpression syntax("^(?:tls|https)://(?:\\[[0-9A-Fa-f:]+\\]|[A-Za-z0-9.-]+)(?::[0-9]{1,5})?(?:/[^\\s?#\\\\]*)?$");
        const QUrl url(encrypted, QUrl::StrictMode);
        const bool https = url.scheme() == "https";
        if (encrypted.size() > 2048 || !syntax.match(encrypted).hasMatch()
            || !url.isValid() || (!https && url.scheme() != "tls")
            || !url.userInfo().isEmpty() || url.hasQuery() || url.hasFragment()
            || (!https && !url.path().isEmpty() && url.path() != "/"))
            return invalid();
        const auto name = url.host().toLower();
        const int port = url.port(https ? 443 : 853);
        if (port < 1 || port > 65535 || name.size() > 253 || name.isEmpty()) return invalid();
        QHostAddress address;
        if (!address.setAddress(name)) {
            if (!hostPattern.match(name).hasMatch()) return invalid();
            for (const auto &row : mapped) {
                const auto host = row.toObject();
                if (host.value("name").toString() == name)
                    address.setAddress(host.value("address").toString());
            }
            if (address.isNull())
                return "Rust 加密 DNS 服务器域名需要精确本地 IP 映射；未使用系统 DNS 引导或明文回退。";
        }
        if (!usableAddress(address)) return invalid();
        QJsonObject server{{"address", endpoint(address, port)},
            {"tls", QJsonObject{{"server_name", name}, {"alpn", QJsonArray{https ? "http/1.1" : "dot"}}}}};
        if (https) {
            const auto path = url.path(QUrl::FullyEncoded).isEmpty() ? QString("/") : url.path(QUrl::FullyEncoded);
            if (path.size() > 1024 || path.startsWith("//")) return invalid();
            server["https_path"] = path;
        }
        tlsServers.append(server);
    }
'''
    text = text[:start] + replacement + text[end:]
    text = text.replace('精确映射和严格 DoT', '精确映射、严格 DoT 和 DoH POST')
    text = text.replace('Rust DoT 此阶段', 'Rust 加密 DNS 此阶段')
    changes[qt] = text

qt_test = 'src/Swirl.Quick/tests/RustCoreTests.cpp'
if ' void nativeDohMapsExistingHttpsField(){' not in read(qt_test):
    change(qt_test, 'private slots:\n', '''private slots:
 void nativeDohMapsExistingHttpsField(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="direct";
  o.dnsConfig={{"mode",0},{"servers",""},{"encrypted","https://DNS.fixture.invalid:8443/dns-query"},{"useHosts",false},
    {"hosts",QVariantList{QVariantMap{{"name","dns.fixture.invalid"},{"value","127.0.0.1"}}}}};
  QJsonObject config;QVERIFY2(RustCoreEngine::configuration(o,&config).isEmpty(),"DoH configuration maps");
  const auto endpoint=config["dns"].toObject()["tls_servers"].toArray().first().toObject();
  QCOMPARE(endpoint["address"].toString(),QString("127.0.0.1:8443"));
  QCOMPARE(endpoint["https_path"].toString(),QString("/dns-query"));
  QCOMPARE(endpoint["tls"].toObject()["server_name"].toString(),QString("dns.fixture.invalid"));
  QCOMPARE(endpoint["tls"].toObject()["alpn"].toArray(),QJsonArray{"http/1.1"});
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));engine.stop();
  const QJsonObject sentinel{{"unchanged",true}};
  for(const auto &url:QStringList{"http://127.0.0.1/dns-query","https://missing.invalid/dns-query","https://user@127.0.0.1/dns-query","https://127.0.0.1/dns-query?x=1","https://127.0.0.1/dns-query#x","https://127.0.0.1:0/dns-query","https://127.0.0.1//bad"}){
   o.dnsConfig["encrypted"]=url;config=sentinel;QVERIFY2(!RustCoreEngine::configuration(o,&config).isEmpty(),qPrintable(url));QCOMPARE(config,sentinel);
  }
 }
''')

workflow = '.github/workflows/rust-core.yml'
if 'test_dns_https.py' not in read(workflow):
    lines = read(workflow).splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if 'python ../tools/tests/test_dns_tls.py' in lines[i]:
            windows = i + 1 < len(lines) and 'if ($LASTEXITCODE' in lines[i+1]
            guard = lines[i+1] if windows else ''
            if windows:
                out.append(guard)
                i += 1
            for test in ['test_dns_https.py', 'test_socks4.py']:
                out.append('          python ../tools/tests/' + test + '\n')
                if windows:
                    out.append(guard)
        i += 1
    changes[workflow] = ''.join(out)

for name, text in changes.items():
    Path(name).write_text(text, encoding='utf-8')
    print('Updated source:', name)

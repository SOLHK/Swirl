"""Checked source-only WebSocket integration. No user data or workflow edits."""
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
if 'pub use websocket::WebSocket;' not in read(sub):
    change(sub, 'mod dns_tls;', 'mod dns_tls;\nmod websocket;\npub use websocket::WebSocket;')
    change(sub, '''        uuid: String,
        #[serde(default)]
        tls: Option<Tls>,''', '''        uuid: String,
        #[serde(default)]
        tls: Option<Tls>,
        #[serde(default)]
        websocket: Option<WebSocket>,''')
    change(sub, '''        password: String,
        tls: Tls,
    },''', '''        password: String,
        tls: Tls,
        #[serde(default)]
        websocket: Option<WebSocket>,
    },''')
    change(sub, '            let tls = match &node.outbound {', '''            match &node.outbound {
                Outbound::Vless {websocket: Some(ws), tls, ..} => ws.validate_tls(tls.as_ref())?,
                Outbound::Trojan {websocket: Some(ws), tls, ..} => ws.validate_tls(Some(tls))?,
                _ => {}
            }
            let tls = match &node.outbound {''')
proto = 'core/crates/swirl-protocol/src/lib.rs'
if 'mod websocket;' not in read(proto):
    change(proto, 'mod vless;', 'mod vless;\nmod websocket;')
    change(proto, '    if let Outbound::Shadowsocks {\n        password,', '''    let ws = match outbound {
        Outbound::Vless {websocket, ..} | Outbound::Trojan {websocket, ..} => websocket.as_ref(),
        _ => None,
    };
    if let Some(ws) = ws { stream = websocket::connect(stream, ws).await?; }
    if let Outbound::Shadowsocks {
        password,''')
inspect = 'core/crates/swirl-subscription/src/inspect.rs'
if 'mod inspect_websocket;' not in read(inspect):
    change(inspect, 'use crate::{Config, Credentials, Limits, Node, ObfsHttp, Outbound, Tls};',
           'use crate::{Config, Credentials, Limits, Node, ObfsHttp, Outbound, Tls};\n#[path = "inspect_websocket.rs"]\nmod inspect_websocket;')
    change(inspect, '    let obfuscation = if kind == "ss"', '''    if transport == "ws" && matches!(kind, "vless" | "trojan") {
        return inspect_websocket::inspect(raw, index, family);
    }
    let obfuscation = if kind == "ss"''')
    change(inspect, '''                    uuid: raw.get("uuid").and_then(Value::as_str).unwrap_or("").into(),
                    tls,
                }),''', '''                    uuid: raw.get("uuid").and_then(Value::as_str).unwrap_or("").into(),
                    tls,
                    websocket: None,
                }),''')
    change(inspect, '''                "trojan" => tls.map(|tls| Outbound::Trojan {
                    host,
                    port: port as u16,
                    password,
                    tls,
                }),''', '''                "trojan" => tls.map(|tls| Outbound::Trojan {
                    host,
                    port: port as u16,
                    password,
                    tls,
                    websocket: None,
                }),''')
qt = 'src/Swirl.Quick/engine/RustCoreEngine.cpp'
if '// Native WS mapping; no QML changes.' not in read(qt):
    change(qt, '  if(n.protocol=="vless")allowed.unite(QSet<QString>{"uuid","flow","encryption"});', '''  if(n.protocol=="vless")allowed.unite(QSet<QString>{"uuid","flow","encryption"});
  if(n.protocol=="vless"||n.protocol=="trojan")allowed.unite(QSet<QString>{"network","ws-opts"});''')
    change(qt, '  nodes.append(QJsonObject{{"id",n.id},{"outbound",outbound}});', '''  // Native WS mapping; no QML changes.
  if(n.parameters.contains("network")||n.parameters.contains("ws-opts")){
   const auto network=n.parameters.value("network");
   if(!network.isString()||(network.toString()!="tcp"&&network.toString()!="ws"))return "Rust 尚未实现此传输。";
   if(network.toString()=="ws"){
    if(n.parameters.contains("ws-opts")&&!n.parameters.value("ws-opts").isObject())return "WebSocket 配置类型无效。";
    const auto ws=n.parameters.value("ws-opts").toObject();
    for(auto p=ws.begin();p!=ws.end();++p)if(p.key()!="path"&&p.key()!="headers")return "WebSocket 含未实现的扩展，未忽略。";
    if(ws.contains("path")&&!ws.value("path").isString())return "WebSocket 路径类型无效。";
    QString host=n.host.contains(':')?"["+n.host+"]":n.host;
    if(ws.contains("headers")){
     if(!ws.value("headers").isObject())return "WebSocket 请求头类型无效。";
     const auto headers=ws.value("headers").toObject();if(headers.size()>1)return "WebSocket 此阶段只支持 Host 请求头。";
     for(auto h=headers.begin();h!=headers.end();++h){if(h.key().compare("host",Qt::CaseInsensitive)!=0||!h.value().isString())return "WebSocket 请求头尚未实现。";host=h.value().toString();}
    }
    const auto path=ws.contains("path")?ws.value("path").toString():QString("/");
    if(host.isEmpty()||host.contains(QRegularExpression("[\\\\s/@?#]"))||!path.startsWith('/')||path.startsWith("//")||path.size()>2048||path.contains(QRegularExpression("[\\\\s#]")))return "WebSocket Host 或路径无效。";
    const auto alpn=outbound.value("tls").toObject().value("alpn").toArray();
    if(!alpn.isEmpty()&&alpn!=QJsonArray{"http/1.1"})return "WebSocket 目前仅支持 HTTP/1.1 ALPN。";
    outbound["websocket"]=QJsonObject{{"host",host},{"path",path}};
   }else if(n.parameters.contains("ws-opts"))return "TCP 传输不能附带 WebSocket 配置。";
  }
  nodes.append(QJsonObject{{"id",n.id},{"outbound",outbound}});''')
for name,text in changes.items():
    Path(name).write_text(text,encoding='utf-8')
    print('Updated source:',name)

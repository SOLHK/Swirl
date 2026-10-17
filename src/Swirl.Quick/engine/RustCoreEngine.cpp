#include "RustCoreEngine.h"
#include "RustDnsConfiguration.h"
#include <QCoreApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QDateTime>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QUuid>
#include <QSet>
#include <QHostAddress>
#include <QRegularExpression>
#include <algorithm>
#include <functional>

namespace {
QString dnsConfiguration(const EngineStartOptions &o,QJsonObject *output){
 return SwirlRustDns::configuration(o.dnsConfig,output);
}

QString routingConfiguration(const EngineStartOptions &o,const QString &selected,QJsonArray *nodes,QJsonArray *rules,QJsonArray *selectors){
 if(o.directSession||o.routingMode!="rule")return {};
 if(o.customRules.size()>1000)return "Rust 自定义规则数量超过限制。";
 QSet<QString> reserved;for(const auto &n:o.nodes)reserved.insert(n.id);
 const auto unique=[&](const QString &base){QString id=base;int suffix=0;while(reserved.contains(id))id=base+'-'+QString::number(++suffix);reserved.insert(id);return id;};
 const auto direct=unique("swirl-rule-direct"),reject=unique("swirl-rule-reject");
 bool needsDirect=false,needsReject=false;int index=0;
 QHash<QString,QString> groups;QSet<QString> included{selected};
 const auto invalidGroup=[] {return QString("Rust 策略组参数无效或尚未支持；配置保持原值，未忽略该组。");};
 if(o.customGroups.size()>128)return "Rust 策略组数量超过限制。";
 // Allocate every name before resolving members so forward references have
 // the same meaning as backward references. Node IDs and group names may not
 // be ambiguous, and generated IR IDs never collide with stored node IDs.
 for(const auto &value:o.customGroups){
  if(!QJsonValue::fromVariant(value).isObject())return invalidGroup();
  const auto group=QJsonObject::fromVariantMap(value.toMap());
  const auto name=group.value("name").toString();
  if(name.isEmpty()||name!=name.trimmed()||name.size()>100||name.contains(QRegularExpression("[,\\x00-\\x1f\\x7f]"))||QStringList{"DIRECT","REJECT","SWIRL","GLOBAL"}.contains(name)||groups.contains(name))return invalidGroup();
  for(const auto &node:o.nodes)if(node.id==name)return invalidGroup();
  groups.insert(name,unique("swirl-group-"+QString::number(groups.size())));
 }
 QHash<QString,QStringList> edges;int automaticCount=0,probeCount=0;
 for(const auto &value:o.customGroups){
  const auto group=QJsonObject::fromVariantMap(value.toMap());const auto name=group.value("name").toString();
  const auto type=group.value("type").toString();const bool manual=type=="select";
  if(!QStringList{"select","url-test","fallback","load-balance"}.contains(type)||!group.value("proxies").isArray())return invalidGroup();
  const QStringList allowed=manual?QStringList{"name","type","proxies","default-selected","url","interval"}
   :QStringList{"name","type","proxies","url","interval","timeout","expected-status","tolerance","strategy"};
  for(auto it=group.begin();it!=group.end();++it)if(!allowed.contains(it.key()))return invalidGroup();
  QJsonObject selector{{"id",groups.value(name)}};
  if(manual){
   // The existing editor writes these exact placeholders on manual groups.
   // Custom probe settings must not be silently discarded on select groups.
   if(group.contains("url")&&group.value("url").toString()!="https://www.gstatic.com/generate_204")return invalidGroup();
   if(group.contains("interval")&&(!group.value("interval").isDouble()||group.value("interval").toDouble()!=300))return invalidGroup();
  }else{
   if(type=="load-balance"){
    // Mihomo defaults to hashing, while native Swirl implements per-session
    // round robin. An absent/different strategy cannot be safely translated.
    if(group.value("strategy").toString()!="round-robin")return "Rust 负载均衡目前只支持显式 strategy=round-robin；未将默认哈希策略改成轮询。";
   }else if(group.contains("strategy"))return invalidGroup();
   const auto integer=[&](const QString &key,int fallback,int low,int high){
    if(!group.contains(key))return fallback;const auto v=group.value(key);
    if(!v.isDouble()||v.toDouble()<low||v.toDouble()>high||v.toDouble()!=v.toInt())return -1;return v.toInt();
   };
   // URL is explicit. Seconds in existing Qt groups become milliseconds in
   // Swirl IR. The exact expected status defaults to the editor's 204 target.
   const auto text=group.value("url").toString();const QUrl url(text,QUrl::StrictMode);
   const auto host=url.host();const auto address=QHostAddress(host);
   const QRegularExpression hostSyntax("^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$");
   if(text.size()>2048||!QRegularExpression("^[\\x21-\\x7e]+$").match(text).hasMatch()||text.contains('\\')||!url.isValid()
    ||!QStringList{"http","https"}.contains(url.scheme())||!url.userInfo().isEmpty()||url.hasFragment()||url.authority().contains('@')
    ||host.isEmpty()||host.size()>253||(!address.scopeId().isEmpty())||(address.isNull()&&!hostSyntax.match(host).hasMatch())||url.port(80)<1)return invalidGroup();
   const int interval=integer("interval",300,1,3600),timeout=integer("timeout",5000,100,30000),status=integer("expected-status",204,200,299),tolerance=integer("tolerance",0,0,10000);
   if(interval<0||timeout<0||timeout>interval*1000||status<0||tolerance<0||(type!="url-test"&&tolerance!=0))return invalidGroup();
   selector["strategy"]=type=="url-test"?"url_test":type=="fallback"?"fallback":"load_balance";
   selector["probe"]=QJsonObject{{"url",text},{"interval_ms",interval*1000},{"timeout_ms",timeout},{"expected_status",status},{"tolerance_ms",tolerance}};
  }
  const auto members=group.value("proxies").toArray();if(members.isEmpty()||members.size()>(manual?512:64))return invalidGroup();
  if(!manual&&(++automaticCount>32||(probeCount+=members.size())>512))return invalidGroup();
  QJsonArray mapped;QSet<QString> seen;QHash<QString,QString> memberIds;
  for(const auto &memberValue:members){
   if(!memberValue.isString())return invalidGroup();const auto member=memberValue.toString();if(member.isEmpty()||seen.contains(member))return invalidGroup();seen.insert(member);
   QString id=member;
   if(member=="DIRECT"){id=direct;needsDirect=true;}
   else if(member=="REJECT"){if(!manual)return invalidGroup();id=reject;needsReject=true;}
   else if(groups.contains(member)){
    if(!manual)return "Rust 自动策略组成员必须是具体节点；尚未支持自动组探测嵌套组。";
    id=groups.value(member);edges[name].append(member);
   }
   else if(!included.contains(member)){
    // Reuse precisely the same protocol validation as the top-level selection.
    // Clearing groups/rules makes this a single bounded leaf conversion.
    auto leaf=o;leaf.customGroups.clear();leaf.customRules.clear();leaf.routingMode="global";leaf.smartRouting=false;leaf.selectedNodeId=member;
    QJsonObject config;if(!RustCoreEngine::configuration(leaf,&config).isEmpty())return invalidGroup();
    nodes->append(config.value("nodes").toArray().first());included.insert(member);if(nodes->size()>512)return invalidGroup();
   }
   memberIds.insert(member,id);mapped.append(id);
  }
  selector["members"]=mapped;
  if(manual){
   QString chosen=members.first().toString();
   if(group.contains("default-selected")){if(!group.value("default-selected").isString())return invalidGroup();chosen=group.value("default-selected").toString();}
   if(!memberIds.contains(chosen))return invalidGroup();selector["selected"]=memberIds.value(chosen);
  }
  selectors->append(selector);
 }
 // Validate every edge, including inactive alternatives. This mirrors the
 // native IR's 16-group depth bound before saving or activating Qt settings.
 QSet<QString> visiting;QHash<QString,int> depths;
 const std::function<int(const QString &)> depth=[&](const QString &name){
  if(visiting.contains(name))return 17;if(depths.contains(name))return depths.value(name);
  visiting.insert(name);int longest=1;for(const auto &member:edges.value(name)){longest=qMax(longest,1+depth(member));if(longest>16)break;}
  visiting.remove(name);depths.insert(name,longest);return longest;
 };
 for(auto it=groups.cbegin();it!=groups.cend();++it)if(depth(it.key())>16)return "Rust 策略组存在循环或超过 16 层嵌套；未应用配置。";
 for(const auto &line:o.customRules){
  ++index;const auto invalid=[index]{return QString("第 %1 条规则无效或 Rust 尚未支持；未忽略该规则。").arg(index);};
  if(line.size()>2300||line.contains('\n')||line.contains('\r')||line.contains(QChar(0)))return invalid();
  auto parts=line.split(',');for(auto &part:parts)part=part.trimmed();
  const auto type=parts.value(0);const bool final=type=="MATCH";
  const bool cidr=type=="IP-CIDR"||type=="IP-CIDR6";
  const bool noResolve=cidr&&parts.size()==4&&parts[3]=="no-resolve";
  if(parts.size()!=(final?2:3)&&!noResolve)return invalid();
  const auto pattern=final?QString():parts[1];const auto policy=parts[final?1:2];
  QJsonObject matcher;
  if(final)matcher={{"type","match"}};
  else if(type=="DOMAIN"||type=="DOMAIN-SUFFIX"){
   if(pattern.size()>253||!QRegularExpression("^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$").match(pattern).hasMatch())return invalid();
   matcher={{"type",type=="DOMAIN"?"domain":"domain_suffix"},{"value",pattern.toLower()}};
  }else if(type=="DOMAIN-KEYWORD"){
   if(!QRegularExpression("^[A-Za-z0-9_.-]{1,253}$").match(pattern).hasMatch())return invalid();
   matcher={{"type","domain_keyword"},{"value",pattern.toLower()}};
  }else if(cidr||type=="SRC-IP-CIDR"){
   if(!pattern.contains('/'))return invalid();
   const auto subnet=QHostAddress::parseSubnet(pattern);
   if(subnet.first.isNull()||subnet.second<0||(type=="IP-CIDR"&&subnet.first.protocol()!=QAbstractSocket::IPv4Protocol)||(type=="IP-CIDR6"&&subnet.first.protocol()!=QAbstractSocket::IPv6Protocol))return invalid();
   matcher={{"type",cidr?"cidr":"source_cidr"},{"value",subnet.first.toString()+"/"+QString::number(subnet.second)}};
   if(cidr)matcher["resolve"]=!noResolve;
  }else if(type=="DST-PORT"){
   bool ok=false;const auto port=pattern.toUInt(&ok);
   if(!ok||port==0||port>65535||!QRegularExpression("^[0-9]+$").match(pattern).hasMatch())return invalid();
   matcher={{"type","destination_port"},{"value",int(port)}};
  }else return invalid();
  QString outbound;
  if(policy=="SWIRL")outbound=selected;
  else if(policy=="DIRECT"){outbound=direct;needsDirect=true;}
  else if(policy=="REJECT"){outbound=reject;needsReject=true;}
  else if(groups.contains(policy))outbound=groups.value(policy);
  else return invalid();
  rules->append(QJsonObject{{"matcher",matcher},{"outbound",outbound}});
 }
 if(needsDirect)nodes->append(QJsonObject{{"id",direct},{"outbound",QJsonObject{{"type","direct"}}}});
 if(needsReject)nodes->append(QJsonObject{{"id",reject},{"outbound",QJsonObject{{"type","reject"}}}});
 if(nodes->size()>512)return invalidGroup();
 return {};
}
}

RustCoreEngine::RustCoreEngine(QObject *parent):ProxyEngine(parent){
 m_poll.setInterval(250);connect(&m_poll,&QTimer::timeout,this,&RustCoreEngine::refresh);
 m_network.setProxy(QNetworkProxy::NoProxy);
 m_status.engineName="Swirl Core Rust";m_status.engineKind="rust";
}
// Owners can destroy their telemetry members before their engine member.
// Shutdown during destruction must not signal those partially destroyed owners.
RustCoreEngine::~RustCoreEngine(){disconnect();stop();}
QString RustCoreEngine::configurationSummary()const{return "Swirl Core Rust · Mixed HTTP/SOCKS5 · 原生 TCP/有界 UDP · 无外部内核回退";}
QString RustCoreEngine::validatePolicyGroups(const QList<ProxyNode> &nodes,const QVariantList &groups){
 EngineStartOptions options;options.nodes=nodes;options.customGroups=groups;
 QJsonArray mapped,rules,selectors;return routingConfiguration(options,{},&mapped,&rules,&selectors);
}
QVariantList RustCoreEngine::routingRules()const{
 QVariantList rows;int order=0;const bool direct=m_options.directSession||m_options.routingMode=="direct";
 if(!direct&&m_options.routingMode=="rule")for(const auto &line:m_options.customRules){
  const auto parts=line.split(',');const bool final=parts.value(0).trimmed()=="MATCH";
  rows.append(QVariantMap{{"id",QString::number(order)},{"order",order},{"customIndex",order},{"type",final?"FINAL":parts.value(0).trimmed()},{"pattern",final?QString():parts.value(1).trimmed()},{"policy",parts.value(final?1:2).trimmed()},{"hits","—"}});++order;
 }
 rows.append(QVariantMap{{"id","final"},{"order",order},{"type","FINAL"},{"pattern",""},{"policy",direct?"DIRECT":"SWIRL"},{"hits","—"}});
 return rows;
}
QString RustCoreEngine::configuration(const EngineStartOptions &o,QJsonObject *output){
 if(o.preferCompatibility||o.tunEnabled||o.gatewayForwarding||o.allowLan||o.meteredNetwork||(o.smartRouting&&o.routingMode=="rule"&&!o.directSession))
  return "当前 Rust 阶段尚未迁移此会话的 TUN、LAN、智能规则库或兼容模式；已拒绝启动，不回退外部内核。";
 if(o.routingMode!="global"&&o.routingMode!="rule"&&o.routingMode!="direct")return "Rust 路由模式无效。";
 QJsonObject dns;const auto dnsError=dnsConfiguration(o,&dns);if(!dnsError.isEmpty())return dnsError;
 QJsonArray nodes;QString selected=o.selectedNodeId;
 if(o.directSession||o.routingMode=="direct") {selected="explicit-direct";nodes.append(QJsonObject{{"id",selected},{"outbound",QJsonObject{{"type","direct"}}}});}
 else {
  // First map the default route. Policy groups add their referenced members.
  // Unreferenced unsupported imports remain in NodeStore without activation.
  const auto it=std::find_if(o.nodes.cbegin(),o.nodes.cend(),[&](const auto &n){return n.id==selected;});
  if(it==o.nodes.cend())return "未选择节点。";
  const auto &n=*it;
  if(!n.conversionIssues.isEmpty()||!ProxyNode::validate(n).isEmpty())return "节点含无效或未映射参数，Rust 拒绝执行。";
  if(!QStringList{"http","socks4","socks4a","socks5","trojan","ss","vless"}.contains(n.protocol))return "此节点协议尚未迁移到 Rust；未使用外部内核。";
  const bool socks4=n.protocol=="socks4"||n.protocol=="socks4a";
  QSet<QString> allowed=socks4?QSet<QString>{"tls","udp","network","tfo","skip-cert-verify"}:n.protocol=="ss"?QSet<QString>{"udp","plugin","plugin-opts"}:QSet<QString>{"tls","udp","sni","servername","alpn","skip-cert-verify"};
  if(n.protocol=="vless")allowed.unite(QSet<QString>{"uuid","flow","encryption"});
  if(n.protocol=="vless"||n.protocol=="trojan")allowed.unite(QSet<QString>{"network","ws-opts"});
  for(auto p=n.parameters.begin();p!=n.parameters.end();++p)if(!allowed.contains(p.key()))return "Rust 尚未实现此传输或扩展参数。";
  for(const auto &key:QStringList{"tls","udp","skip-cert-verify"})if(n.parameters.contains(key)&&!n.parameters.value(key).isBool())return "Rust 布尔参数类型无效。";
  if((n.protocol!="ss"&&n.parameters.value("udp").toBool())||n.parameters.value("skip-cert-verify").toBool())return "Rust 尚不支持该出口的代理 UDP，且不允许关闭证书验证。";
  for(const auto &key:QStringList{"sni","servername"})if(n.parameters.contains(key)&&(!n.parameters.value(key).isString()||n.parameters.value(key).toString()!=n.serverName))return "TLS 名称字段不一致。";
  if(n.protocol=="trojan"&&n.parameters.contains("tls")&&!n.parameters.value("tls").toBool())return "Trojan 必须使用 TLS。";
  const bool tls=n.protocol=="trojan"||n.parameters.value("tls").toBool();
  if(!tls&&(!n.serverName.isEmpty()||n.parameters.contains("alpn")))return "未启用 TLS 却含 TLS 参数。";
  QJsonObject outbound{{"type",socks4?"socks4":n.protocol=="http"?"http_connect":n.protocol=="ss"?"shadowsocks":n.protocol},{"host",n.host},{"port",n.port}};
  if(socks4){
   if(tls||!n.cipher.isEmpty()||(n.parameters.contains("tfo")&&n.parameters.value("tfo")!=QJsonValue(false)))return "SOCKS4/4a 不支持 TLS、密码加密或 TCP Fast Open。";
   if(n.parameters.contains("network")&&n.parameters.value("network")!=QJsonValue(QStringLiteral("tcp")))return "SOCKS4/4a 此阶段只支持 TCP。";
   outbound["user_id"]=n.username;outbound["remote_dns"]=n.protocol=="socks4a";
  }
  else if(n.protocol=="ss"){
   if(!n.username.isEmpty()||!QStringList{"aes-128-gcm","aes-256-gcm","chacha20-ietf-poly1305"}.contains(n.cipher))return "Rust 尚未实现此 Shadowsocks 加密或认证方式。";
   outbound["password"]=n.password;outbound["cipher"]=n.cipher;outbound["udp"]=n.parameters.value("udp").toBool();
   if(n.parameters.contains("plugin")){
    if(!n.parameters.value("plugin").isString()||!QStringList{"obfs","obfs-local","simple-obfs"}.contains(n.parameters.value("plugin").toString())||!n.parameters.value("plugin-opts").isObject())return "Rust 尚未实现此 Shadowsocks 插件。";
    const auto plugin=n.parameters.value("plugin-opts").toObject();
    for(auto p=plugin.begin();p!=plugin.end();++p)if(p.key()!="mode"&&p.key()!="host")return "Rust 尚未映射此混淆参数。";
    if(plugin.value("mode").toString()!="http"||!plugin.value("host").isString()||plugin.value("host").toString().isEmpty())return "Rust 目前只支持显式主机的 HTTP 混淆。";
    outbound["obfs_http"]=QJsonObject{{"host",plugin.value("host")}};
   }else if(n.parameters.contains("plugin-opts"))return "缺少 Shadowsocks 插件类型。";
  }
  else if(n.protocol=="vless"){
   if(!n.username.isEmpty()||!n.password.isEmpty())return "VLESS 只支持 UUID 认证。";
   if(n.parameters.contains("flow")&&(!n.parameters.value("flow").isString()||!n.parameters.value("flow").toString().isEmpty()))return "Rust 尚未实现 VLESS flow/Vision。";
   if(n.parameters.contains("encryption")&&n.parameters.value("encryption").toString()!="none")return "Rust 尚未实现该 VLESS encryption 扩展。";
   outbound["uuid"]=QUuid(n.parameters.value("uuid").toString()).toString(QUuid::WithoutBraces);
  }
  else if(n.protocol=="trojan")outbound["password"]=n.password;
  else if(!n.username.isEmpty()||!n.password.isEmpty())outbound["auth"]=QJsonObject{{"username",n.username},{"password",n.password}};
  if(tls){
   auto alpn=n.parameters.value("alpn");if(!alpn.isUndefined()&&!alpn.isArray())return "ALPN 格式无效。";
   outbound["tls"]=QJsonObject{{"server_name",n.serverName.isEmpty()?n.host:n.serverName},{"alpn",alpn.isUndefined()?QJsonArray{}:alpn.toArray()}};
  }
  // Native WS mapping; no QML changes.
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
    if(host.isEmpty()||host.contains(QRegularExpression("[\\s/@?#]"))||!path.startsWith('/')||path.startsWith("//")||path.size()>2048||path.contains(QRegularExpression("[\\s#]")))return "WebSocket Host 或路径无效。";
    const auto alpn=outbound.value("tls").toObject().value("alpn").toArray();
    if(!alpn.isEmpty()&&alpn!=QJsonArray{"http/1.1"})return "WebSocket 目前仅支持 HTTP/1.1 ALPN。";
    outbound["websocket"]=QJsonObject{{"host",host},{"path",path}};
   }else if(n.parameters.contains("ws-opts"))return "TCP 传输不能附带 WebSocket 配置。";
  }
  nodes.append(QJsonObject{{"id",n.id},{"outbound",outbound}});
 }
 QJsonArray rules,selectors;const auto routingError=routingConfiguration(o,selected,&nodes,&rules,&selectors);if(!routingError.isEmpty())return routingError;
 QJsonObject config{{"schema",1},{"listen",QString("127.0.0.1:%1").arg(o.proxyPort)},{"selected",selected},{"nodes",nodes},{"rules",rules},{"selectors",selectors},{"dns",dns},
  {"limits",QJsonObject{{"max_connections",128},{"handshake_timeout_ms",qBound(100,o.startupTimeoutMs,30000)}}}};
 if(!o.inboundUsername.isEmpty()||!o.inboundPassword.isEmpty())config["inbound_auth"]=QJsonObject{{"username",o.inboundUsername},{"password",o.inboundPassword}};
 *output=config;return {};
}
QJsonObject RustCoreEngine::call(QJsonObject command){
 if(!m_command)return {{"ok",false},{"error","RustLibraryUnavailable"}};
 auto input=QJsonDocument(command).toJson(QJsonDocument::Compact);QByteArray output(1024*1024,Qt::Uninitialized);
 const auto count=m_command(reinterpret_cast<const unsigned char *>(input.constData()),size_t(input.size()),reinterpret_cast<unsigned char *>(output.data()),size_t(output.size()));input.fill('\0');
 if(count<=0||count>output.size())return {{"ok",false},{"error","RustAbiFailure"}};
 output.resize(count);return QJsonDocument::fromJson(output).object();
}
void RustCoreEngine::fail(Error error,const QString &reason){m_status.state=State::Failed;m_status.error=error;m_status.message=reason;m_status.apiHealthy=false;emit diagnostic("SwirlRust","CoreFailure",reason);emit statusChanged();}
void RustCoreEngine::start(const EngineStartOptions &options){
 stop();m_options=options;m_status={};m_status.engineName="Swirl Core Rust";m_status.engineKind="rust";
 QJsonObject config;const auto reason=configuration(options,&config);if(!reason.isEmpty()){fail(Error::InvalidOptions,reason);return;}
 if(!m_command){
  m_library.setFileName(QCoreApplication::applicationDirPath()+"/swirl_api");
  // Keep code mapped: cancelled OS DNS work can finish after bounded shutdown.
  m_library.setLoadHints(QLibrary::PreventUnloadHint);
  if(!m_library.load()){fail(Error::MissingExecutable,"Swirl Rust DLL 不可用；未切换到外部内核。");return;}
  auto version=reinterpret_cast<quint32(*)()>(m_library.resolve("swirl_core_abi_version"));
  m_command=reinterpret_cast<Command>(m_library.resolve("swirl_core_command"));
  if(!version||version()!=1||!m_command){m_command=nullptr;fail(Error::InvalidResponse,"Rust ABI 版本不兼容。");return;}
 }
 const auto response=call({{"op","start"},{"config",config}});
 if(!response["ok"].toBool()){fail(Error::ConfigurationFailed,response["error"].toString("RustStartFailed"));return;}
 m_handle=quint64(response["handle"].toInteger());m_status.sessionId=QUuid::createUuid().toString(QUuid::WithoutBraces);
 m_status.processId=QCoreApplication::applicationPid();m_status.version="Swirl Core Rust 0.1";m_status.controlEndpoint="in-process://SwirlRust/v1";
 m_status.mode=options.routingMode;m_status.directSession=options.directSession||options.routingMode=="direct";
 m_status.selectedNodeId=options.selectedNodeId;m_status.proxyPort=options.proxyPort;
 m_uptime.start();m_rateClock.start();m_poll.start();refresh();
}
void RustCoreEngine::stop(){
 m_poll.stop();if(m_reply){m_reply->disconnect(this);m_reply->abort();m_reply->deleteLater();m_reply=nullptr;}
 if(m_handle){call({{"op","stop"},{"handle",qint64(m_handle)}});m_handle=0;}
 m_status.state=State::Stopped;m_status.processAlive=false;m_status.apiHealthy=false;m_status.nodeBusy=false;m_status.proxyPort=0;m_status.connections.clear();emit statusChanged();
}
void RustCoreEngine::refresh(){
 if(!m_handle)return;
 const auto response=call({{"op","snapshot"},{"handle",qint64(m_handle)}});
 if(!response["ok"].toBool()){fail(Error::ApiUnavailable,"Rust 状态读取失败。");return;}
 const auto state=response["status"].toObject();const auto elapsed=m_rateClock.restart();
 const auto up=state["upload"].toInteger(),down=state["download"].toInteger();
 m_status.uploadRate=elapsed>0?double(up-m_status.uploadTotal)*1000/elapsed:0;m_status.downloadRate=elapsed>0?double(down-m_status.downloadTotal)*1000/elapsed:0;
 m_status.uploadTotal=up;m_status.downloadTotal=down;m_status.processAlive=state["running"].toBool();m_status.apiHealthy=m_status.processAlive;
 m_status.state=m_status.processAlive?State::Running:State::Failed;m_status.uptimeSeconds=m_uptime.elapsed()/1000;
 m_status.connectionsAt=m_status.trafficAt=qMax(QDateTime::currentMSecsSinceEpoch(),m_status.connectionsAt+1);m_status.connections.clear();
 for(const auto &value:state["connections"].toArray()){
  const auto row=value.toObject();const auto node=row["node"].toString();
  m_status.connections.append(QVariantMap{{"id",QString::number(row["id"].toInteger())},{"host",row["host"].toString()},{"port",row["port"].toInt()},
   {"sourceIp",row["source_ip"].toString()},{"sourcePort",row["source_port"].toInt()},{"policy",node},{"nodeChain",QStringList{node}},{"category",row["category"].toString()},
   {"closed",row["ended"].toBool()},{"uploadBytes",row["upload"].toInteger()},{"downloadBytes",row["download"].toInteger()},
   {"time",QDateTime::fromMSecsSinceEpoch(m_status.connectionsAt-row["elapsed_ms"].toInteger()).toString(Qt::ISODateWithMs)},{"process","未知进程"}});
 }
 emit statusChanged();
}
void RustCoreEngine::selectNode(const QString &id){
 if(!m_handle)return;auto options=m_options;options.selectedNodeId=id;options.directSession=false;
 QJsonObject config;const auto reason=configuration(options,&config);if(!reason.isEmpty()){emit diagnostic("SwirlRust","SelectionUnsupported",reason);return;}
 const auto result=call({{"op","configure"},{"handle",qint64(m_handle)},{"config",config}});
 if(!result["ok"].toBool()){emit diagnostic("SwirlRust","SelectionFailed",result["error"].toString());return;}
 m_options=options;m_status.selectedNodeId=id;m_status.directSession=options.directSession||options.routingMode=="direct";m_status.requestState=RequestState::NotTested;refresh();
}
void RustCoreEngine::setRoutingMode(const QString &mode){
 if(!m_handle)return;auto options=m_options;options.routingMode=mode;QJsonObject config;const auto reason=configuration(options,&config);
 if(!reason.isEmpty()){emit diagnostic("SwirlRust","RoutingUnsupported",reason);return;}
 const auto result=call({{"op","configure"},{"handle",qint64(m_handle)},{"config",config}});
 if(!result["ok"].toBool()){emit diagnostic("SwirlRust","RoutingFailed",result["error"].toString());return;}
 m_options=options;m_status.mode=mode;m_status.directSession=options.directSession||mode=="direct";refresh();
}
void RustCoreEngine::probeNode(const QUrl &url){
 if(!m_handle||m_reply)return;
 if(!url.isValid()||!QStringList{"http","https"}.contains(url.scheme())||url.host().isEmpty()||!url.userInfo().isEmpty()||url.hasFragment())return;
 m_network.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",m_status.proxyPort,m_options.inboundUsername,m_options.inboundPassword));
 QNetworkRequest request(url);request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);request.setTransferTimeout(8000);request.setRawHeader("Connection","close");
 auto reply=m_network.get(request);m_reply=reply;reply->setReadBufferSize(65536);auto clock=std::make_shared<QElapsedTimer>();clock->start();
 auto deadline=new QTimer(reply);deadline->setSingleShot(true);connect(deadline,&QTimer::timeout,reply,&QNetworkReply::abort);deadline->start(9000);
 m_status.nodeBusy=true;m_status.requestState=RequestState::InProgress;emit statusChanged();
 connect(reply,&QNetworkReply::readyRead,this,[reply]{const auto count=reply->property("count").toLongLong()+reply->readAll().size();reply->setProperty("count",count);if(count>256*1024)reply->abort();});
 connect(reply,&QNetworkReply::finished,this,[this,reply,clock]{
  m_reply=nullptr;const auto code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&code>=200&&code<300;
  m_status.nodeBusy=false;m_status.requestState=ok?RequestState::Succeeded:RequestState::Failed;m_status.nodeHealth=ok?NodeHealth::Available:NodeHealth::Unavailable;
  m_status.responseCode=code;m_status.latencyMs=ok?int(clock->elapsed()):-1;m_status.nodeMessage=ok?"Rust 原生请求成功":"Rust 原生请求失败；未切换出口或重放请求";reply->deleteLater();refresh();
 });
}

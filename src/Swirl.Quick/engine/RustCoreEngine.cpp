#include "RustCoreEngine.h"
#include <QCoreApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QDateTime>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QUuid>
#include <QSet>
#include <algorithm>

RustCoreEngine::RustCoreEngine(QObject *parent):ProxyEngine(parent){
 m_poll.setInterval(250);connect(&m_poll,&QTimer::timeout,this,&RustCoreEngine::refresh);
 m_network.setProxy(QNetworkProxy::NoProxy);
 m_status.engineName="Swirl Core Rust";m_status.engineKind="rust";
}
RustCoreEngine::~RustCoreEngine(){stop();}
QString RustCoreEngine::configurationSummary()const{return "Swirl Core Rust · Mixed HTTP/SOCKS5 · 原生 TCP/有界 UDP · 无外部内核回退";}
QString RustCoreEngine::configuration(const EngineStartOptions &o,QJsonObject *output){
 if(o.preferCompatibility||o.tunEnabled||o.gatewayForwarding||o.allowLan||o.meteredNetwork||!o.dnsConfig.isEmpty()||!o.customRules.isEmpty()||!o.customGroups.isEmpty()||(o.smartRouting&&o.routingMode=="rule"&&!o.directSession))
  return "当前 Rust 阶段尚未迁移此会话的 TUN、LAN、DNS、规则或兼容模式；已拒绝启动，不回退外部内核。";
 if(o.routingMode!="global"&&o.routingMode!="rule"&&o.routingMode!="direct")return "Rust 路由模式无效。";
 QJsonArray nodes;QString selected=o.selectedNodeId;
 if(o.directSession||o.routingMode=="direct") {selected="explicit-direct";nodes.append(QJsonObject{{"id",selected},{"outbound",QJsonObject{{"type","direct"}}}});}
 else {
  // Only the selected route is executable. Unsupported unselected imports stay
  // in NodeStore and do not prevent connecting a supported node.
  const auto it=std::find_if(o.nodes.cbegin(),o.nodes.cend(),[&](const auto &n){return n.id==selected;});
  if(it==o.nodes.cend())return "未选择节点。";
  const auto &n=*it;
  if(!n.conversionIssues.isEmpty()||!ProxyNode::validate(n).isEmpty())return "节点含无效或未映射参数，Rust 拒绝执行。";
  if(!QStringList{"http","socks5","trojan","ss"}.contains(n.protocol))return "此节点协议尚未迁移到 Rust；未使用外部内核。";
  const QSet<QString> allowed=n.protocol=="ss"?QSet<QString>{"udp","plugin","plugin-opts"}:QSet<QString>{"tls","udp","sni","servername","alpn","skip-cert-verify"};
  for(auto p=n.parameters.begin();p!=n.parameters.end();++p)if(!allowed.contains(p.key()))return "Rust 尚未实现此传输或扩展参数。";
  for(const auto &key:QStringList{"tls","udp","skip-cert-verify"})if(n.parameters.contains(key)&&!n.parameters.value(key).isBool())return "Rust 布尔参数类型无效。";
  if((n.protocol!="ss"&&n.parameters.value("udp").toBool())||n.parameters.value("skip-cert-verify").toBool())return "Rust 尚不支持该出口的代理 UDP，且不允许关闭证书验证。";
  for(const auto &key:QStringList{"sni","servername"})if(n.parameters.contains(key)&&(!n.parameters.value(key).isString()||n.parameters.value(key).toString()!=n.serverName))return "TLS 名称字段不一致。";
  if(n.protocol=="trojan"&&n.parameters.contains("tls")&&!n.parameters.value("tls").toBool())return "Trojan 必须使用 TLS。";
  const bool tls=n.protocol=="trojan"||n.parameters.value("tls").toBool();
  if(!tls&&(!n.serverName.isEmpty()||n.parameters.contains("alpn")))return "未启用 TLS 却含 TLS 参数。";
  QJsonObject outbound{{"type",n.protocol=="http"?"http_connect":n.protocol=="ss"?"shadowsocks":n.protocol},{"host",n.host},{"port",n.port}};
  if(n.protocol=="ss"){
   if(!n.username.isEmpty()||!QStringList{"aes-128-gcm","aes-256-gcm","chacha20-ietf-poly1305"}.contains(n.cipher))return "Rust 尚未实现此 Shadowsocks 加密或认证方式。";
   outbound["password"]=n.password;outbound["cipher"]=n.cipher;
   if(n.parameters.contains("plugin")){
    if(!n.parameters.value("plugin").isString()||!QStringList{"obfs","obfs-local"}.contains(n.parameters.value("plugin").toString())||!n.parameters.value("plugin-opts").isObject())return "Rust 尚未实现此 Shadowsocks 插件。";
    const auto plugin=n.parameters.value("plugin-opts").toObject();
    for(auto p=plugin.begin();p!=plugin.end();++p)if(p.key()!="mode"&&p.key()!="host")return "Rust 尚未映射此混淆参数。";
    if(plugin.value("mode").toString()!="http"||!plugin.value("host").isString()||plugin.value("host").toString().isEmpty())return "Rust 目前只支持显式主机的 HTTP 混淆。";
    outbound["obfs_http"]=QJsonObject{{"host",plugin.value("host")}};
   }else if(n.parameters.contains("plugin-opts"))return "缺少 Shadowsocks 插件类型。";
  }
  else if(n.protocol=="trojan")outbound["password"]=n.password;
  else if(!n.username.isEmpty()||!n.password.isEmpty())outbound["auth"]=QJsonObject{{"username",n.username},{"password",n.password}};
  if(tls){
   auto alpn=n.parameters.value("alpn");if(!alpn.isUndefined()&&!alpn.isArray())return "ALPN 格式无效。";
   outbound["tls"]=QJsonObject{{"server_name",n.serverName.isEmpty()?n.host:n.serverName},{"alpn",alpn.isUndefined()?QJsonArray{}:alpn.toArray()}};
  }
  nodes.append(QJsonObject{{"id",n.id},{"outbound",outbound}});
 }
 QJsonObject config{{"schema",1},{"listen",QString("127.0.0.1:%1").arg(o.proxyPort)},{"selected",selected},{"nodes",nodes},
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
 m_options=options;m_status.selectedNodeId=id;m_status.directSession=false;m_status.requestState=RequestState::NotTested;refresh();
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

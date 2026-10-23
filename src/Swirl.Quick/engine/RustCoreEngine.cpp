#include "RustCoreEngine.h"
#include "RustDnsConfiguration.h"
#include "XrayJsonBridge.h"
#include "NativeNodeBridge.h"
#include <QCoreApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QDateTime>
#include <QUuid>
#include <QSet>
#include <QHostAddress>
#include <QRegularExpression>
#include <algorithm>
#include <functional>
#include <limits>

namespace {
const QStringList &privateSubnets(){
 static const QStringList values{"127.0.0.0/8","10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","169.254.0.0/16","100.64.0.0/10","::1/128","fc00::/7","fe80::/10"};
 return values;
}
QString dnsConfiguration(const EngineStartOptions &o,QJsonObject *output){
 return SwirlRustDns::configuration(o.dnsConfig,output);
}

QString routingConfiguration(const EngineStartOptions &o,const QString &selected,QJsonArray *nodes,QJsonArray *rules,QJsonArray *selectors){
 if(o.directSession||o.routingMode!="rule")return {};
 if(o.customRules.size()>1000)return "Rust 自定义规则数量超过限制。";
 QSet<QString> reserved;for(const auto &n:o.nodes)reserved.insert(n.id);
 const auto unique=[&](const QString &base){QString id=base;int suffix=0;while(reserved.contains(id))id=base+'-'+QString::number(++suffix);reserved.insert(id);return id;};
 const auto direct=unique("swirl-rule-direct"),reject=unique("swirl-rule-reject");
 bool needsDirect=o.smartRouting,needsReject=false;int index=0;
 QHash<QString,QString> groups;QSet<QString> included{selected};
 const auto invalidGroup=[] {return QString("Rust 策略组参数无效或尚未支持；配置保持原值，未忽略该组。");};
 const auto includeNode=[&](const QString &id){
  if(id.isEmpty())return false;if(included.contains(id))return true;
  // Both a rule leaf and a group member use the selected-node converter, so
  // neither boundary can discard protocol, transport or authentication fields.
  auto leaf=o;leaf.customGroups.clear();leaf.customRules.clear();leaf.routingMode="global";leaf.smartRouting=false;leaf.selectedNodeId=id;
  QJsonObject config;if(!RustCoreEngine::configuration(leaf,&config).isEmpty())return false;
  nodes->append(config.value("nodes").toArray().first());included.insert(id);return nodes->size()<=512;
 };
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
    if(!includeNode(member))return invalidGroup();
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
 QJsonObject finalRule;QHash<QByteArray,QPair<int,QString>> seenRules;
 for(const auto &line:o.customRules){
  ++index;const auto invalid=[index]{return QString("第 %1 条规则无效或 Rust 尚未支持；未忽略该规则。").arg(index);};
  if(line.size()>2300||line.contains('\n')||line.contains('\r')||line.contains(QChar(0)))return invalid();
  auto parts=line.split(',');for(auto &part:parts)part=part.trimmed();
  const auto type=parts.value(0);const bool final=type=="MATCH";
  if(final&&o.nativePrivateRouting&&index!=o.customRules.size())return QString("MATCH 必须是最后一条用户规则；第 %1 条之后的规则不会被执行。").arg(index);
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
  else if(includeNode(policy))outbound=policy;
  else return invalid();
  if(o.nativePrivateRouting){
   const auto key=QJsonDocument(matcher).toJson(QJsonDocument::Compact);
   if(seenRules.contains(key)&&seenRules.value(key).second!=outbound)
    return QString("第 %1 条规则与第 %2 条规则的匹配条件相同但出站不同；前者会遮蔽后者，未应用配置。").arg(seenRules.value(key).first).arg(index);
   if(!seenRules.contains(key))seenRules.insert(key,{index,outbound});
  }
  const QJsonObject mapped{{"matcher",matcher},{"outbound",outbound}};
  if(final&&o.nativePrivateRouting)finalRule=mapped;else rules->append(mapped);
 }
 if(o.nativePrivateRouting){
  needsDirect=true;
  for(const auto &subnet:privateSubnets())
   rules->append(QJsonObject{{"matcher",QJsonObject{{"type","cidr"},{"value",subnet},{"resolve",false}}},{"outbound",direct}});
  rules->append(QJsonObject{{"matcher",QJsonObject{{"type","domain"},{"value","localhost"}}},{"outbound",direct}});
  rules->append(QJsonObject{{"matcher",QJsonObject{{"type","domain_suffix"},{"value","local"}}},{"outbound",direct}});
 }
 if(!finalRule.isEmpty())rules->append(finalRule);
 if(needsDirect)nodes->append(QJsonObject{{"id",direct},{"outbound",QJsonObject{{"type","direct"}}}});
 if(needsReject)nodes->append(QJsonObject{{"id",reject},{"outbound",QJsonObject{{"type","reject"}}}});
 if(nodes->size()>512)return invalidGroup();
 return {};
}
}

RustCoreEngine::RustCoreEngine(QObject *parent):ProxyEngine(parent){
 m_poll.setInterval(250);connect(&m_poll,&QTimer::timeout,this,&RustCoreEngine::refresh);
 m_status.engineName="Swirl Core Rust";m_status.engineKind="rust";
}
// Owners can destroy their telemetry members before their engine member.
// Shutdown during destruction must not signal those partially destroyed owners.
RustCoreEngine::~RustCoreEngine(){disconnect();stop();}
QString RustCoreEngine::configurationSummary()const{return "Swirl Core Rust · Mixed HTTP/SOCKS5 · 原生 TCP/有界 UDP · 无外部内核回退";}
QString RustCoreEngine::validateNetworkConfiguration(const QList<ProxyNode> &nodes,const QVariantMap &dns,const QStringList &rules,const QVariantList &groups,bool nativePrivateRouting){
 EngineStartOptions options;options.nodes=nodes;options.dnsConfig=dns;options.customRules=rules;options.customGroups=groups;options.routingMode="rule";options.nativePrivateRouting=nativePrivateRouting;
 QJsonObject mappedDns;const auto error=dnsConfiguration(options,&mappedDns);if(!error.isEmpty())return error;
 QJsonArray mapped,mappedRules,selectors;return routingConfiguration(options,{},&mapped,&mappedRules,&selectors);
}
QString RustCoreEngine::validatePolicyGroups(const QList<ProxyNode> &nodes,const QVariantList &groups){
 EngineStartOptions options;options.nodes=nodes;options.customGroups=groups;
 QJsonArray mapped,rules,selectors;return routingConfiguration(options,{},&mapped,&rules,&selectors);
}
QVariantList RustCoreEngine::routingRules()const{return routingRulesForOptions(m_options);}
QVariantList RustCoreEngine::routingRulesForOptions(const EngineStartOptions &options){
 QVariantList rows;int order=0;const bool direct=options.directSession||options.routingMode=="direct";
 QVariantMap terminal;
 if(!direct&&options.routingMode=="rule")for(int index=0;index<options.customRules.size();++index){
  const auto parts=options.customRules[index].split(',');const bool final=parts.value(0).trimmed()=="MATCH";
  QVariantMap row{{"id",QString::number(index)},{"order",order},{"customIndex",index},{"type",final?"FINAL":parts.value(0).trimmed()},{"pattern",final?QString():parts.value(1).trimmed()},{"policy",parts.value(final?1:2).trimmed()},{"hits","—"}};
  if(final&&options.nativePrivateRouting)terminal=row;else {rows.append(row);++order;}
 }
 if(!direct&&options.routingMode=="rule"&&options.nativePrivateRouting){
  for(const auto &subnet:privateSubnets())rows.append(QVariantMap{{"id","private-"+QString::number(order)},{"order",order++},{"type",subnet.contains(':')?"IP-CIDR6":"IP-CIDR"},{"pattern",subnet},{"policy","DIRECT"},{"hits","—"}});
  for(const auto &pattern:QStringList{"localhost","local"})rows.append(QVariantMap{{"id","private-"+QString::number(order)},{"order",order++},{"type",pattern=="localhost"?"DOMAIN":"DOMAIN-SUFFIX"},{"pattern",pattern},{"policy","DIRECT"},{"hits","—"}});
  if(!terminal.isEmpty()){terminal["order"]=order++;rows.append(terminal);}
 }
 if(terminal.isEmpty())rows.append(QVariantMap{{"id","final"},{"order",order},{"type","FINAL"},{"pattern",""},{"policy",direct?"DIRECT":"SWIRL"},{"hits","—"}});
 return rows;
}
QString RustCoreEngine::configuration(const EngineStartOptions &o,QJsonObject *output){
 if(o.tunEnabled||o.gatewayForwarding)return "当前会话要求增强模式或网关转发，但 Rust 版尚未支持。请在“概览”关闭增强模式后重试。";
 if(o.allowLan)return "当前会话要求局域网代理，但 Rust 版尚未支持。请在“概览”关闭局域网代理后重试。";
 if(o.meteredNetwork)return "当前会话要求计费网络模式，但 Rust 版尚未支持。请在“设置”关闭计费网络模式后重试。";
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
  if(n.isXray()){
   // Persisted capability/cache fields are display data, never authority to
   // start a proxy. Replay the exact bounded source through the Rust parser
   // and converter each time this node enters a selected or rule route.
   if(!ProxyNode::validate(n).isEmpty())return "JSON 节点来源或标识无效；请重新导入。";
   QJsonObject outbound;const auto error=XrayJsonBridge::executableOutbound(n,&outbound);
   if(!error.isEmpty())return error;
   nodes.append(QJsonObject{{"id",n.id},{"outbound",outbound}});
  }else{
  if(!n.conversionIssues.isEmpty()||!ProxyNode::validate(n).isEmpty())return "节点含无效或未映射参数，Rust 拒绝执行。";
  const bool reality=n.protocol=="vless"&&n.parameters.contains("reality-opts");
  // Check the preserved sing-box requirement before accepting its normalized
  // profile. A default inferred by the importer cannot authorize a browser
  // handshake, and a source profile named rustls does not implement uTLS.
  const auto sourceTls=n.originalConfiguration.value("tls").toObject();
  if(sourceTls.contains("utls")){
   if(!sourceTls.value("utls").isObject())return "源配置 uTLS 参数类型无效。";
   const auto utls=sourceTls.value("utls").toObject();
   for(auto p=utls.begin();p!=utls.end();++p)if(p.key()!="enabled"&&p.key()!="fingerprint")return "源配置 uTLS 含未映射参数；未丢弃原值。";
   if(utls.value("enabled")==QJsonValue(true)){
    const auto fingerprint=utls.value("fingerprint");
    if(!reality||sourceTls.value("enabled")!=QJsonValue(true)||sourceTls.value("reality").toObject().value("enabled")!=QJsonValue(true)||!fingerprint.isString()||!QStringList{"chrome","chrome_133"}.contains(fingerprint.toString()))return "源配置 uTLS 仅支持 REALITY 的显式 chrome 或 chrome_133 指纹；未替换原值。";
    if(fingerprint!=n.parameters.value("client-fingerprint"))return "源配置 uTLS 指纹与节点指纹冲突；未覆盖原值。";
   }else if((!utls.value("enabled").isUndefined()&&utls.value("enabled")!=QJsonValue(false))||utls.contains("fingerprint"))return "源配置 uTLS 未明确启用却含指纹要求；未丢弃原值。";
  }
  if(reality&&n.originalConfiguration.value("_swirl-default-client-fingerprint").toBool())return "REALITY 需要源配置明确声明受支持的指纹；未执行导入时推断的默认值。";
  // The same Rust inspector owns non-JSON protocol, transport and UDP
  // mapping. No stale C++ protocol allowlist can hide completed Rust work.
  QJsonObject outbound;const auto error=NativeNodeBridge::executableOutbound(n,&outbound);
  if(!error.isEmpty())return error;
  nodes.append(QJsonObject{{"id",n.id},{"outbound",outbound}});
  }
 }
 QJsonArray rules,selectors;const auto routingError=routingConfiguration(o,selected,&nodes,&rules,&selectors);if(!routingError.isEmpty())return routingError;
 QJsonObject config{{"schema",1},{"listen",QString("127.0.0.1:%1").arg(o.proxyPort)},{"selected",selected},{"nodes",nodes},{"rules",rules},{"selectors",selectors},{"dns",dns},{"smart_routing",o.smartRouting&&o.routingMode=="rule"&&!o.directSession},
  {"limits",QJsonObject{{"max_connections",128},{"handshake_timeout_ms",qBound(100,o.startupTimeoutMs,30000)}}}};
 if(o.smartRouting&&o.routingMode=="rule"&&!o.directSession&&!o.rulesDirectory.isEmpty())
  config["china_rules_directory"]=o.rulesDirectory;
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
void RustCoreEngine::resetProbeState(){
 m_probeRequestId=0;m_probeFailureStage.clear();m_probeOutboundConnectMs=m_probeOriginTlsMs=-1;
 m_status.nodeBusy=false;m_status.requestState=RequestState::NotTested;m_status.nodeHealth=NodeHealth::Unknown;
 m_status.latencyMs=-1;m_status.responseCode=0;m_status.nodeMessage.clear();
}
void RustCoreEngine::cancelProbe(){
 if(m_handle&&m_probeRequestId)call({{"op","probe_cancel"},{"handle",qint64(m_handle)}});
 resetProbeState();
}
void RustCoreEngine::failProbe(const QString &stage,const QString &code,int httpStatus){
 m_probeRequestId=0;m_probeFailureStage=stage;m_probeOutboundConnectMs=m_probeOriginTlsMs=-1;
 m_status.nodeBusy=false;m_status.requestState=RequestState::Failed;
 m_status.nodeHealth=QStringList{"dns","tcp_connect","outbound_handshake","outbound_connect"}.contains(stage)
  ?NodeHealth::Unavailable:NodeHealth::Unknown;
 m_status.latencyMs=-1;m_status.responseCode=httpStatus;
 m_status.nodeMessage=QStringLiteral("Rust HEAD 探测失败（阶段 %1，代码 %2）").arg(stage.isEmpty()?QStringLiteral("unknown"):stage,code);
}
void RustCoreEngine::updateProbe(const QJsonObject &probe){
 const auto requestId=probe.value("request_id").toInteger(-1);
 if(requestId<=0){failProbe("probe_status","ProbeStateInvalid");return;}
 if(requestId!=m_probeRequestId){resetProbeState();return;}
 const auto state=probe.value("state").toString();
 if(state=="running")return;
 if(state=="succeeded"){
  const auto metrics=probe.value("metrics").toObject();
  const auto elapsed=metrics.value("response_headers_ms").toInteger(-1);
  const auto outbound=metrics.value("outbound_connect_ms").toInteger(-1);
  const auto tlsValue=metrics.value("origin_tls_ms");
  const auto originTls=tlsValue.isNull()?-1:tlsValue.toInteger(-1);
  const auto code=metrics.value("http_status").toInt();
  if(elapsed<0||elapsed>std::numeric_limits<int>::max()||outbound<0||outbound>elapsed||(!tlsValue.isNull()&&originTls<0)||code<200||code>=300){failProbe("probe_status","ProbeMetricsInvalid");return;}
  m_probeRequestId=0;m_probeFailureStage.clear();m_status.nodeBusy=false;
  m_probeOutboundConnectMs=outbound;m_probeOriginTlsMs=originTls;
  m_status.requestState=RequestState::Succeeded;m_status.nodeHealth=NodeHealth::Available;
  m_status.latencyMs=int(elapsed);m_status.responseCode=code;
  m_status.nodeMessage=QStringLiteral("Rust HEAD 响应首部已接收");return;
 }
 if(state=="failed"){
  const auto failure=probe.value("failure").toObject();
  failProbe(failure.value("stage").toString("probe_status"),failure.value("code").toString("ProbeFailed"),failure.value("http_status").toInt());return;
 }
 if(state=="idle"||state=="cancelled"){resetProbeState();return;}
 failProbe("probe_status","ProbeStateInvalid");
}
void RustCoreEngine::fail(Error error,const QString &reason){cancelProbe();m_status.state=State::Failed;m_status.error=error;m_status.message=reason;m_status.apiHealthy=false;emit diagnostic("SwirlRust","CoreFailure",reason);emit statusChanged();}
void RustCoreEngine::start(const EngineStartOptions &options){
 QJsonObject config;const auto reason=configuration(options,&config);
 if(m_handle){
  // A duplicate/queued start must not destroy the valid runtime before the
  // candidate has passed every Rust validation. configure commits atomically,
  // retains established streams and rejects listener changes without rebinding.
  if(!reason.isEmpty()){
   emit diagnostic("SwirlRust","CoreStartRejected",reason);emit statusChanged();return;
  }
  const auto response=call({{"op","configure"},{"handle",qint64(m_handle)},{"config",config}});
  if(!response.value("ok").toBool()){
   emit diagnostic("SwirlRust","CoreStartRejected",response.value("error").toString("RustConfigureFailed"));emit statusChanged();return;
  }
  cancelProbe();m_options=options;
  m_status.mode=options.routingMode;m_status.directSession=options.directSession||options.routingMode=="direct";
  m_status.selectedNodeId=options.selectedNodeId;resetProbeState();refresh();return;
 }
 stop();m_options=options;m_status={};m_status.engineName="Swirl Core Rust";m_status.engineKind="rust";
 if(!reason.isEmpty()){fail(Error::InvalidOptions,reason);return;}
 if(!m_command){
  if(!m_library.load()){fail(Error::MissingExecutable,m_library.errorString());return;}
  m_command=m_library.command();
  emit diagnostic("SwirlRust","LibraryReady",QString::fromUtf8(QJsonDocument(m_library.diagnostics()).toJson(QJsonDocument::Compact)));
 }
 const auto response=call({{"op","start"},{"config",config}});
 if(!response["ok"].toBool()){fail(Error::ConfigurationFailed,response["error"].toString("RustStartFailed"));return;}
 m_handle=quint64(response["handle"].toInteger());m_status.sessionId=QUuid::createUuid().toString(QUuid::WithoutBraces);
 m_status.processId=QCoreApplication::applicationPid();m_status.version="Swirl Core Rust "+m_library.diagnostics().value("package_version").toString();m_status.controlEndpoint="in-process://SwirlRust/v1";
 m_status.mode=options.routingMode;m_status.directSession=options.directSession||options.routingMode=="direct";
 m_status.selectedNodeId=options.selectedNodeId;m_status.proxyPort=options.proxyPort;
 m_uptime.start();m_rateClock.start();m_poll.start();refresh();
}
void RustCoreEngine::stop(){
 m_poll.stop();cancelProbe();
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
 m_status.uploadTotal=up;m_status.downloadTotal=down;
 m_status.rustAccepted=state["accepted"].toInteger();m_status.rustFailed=state["failed"].toInteger();
 m_status.rustLastErrorStage=state["last_error_stage"].toString();
 m_status.processAlive=state["running"].toBool();m_status.apiHealthy=m_status.processAlive;
 m_status.state=m_status.processAlive?State::Running:State::Failed;m_status.uptimeSeconds=m_uptime.elapsed()/1000;
 m_status.connectionsAt=m_status.trafficAt=qMax(QDateTime::currentMSecsSinceEpoch(),m_status.connectionsAt+1);m_status.connections.clear();
 for(const auto &value:state["connections"].toArray()){
  const auto row=value.toObject();const auto node=row["node"].toString(),category=row["category"].toString();
  QString proxyNode;
  if(category=="proxy"){
   const auto named=std::find_if(m_options.nodes.cbegin(),m_options.nodes.cend(),[&](const auto &item){return item.id==node;});
   proxyNode=named==m_options.nodes.cend()?node:named->name;
  }
  m_status.connections.append(QVariantMap{{"id",QString::number(row["id"].toInteger())},{"host",row["host"].toString()},{"port",row["port"].toInt()},
   {"sourceIp",row["source_ip"].toString()},{"sourcePort",row["source_port"].toInt()},{"policy",node},{"nodeChain",QStringList{node}},{"category",category},
   {"rule",row["matched_rule"].toString()},{"outbound",category.toUpper()},{"proxyNode",proxyNode},{"transportState",row["transport_state"].toString()},
   {"closed",row["ended"].toBool()},{"uploadBytes",row["upload"].toInteger()},{"downloadBytes",row["download"].toInteger()},
   {"time",QDateTime::fromMSecsSinceEpoch(m_status.connectionsAt-row["elapsed_ms"].toInteger()).toString(Qt::ISODateWithMs)},{"process","未知进程"}});
 }
 if(m_probeRequestId){
  const auto result=call({{"op","probe_status"},{"handle",qint64(m_handle)}});
  if(!result.value("ok").toBool()){cancelProbe();failProbe("probe_status",result.value("error").toString("ProbeStatusFailed"));}
  else updateProbe(result.value("probe").toObject());
 }
 emit statusChanged();
}
void RustCoreEngine::selectNode(const QString &id){
 if(!m_handle)return;cancelProbe();auto options=m_options;options.selectedNodeId=id;options.directSession=false;
 if(options.routingMode=="direct"){
  // Validate the selected node independently of the current DIRECT route.
  // The installed route and its explicit DIRECT status remain unchanged.
  auto candidate=options;candidate.routingMode="global";QJsonObject node;
   const auto reason=configuration(candidate,&node);if(!reason.isEmpty()){emit diagnostic("SwirlRust","SelectionUnsupported",reason);emit statusChanged();return;}
 }
  QJsonObject config;const auto reason=configuration(options,&config);if(!reason.isEmpty()){emit diagnostic("SwirlRust","SelectionUnsupported",reason);emit statusChanged();return;}
 const auto result=call({{"op","configure"},{"handle",qint64(m_handle)},{"config",config}});
  if(!result["ok"].toBool()){emit diagnostic("SwirlRust","SelectionFailed",result["error"].toString());emit statusChanged();return;}
 m_options=options;m_status.selectedNodeId=id;m_status.directSession=options.directSession||options.routingMode=="direct";
 m_status.requestState=RequestState::NotTested;m_status.nodeHealth=NodeHealth::Unknown;
 m_status.latencyMs=-1;m_status.responseCode=0;m_status.nodeMessage.clear();refresh();
}
void RustCoreEngine::setRoutingMode(const QString &mode){
 if(!m_handle)return;cancelProbe();auto options=m_options;options.routingMode=mode;options.directSession=mode=="direct";QJsonObject config;const auto reason=configuration(options,&config);
 if(!reason.isEmpty()){emit diagnostic("SwirlRust","RoutingUnsupported",reason);emit statusChanged();return;}
 const auto result=call({{"op","configure"},{"handle",qint64(m_handle)},{"config",config}});
 if(!result["ok"].toBool()){emit diagnostic("SwirlRust","RoutingFailed",result["error"].toString());emit statusChanged();return;}
 m_options=options;m_status.mode=mode;m_status.directSession=options.directSession||mode=="direct";refresh();
}
void RustCoreEngine::probeNode(const QUrl &url){
 if(!m_handle||m_probeRequestId)return;
 const auto text=url.toString(QUrl::FullyEncoded);
 if(text.size()>2048||!url.isValid()||!QStringList{"http","https"}.contains(url.scheme())||url.host().isEmpty()||!url.userInfo().isEmpty()||url.hasFragment()){
  failProbe("input","ProbeUrlInvalid");emit statusChanged();return;
 }
 resetProbeState();
 const auto response=call({{"op","probe_start"},{"handle",qint64(m_handle)},{"url",text},{"timeout_ms",8000}});
 if(!response.value("ok").toBool()){
  failProbe("probe_start",response.value("error").toString("ProbeStartFailed"));emit statusChanged();return;
 }
 const auto probe=response.value("probe").toObject();const auto requestId=probe.value("request_id").toInteger(-1);
 if(requestId<=0||probe.value("state").toString()!="running"){
  failProbe("probe_start","ProbeStateInvalid");emit statusChanged();return;
 }
 m_probeRequestId=requestId;m_status.nodeBusy=true;m_status.requestState=RequestState::InProgress;
 m_status.nodeHealth=NodeHealth::Checking;emit statusChanged();
}

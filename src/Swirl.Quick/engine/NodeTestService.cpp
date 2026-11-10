#include "NodeTestService.h"
#include "RustCoreEngine.h"
#include "ThreadedEngine.h"
#include <QSet>
#include <QJsonArray>
#include <QJsonObject>
#include <QTimer>
#include <QDateTime>
#include <QPointer>
#include <QCryptographicHash>
NodeTestService::~NodeTestService(){cancel();}
QString NodeTestService::nodeReference(const QString &id){
 return QString::fromLatin1(QCryptographicHash::hash(id.toUtf8(),QCryptographicHash::Sha256).toHex().left(12));
}
QString NodeTestService::failureStatusText(const QVariantMap &result){
 const auto phase=result.value("phase").toString(),code=result.value("failureCode").toString();
 if(code=="ProbeEgressNetworkConflict")return QStringLiteral("网络路由冲突");
 if(code.startsWith("ProbeEgress"))return QStringLiteral("物理出口不可用");
 const bool timeout=QStringList{"UrlTestTimeout","UpstreamDnsTimeout","DnsTimeout","TuicDnsTimeout","Hysteria2DnsTimeout","UpstreamTcpTimeout",
  "UpstreamTlsTimeout","TlsHandshakeIoTimeout","UpstreamProtocolTimeout","QuicHandshakeTimeout","RealityHandshakeTimeout",
  "WebSocketUpgradeTimeout","InitialWriteTimeout","ProbeDeadlineExceeded"}.contains(code);
 const bool certificate=QStringList{"TlsCertificateExpired","TlsCertificateNotValidYet","TlsCertificateNameMismatch",
  "TlsCertificateUnknownIssuer","TlsCertificateRevoked","TlsCertificateInvalid","TlsCertificateMissing"}.contains(code);
 if(phase=="configuration")return QStringLiteral("配置无效");
 if(phase=="startup")return QStringLiteral("内核启动失败");
 if(phase=="dns")return timeout?QStringLiteral("DNS 超时"):QStringLiteral("DNS 失败");
 if(phase=="tcp_connect"||phase=="outbound_connect")return timeout?QStringLiteral("连接超时"):QStringLiteral("连接失败");
 if(phase=="outbound_handshake")return certificate?QStringLiteral("TLS 验证失败"):timeout?QStringLiteral("握手超时"):QStringLiteral("握手失败");
 if(phase=="origin_tls")return timeout?QStringLiteral("目标 TLS 超时"):QStringLiteral("目标 TLS 失败");
 if(phase=="request_write")return timeout?QStringLiteral("请求超时"):QStringLiteral("请求失败");
 if(phase=="response_headers")return timeout?QStringLiteral("响应超时"):QStringLiteral("响应失败");
 if(phase=="http_status")return QStringLiteral("HTTP 异常");
 if(phase=="input")return QStringLiteral("测试地址无效");
 if(phase=="timeout"&&timeout)return QStringLiteral("测试超时");
 const auto error=result.value("error").toString();
 return timeout||error.contains("timeout",Qt::CaseInsensitive)||error.contains(QStringLiteral("超时"))?QStringLiteral("超时"):QStringLiteral("测试失败");
}
EngineStartOptions NodeTestService::isolatedOptions(const EngineStartOptions &source){
 // Preserve resolver data as well as nodes: the configured DNS/hosts may be
 // the only way to resolve a node endpoint. configuration() still validates
 // the entire map; invalid options must fail instead of falling back to the OS.
 // This creates an independent resolver, never inheriting live TUN, LAN,
 // routing, inbound authentication or system-network ownership.
 EngineStartOptions result;
 result.nodes=source.nodes;result.dnsConfig=source.dnsConfig;
#ifdef SWIRL_PRIVATE_UI_QUOTA
  result.privateUiDnsTrust=source.privateUiDnsTrust;
#endif
 result.internalProbePhysicalEgress=source.internalProbePhysicalEgress;
 result.proxyPort=0;result.internalProbeListener=true;
 result.routingMode="global";result.smartRouting=false;
 result.healthIntervalMs=2000;result.requestTimeoutMs=3000;result.startupTimeoutMs=20000;
 return result;
}
void NodeTestService::start(const EngineStartOptions &options,const QStringList &ids,const QUrl &url){
 if(busy())return;
 if(!url.isValid()||(url.scheme()!="https"&&url.scheme()!="http")||url.host().isEmpty()||!url.userInfo().isEmpty()||url.hasFragment()||url.toString().size()>2048){m_message="测试地址必须为有效且不含凭据的 HTTP/HTTPS URL";emit changed();return;}
 m_options=isolatedOptions(options);m_url=url;m_completed=0;m_succeeded=0;m_failed=0;m_queue.clear();
 QSet<QString> available;for(const auto &node:options.nodes)available.insert(node.id);
 QSet<QString> queued;for(const auto &id:ids)if(available.contains(id)&&!queued.contains(id)){queued.insert(id);m_queue.enqueue(id);m_results.remove(id);}
 m_total=m_queue.size();m_message=m_total?"正在独立测试节点":"没有可测试的节点";emit changed();next();
}
ProxyEngine *NodeTestService::createWorker(){
 auto *runner=new ThreadedEngine(this);
 auto *deadline=new QTimer(runner);deadline->setObjectName("probeDeadline");deadline->setSingleShot(true);deadline->setInterval(40000);
 connect(deadline,&QTimer::timeout,this,[this,runner]{
  const auto id=runner->property("probeNodeId").toString();
  if(!id.isEmpty())finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"phase","timeout"},{"failureCode","ProbeDeadlineExceeded"},{"error","节点测试超时"}});
 });
 connect(runner,&ProxyEngine::diagnostic,this,[this,runner](const QString &,const QString &code,const QString &message){
  // A rejected configure keeps the old runtime alive. It must still finish the
  // newly assigned node as a failure, without testing the previous node.
  if(code!="SelectionUnsupported"&&code!="SelectionFailed")return;
  const auto id=runner->property("probeNodeId").toString();
  if(!id.isEmpty())finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"phase","configuration"},{"failureCode",code},{"error",message}});
 });
 connect(runner,&ProxyEngine::statusChanged,this,[this,runner]{
  const auto id=runner->property("probeNodeId").toString();
  if(id.isEmpty()||m_running.value(id)!=runner)return;
  const auto status=runner->status();
  if(status.state==ProxyEngine::State::Failed){finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"phase","startup"},{"failureCode","CoreStartupFailed"},{"engineError",int(status.error)},{"error",status.message}});return;}
  // Worker snapshots can already be queued while the next node is assigned.
  // Never let an old node's success satisfy a new node's test.
  if(status.selectedNodeId!=id)return;
  if(status.apiHealthy&&!runner->property("probeStarted").toBool()){
   runner->setProperty("probeStarted",true);
   // Give a catalogue mutation/cancellation observed with this snapshot a
   // chance to revoke the request before it is posted to the network thread.
   // The runner context also cancels this callback when it is destroyed.
   QTimer::singleShot(0,runner,[this,runner,id,url=m_url]{
    if(m_running.value(id)!=runner||runner->property("probeNodeId").toString()!=id)return;
    runner->probeNode(url);
   });return;
  }
  if(!runner->property("probeStarted").toBool()||status.nodeBusy)return;
  if(status.requestState!=ProxyEngine::RequestState::Succeeded&&status.requestState!=ProxyEngine::RequestState::Failed&&status.nodeHealth!=ProxyEngine::NodeHealth::Unavailable)return;
  const auto phase=!status.probeFailureStage.isEmpty()?status.probeFailureStage:status.nodeHealth==ProxyEngine::NodeHealth::Unavailable?QString("availability"):QString("request");
  finish(id,runner,{{"success",status.requestState==ProxyEngine::RequestState::Succeeded},{"latency",status.latencyMs},{"http",status.responseCode},{"phase",phase},
   {"failureCode",status.probeFailureCode},
   {"error",status.requestState==ProxyEngine::RequestState::Succeeded?QString():status.nodeMessage},
   {"outboundConnectMs",status.probeOutboundConnectMs},{"originTlsMs",status.probeOriginTlsMs}});
 });
 return runner;
}
void NodeTestService::next(){
 if(m_batchRunner||m_batchAwaitingStart)return;
 // Prefer one concurrent sweep inside a single engine. Engines without batch
 // support (test doubles) keep the isolated per-node path below.
 if(m_queue.size()>=2&&m_running.isEmpty()&&m_idle.isEmpty()&&tryBatch())return;
 while(!m_queue.isEmpty()&&(!m_idle.isEmpty()||m_running.size()+m_retiring.size()<3)){
  const auto id=m_queue.dequeue();auto opts=m_options;opts.selectedNodeId=id;
  // Validate imported data before reserving a runtime. Unsupported nodes stay
  // in the catalogue and receive an explicit per-node failure.
  QJsonObject configuration;const auto reason=RustCoreEngine::configuration(opts,&configuration);
  if(!reason.isEmpty()){record(id,{{"success",false},{"latency",-1},{"http",0},{"phase","configuration"},{"failureCode","NodeConfigurationRejected"},{"error",reason}});continue;}
  const bool reuse=!m_idle.isEmpty();
  // The Rust worker owns its TCP bind from allocation onward. A temporary Qt
  // TCP/UDP reservation could reject a valid TCP-only probe or lose the port
  // before Rust starts. No application proxy, UDP gate or port handoff is used.
  auto *runner=reuse?m_idle.dequeue():createWorker();
  m_running[id]=runner;runner->setProperty("probeNodeId",id);runner->setProperty("probeStarted",false);
  runner->findChild<QTimer *>("probeDeadline")->start();
  // Rust's configure operation reuses the existing Tokio runtime/listener and
  // invalidates old probe state. Only the fresh network request is measured.
  if(reuse)runner->selectNode(id);else runner->start(opts);
 }
 if(m_queue.isEmpty()&&m_running.isEmpty()){
  m_options={};
  while(!m_idle.isEmpty())retire(m_idle.dequeue());
 }
 emit changed();
}
void NodeTestService::finish(const QString &id,ProxyEngine *runner,const QVariantMap &result){
 if(m_running.value(id)!=runner)return;
 m_running.remove(id);runner->setProperty("probeNodeId",QString());runner->findChild<QTimer *>("probeDeadline")->stop();
 const auto status=runner->status();
 if(status.apiHealthy&&status.processAlive&&result.value("phase")!="timeout")m_idle.enqueue(runner);else retire(runner);
 record(id,result);QTimer::singleShot(0,this,&NodeTestService::next);
}
void NodeTestService::record(const QString &id,QVariantMap row){
 row["nodeReference"]=nodeReference(id);
 row["engineKind"]=QStringLiteral("rust");row["metricType"]=QStringLiteral("http_headers");
 row["resolverPolicy"]=m_options.dnsConfig.isEmpty()?QStringLiteral("isolated_default_dns"):QStringLiteral("isolated_configured_dns");
 row["egressPolicy"]=m_options.internalProbePhysicalEgress?QStringLiteral("isolated_physical_egress"):QStringLiteral("system_routes");
 row["time"]=QDateTime::currentDateTime().toString(Qt::ISODate);m_results[id]=row;++m_completed;
 if(row.value("success").toBool())++m_succeeded;else{++m_failed;emit diagnostic("NodeTestFailed",QStringLiteral("节点 #%1 · %2 · %3 · %4").arg(row.value("nodeReference").toString(),row.value("phase").toString(),row.value("failureCode").toString(),row.value("error").toString()));}
 m_message=QString("%1/%2 · 成功 %3 · 失败 %4").arg(m_completed).arg(m_total).arg(m_succeeded).arg(m_failed);emit changed();
}
void NodeTestService::retire(ProxyEngine *runner){
 runner->setProperty("probeNodeId",QString());runner->findChild<QTimer *>("probeDeadline")->stop();
 runner->disconnect(this);m_retiring.insert(runner);
 const auto release=[this,runner]{
  if(runner->status().processAlive || runner->status().state==ProxyEngine::State::Stopping)return;
  if(!m_retiring.remove(runner))return;
  runner->deleteLater();emit changed();QTimer::singleShot(0,this,&NodeTestService::next);
 };
 connect(runner,&ProxyEngine::statusChanged,this,release);runner->stop();release();
}
void NodeTestService::cancel(){
 if(m_batchRunner)m_batchRunner->cancelProbeNodes();
 endBatch();
 m_queue.clear();m_options={};const auto runners=m_running;m_running.clear();
 for(auto runner:runners)retire(runner);
 while(!m_idle.isEmpty())retire(m_idle.dequeue());
 if(!runners.isEmpty())m_message=QString("已取消 · 正在释放测试内核 · 完成 %1/%2").arg(m_completed).arg(m_total);
 emit changed();
}
bool NodeTestService::tryBatch(){
 // Validate each node's configuration without starting an engine, then hand
 // the whole batch to one concurrent sweep. Unsupported nodes keep an explicit
 // per-node failure instead of blocking the sweep.
 QStringList valid;
 while(!m_queue.isEmpty()){
  const auto id=m_queue.dequeue();
  auto opts=m_options;opts.selectedNodeId=id;
  QJsonObject configuration;
  const auto reason=RustCoreEngine::configuration(opts,&configuration);
  if(!reason.isEmpty()){record(id,{{"success",false},{"latency",-1},{"http",0},{"phase","configuration"},{"failureCode","NodeConfigurationRejected"},{"error",reason}});continue;}
  valid.append(id);
 }
 if(valid.isEmpty())return false;
 m_batchRunner=createWorker();
 m_batchSwept.clear();for(const auto &id:valid)m_batchSwept.insert(id);
 m_batchRecorded.clear();
 connect(m_batchRunner,&ProxyEngine::statusChanged,this,&NodeTestService::batchStatusChanged);
 auto opts=m_options;opts.selectedNodeId=valid.first();
 m_batchAwaitingStart=true;
 m_batchRunner->start(opts);
 return true;
}

void NodeTestService::batchStatusChanged(){
 if(!m_batchAwaitingStart||!m_batchRunner)return;
 const auto status=m_batchRunner->status();
 if(status.state==ProxyEngine::State::Failed||status.state==ProxyEngine::State::Stopped){
  const auto pending=m_batchSwept;
  m_batchAwaitingStart=false;
  endBatch();
  for(const auto &id:pending)if(!m_batchRecorded.contains(id))m_queue.enqueue(id);
  next();
  return;
 }
 if(!status.apiHealthy||status.state!=ProxyEngine::State::Running)return;
 QStringList ids;for(const auto &id:m_batchSwept)ids.append(id);
 QString error;
 if(!m_batchRunner->probeNodes(ids,m_url,&error)){
  const auto pending=m_batchSwept;
  m_batchAwaitingStart=false;
  endBatch();
  for(const auto &id:pending)if(!m_batchRecorded.contains(id))m_queue.enqueue(id);
  next();
  return;
 }
 m_batchAwaitingStart=false;
 if(!m_batchPoll){
  m_batchPoll=new QTimer(this);m_batchPoll->setInterval(50);
  connect(m_batchPoll,&QTimer::timeout,this,&NodeTestService::pollBatch);
 }
 m_batchPoll->start();
 m_message=QStringLiteral("并行测速中 · %1 个节点").arg(ids.size());emit changed();
}

void NodeTestService::pollBatch(){
 if(!m_batchRunner)return;
 const auto sweep=m_batchRunner->probeNodesStatus().value("sweep").toObject();
 if(sweep.isEmpty())return;
 const auto rows=sweep.value("rows").toArray();
 for(const auto &value:rows){
  const auto row=value.toObject();
  const auto id=row.value("node").toString();
  if(id.isEmpty()||m_batchRecorded.contains(id))continue;
  const auto state=row.value("state").toString();
  if(state=="running")continue;
  m_batchRecorded.insert(id);
  const bool ok=state=="ok";
  QVariantMap result;
  result["success"]=ok;
  result["latency"]=ok?row.value("latency_ms").toInteger(-1):qint64(-1);
  result["http"]=row.value("http_status").toInteger(0);
  result["phase"]=ok?QStringLiteral("measured"):row.value("failure_stage").toString("probe");
  result["failureCode"]=row.value("failure_code").toString();
  result["error"]=ok?QString():row.value("failure_code").toString();
  result["outboundConnectMs"]=row.value("outbound_connect_ms").toInteger(-1);
  result["originTlsMs"]=qint64(-1);
  record(id,result);
 }
 if(sweep.value("done").toBool()){
  endBatch();
  next();
 }
}

void NodeTestService::endBatch(){
 if(m_batchPoll)m_batchPoll->stop();
 if(m_batchRunner){retire(m_batchRunner);m_batchRunner=nullptr;}
 m_batchAwaitingStart=false;
 m_batchSwept.clear();
 emit changed();
}

void NodeTestService::invalidateResults(){
 const bool hadWork=busy()||!m_results.isEmpty();
 if(!hadWork)return;
 cancel();m_results.clear();m_completed=0;m_total=0;m_succeeded=0;m_failed=0;
 m_message=QStringLiteral("节点库已更新，旧测试结果已清除；请对当前参数重新发起请求。");
 emit changed();
}

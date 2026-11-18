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
#include <QThreadPool>
namespace {
bool validProbeUrl(const QUrl &url){return url.isValid()&&(url.scheme()=="https"||url.scheme()=="http")&&!url.host().isEmpty()&&url.userInfo().isEmpty()&&!url.hasFragment()&&url.toString().size()<=2048;}
}
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
 if(!validProbeUrl(url)){m_message="测试地址必须为有效且不含凭据的 HTTP/HTTPS URL";emit changed();return;}
 ++m_generation;m_options=isolatedOptions(options);m_url=url;m_completed=0;m_succeeded=0;m_failed=0;m_queue.clear();m_batchDisabled=false;
 QSet<QString> available;for(const auto &node:options.nodes)available.insert(node.id);
 QSet<QString> queued;for(const auto &id:ids)if(available.contains(id)&&!queued.contains(id)){queued.insert(id);m_queue.enqueue(id);m_results.remove(id);}
 m_total=m_queue.size();m_message=m_total?"正在独立测试节点":"没有可测试的节点";emit changed();next();
}
bool NodeTestService::testing(const QString &id) const{
 if(m_running.contains(id)||m_queue.contains(id)||(m_batchSwept.contains(id)&&!m_batchRecorded.contains(id))||(m_interactive&&m_interactive->testing(id)))return true;
 for(const auto &request:m_refreshQueue)if(request.id==id)return true;
 return false;
}
void NodeTestService::refreshNode(const EngineStartOptions &options,const QString &id,const QUrl &url){
 if(!validProbeUrl(url)){m_message="测试地址必须为有效且不含凭据的 HTTP/HTTPS URL";emit changed();return;}
 if(testing(id))return;
 if(!busy()){start(options,{id},url);return;}
 // One interactive worker can refresh a completed row while slow batch rows
 // continue. Coalesce clicks and bound the queue instead of cancelling a sweep.
 if(m_refreshQueue.size()>=8)return;
 auto isolated=isolatedOptions(options);
 isolated.nodes.removeIf([&](const ProxyNode &node){return node.id!=id;});
 if(isolated.nodes.isEmpty())return;
 if(!m_interactive){
  m_interactive=new NodeTestService(this);
  connect(m_interactive,&NodeTestService::diagnostic,this,&NodeTestService::diagnostic);
  connect(m_interactive,&NodeTestService::changed,this,[this]{
   const auto measured=m_interactive->result(m_refreshId);
   if(!m_refreshId.isEmpty()&&!measured.isEmpty())m_results[m_refreshId]=measured;
   emit changed();
   if(!m_interactive->busy())QTimer::singleShot(0,this,&NodeTestService::nextRefresh);
  });
 }
 m_refreshQueue.enqueue({isolated,id,url});emit changed();nextRefresh();
}
void NodeTestService::nextRefresh(){
 if(!m_interactive||m_interactive->busy()||m_refreshQueue.isEmpty())return;
 if(m_running.size()+m_retiring.size()+m_idle.size()>=3)return;
 const auto request=m_refreshQueue.dequeue();m_refreshId=request.id;
 m_results.remove(request.id);m_interactive->start(request.options,{request.id},request.url);
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
  finish(id,runner,{{"success",status.requestState==ProxyEngine::RequestState::Succeeded},{"latency",status.probeRequestRttMs},{"totalMs",status.latencyMs},{"http",status.responseCode},{"phase",phase},
   {"failureCode",status.probeFailureCode},
   {"error",status.requestState==ProxyEngine::RequestState::Succeeded?QString():status.nodeMessage},
   {"outboundConnectMs",status.probeOutboundConnectMs},{"originTlsMs",status.probeOriginTlsMs}});
 });
 return runner;
}
void NodeTestService::next(){
 if(m_batchPreparation||m_batchRunner||m_batchAwaitingStart)return;
 // Prefer one concurrent sweep inside a single engine. Engines without batch
 // support (test doubles) keep the isolated per-node path below.
 if(m_queue.size()>=2&&m_running.isEmpty()&&m_idle.isEmpty()&&!m_batchDisabled&&tryBatch())return;
 while(!m_queue.isEmpty()&&(!m_idle.isEmpty()||m_running.size()+m_retiring.size()+(m_interactive&&m_interactive->busy()?1:0)<3)){
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
void NodeTestService::record(const QString &id,QVariantMap row,bool notify){
 row["nodeReference"]=nodeReference(id);
 row["engineKind"]=QStringLiteral("rust");row["metricType"]=QStringLiteral("http_request_rtt");
 row["resolverPolicy"]=m_options.dnsConfig.isEmpty()?QStringLiteral("isolated_default_dns"):QStringLiteral("isolated_configured_dns");
 row["egressPolicy"]=m_options.internalProbePhysicalEgress?QStringLiteral("isolated_physical_egress"):QStringLiteral("system_routes");
 row["time"]=QDateTime::currentDateTime().toString(Qt::ISODate);++m_completed;
 row["measuredAtMs"]=QDateTime::currentMSecsSinceEpoch();row["probeUrl"]=m_url.toString();m_results[id]=row;
 if(row.value("success").toBool())++m_succeeded;else{++m_failed;emit diagnostic("NodeTestFailed",QStringLiteral("节点 #%1 · %2 · %3 · %4").arg(row.value("nodeReference").toString(),row.value("phase").toString(),row.value("failureCode").toString(),row.value("error").toString()));}
 m_message=QString("%1/%2 · 成功 %3 · 失败 %4").arg(m_completed).arg(m_total).arg(m_succeeded).arg(m_failed);if(notify)emit changed();
}
bool NodeTestService::hasFreshResults(const QStringList &ids,const QUrl &url) const{
 if(ids.isEmpty())return false;
 const auto now=QDateTime::currentMSecsSinceEpoch();
 for(const auto &id:ids){const auto row=result(id);const auto age=now-row.value("measuredAtMs").toLongLong();
  if(row.isEmpty()||row.value("probeUrl").toString()!=url.toString()||age<0||age>30000)return false;
 }
 return true;
}
void NodeTestService::retire(ProxyEngine *runner){
 runner->setProperty("probeNodeId",QString());runner->findChild<QTimer *>("probeDeadline")->stop();
 runner->disconnect(this);m_retiring.insert(runner);
 const auto release=[this,runner]{
  if(runner->status().processAlive || runner->status().state==ProxyEngine::State::Stopping)return;
  if(!m_retiring.remove(runner))return;
  runner->deleteLater();emit changed();QTimer::singleShot(0,this,&NodeTestService::next);QTimer::singleShot(0,this,&NodeTestService::nextRefresh);
 };
 connect(runner,&ProxyEngine::statusChanged,this,release);runner->stop();release();
}
void NodeTestService::cancel(){
 const bool hadWork=busy();if(m_batchPreparation)m_batchPreparation->store(true);
 m_refreshQueue.clear();m_refreshId.clear();if(m_interactive)m_interactive->cancel();
 if(m_batchRunner)m_batchRunner->cancelProbeNodes();
 endBatch();
 m_queue.clear();m_options={};const auto runners=m_running;m_running.clear();
 for(auto runner:runners)retire(runner);
 while(!m_idle.isEmpty())retire(m_idle.dequeue());
 if(hadWork)m_message=QString("已取消 · 完成 %1/%2").arg(m_completed).arg(m_total);
 emit changed();
}
bool NodeTestService::tryBatch(){
 // Native conversion of a large subscription can occupy a full GUI frame.
 // Validate immutable copies in the pool, then publish one result on our thread.
 const auto cancelled=std::make_shared<std::atomic_bool>(false);m_batchPreparation=cancelled;
 const QPointer<NodeTestService> owner(this);const auto ids=m_queue;const auto options=m_options;
 auto dispatch=std::shared_ptr<QObject>(new QObject,[](QObject *object){object->deleteLater();});
 QThreadPool::globalInstance()->start([owner,dispatch,cancelled,ids,options]{
  QStringList valid;QList<QPair<QString,QString>> rejected;auto opts=options;
  for(const auto &id:ids){
   if(cancelled->load())break;
   opts.selectedNodeId=id;QJsonObject configuration;
   const auto reason=RustCoreEngine::configuration(opts,&configuration);
   if(reason.isEmpty())valid.append(id);else rejected.append({id,reason});
  }
  QMetaObject::invokeMethod(dispatch.get(),[owner,dispatch,cancelled,valid,rejected]{
   if(!owner||owner->m_batchPreparation!=cancelled)return;
   if(cancelled->load()){owner->m_batchPreparation.reset();owner->next();return;}
   owner->m_queue.clear();
   for(const auto &failure:rejected){
    owner->record(failure.first,{{"success",false},{"latency",-1},{"http",0},{"phase","configuration"},{"failureCode","NodeConfigurationRejected"},{"error",failure.second}},false);
    if(!owner)return;
    if(cancelled->load())break;
   }
   owner->m_batchPreparation.reset();
   if(cancelled->load()){owner->next();return;}
   if(valid.isEmpty())owner->next();else owner->beginBatch(valid);
  },Qt::QueuedConnection);
 });
 return true;
}
void NodeTestService::beginBatch(const QStringList &valid){
 m_batchRunner=createWorker();
 m_batchSwept.clear();for(const auto &id:valid)m_batchSwept.insert(id);
 m_batchRecorded.clear();
 m_batchRequestId=0;
 connect(m_batchRunner,&ProxyEngine::statusChanged,this,&NodeTestService::batchStatusChanged);
 auto opts=m_options;opts.selectedNodeId=valid.first();opts.probeAllNodes=true;
 opts.nodes.removeIf([this](const ProxyNode &node){return !m_batchSwept.contains(node.id);});
 m_batchAwaitingStart=true;
 m_batchStartClock.start();
 if(!m_batchPoll){
  m_batchPoll=new QTimer(this);m_batchPoll->setInterval(50);
  connect(m_batchPoll,&QTimer::timeout,this,&NodeTestService::pollBatch);
 }
 // Polling drives the startup handshake. ThreadedEngine publishes its pre-start
 // snapshot after start(), so a single statusChanged(Stopped) is not a failure.
 m_batchPoll->start();
 m_batchRunner->start(opts);
 emit changed();
}

void NodeTestService::batchStatusChanged(){
 // Accelerate the handshake; correctness comes from the poll state machine.
 pollBatch();
}

void NodeTestService::pollBatch(){
 if(!m_batchRunner)return;
 if(m_batchAwaitingStart){
  const auto status=m_batchRunner->status();
  if(status.state==ProxyEngine::State::Failed){
   batchFallback(QStringLiteral("start-failed"),status.message);
   return;
  }
  if(m_batchStartClock.elapsed()>20000){
   batchFallback(QStringLiteral("start-timeout"),status.message);
   return;
  }
  if(status.state!=ProxyEngine::State::Running||!status.apiHealthy)return;
  QStringList ids;for(const auto &id:m_batchSwept)ids.append(id);
  QString error;
  if(!m_batchRunner->probeNodes(ids,m_url,&error)){
   batchFallback(QStringLiteral("issue-failed"),error);
   return;
  }
  m_batchAwaitingStart=false;
  m_message=QStringLiteral("并行测速中 · %1 个节点").arg(ids.size());emit changed();
 }
 const auto status=m_batchRunner->status();
 if(status.state==ProxyEngine::State::Failed||status.state==ProxyEngine::State::Stopped){failBatch("ProbeCoreStopped");return;}
 // Eight seconds per bounded wave, plus startup and cancellation headroom.
 // The one-second UI goal is never a node failure deadline.
 if(m_batchStartClock.elapsed()>20000+((m_batchSwept.size()+63)/64)*8000){failBatch("ProbeDeadlineExceeded");return;}
 const auto response=m_batchRunner->probeNodesStatus();
 if(response.value("pending").toBool())return;
 if(!response.value("ok").toBool()){failBatch(response.value("error").toString("ProbeStatusFailed"));return;}
 const auto sweep=response.value("sweep").toObject();
 const auto requestId=sweep.value("request_id").toInteger();
 if(requestId<=0||(m_batchRequestId&&m_batchRequestId!=requestId)){failBatch("ProbeStateInvalid");return;}
 m_batchRequestId=requestId;
 const auto rows=sweep.value("rows").toArray();
 bool changedRows=false;
 for(const auto &value:rows){
  const auto row=value.toObject();
  const auto id=row.value("node").toString();
  if(!m_batchSwept.contains(id)||m_batchRecorded.contains(id))continue;
  const auto state=row.value("state").toString();
  if(state=="running")continue;
  if(state!="ok"&&state!="failed"){failBatch("ProbeStateInvalid");return;}
  m_batchRecorded.insert(id);
  const bool ok=state=="ok";
  QVariantMap result;
  result["success"]=ok;
  result["latency"]=ok?row.value("request_rtt_ms").toInteger(-1):qint64(-1);
  result["totalMs"]=ok?row.value("latency_ms").toInteger(-1):qint64(-1);
  result["http"]=row.value("http_status").toInteger(0);
  result["phase"]=ok?QStringLiteral("measured"):row.value("failure_stage").toString("probe");
  result["failureCode"]=ok?QString():row.value("failure_code").toString();
  result["error"]=ok?QString():row.value("failure_code").toString();
  result["outboundConnectMs"]=row.value("outbound_connect_ms").toInteger(-1);
  result["originTlsMs"]=row.value("origin_tls_ms").toInteger(-1);
  result["outboundTiming"]=row.value("outbound_timing").toObject().toVariantMap();
  record(id,result,false);changedRows=true;
 }
 if(changedRows)emit changed();
 if(sweep.value("done").toBool()){
  if(m_batchRecorded.size()!=m_batchSwept.size()){failBatch("ProbeStateInvalid");return;}
  endBatch();
  next();
 }
}

void NodeTestService::failBatch(const QString &code){
 const auto pending=m_batchSwept;
 for(const auto &id:pending)if(!m_batchRecorded.contains(id)){
  m_batchRecorded.insert(id);
  record(id,{{"success",false},{"latency",-1},{"http",0},{"phase","probe_status"},{"failureCode",code},{"error",code}},false);
 }
 if(m_batchRunner)m_batchRunner->cancelProbeNodes();
 endBatch();next();
}

void NodeTestService::batchFallback(const QString &reason,const QString &detail){
 // Fall back to the isolated per-node path for the rest of this sweep. Without
 // the latch the same batch start failure would re-queue and repeat forever.
 m_batchDisabled=true;
 qWarning()<<"NODE_BATCH_FALLBACK"<<reason<<detail;
 const auto pending=m_batchSwept;
 m_batchAwaitingStart=false;
 endBatch();
 for(const auto &id:pending)if(!m_batchRecorded.contains(id))m_queue.enqueue(id);
 next();
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
 cancel();if(m_interactive)m_interactive->invalidateResults();m_results.clear();m_completed=0;m_total=0;m_succeeded=0;m_failed=0;
 m_message=QStringLiteral("网络或节点配置已变化，旧测试结果已清除；请重新检测。");
 emit changed();
}

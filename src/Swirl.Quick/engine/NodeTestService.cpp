#include "NodeTestService.h"
#include "RustCoreEngine.h"
#include "ThreadedEngine.h"
#include <QTcpServer>
#include <QSet>
#include <QDateTime>
#include <QPointer>
#include <QUdpSocket>
namespace {
quint16 freePort(){
 QTcpServer tcp;QUdpSocket udp;
 for(int attempt=0;attempt<16;++attempt){
  if(!tcp.listen(QHostAddress::LocalHost,0))return 0;
  if(udp.bind(QHostAddress::LocalHost,tcp.serverPort(),QUdpSocket::DontShareAddress))return tcp.serverPort();
  tcp.close();
 }
 return 0;
}
}
NodeTestService::~NodeTestService(){cancel();}
EngineStartOptions NodeTestService::isolatedOptions(const EngineStartOptions &source){
 // Keep only node data. A test must not inherit saved TUN, LAN, routing,
 // authentication, external executable paths or the live resolver owner.
 EngineStartOptions result;
 result.nodes=source.nodes;
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
  if(!id.isEmpty())finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"phase","timeout"},{"error","节点测试超时"}});
 });
 connect(runner,&ProxyEngine::diagnostic,this,[this,runner](const QString &,const QString &code,const QString &message){
  // A rejected configure keeps the old runtime alive. It must still finish the
  // newly assigned node as a failure, without testing the previous node.
  if(code!="SelectionUnsupported"&&code!="SelectionFailed")return;
  const auto id=runner->property("probeNodeId").toString();
  if(!id.isEmpty())finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"phase","configuration"},{"error",message}});
 });
 connect(runner,&ProxyEngine::statusChanged,this,[this,runner]{
  const auto id=runner->property("probeNodeId").toString();
  if(id.isEmpty()||m_running.value(id)!=runner)return;
  const auto status=runner->status();
  if(status.state==ProxyEngine::State::Failed){finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"phase","startup"},{"engineError",int(status.error)},{"error",status.message}});return;}
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
   {"error",status.requestState==ProxyEngine::RequestState::Succeeded?QString():status.nodeMessage},
   {"outboundConnectMs",status.probeOutboundConnectMs},{"originTlsMs",status.probeOriginTlsMs}});
 });
 return runner;
}
void NodeTestService::next(){
 while(!m_queue.isEmpty()&&(!m_idle.isEmpty()||m_running.size()+m_retiring.size()<3)){
  const auto id=m_queue.dequeue();auto opts=m_options;opts.selectedNodeId=id;
  // Validate imported data before reserving a runtime. Unsupported nodes stay
  // in the catalogue and receive an explicit per-node failure.
  QJsonObject configuration;const auto reason=RustCoreEngine::configuration(opts,&configuration);
  if(!reason.isEmpty()){record(id,{{"success",false},{"latency",-1},{"http",0},{"phase","configuration"},{"error",reason}});continue;}
  const bool reuse=!m_idle.isEmpty();
  if(!reuse){opts.proxyPort=freePort();if(!opts.proxyPort){record(id,{{"success",false},{"latency",-1},{"http",0},{"phase","listener"},{"error","无法分配本机测试端口"}});continue;}}
  auto *runner=reuse?m_idle.dequeue():createWorker();
  m_running[id]=runner;runner->setProperty("probeNodeId",id);runner->setProperty("probeStarted",false);
  runner->findChild<QTimer *>("probeDeadline")->start();
  // Rust's configure operation reuses the existing Tokio runtime/listener and
  // invalidates old probe state. Only the fresh network request is measured.
  if(reuse)runner->selectNode(id);else runner->start(opts);
 }
 if(m_queue.isEmpty()&&m_running.isEmpty())while(!m_idle.isEmpty())retire(m_idle.dequeue());
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
 row["engineKind"]=QStringLiteral("rust");row["metricType"]=QStringLiteral("http_headers");row["resolverPolicy"]=QStringLiteral("isolated_default_dns");
 row["time"]=QDateTime::currentDateTime().toString(Qt::ISODate);m_results[id]=row;++m_completed;
 if(row.value("success").toBool())++m_succeeded;else{++m_failed;emit diagnostic("NodeTestFailed",row.value("error").toString());}
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
 m_queue.clear();const auto runners=m_running;m_running.clear();
 for(auto runner:runners)retire(runner);
 while(!m_idle.isEmpty())retire(m_idle.dequeue());
 if(!runners.isEmpty())m_message=QString("已取消 · 正在释放测试内核 · 完成 %1/%2").arg(m_completed).arg(m_total);
 emit changed();
}
void NodeTestService::invalidateResults(){
 const bool hadWork=busy()||!m_results.isEmpty();
 if(!hadWork)return;
 cancel();m_results.clear();m_completed=0;m_total=0;m_succeeded=0;m_failed=0;
 m_message=QStringLiteral("节点库已更新，旧测试结果已清除；请对当前参数重新发起请求。");
 emit changed();
}

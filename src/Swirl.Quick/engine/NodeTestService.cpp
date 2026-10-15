#include "NodeTestService.h"
#include <QTcpServer>
#include <QSet>
#include <QDateTime>
#include <QPointer>
#include <QUdpSocket>
namespace {
quint16 freePort(quint16 excludedPort=0){
 QTcpServer tcp;QUdpSocket udp;
 for(int attempt=0;attempt<16;++attempt){
  if(!tcp.listen(QHostAddress::LocalHost,0))return 0;
  if(tcp.serverPort()!=excludedPort && udp.bind(QHostAddress::LocalHost,tcp.serverPort(),QUdpSocket::DontShareAddress))return tcp.serverPort();
  tcp.close();
 }
 return 0;
}
}
NodeTestService::~NodeTestService(){cancel();}
EngineStartOptions NodeTestService::isolatedOptions(const EngineStartOptions &source){
 // Build a probe session from an allowlist. Copying the live session could
 // spawn three competing TUN/DNS/route owners during a latency test.
 EngineStartOptions result;
 result.executablePath=source.executablePath;result.expectedSha256=source.expectedSha256;result.expectedVersion=source.expectedVersion;
 result.nodes=source.nodes;result.rulesDirectory=source.rulesDirectory;
 result.routingMode="global";result.smartRouting=false;
 result.healthIntervalMs=2000;result.requestTimeoutMs=3000;result.startupTimeoutMs=20000;
 return result;
}
void NodeTestService::start(const EngineStartOptions &options,const QStringList &ids,const QUrl &url){
 if(busy())return;
 if(!url.isValid()||(url.scheme()!="https"&&url.scheme()!="http")||url.host().isEmpty()||!url.userInfo().isEmpty()||url.hasFragment()||url.toString().size()>2048){m_message="测试地址必须为有效且不含凭据的 HTTP/HTTPS URL";emit changed();return;}
 m_options=options;m_url=url;m_completed=0;m_succeeded=0;m_failed=0;m_queue.clear();
 for(const auto &id:ids)if(!m_queue.contains(id)){bool found=false;for(const auto &n:options.nodes)if(n.id==id)found=true;if(found)m_queue.enqueue(id);}
 m_total=m_queue.size();m_message=m_total?"正在独立测试节点":"没有可测试的节点";emit changed();next();
}
void NodeTestService::next(){
 while(m_running.size()+m_retiring.size()<3&&!m_queue.isEmpty()){
  const auto id=m_queue.dequeue();auto opts=isolatedOptions(m_options);opts.selectedNodeId=id;opts.controlPort=freePort();opts.proxyPort=freePort(opts.controlPort);opts.healthIntervalMs=2000;opts.requestTimeoutMs=3000;opts.startupTimeoutMs=20000;
  // Include only the selected node and its explicit dialer dependencies.
  QSet<QString> needed{id};bool added=true;while(added){added=false;for(const auto &node:m_options.nodes)if(needed.contains(node.id)){const auto dependency=node.parameters.value("dialer-proxy").toString();for(const auto &other:m_options.nodes)if(other.sourceId==node.sourceId&&(other.name==dependency||other.id==dependency)&&!needed.contains(other.id)){needed.insert(other.id);added=true;}}}
  opts.nodes.clear();for(const auto &node:m_options.nodes)if(needed.contains(node.id))opts.nodes.append(node);
  auto runner=new MihomoAdapter(this);m_running[id]=runner;auto deadline=new QTimer(runner);deadline->setSingleShot(true);deadline->setInterval(40000);
  connect(deadline,&QTimer::timeout,this,[this,runner,id]{finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"error","节点测试超时"}});});deadline->start();
  connect(runner,&ProxyEngine::statusChanged,this,[this,runner,id]{
   if(m_running.value(id)!=runner)return;const auto status=runner->status();
   if(status.state==ProxyEngine::State::Failed){finish(id,runner,{{"success",false},{"latency",-1},{"http",0},{"error",status.message}});return;}
   if(status.apiHealthy&&!runner->property("probeStarted").toBool()){runner->setProperty("probeStarted",true);QPointer<MihomoAdapter> guard(runner);QTimer::singleShot(0,runner,[this,guard]{if(guard)guard->probeNode(m_url);});}
   if(runner->property("probeStarted").toBool()&&!status.nodeBusy&&(status.requestState==ProxyEngine::RequestState::Succeeded||status.requestState==ProxyEngine::RequestState::Failed||status.nodeHealth==ProxyEngine::NodeHealth::Unavailable)){
    finish(id,runner,{{"success",status.requestState==ProxyEngine::RequestState::Succeeded},{"latency",status.latencyMs},{"http",status.responseCode},{"error",status.requestState==ProxyEngine::RequestState::Succeeded?QString():status.nodeMessage}});
   }
  });runner->start(opts);
 }
}
void NodeTestService::finish(const QString &id,MihomoAdapter *runner,const QVariantMap &result){
 if(m_running.value(id)!=runner)return;m_running.remove(id);retire(runner);
 auto row=result;row["time"]=QDateTime::currentDateTime().toString(Qt::ISODate);m_results[id]=row;++m_completed;if(row.value("success").toBool())++m_succeeded;else{++m_failed;emit diagnostic("NodeTestFailed",row.value("error").toString());}
 m_message=QString("%1/%2 · 成功 %3 · 失败 %4").arg(m_completed).arg(m_total).arg(m_succeeded).arg(m_failed);emit changed();QTimer::singleShot(0,this,&NodeTestService::next);
}
void NodeTestService::retire(MihomoAdapter *runner){
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
 if(!runners.isEmpty())m_message=QString("已取消 · 正在释放测试内核 · 完成 %1/%2").arg(m_completed).arg(m_total);
 emit changed();
}

#include "ProxyLatencyProbe.h"
#include <QNetworkProxy>

ProxyLatencyProbe::ProxyLatencyProbe(const ProxyEngine::Status &status,const QUrl &url,Completion completion,QObject *parent)
 :QObject(parent),m_url(url),m_node(status.selectedNodeId),m_completion(std::move(completion)){
 m_elapsed.start();m_socket.setProxy(QNetworkProxy::NoProxy);m_socket.setReadBufferSize(16384);
 m_deadline.setSingleShot(true);m_observationDeadline.setSingleShot(true);
 connect(&m_deadline,&QTimer::timeout,this,[this]{finish("timeout",QStringLiteral("测量超时"));});
 connect(&m_observationDeadline,&QTimer::timeout,this,[this]{finish("route-unverified",QStringLiteral("策略未确认"));});
 connect(&m_socket,&QSslSocket::connected,this,[this]{
  m_sourcePort=m_socket.localPort();m_phase="tunnel";
  const auto authority=m_url.host().toUtf8()+":"+QByteArray::number(m_url.port(m_url.scheme()=="https"?443:80));
  m_socket.write("CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\n\r\n");
 });
 connect(&m_socket,&QSslSocket::encrypted,this,&ProxyLatencyProbe::sendRequest);
 connect(&m_socket,&QSslSocket::readyRead,this,&ProxyLatencyProbe::read);
 connect(&m_socket,&QSslSocket::errorOccurred,this,[this](QAbstractSocket::SocketError error){
  if(m_done||(m_response&&error==QAbstractSocket::RemoteHostClosedError))return;
  m_networkError=int(error);
  if(error==QAbstractSocket::SslHandshakeFailedError)finish("tls",QStringLiteral("TLS 验证失败"));
  else if(m_phase=="connect")finish("proxy-port",QStringLiteral("入口异常"));
  else finish("transport",QStringLiteral("代理连接失败"));
 });
 m_deadline.start(9000);m_socket.connectToHost("127.0.0.1",status.proxyPort);
}
void ProxyLatencyProbe::sendRequest(){
 m_phase="http";auto path=m_url.path(QUrl::FullyEncoded).toUtf8();if(path.isEmpty())path="/";
 // Production probe has no query, credentials, redirects or response-body logging.
 m_socket.write("HEAD "+path+" HTTP/1.1\r\nHost: "+m_url.host().toUtf8()+"\r\nConnection: keep-alive\r\n\r\n");
}
void ProxyLatencyProbe::read(){
 if(m_done)return;
 if(m_response){m_socket.readAll();return;}
 m_header+=m_socket.readAll();
 if(m_header.size()>16384){finish("invalid-response",QStringLiteral("响应头过大"));return;}
 const auto end=m_header.indexOf("\r\n\r\n");if(end<0)return;
 const auto first=m_header.left(m_header.indexOf("\r\n")).split(' ');
 bool numeric=false;const int status=first.size()>1?first[1].toInt(&numeric):0;
 m_header.clear();
 if(!numeric||first.isEmpty()||!first[0].startsWith("HTTP/1.")||status<100||status>599){finish("invalid-response",QStringLiteral("响应无效"));return;}
 if(m_phase=="tunnel"){
  if(status!=200){m_http=status;finish(status==407?"proxy-auth":"connect-rejected",QString("CONNECT %1").arg(status));return;}
  if(m_url.scheme()=="https"){m_phase="tls";m_socket.setPeerVerifyName(m_url.host());m_socket.startClientEncryption();}
  else sendRequest();
  return;
 }
 if(status<200)return;
 m_http=status;m_latency=m_elapsed.elapsed();m_response=true;
 if(status>=300){finish("http",QString("HTTP %1").arg(status));return;}
 if(m_observed)finish(m_category=="proxy"&&m_chain.contains(m_node)?"success":"route-mismatch",m_category=="proxy"&&m_chain.contains(m_node)?QString::number(m_latency)+" ms":QStringLiteral("策略与所选节点不符"));
 else m_observationDeadline.start(2500);
}
void ProxyLatencyProbe::observe(const ProxyEngine::Status &status){
 if(m_done||!m_sourcePort)return;
 for(const auto &value:status.connections){const auto row=value.toMap();
  if(row.value("sourcePort").toInt()!=m_sourcePort||row.value("host").toString()!=m_url.host()||!QHostAddress(row.value("sourceIp").toString()).isLoopback())continue;
  m_observed=true;m_policy=row.value("policy").toString();m_category=row.value("category").toString();m_chain=row.value("nodeChain").toStringList();
  if(m_response)finish(m_category=="proxy"&&m_chain.contains(m_node)?"success":"route-mismatch",m_category=="proxy"&&m_chain.contains(m_node)?QString::number(m_latency)+" ms":QStringLiteral("策略与所选节点不符"));
  return;
 }
}
void ProxyLatencyProbe::finish(QString code,QString state){
 if(m_done)return;m_done=true;m_deadline.stop();m_observationDeadline.stop();m_socket.abort();
 const QVariantMap result{{"code",code},{"state",state},{"success",code=="success"},{"http",m_http},{"networkError",m_networkError},{"elapsedMs",m_latency>=0?m_latency:m_elapsed.elapsed()},
  {"routeVerified",m_observed},{"route",m_policy},{"detail",m_observed?QStringLiteral("独立 HTTPS 往返；已按本地源端口核对实际连接链。"):QStringLiteral("未取得匹配的引擎连接链，不能确认流量经过所选节点。")}};
 m_completion(result);deleteLater();
}

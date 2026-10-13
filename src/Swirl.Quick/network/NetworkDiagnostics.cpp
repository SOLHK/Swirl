#include "NetworkDiagnostics.h"
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QElapsedTimer>
#include <QDateTime>
#include <QDebug>
#include <QHostInfo>

NetworkDiagnostics::NetworkDiagnostics(QObject *parent):QObject(parent) {
    m_direct.network.setProxy(QNetworkProxy::NoProxy);
    m_endpoints={QUrl("https://www.gstatic.com/generate_204"),QUrl("https://cp.cloudflare.com/generate_204"),QUrl("https://connectivitycheck.platform.hicloud.com/generate_204")};
}
NetworkDiagnostics::~NetworkDiagnostics() {
    ++m_dnsGeneration;if(m_lookup>=0)QHostInfo::abortHostLookup(m_lookup);
    reset(m_direct,QStringLiteral("已取消"));reset(m_proxy,QStringLiteral("已取消"));
}
void NetworkDiagnostics::reset(Route &route,const QString &state) {
    route.pending=false;
    if(route.reply){route.reply->disconnect(this);route.reply->abort();route.reply->deleteLater();route.reply=nullptr;}
    route.network.clearAccessCache();
    route.result={{"state",state},{"latency",-1}};
}
void NetworkDiagnostics::setProxyPort(int port) {
    if(port==m_proxyPort)return;
    reset(m_proxy,QStringLiteral("尚未检测"));m_proxyPort=port;
    m_proxy.network.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",port));
    emit changed();
}
void NetworkDiagnostics::cancel() {
    ++m_dnsGeneration;
    if(m_lookup>=0){QHostInfo::abortHostLookup(m_lookup);m_lookup=-1;m_dns={{"state",QStringLiteral("已取消")},{"latency",-1}};}
    if(m_direct.pending)reset(m_direct,QStringLiteral("已取消"));
    if(m_proxy.pending)reset(m_proxy,QStringLiteral("已取消"));
    emit changed();
}
void NetworkDiagnostics::invalidate() {
    cancel();m_dns={{"state",QStringLiteral("尚未检测")},{"latency",-1}};
    reset(m_direct,QStringLiteral("尚未检测"));reset(m_proxy,QStringLiteral("尚未检测"));
    m_log.append(QStringLiteral("网络或节点已变化；旧探测结果及连接缓存已清除。"));emit changed();
}
void NetworkDiagnostics::start() {
    cancel();m_log.clear();
    if(!m_endpoints.isEmpty()) {
        m_dns={{"state",QStringLiteral("正在检测")},{"latency",-1}};
        const auto generation=m_dnsGeneration;QElapsedTimer dnsTimer;dnsTimer.start();
        m_lookup=QHostInfo::lookupHost(m_endpoints.first().host(),this,[this,generation,dnsTimer](const QHostInfo &info){
            if(generation!=m_dnsGeneration)return;m_lookup=-1;
            const bool ok=info.error()==QHostInfo::NoError && !info.addresses().isEmpty();
            QStringList addresses;for(const auto &address:info.addresses())addresses.append(address.toString());
            m_dns={{"state",ok?QStringLiteral("检测成功"):QStringLiteral("DNS 错误")},{"latency",ok?dnsTimer.elapsed():-1}};
            m_log.append(QStringLiteral("系统解析器 %1：%2；%3 ms；这是候选地址，不代表 HTTP 实际连接地址。")
                .arg(info.hostName(),ok?addresses.join(", "):info.errorString()).arg(dnsTimer.elapsed()));emit changed();
        });
        QTimer::singleShot(m_timeout,this,[this,generation]{if(generation==m_dnsGeneration && m_lookup>=0){QHostInfo::abortHostLookup(m_lookup);m_lookup=-1;++m_dnsGeneration;m_dns={{"state",QStringLiteral("探测超时")},{"latency",-1}};emit changed();}});
    }
    reset(m_direct,QStringLiteral("正在检测"));m_direct.endpoint=0;m_direct.pending=true;
    reset(m_proxy,m_proxyPort?QStringLiteral("正在检测"):QStringLiteral("代理未运行"));
    next(m_direct,false);
    if(m_proxyPort){m_proxy.endpoint=0;m_proxy.pending=true;next(m_proxy,true);}
    emit changed();
}
QString NetworkDiagnostics::classify(QNetworkReply::NetworkError error,bool timeout,int code,const QByteArray &body) {
    if(timeout || error==QNetworkReply::TimeoutError || error==QNetworkReply::ProxyTimeoutError)return QStringLiteral("探测超时");
    if(error==QNetworkReply::HostNotFoundError)return QStringLiteral("DNS 错误");
    if(error==QNetworkReply::SslHandshakeFailedError)return QStringLiteral("TLS 错误");
    if(error>=QNetworkReply::ProxyConnectionRefusedError && error<=QNetworkReply::UnknownProxyError)return QStringLiteral("代理链路异常");
    if(code && (code!=204 || !body.isEmpty()))return QStringLiteral("HTTP 响应不符合预期");
    if(error!=QNetworkReply::NoError)return QStringLiteral("TCP 连接失败");
    return code==204 && body.isEmpty()?QStringLiteral("检测成功"):QStringLiteral("HTTP 响应不符合预期");
}
void NetworkDiagnostics::next(Route &route,bool proxy) {
    if(route.endpoint>=m_endpoints.size()){route.pending=false;emit changed();return;}
    const auto url=m_endpoints.at(route.endpoint++);
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    request.setAttribute(QNetworkRequest::CacheLoadControlAttribute,QNetworkRequest::AlwaysNetwork);
    request.setRawHeader("Connection","close");
    auto *reply=route.network.get(request);route.reply=reply;
    reply->setReadBufferSize(8192);
    QElapsedTimer timer;timer.start();
    auto *deadline=new QTimer(reply);deadline->setSingleShot(true);
    connect(deadline,&QTimer::timeout,reply,[reply]{reply->setProperty("timedOut",true);reply->abort();});
    connect(reply,&QNetworkReply::readyRead,reply,[reply]{if(reply->bytesAvailable()>4096){reply->setProperty("oversized",true);reply->abort();}});
    connect(reply,&QNetworkReply::finished,this,[this,&route,reply,deadline,timer,url,proxy]{
        deadline->stop();reply->deleteLater();route.reply=nullptr;
        const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto body=reply->isReadable()?reply->readAll():QByteArray();
        const auto state=reply->property("oversized").toBool()?QStringLiteral("HTTP 响应不符合预期"):classify(reply->error(),reply->property("timedOut").toBool(),code,body);
        const bool ok=state==QStringLiteral("检测成功");
        route.result={{"state",state},{"latency",ok?timer.elapsed():-1},{"endpoint",url.toString()},{"httpStatus",code},{"error",reply->errorString()}};
        const auto entry=QStringLiteral("%1 %2 %3 | %4 | HTTP %5 | Qt %6 | %7 ms | %8")
            .arg(QDateTime::currentDateTime().toString(Qt::ISODate),proxy?QStringLiteral("PROXY"):QStringLiteral("DIRECT"),url.toString(),state)
            .arg(code).arg(int(reply->error())).arg(timer.elapsed()).arg(reply->errorString());
        m_log.append(entry);if(m_log.size()>100)m_log.removeFirst();qInfo().noquote()<<entry;
        if(ok)route.pending=false;
        else next(route,proxy);
        emit changed();
    });
    deadline->start(m_timeout);
}

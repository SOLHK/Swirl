#include "NodeImportService.h"
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QClipboard>
#include <QCoreApplication>
#include <QThreadPool>

NodeImportService::NodeImportService(NodeStore *store,QObject *parent,std::function<qint64()> clock,int interval)
    :QObject(parent),m_store(store),m_clock(clock?std::move(clock):[]{return QDateTime::currentSecsSinceEpoch();}) {
    m_network.setProxy(QNetworkProxy::NoProxy); // Never inherit/change the Windows system proxy.
    m_deadline.setSingleShot(true);m_deadline.setInterval(30000);
    connect(&m_deadline,&QTimer::timeout,this,[this]{if(m_reply)m_reply->abort();});
    connect(&m_timer,&QTimer::timeout,this,&NodeImportService::checkDue);
    connect(store,&NodeStore::changed,this,&NodeImportService::changed);
    m_timer.start(qMax(100,interval));QTimer::singleShot(1000,this,&NodeImportService::checkDue);
}
QVariantList NodeImportService::providers() const {
    auto rows=m_store->publicSubscriptions();
    for(auto &row:rows){auto r=row.toMap();const auto id=r.value("id").toString();
        r.insert("status",m_busy&&id==m_source?QStringLiteral("正在更新"):m_errors.contains(id)?QStringLiteral("更新失败"):r.value("lastSuccess").toLongLong()>0?QStringLiteral("已保存真实节点"):QStringLiteral("等待更新"));
        r.insert("error",m_errors.value(id));
        const auto due=qMax(r.value("lastSuccess").toLongLong()+r.value("intervalMinutes").toLongLong()*60,m_attempts.value(id)+900);
        r.insert("nextUpdate",r.value("enabled").toBool()?QDateTime::fromSecsSinceEpoch(qMax(due,m_clock())).toLocalTime().toString("yyyy-MM-dd HH:mm"):QStringLiteral("已关闭"));row=r;
    }return rows;
}
void NodeImportService::importText(const QString &text) {
    if(m_busy){m_message=QStringLiteral("已有导入或更新正在进行，请稍后重试。");emit changed();return;}
    m_busy=true;m_source.clear();m_message=QStringLiteral("正在解析节点配置…");emit changed();parse(text.toUtf8());
}
void NodeImportService::importClipboard() {
    if(auto *clipboard=QGuiApplication::clipboard())importText(clipboard->text());
}
void NodeImportService::importFile(const QUrl &file) {
    if(m_busy)return;
    if(!file.isLocalFile() || !file.host().isEmpty() || file.toLocalFile().startsWith("\\\\")) {m_message=QStringLiteral("请选择本机 YAML/JSON 文件。");emit changed();return;}
    QFile input(file.toLocalFile());
    if(!input.open(QIODevice::ReadOnly) || input.size()>NodeImporter::MaximumBytes){m_message=QStringLiteral("导入文件无法读取或超过 4 MiB。");emit changed();return;}
    m_busy=true;m_source.clear();m_message=QStringLiteral("正在导入本机配置…");emit changed();parse(input.read(NodeImporter::MaximumBytes+1));
}
void NodeImportService::importUrl(const QUrl &url) {
    if(m_busy)return;
    if(!NodeStore::allowedSubscriptionUrl(url)){m_message=QStringLiteral("请使用 HTTPS 地址；只有本机测试地址允许 HTTP。");emit changed();return;}
    m_busy=true;m_source.clear();m_message=QStringLiteral("正在安全下载节点配置…");emit changed();m_deadline.start();download(url);
}
bool NodeImportService::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled) {
    if(m_busy)return false;
    const bool ok=m_store->saveSubscription(id,name,url,interval,enabled);
    m_message=ok?QStringLiteral("订阅已加密保存；自动更新设置已生效。"):m_store->error();
    if(ok && !id.isEmpty())m_errors.remove(id);
    emit changed();return ok;
}
bool NodeImportService::removeSubscription(const QString &id) {
    if(m_busy)return false;
    const bool ok=m_store->removeSubscription(id);
    m_message=ok?QStringLiteral("订阅已删除，已导入节点保留为手动节点。"):m_store->error();
    m_errors.remove(id);emit changed();return ok;
}
void NodeImportService::refreshSubscription(const QString &id) {
    if(id.isEmpty())return;
    if(!m_queue.contains(id) && !(m_busy&&m_source==id))m_queue.enqueue(id);next();
}
void NodeImportService::refreshAll() {
    for(const auto &s:m_store->subscriptions())if(!m_queue.contains(s.id) && !(m_busy&&m_source==s.id))m_queue.enqueue(s.id);next();
}
void NodeImportService::checkDue() {
    if(m_busy || !m_queue.isEmpty())return;
    const auto now=m_clock();
    for(const auto &s:m_store->subscriptions())if(s.enabled &&
        (s.lastSuccess==0 || now-s.lastSuccess>=s.intervalMinutes*60LL) &&
        (!m_attempts.contains(s.id) || now-m_attempts.value(s.id)>=900))m_queue.enqueue(s.id);
    next();
}
void NodeImportService::next() {
    if(m_busy)return;
    while(!m_queue.isEmpty()) {
        const auto id=m_queue.dequeue();
        for(const auto &s:m_store->subscriptions())if(s.id==id){
            m_source=id;m_busy=true;m_attempts.insert(id,m_clock());m_message=QStringLiteral("正在更新订阅（地址已隐藏）…");emit changed();
            m_deadline.start();download(s.url);return;
        }
    }
}
void NodeImportService::download(const QUrl &url,int redirects) {
    if(!NodeStore::allowedSubscriptionUrl(url) || redirects>5){finish(QStringLiteral("订阅重定向不安全或次数过多；旧节点保持不变。"));return;}
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    request.setRawHeader("User-Agent","Clash.Meta/1.19.32 Swirl/1.0");
    request.setRawHeader("Accept","application/yaml, application/json, text/plain");
    request.setTransferTimeout(15000);
    const bool local=url.host()=="localhost"||url.host()=="127.0.0.1"||url.host()=="::1";
    m_network.setProxy(!local&&m_proxyPort>0?QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",m_proxyPort):QNetworkProxy(QNetworkProxy::NoProxy));
    auto *reply=m_network.get(request);m_reply=reply;reply->setReadBufferSize(NodeImporter::MaximumBytes+1);
    auto bytes=std::make_shared<QByteArray>();auto tooLarge=std::make_shared<bool>(false);
    connect(reply,&QNetworkReply::readyRead,this,[reply,bytes,tooLarge]{
        bytes->append(reply->readAll());if(bytes->size()>NodeImporter::MaximumBytes){*tooLarge=true;reply->abort();}
    });
    connect(reply,&QNetworkReply::finished,this,[this,reply,bytes,tooLarge,url,redirects]{
        if(m_reply==reply)m_reply=nullptr;
        bytes->append(reply->readAll());const auto code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto redirect=reply->attribute(QNetworkRequest::RedirectionTargetAttribute).toUrl();
        const auto error=reply->error();reply->deleteLater();
        if(*tooLarge || bytes->size()>NodeImporter::MaximumBytes){finish(QStringLiteral("订阅内容超过 4 MiB；旧节点保持不变。"));return;}
        if((code==301||code==302||code==303||code==307||code==308) && !redirect.isEmpty()) {
            const auto nextUrl=url.resolved(redirect);
            if(url.scheme()=="https" && nextUrl.scheme()!="https"){finish(QStringLiteral("已拒绝从 HTTPS 降级的重定向。"));return;}
            download(nextUrl,redirects+1);return;
        }
        if(error!=QNetworkReply::NoError){finish(QStringLiteral("订阅下载失败（HTTP %1，网络错误 %2）；请检查认证、TLS 或网络出口。旧节点保持不变。").arg(code).arg(int(error)));return;}
        if(code!=200){finish(QStringLiteral("订阅服务器返回 HTTP %1；旧节点保持不变。").arg(code));return;}
        m_deadline.stop();parse(*bytes);
    });
}
void NodeImportService::parse(QByteArray bytes) {
    QPointer<NodeImportService> guard(this);
    QThreadPool::globalInstance()->start([guard,bytes=std::move(bytes)]() mutable {
        auto result=NodeImporter::parse(bytes);bytes.fill('\0');
        QMetaObject::invokeMethod(QCoreApplication::instance(),[guard,result=std::move(result)]() mutable {
            if(!guard)return;
            if(!result){guard->finish(result.error);return;}
            const auto count=result.nodes.size();
            if(!guard->m_store->importNodes(std::move(result.nodes),guard->m_source)){guard->finish(guard->m_store->error());return;}
            guard->m_message=QStringLiteral("已导入 %1 个真实配置节点；可用性与实际请求需连接后检测。").arg(count);
            emit guard->nodesApplied();guard->finish();
        },Qt::QueuedConnection);
    });
}
void NodeImportService::finish(const QString &error) {
    m_deadline.stop();
    if(!m_source.isEmpty()){if(error.isEmpty())m_errors.remove(m_source);else m_errors.insert(m_source,error);}
    if(!error.isEmpty())m_message=error;
    m_source.clear();m_busy=false;emit changed();QTimer::singleShot(0,this,&NodeImportService::next);
}

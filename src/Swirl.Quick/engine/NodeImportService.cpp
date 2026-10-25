#include "NodeImportService.h"
#include "../network/HttpRequestPolicy.h"
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QNetworkProxyFactory>
#include <QNetworkRequest>
#include <QHostAddress>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QClipboard>
#include <QCoreApplication>
#include <QMetaEnum>
#include <QThreadPool>

namespace {
bool loopbackHost(const QString &host) {
    return host.compare("localhost",Qt::CaseInsensitive)==0 || host.compare("localhost.",Qt::CaseInsensitive)==0 || QHostAddress(host).isLoopback();
}
class DownloadProxyFactory final : public QNetworkProxyFactory {
public:
    explicit DownloadProxyFactory(QList<QNetworkProxy> proxies):m_proxies(std::move(proxies)){}
    QList<QNetworkProxy> queryProxy(const QNetworkProxyQuery &) override{return m_proxies;}
private:
    const QList<QNetworkProxy> m_proxies;
};
}

NodeImportService::NodeImportService(NodeStore *store,QObject *parent,std::function<qint64()> clock,int interval,SystemProxyResolver systemProxies)
    :QObject(parent),m_store(store),m_clock(clock?std::move(clock):[]{return QDateTime::currentSecsSinceEpoch();}),m_systemProxyResolver(std::move(systemProxies)) {
    // Query system/PAC settings only for this downloader. Do not change the
    // application's other sockets or the user's operating-system settings.
    if(!m_systemProxyResolver)m_systemProxyResolver=[](const QNetworkProxyQuery &query){return QNetworkProxyFactory::systemProxyForQuery(query);};
    m_deadline.setSingleShot(true);m_deadline.setInterval(30000);
    connect(&m_deadline,&QTimer::timeout,this,[this]{
        if(!m_busy)return;
        m_downloadTimedOut=true;
        if(m_reply)m_reply->abort();
        else {++m_generation;finish(QStringLiteral("订阅下载超过 30 秒（含系统代理发现）；旧节点保持不变。"));}
    });
    connect(&m_timer,&QTimer::timeout,this,&NodeImportService::checkDue);
    connect(store,&NodeStore::changed,this,&NodeImportService::changed);
    m_timer.start(qMax(100,interval));QTimer::singleShot(1000,this,&NodeImportService::checkDue);
}
QVariantList NodeImportService::providers() const {
    auto rows=m_store->publicSubscriptions();
    for(auto &row:rows){auto r=row.toMap();const auto id=r.value("id").toString();
        const auto outcome=m_store->networkConfiguration().value("subscriptionImportResults").toObject().value(id).toObject();
        const auto mode=outcome.value("mode").toString();
        r.insert("importMode",QStringList{"nodes","full","nodes-with-warning"}.contains(mode)?mode:QString());
        r.insert("warning",outcome.value("notice").toString().left(2048));
        const bool updating=m_busy&&id==m_source,queued=m_queue.contains(id);
        r.insert("status",updating?QStringLiteral("正在更新"):queued?QStringLiteral("等待更新"):m_cancelled.contains(id)?QStringLiteral("已取消"):m_errors.contains(id)?QStringLiteral("更新失败"):r.value("lastSuccess").toLongLong()>0?QStringLiteral("已保存真实节点"):QStringLiteral("等待更新"));
        r.insert("queued",queued);r.insert("canCancel",!m_shuttingDown&&(queued||(updating&&!m_committing)));
        r.insert("error",m_errors.value(id));
        const auto due=qMax(r.value("lastSuccess").toLongLong()+r.value("intervalMinutes").toLongLong()*60,m_attempts.value(id)+900);
        r.insert("nextUpdate",r.value("enabled").toBool()?QDateTime::fromSecsSinceEpoch(qMax(due,m_clock())).toLocalTime().toString("yyyy-MM-dd HH:mm"):QStringLiteral("已关闭"));row=r;
    }return rows;
}
void NodeImportService::importText(const QString &text) {
    parseText(text,QStringLiteral("text"),false);
}
void NodeImportService::importNodesOnlyText(const QString &text) {
    parseText(text,QStringLiteral("text"),true);
}
void NodeImportService::parseText(const QString &text,const QString &origin,bool nodesOnly) {
    if(m_shuttingDown)return;
    if(m_busy || hasPreview()){m_message=QStringLiteral("请先确认或取消当前导入。");emit changed();return;}
    // Every UTF-16 code unit needs at least one UTF-8 byte. Reject this
    // inexpensive bound before allocating; the parser checks exact byte size.
    if(text.size()>NodeImporter::MaximumBytes){m_message=QStringLiteral("配置文本超过 4 MiB；现有节点保持不变。");emit changed();return;}
    m_previewRequested=true;m_importSource=origin;m_nodesOnly=nodesOnly;
    m_busy=true;m_source.clear();m_message=QStringLiteral("正在解析节点配置…");
    QPointer<NodeImportService> guard(this);const auto generation=m_generation;emit changed();
    if(!guard || m_shuttingDown || !m_busy || m_generation!=generation)return;
    QThreadPool::globalInstance()->start([guard,generation,text] {
        auto bytes=text.toUtf8();auto result=NodeImporter::parse(bytes);bytes.fill('\0');
        QMetaObject::invokeMethod(QCoreApplication::instance(),[guard,generation,result=std::move(result)]() mutable {
            if(guard && !guard->m_shuttingDown && guard->m_generation==generation)guard->parsed(std::move(result));
        },Qt::QueuedConnection);
    });
}
void NodeImportService::importClipboard() {
    if(auto *clipboard=QGuiApplication::clipboard())parseText(clipboard->text(),QStringLiteral("clipboard"),false);
}
void NodeImportService::importNodesOnlyClipboard() {
    if(auto *clipboard=QGuiApplication::clipboard())parseText(clipboard->text(),QStringLiteral("clipboard"),true);
}
void NodeImportService::importFile(const QUrl &file) {
    startFile(file,false);
}
void NodeImportService::importNodesOnlyFile(const QUrl &file) {
    startFile(file,true);
}
void NodeImportService::startFile(const QUrl &file,bool nodesOnly) {
    if(m_busy || hasPreview() || m_shuttingDown)return;
    if(!file.isLocalFile() || !file.host().isEmpty() || file.toLocalFile().startsWith("\\\\")) {m_message=QStringLiteral("请选择本机 YAML/JSON 文件。");emit changed();return;}
    m_busy=true;m_source.clear();m_importSource="file";m_previewRequested=true;m_nodesOnly=nodesOnly;
    m_message=QStringLiteral("正在读取并校验本机配置…");
    const auto path=file.toLocalFile();QPointer<NodeImportService> guard(this);const auto generation=m_generation;emit changed();
    if(!guard || m_shuttingDown || !m_busy || m_generation!=generation)return;
    QThreadPool::globalInstance()->start([guard,path,generation]{
        NodeImporter::Result result;
        const QFileInfo info(path);QFile input(path);
        if(!info.isFile() || info.size()>NodeImporter::MaximumBytes || !input.open(QIODevice::ReadOnly))
            result.error=QStringLiteral("请选择可读取的普通文件，大小不得超过 4 MiB。");
        else {
            auto bytes=input.read(NodeImporter::MaximumBytes+1);
            if(input.error()!=QFileDevice::NoError || bytes.size()>NodeImporter::MaximumBytes)
                result.error=QStringLiteral("文件读取失败或已超过 4 MiB；原节点保持不变。");
            else result=NodeImporter::parse(bytes);
            bytes.fill('\0');
        }
        QMetaObject::invokeMethod(QCoreApplication::instance(),[guard,generation,result=std::move(result)]() mutable {
            if(guard && !guard->m_shuttingDown && guard->m_generation==generation)guard->parsed(std::move(result));
        },Qt::QueuedConnection);
    });
}
void NodeImportService::importUrl(const QUrl &url) {
    startUrl(url,false);
}
void NodeImportService::importNodesOnlyUrl(const QUrl &url) {
    startUrl(url,true);
}
void NodeImportService::startUrl(const QUrl &url,bool nodesOnly) {
    if(m_busy || hasPreview() || m_shuttingDown)return;
    if(!m_store->configurationAvailable()){m_message=QStringLiteral("配置库需要恢复或重新打开；未发起下载。");emit changed();return;}
    if(!NodeStore::allowedSubscriptionUrl(url)){m_message=QStringLiteral("请使用 HTTPS 地址；只有本机测试地址允许 HTTP。");emit changed();return;}
    m_previewRequested=true;m_importSource="url";m_downloadTimedOut=false;m_nodesOnly=nodesOnly;
    m_downloadUrl=url;m_compatibilityRequest=false;m_downloadAttempts=0;
    m_busy=true;m_source.clear();m_formatHint="auto";m_message=QStringLiteral("正在安全下载节点配置…");
    const QPointer<NodeImportService> guard(this);const auto generation=m_generation;emit changed();
    if(!guard || m_shuttingDown || !m_busy || m_generation!=generation)return;
    m_deadline.start();download(url);
}
bool NodeImportService::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled,const QString &formatHint,const QString &importScope) {
    if(m_busy || hasPreview())return false;
    if(m_store->configurationV2())return mutateCatalog("save_subscription",{{"id",id},{"name",name},{"url",url},{"interval",interval},{"enabled",enabled},{"formatHint",formatHint},{"importScope",importScope}},QStringLiteral("订阅已加密保存；自动更新设置已生效。"));
    const bool ok=m_store->saveSubscription(id,name,url,interval,enabled,formatHint,importScope);
    m_message=ok?QStringLiteral("订阅已加密保存；自动更新设置已生效。"):m_store->error();
    if(ok && !id.isEmpty()){m_errors.remove(id);m_cancelled.remove(id);}
    emit changed();return ok;
}
bool NodeImportService::removeSubscription(const QString &id) {
    if(m_busy || hasPreview())return false;
    if(m_store->configurationV2())return mutateCatalog("remove_subscription",{{"id",id}},QStringLiteral("订阅及关联节点已删除；相关流量撤销已确认。"));
    const bool ok=m_store->removeSubscription(id);
    m_message=ok?QStringLiteral("订阅及其所属节点已原子删除；手动节点与待确认归属的历史节点保持不变。"):m_store->error();
    if(ok){m_cancelled.remove(id);m_errors.remove(id);m_queue.removeAll(id);m_attempts.remove(id);}
    emit changed();return ok;
}
bool NodeImportService::cleanLegacyNodes() {
    if(m_busy || hasPreview())return false;
    if(m_store->configurationV2())return mutateCatalog("clean_legacy",{},QStringLiteral("历史未归属节点已清理；相关流量撤销已确认。"));
    const auto count=m_store->legacyNodeCount();
    const bool ok=m_store->cleanLegacyNodes();
    m_message=ok?QStringLiteral("已清理 %1 个历史未归属节点，剩余 %2 个节点；已确认的手动节点与有效订阅节点保持不变。")
        .arg(count).arg(m_store->nodes().size()):m_store->error();
    emit changed();return ok;
}
void NodeImportService::refreshSubscription(const QString &id) {
    if(id.isEmpty() || m_shuttingDown)return;
    if(!m_store->configurationAvailable()){m_message=QStringLiteral("配置库需要恢复或重新打开；未使用旧来源发起更新。");emit changed();return;}
    const QPointer<NodeImportService> guard(this);
    if(!m_queue.contains(id) && !(m_busy&&m_source==id)){m_queue.enqueue(id);emit changed();}
    if(guard)next();
}
void NodeImportService::refreshAll() {
    if(m_shuttingDown)return;
    if(!m_store->configurationAvailable()){m_message=QStringLiteral("配置库需要恢复或重新打开；未使用旧来源发起更新。");emit changed();return;}
    bool queued=false;
    for(const auto &s:m_store->subscriptions())if(!m_queue.contains(s.id) && !(m_busy&&m_source==s.id)){m_queue.enqueue(s.id);queued=true;}
    const QPointer<NodeImportService> guard(this);
    if(queued)emit changed();if(guard)next();
}
bool NodeImportService::cancelRefresh(const QString &id) {
    if(id.isEmpty() || m_shuttingDown)return false;
    const bool active=m_busy&&m_source==id;
    // Encryption/atomic commit already owns a durable write lease. Do not
    // report cancellation after any node state may have been committed.
    if(active&&m_committing)return false;
    const bool queued=m_queue.removeAll(id)>0;
    if(!active&&!queued)return false;
    m_cancelled.insert(id);m_errors.remove(id);m_attempts.insert(id,m_clock());
    m_message=active?QStringLiteral("已取消订阅更新，现有节点保持不变。"):QStringLiteral("已取消此订阅的排队更新，现有节点保持不变。");
    if(active){
        ++m_generation; // Revoke late system-proxy discovery and parser callbacks.
        if(m_reply){m_reply->disconnect(this);m_reply->abort();m_reply->deleteLater();m_reply=nullptr;}
        m_pending.reset();finish();
    }else emit changed();
    return true;
}
void NodeImportService::shutdown() {
    m_shuttingDown=true;++m_generation;m_timer.stop();m_deadline.stop();m_queue.clear();
    m_pending.reset();m_sourceDefinition.reset();
    if(m_reply){m_reply->disconnect(this);m_reply->abort();m_reply->deleteLater();m_reply=nullptr;}
    m_busy=false;
}
void NodeImportService::checkDue() {
    if(m_shuttingDown)return;
    if(!m_store->configurationAvailable())return;
    if(m_busy || hasPreview() || !m_queue.isEmpty())return;
    const auto now=m_clock();
    for(const auto &s:m_store->subscriptions())if(s.enabled &&
        (s.lastSuccess==0 || now-s.lastSuccess>=s.intervalMinutes*60LL) &&
        (!m_attempts.contains(s.id) || now-m_attempts.value(s.id)>=900))m_queue.enqueue(s.id);
    next();
}
void NodeImportService::next() {
    if(m_shuttingDown)return;
    if(!m_store->configurationAvailable()){m_queue.clear();return;}
    if(m_busy || hasPreview())return;
    while(!m_queue.isEmpty()) {
        const auto id=m_queue.dequeue();
        for(const auto &s:m_store->subscriptions())if(s.id==id){
            // Direct signal handlers can cancel, edit or remove this provider.
            // Keep value copies and do not start work after a cancelled signal.
            const auto url=s.url;const auto generation=m_generation;
            const QPointer<NodeImportService> guard(this);
            m_cancelled.remove(id);
            m_previewRequested=false;m_importSource="subscription";m_downloadTimedOut=false;
            m_downloadUrl=url;m_compatibilityRequest=false;m_downloadAttempts=0;
            // Legacy scope values never authorize a background policy change.
            // Only an explicit, separately reviewed operation may apply one.
            m_sourceDefinition=s;
            m_source=id;m_formatHint=s.formatHint;m_nodesOnly=true;m_automaticImport=true;
            m_appliedMode.clear();m_applicationNotice.clear();m_busy=true;m_attempts.insert(id,m_clock());m_message=QStringLiteral("正在下载并自动识别订阅（地址已隐藏）…");emit changed();
            if(!guard || m_shuttingDown || !m_busy || m_source!=id || m_generation!=generation)return;
            if(!sourceDefinitionCurrent()){finish(QStringLiteral("订阅定义已更改，已丢弃旧响应；请重新更新。"));return;}
            m_deadline.start();download(url);return;
        }
    }
}
void NodeImportService::setDownloadProxy(int port) {
    m_proxyPort=port>0&&port<=65535?port:0;
    rememberOwnedProxyPort(m_proxyPort);
}
void NodeImportService::rememberOwnedProxyPort(int port) {
    // Only actual runtime ports are recorded. A third-party loopback proxy at
    // a coincidentally configured but never-used Swirl port remains eligible.
    if(port>0&&port<=65535)m_ownedProxyPorts.insert(quint16(port));
}
void NodeImportService::download(const QUrl &url,int redirects) {
    if(!NodeStore::allowedSubscriptionUrl(url) || redirects>5){finish(QStringLiteral("订阅重定向不安全或次数过多；旧节点保持不变。"));return;}
    if(loopbackHost(url.host())){startDownload(url,redirects,{QNetworkProxy(QNetworkProxy::NoProxy)});return;}
    if(m_proxyPort){startDownload(url,redirects,{QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",quint16(m_proxyPort))});return;}
    // PAC discovery can block in platform APIs. Keep it off the UI thread and
    // within the same cancellation generation / total download deadline.
    const auto resolver=m_systemProxyResolver;const auto generation=m_generation;QPointer<NodeImportService> guard(this);
    QThreadPool::globalInstance()->start([guard,generation,resolver,url,redirects]{
        const auto proxies=resolver(QNetworkProxyQuery(url));
        QMetaObject::invokeMethod(QCoreApplication::instance(),[guard,generation,url,redirects,proxies]{
            if(!guard || guard->m_shuttingDown || !guard->m_busy || guard->m_generation!=generation)return;
            if(guard->m_proxyPort){guard->startDownload(url,redirects,{QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",quint16(guard->m_proxyPort))});return;}
            QList<QNetworkProxy> usable;bool stoppedCore=false;
            for(const auto &proxy:proxies){
                if(proxy.type()==QNetworkProxy::NoProxy){usable.append(proxy);continue;}
                if(loopbackHost(proxy.hostName()) && guard->m_ownedProxyPorts.contains(proxy.port())){stoppedCore=true;continue;}
                if(proxy.hostName().isEmpty() || !proxy.port())continue;
                if(proxy.type()==QNetworkProxy::HttpProxy || proxy.type()==QNetworkProxy::Socks5Proxy ||
                   (url.scheme()=="http" && proxy.type()==QNetworkProxy::HttpCachingProxy))usable.append(proxy);
            }
            if(usable.isEmpty()){
                guard->finish(stoppedCore?QStringLiteral("系统代理仍指向已停止的 Swirl 端口；请恢复系统代理或重新连接后重试。旧节点保持不变。"):
                    QStringLiteral("无法获得适用于订阅下载的系统代理；请检查系统代理设置后重试。旧节点保持不变。"));return;
            }
            // Preserve the platform's ordered alternatives, including DIRECT
            // only when the platform explicitly returned NoProxy.
            guard->startDownload(url,redirects,usable);
        },Qt::QueuedConnection);
    });
}
void NodeImportService::startDownload(const QUrl &url,int redirects,const QList<QNetworkProxy> &proxies) {
    if(!m_store->configurationAvailable()){finish(QStringLiteral("配置库需要恢复或重新打开；未使用旧来源发起下载。"));return;}
    QNetworkRequest request(url);
    SwirlNetwork::applyHttp1OnlyPolicy(request);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    const QHash<QString,QByteArray> agents{{"auto","Swirl/"+QCoreApplication::applicationVersion().toUtf8()},{"clash","Clash.Meta/1.19.32 Swirl"},{"loon","Loon/1.0"},{"shadowrocket","Shadowrocket/2.2.67"},{"surge","Surge/5.0"},{"quantumult-x","Quantumult X/1.0"},{"sing-box","sing-box/1.12"}};
    // Some subscription services negotiate solely through a known client UA.
    // Keep Swirl's native request first, with one bounded retry using the exact
    // previously shipped automatic identity. The response still determines its
    // format and passes every existing parser/profile/security check.
    request.setRawHeader("User-Agent",m_compatibilityRequest?QByteArray("Clash.Meta/1.19.32 Swirl/1.0"):agents.value(m_formatHint,agents.value("auto")));
    request.setRawHeader("Accept","application/json, application/yaml, text/yaml, text/plain, */*;q=0.5");
    request.setTransferTimeout(15000);
    m_network.setProxyFactory(new DownloadProxyFactory(proxies));
    auto *reply=m_network.get(request);m_reply=reply;reply->setReadBufferSize(64*1024);
    const auto generation=m_generation;
    const auto attempt=++m_downloadAttempts;
    const auto negotiation=m_compatibilityRequest?QStringLiteral("legacy-auto"):QStringLiteral("native");
    const auto format=agents.contains(m_formatHint)?m_formatHint:QStringLiteral("auto");
    const auto route=loopbackHost(url.host())?QStringLiteral("loopback-direct"):
        proxies.size()==1 && proxies.first().type()==QNetworkProxy::NoProxy?QStringLiteral("direct-policy"):
        proxies.size()==1 && loopbackHost(proxies.first().hostName())?QStringLiteral("loopback-proxy"):QStringLiteral("proxy-policy");
    auto bytes=std::make_shared<QByteArray>();auto tooLarge=std::make_shared<bool>(false);
    connect(reply,&QNetworkReply::metaDataChanged,this,[reply,tooLarge] {
        bool ok=false;const auto length=reply->header(QNetworkRequest::ContentLengthHeader).toLongLong(&ok);
        if(ok && length>NodeImporter::MaximumBytes){*tooLarge=true;reply->abort();}
    });
    const auto drain=[reply,bytes,tooLarge] {
        while(!*tooLarge && reply->bytesAvailable()>0) {
            const auto remaining=NodeImporter::MaximumBytes+1-bytes->size();
            const auto chunk=reply->read(qMin<qint64>(64*1024,remaining));
            if(chunk.isEmpty())break;
            bytes->append(chunk);
            if(bytes->size()>NodeImporter::MaximumBytes){*tooLarge=true;reply->abort();}
        }
    };
    connect(reply,&QNetworkReply::readyRead,this,drain);
    connect(reply,&QNetworkReply::finished,this,[this,reply,bytes,tooLarge,url,redirects,generation,drain,proxies,attempt,negotiation,format,route]{
        if(m_shuttingDown || generation!=m_generation){reply->deleteLater();return;}
        if(m_reply==reply)m_reply=nullptr;
        drain();const auto code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto redirect=reply->attribute(QNetworkRequest::RedirectionTargetAttribute).toUrl();
        const auto error=reply->error();reply->deleteLater();
        const QPointer<NodeImportService> guard(this);
        emit downloadDiagnostic(QStringLiteral("attempt=%1; negotiation=%2; format=%3; route=%4; http=%5; qt=%6")
            .arg(attempt).arg(negotiation,format,route).arg(code).arg(int(error)));
        if(!guard || guard->m_shuttingDown || guard->m_generation!=generation || !guard->m_busy)return;
        if(*tooLarge || bytes->size()>NodeImporter::MaximumBytes){finish(QStringLiteral("订阅内容超过 4 MiB；旧节点保持不变。"));return;}
        if(m_downloadTimedOut){finish(QStringLiteral("订阅下载超过 30 秒；旧节点保持不变。"));return;}
        if(code==301||code==302||code==303||code==307||code==308) {
            if(redirect.isEmpty()){finish(QStringLiteral("订阅重定向失败：HTTP %1 未提供有效 Location；旧节点保持不变。").arg(code));return;}
            const auto nextUrl=url.resolved(redirect);
            if(url.scheme()=="https" && nextUrl.scheme()!="https"){finish(QStringLiteral("已拒绝从 HTTPS 降级的重定向。"));return;}
            // Signed URLs and cookies must not cross an untrusted origin.
            // Do not reflect either URL (which may include a secret) in errors.
            const auto defaultPort=url.scheme()=="https"?443:80;
            if(!NodeStore::allowedSubscriptionUrl(nextUrl) ||
                nextUrl.scheme()!=url.scheme() || nextUrl.host().compare(url.host(),Qt::CaseInsensitive)!=0 ||
                nextUrl.port(defaultPort)!=url.port(defaultPort)) {
                finish(QStringLiteral("重定向目标不安全或不属于同一来源；请直接提供已授权的最终 HTTPS 地址。旧节点保持不变。"));return;
            }
            download(nextUrl,redirects+1);return;
        }
        const auto errorName=QString::fromLatin1(QMetaEnum::fromType<QNetworkReply::NetworkError>().valueToKey(int(error)));
        if(m_formatHint=="auto" && !m_compatibilityRequest && (code==400 || code==406 || code==415)) {
            m_compatibilityRequest=true;
            // Retry the saved QUrl without decoding/rebuilding its signed query.
            // Preserve the proxy alternatives and the existing total deadline
            // and redirect budget; never introduce a direct-connect fallback.
            startDownload(m_downloadUrl,redirects,proxies);return;
        }
        // A Qt enum such as ProtocolInvalidOperationError (302) is not
        // HTTP 302. Preserve the two namespaces without exposing errorString(),
        // which may contain the full credential-bearing request URL.
        if(code>=400){
            const auto reason=code==400?QStringLiteral("请求被服务器拒绝；请检查认证参数与订阅格式协商"):
                code==401||code==403?QStringLiteral("服务器拒绝认证或访问权限"):QStringLiteral("服务器返回错误响应");
            finish(QStringLiteral("订阅下载失败：HTTP %1，%2（Qt %3，代码 %4；非 HTTP 状态码）。旧节点保持不变。").arg(code).arg(reason,errorName).arg(int(error)));return;
        }
        if(error!=QNetworkReply::NoError){
            const auto stage=error==QNetworkReply::SslHandshakeFailedError?QStringLiteral("TLS 校验或握手失败"):
                error==QNetworkReply::TimeoutError?QStringLiteral("网络请求超时"):
                error==QNetworkReply::TooManyRedirectsError||error==QNetworkReply::InsecureRedirectError?QStringLiteral("重定向失败"):QStringLiteral("网络连接失败");
            finish(QStringLiteral("订阅下载失败：%1（Qt %2，代码 %3；HTTP %4）。旧节点保持不变。").arg(stage,errorName).arg(int(error)).arg(code));return;
        }
        if(code!=200){finish(QStringLiteral("订阅下载失败：服务器返回 HTTP %1；旧节点保持不变。").arg(code));return;}
        m_deadline.stop();parse(*bytes);
    });
}
void NodeImportService::parse(QByteArray bytes) {
    QPointer<NodeImportService> guard(this);const auto generation=m_generation;
    QThreadPool::globalInstance()->start([guard,generation,bytes=std::move(bytes)]() mutable {
        auto result=NodeImporter::parse(bytes);bytes.fill('\0');
        QMetaObject::invokeMethod(QCoreApplication::instance(),[guard,generation,result=std::move(result)]() mutable {
            if(!guard || guard->m_shuttingDown || guard->m_generation!=generation)return;
            guard->parsed(std::move(result));
        },Qt::QueuedConnection);
    });
}
QVariantList NodeImportService::preview() const {
    QVariantList rows;
    if(m_pending)for(const auto &node:m_pending->nodes)rows.append(node.publicInfo());
    return rows;
}
void NodeImportService::parsed(NodeImporter::Result result) {
    if(!result){finish((result.errorKind=="unsupported-format"?QStringLiteral("订阅格式不支持：%1"):QStringLiteral("订阅内容解析失败：%1")).arg(result.error));return;}
    for(auto &node:result.nodes)node.importSource=m_importSource;
    if(m_previewRequested && result.format=="xray-v2ray-json") {
        const auto count=result.nodes.size();const auto unsupported=result.incompleteNodes;
        m_pending=std::move(result);m_busy=false;
        m_message=QStringLiteral("JSON 格式校验通过，共 %1 个节点，%2 个当前不可执行。确认后加密保存；尚未验证实际联网。").arg(count).arg(unsupported);
        emit changed();return;
    }
    apply(std::move(result));
}
void NodeImportService::confirmImport() {
    if(m_busy || !m_pending || m_shuttingDown)return;
    m_busy=true;auto result=std::move(*m_pending);m_pending.reset();
    const QPointer<NodeImportService> guard(this);const auto generation=m_generation;emit changed();
    if(!guard || m_shuttingDown || !m_busy || m_generation!=generation)return;
    apply(std::move(result));
}
void NodeImportService::cancelImport() {
    // Closing a manual dialog must discard its in-flight worker/download.
    // A background subscription refresh is owned by the subscription queue.
    if(m_shuttingDown || m_committing || !m_source.isEmpty() || (!m_busy && !m_pending))return;
    ++m_generation;
    if(m_reply){m_reply->disconnect(this);m_reply->abort();m_reply->deleteLater();m_reply=nullptr;}
    m_pending.reset();m_message=QStringLiteral("已取消导入，现有节点保持不变。");finish();
}
void NodeImportService::apply(NodeImporter::Result result) {
    if(m_automaticImport){
        m_nodesOnly=true;
        if(!sourceDefinitionCurrent()){
            finish(QStringLiteral("订阅已删除或定义已更改，已丢弃旧响应；现有配置保持不变。"));return;
        }
    }
    const auto count=result.nodes.size();
    int certificatesEnforced=0;for(const auto &node:result.nodes)if(node.certificateVerificationEnforced)++certificatesEnforced;
    if(m_nodesOnly && !m_apply && !m_applyAsync){
        finish(QStringLiteral("节点专用导入无法校验当前网络配置；旧节点保持不变。"));return;
    }
    if(m_store->configurationV2()&&!m_applyAsync){
        finish(QStringLiteral("V2 节点导入缺少配置事务入口；原配置保持不变。"));return;
    }
    if((result.format=="xray-v2ray-json" && (m_applyAsync || !m_apply)) || m_store->configurationV2()) {
        const QPointer<NodeImportService> guard(this);const auto generation=m_generation;
        m_committing=true;m_message=QStringLiteral("正在加密并原子保存节点…");emit changed();
        if(!guard || m_shuttingDown || !m_busy || m_generation!=generation)return;
        auto completion=[guard,generation,format=result.format,count,incomplete=result.incompleteNodes,certificatesEnforced](bool ok,const QString &error) {
            if(!guard || guard->m_shuttingDown || guard->m_generation!=generation)return;
            if(!ok){guard->finish(error.isEmpty()?QStringLiteral("节点保存失败；旧配置保持不变。"):error);return;}
            // Keep the write boundary through nodesApplied. Its direct signal
            // handlers must not report cancellation after the durable commit.
            guard->applied(format,count,incomplete,certificatesEnforced);
        };
        QString error;bool queued=false;
        if(m_applyAsync)queued=m_applyAsync(result,m_source,m_nodesOnly,std::move(completion),&error);
        else if(!result.configuration.isEmpty())error=QStringLiteral("JSON 导入不允许应用第三方全局配置。");
        else {
            NodeStore::ImportPlan plan;
            if(m_store->prepareImport(result.nodes,m_source,&plan))queued=m_store->commitImportAsync(plan,{},std::move(completion));
            if(!queued)error=m_store->error();
        }
        if(!queued){m_committing=false;finish(error.isEmpty()?QStringLiteral("无法开始安全保存；旧配置保持不变。"):error);}
        return;
    }
    const QPointer<NodeImportService> guard(this);const auto generation=m_generation;
    m_committing=true;emit changed();
    if(!guard || m_shuttingDown || !m_busy || m_generation!=generation)return;
    if(m_apply || m_nodesOnly || !result.configuration.isEmpty()) {
        QString error;
        if(!m_apply || !m_apply(result,m_source,m_nodesOnly,&error)) {
            if(error.isEmpty())error=QStringLiteral("当前入口不能验证完整配置语义；旧配置保持不变。");
            finish(m_nodesOnly?error:QStringLiteral("完整配置校验失败：%1").arg(error));return;
        }
    } else if(!m_store->importNodes(std::move(result.nodes),m_source)){finish(m_store->error());return;}
    applied(result.format,count,result.incompleteNodes,certificatesEnforced);
}
void NodeImportService::applied(const QString &format,qsizetype count,int incomplete,int certificatesEnforced) {
    if(!m_source.isEmpty()){
        qsizetype saved=0;int unsupported=0;
        // The durable catalog has already merged identical source records.
        // Reuse the same cached capability rows displayed by the node list.
        for(const auto &value:m_store->publicRows()){
            const auto row=value.toMap();if(row.value("sourceId").toString()!=m_source)continue;
            ++saved;if(!row.value("nativeExecutable").toBool())++unsupported;
        }
        m_message=QStringLiteral("%1 · 已解析 %2 条节点记录，合并重复后保存 %3 个节点；实际联网需检测。").arg(format).arg(count).arg(saved);
        if(unsupported)m_message+=QStringLiteral(" %1 个已保存节点当前不可执行，原始参数已加密保留。").arg(unsupported);
    }else{
        m_message=QStringLiteral("%1 · 已处理 %2 条节点记录，相同节点已合并保存；实际联网需检测。").arg(format).arg(count);
        if(incomplete)m_message+=QStringLiteral(" %1 条记录含无效或尚未映射的参数，原始参数已加密保留。").arg(incomplete);
    }
    if(m_nodesOnly&&!m_automaticImport)m_message+=QStringLiteral(" 本次仅更新节点；DNS、规则与策略组保持不变。");
    if(m_automaticImport) {
        m_message+=QStringLiteral(" 已自动提取节点；使用现有 Swirl DNS、规则与策略组。");
        if(!m_applicationNotice.isEmpty())m_message+=QStringLiteral(" ")+m_applicationNotice;
    }
    if(m_compatibilityRequest)m_message+=QStringLiteral(" 已通过兼容客户端格式协商下载，内容仍按实际格式完成校验。");
    if(certificatesEnforced)m_message+=QStringLiteral(" %1 条 Trojan 记录原请求跳过证书验证；Swirl 已保持验证开启，证书异常仍会拒绝连接。详情页可查看说明。").arg(certificatesEnforced);
    const QPointer<NodeImportService> guard(this);emit nodesApplied();if(guard)finish();
}
void NodeImportService::finish(const QString &error) {
    m_deadline.stop();
    if(!m_source.isEmpty()){if(error.isEmpty())m_errors.remove(m_source);else m_errors.insert(m_source,error);}
    if(!error.isEmpty())m_message=error;
    m_source.clear();m_sourceDefinition.reset();m_busy=false;m_committing=false;m_nodesOnly=false;m_automaticImport=false;
    m_downloadUrl=QUrl();m_compatibilityRequest=false;m_downloadAttempts=0;
    m_appliedMode.clear();m_applicationNotice.clear();
    const QPointer<NodeImportService> guard(this);emit changed();if(guard)QTimer::singleShot(0,this,&NodeImportService::next);
}
bool NodeImportService::sourceDefinitionCurrent() const {
    if(!m_sourceDefinition||m_sourceDefinition->id!=m_source)return false;
    const auto &captured=*m_sourceDefinition;
    for(const auto &current:m_store->subscriptions())if(current.id==m_source)
        return current.url==captured.url&&current.name==captured.name&&
            current.formatHint==captured.formatHint&&current.importScope==captured.importScope&&
            current.intervalMinutes==captured.intervalMinutes&&current.enabled==captured.enabled;
    return false;
}
bool NodeImportService::mutateCatalog(const QString &operation,const QVariantMap &input,const QString &successMessage) {
    if(m_shuttingDown||m_busy||hasPreview()||!m_catalogApply){
        m_message=QStringLiteral("目录事务不可用或仍在进行；现有数据保持不变。");emit changed();return false;
    }
    m_busy=true;m_committing=true;m_source.clear();m_sourceDefinition.reset();
    m_message=QStringLiteral("正在安全保存目录变更，等待配置与撤销回执…");
    const QPointer<NodeImportService> guard(this);const auto generation=m_generation;emit changed();
    if(!guard||m_shuttingDown||m_generation!=generation)return false;
    auto completion=[guard,generation,operation,id=input.value("id").toString(),successMessage](bool ok,const QString &error){
        if(!guard||guard->m_shuttingDown||guard->m_generation!=generation)return;
        if(!ok){guard->finish(error.isEmpty()?QStringLiteral("目录变更未完成；请检查配置恢复状态。"):error);return;}
        if(operation=="remove_subscription"){
            guard->m_cancelled.remove(id);guard->m_errors.remove(id);guard->m_queue.removeAll(id);guard->m_attempts.remove(id);
        }else if(operation=="save_subscription"&&!id.isEmpty()){
            guard->m_cancelled.remove(id);guard->m_errors.remove(id);
        }
        guard->m_message=successMessage;emit guard->nodesApplied();if(guard)guard->finish();
    };
    QString error;
    const bool queued=m_catalogApply(operation,input,std::move(completion),&error);
    if(!queued&&guard)finish(error.isEmpty()?QStringLiteral("无法受理目录变更；原配置保持不变。"):error);
    return queued;
}

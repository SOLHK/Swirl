#include "NodeImportService.h"
#include "../network/HttpRequestPolicy.h"
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
    connect(&m_deadline,&QTimer::timeout,this,[this]{m_downloadTimedOut=true;if(m_reply)m_reply->abort();});
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
    parseText(text,QStringLiteral("text"));
}
void NodeImportService::parseText(const QString &text,const QString &origin) {
    if(m_shuttingDown)return;
    if(m_busy || hasPreview()){m_message=QStringLiteral("请先确认或取消当前导入。");emit changed();return;}
    // Every UTF-16 code unit needs at least one UTF-8 byte. Reject this
    // inexpensive bound before allocating; the parser checks exact byte size.
    if(text.size()>NodeImporter::MaximumBytes){m_message=QStringLiteral("配置文本超过 4 MiB；现有节点保持不变。");emit changed();return;}
    m_previewRequested=true;m_importSource=origin;
    m_busy=true;m_source.clear();m_message=QStringLiteral("正在解析节点配置…");emit changed();
    QPointer<NodeImportService> guard(this);const auto generation=m_generation;
    QThreadPool::globalInstance()->start([guard,generation,text] {
        auto bytes=text.toUtf8();auto result=NodeImporter::parse(bytes);bytes.fill('\0');
        QMetaObject::invokeMethod(QCoreApplication::instance(),[guard,generation,result=std::move(result)]() mutable {
            if(guard && !guard->m_shuttingDown && guard->m_generation==generation)guard->parsed(std::move(result));
        },Qt::QueuedConnection);
    });
}
void NodeImportService::importClipboard() {
    if(auto *clipboard=QGuiApplication::clipboard())parseText(clipboard->text(),QStringLiteral("clipboard"));
}
void NodeImportService::importFile(const QUrl &file) {
    if(m_busy || hasPreview() || m_shuttingDown)return;
    if(!file.isLocalFile() || !file.host().isEmpty() || file.toLocalFile().startsWith("\\\\")) {m_message=QStringLiteral("请选择本机 YAML/JSON 文件。");emit changed();return;}
    m_busy=true;m_source.clear();m_importSource="file";m_previewRequested=true;
    m_message=QStringLiteral("正在读取并校验本机配置…");emit changed();
    const auto path=file.toLocalFile();QPointer<NodeImportService> guard(this);const auto generation=m_generation;
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
    if(m_busy || hasPreview() || m_shuttingDown)return;
    if(!NodeStore::allowedSubscriptionUrl(url)){m_message=QStringLiteral("请使用 HTTPS 地址；只有本机测试地址允许 HTTP。");emit changed();return;}
    m_previewRequested=true;m_importSource="url";m_downloadTimedOut=false;
    m_busy=true;m_source.clear();m_formatHint="auto";m_message=QStringLiteral("正在安全下载节点配置…");emit changed();m_deadline.start();download(url);
}
bool NodeImportService::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled,const QString &formatHint) {
    if(m_busy || hasPreview())return false;
    const bool ok=m_store->saveSubscription(id,name,url,interval,enabled,formatHint);
    m_message=ok?QStringLiteral("订阅已加密保存；自动更新设置已生效。"):m_store->error();
    if(ok && !id.isEmpty())m_errors.remove(id);
    emit changed();return ok;
}
bool NodeImportService::removeSubscription(const QString &id) {
    if(m_busy || hasPreview())return false;
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
void NodeImportService::shutdown() {
    m_shuttingDown=true;++m_generation;m_timer.stop();m_deadline.stop();m_queue.clear();
    m_pending.reset();
    if(m_reply){m_reply->disconnect(this);m_reply->abort();m_reply->deleteLater();m_reply=nullptr;}
    m_busy=false;
}
void NodeImportService::checkDue() {
    if(m_shuttingDown)return;
    if(m_busy || hasPreview() || !m_queue.isEmpty())return;
    const auto now=m_clock();
    for(const auto &s:m_store->subscriptions())if(s.enabled &&
        (s.lastSuccess==0 || now-s.lastSuccess>=s.intervalMinutes*60LL) &&
        (!m_attempts.contains(s.id) || now-m_attempts.value(s.id)>=900))m_queue.enqueue(s.id);
    next();
}
void NodeImportService::next() {
    if(m_shuttingDown)return;
    if(m_busy || hasPreview())return;
    while(!m_queue.isEmpty()) {
        const auto id=m_queue.dequeue();
        for(const auto &s:m_store->subscriptions())if(s.id==id){
            m_previewRequested=false;m_importSource="subscription";m_downloadTimedOut=false;
            m_source=id;m_formatHint=s.formatHint;m_busy=true;m_attempts.insert(id,m_clock());m_message=QStringLiteral("正在更新订阅（地址已隐藏）…");emit changed();
            m_deadline.start();download(s.url);return;
        }
    }
}
void NodeImportService::download(const QUrl &url,int redirects) {
    if(!NodeStore::allowedSubscriptionUrl(url) || redirects>5){finish(QStringLiteral("订阅重定向不安全或次数过多；旧节点保持不变。"));return;}
    QNetworkRequest request(url);
    SwirlNetwork::applyHttp1OnlyPolicy(request);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    const QHash<QString,QByteArray> agents{{"auto","Clash.Meta/1.19.32 Swirl/1.0"},{"loon","Loon/1.0"},{"shadowrocket","Shadowrocket/2.2.67"},{"surge","Surge/5.0"},{"quantumult-x","Quantumult X/1.0"},{"sing-box","sing-box/1.12"}};
    request.setRawHeader("User-Agent",agents.value(m_formatHint,agents.value("auto")));
    request.setRawHeader("Accept","application/json, application/yaml, text/plain");
    request.setTransferTimeout(15000);
    const bool local=url.host()=="localhost"||url.host()=="127.0.0.1"||url.host()=="::1";
    m_network.setProxy(!local&&m_proxyPort>0?QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",m_proxyPort):QNetworkProxy(QNetworkProxy::NoProxy));
    auto *reply=m_network.get(request);m_reply=reply;reply->setReadBufferSize(64*1024);
    const auto generation=m_generation;
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
    connect(reply,&QNetworkReply::finished,this,[this,reply,bytes,tooLarge,url,redirects,generation,drain]{
        if(m_shuttingDown || generation!=m_generation){reply->deleteLater();return;}
        if(m_reply==reply)m_reply=nullptr;
        drain();const auto code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto redirect=reply->attribute(QNetworkRequest::RedirectionTargetAttribute).toUrl();
        const auto error=reply->error();reply->deleteLater();
        if(*tooLarge || bytes->size()>NodeImporter::MaximumBytes){finish(QStringLiteral("订阅内容超过 4 MiB；旧节点保持不变。"));return;}
        if(m_downloadTimedOut){finish(QStringLiteral("订阅下载超过 30 秒；旧节点保持不变。"));return;}
        if((code==301||code==302||code==303||code==307||code==308) && !redirect.isEmpty()) {
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
        if(error!=QNetworkReply::NoError){finish(QStringLiteral("订阅下载失败（HTTP %1，网络错误 %2）；请检查认证、TLS 或网络出口。旧节点保持不变。").arg(code).arg(int(error)));return;}
        if(code!=200){finish(QStringLiteral("订阅服务器返回 HTTP %1；旧节点保持不变。").arg(code));return;}
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
    if(!result){finish(result.error);return;}
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
    m_busy=true;auto result=std::move(*m_pending);m_pending.reset();emit changed();
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
    const auto count=result.nodes.size();
    if(result.format=="xray-v2ray-json" && (m_applyAsync || !m_apply)) {
        m_committing=true;m_message=QStringLiteral("正在加密并原子保存节点…");emit changed();
        const QPointer<NodeImportService> guard(this);const auto generation=m_generation;
        auto completion=[guard,generation,format=result.format,count,incomplete=result.incompleteNodes](bool ok,const QString &error) {
            if(!guard || guard->m_shuttingDown || guard->m_generation!=generation)return;
            guard->m_committing=false;
            if(!ok){guard->finish(error.isEmpty()?QStringLiteral("节点保存失败；旧配置保持不变。"):error);return;}
            guard->applied(format,count,incomplete);
        };
        QString error;bool queued=false;
        if(m_applyAsync)queued=m_applyAsync(result,m_source,std::move(completion),&error);
        else if(!result.configuration.isEmpty())error=QStringLiteral("JSON 导入不允许应用第三方全局配置。");
        else {
            NodeStore::ImportPlan plan;
            if(m_store->prepareImport(result.nodes,m_source,&plan))queued=m_store->commitImportAsync(plan,{},std::move(completion));
            if(!queued)error=m_store->error();
        }
        if(!queued){m_committing=false;finish(error.isEmpty()?QStringLiteral("无法开始安全保存；旧配置保持不变。"):error);}
        return;
    }
    if(m_apply || !result.configuration.isEmpty()) {
        QString error;
        if(!m_apply || !m_apply(result,m_source,&error)) {
            finish(error.isEmpty()?QStringLiteral("导入包含全局配置，但当前入口不能验证其语义；旧配置保持不变。"):error);return;
        }
    } else if(!m_store->importNodes(std::move(result.nodes),m_source)){finish(m_store->error());return;}
    applied(result.format,count,result.incompleteNodes);
}
void NodeImportService::applied(const QString &format,qsizetype count,int incomplete) {
    m_message=QStringLiteral("%1 · 已解析并保存 %2 个节点；实际联网需检测。").arg(format).arg(count);
    if(incomplete)m_message+=QStringLiteral(" %1 个节点当前不可执行，原始参数已加密保留。").arg(incomplete);
    emit nodesApplied();finish();
}
void NodeImportService::finish(const QString &error) {
    m_deadline.stop();
    if(!m_source.isEmpty()){if(error.isEmpty())m_errors.remove(m_source);else m_errors.insert(m_source,error);}
    if(!error.isEmpty())m_message=error;
    m_source.clear();m_busy=false;emit changed();QTimer::singleShot(0,this,&NodeImportService::next);
}

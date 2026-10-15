#include "CaptureService.h"
#include "Http2Session.h"
#include <QTcpSocket>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointer>
#include <QElapsedTimer>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QSaveFile>
#include <QTimer>
#include <QUrlQuery>
#include <algorithm>
#include <QSettings>
#include <QUuid>
#include <QRegularExpression>
#include <QSslConfiguration>

namespace {
constexpr qsizetype HeaderLimit=64*1024, RequestLimit=1024*1024;
constexpr qsizetype ResponseLimit=2*1024*1024, PreviewLimit=64*1024;
constexpr int SessionLimit=1000, ConnectionLimit=64;
bool sensitive(const QByteArray &name) {
    const auto n=name.toLower();
    return n=="authorization" || n=="proxy-authorization" || n=="cookie" || n=="set-cookie" || n=="x-api-key";
}
bool hopHeader(const QByteArray &name) {
    const auto n=name.toLower();
    return n=="connection" || n=="proxy-connection" || n=="proxy-authorization" || n=="keep-alive" || n=="te" || n=="trailer" || n=="upgrade" || n=="transfer-encoding";
}
QString safeUrl(QUrl url) {
    url.setUserInfo({});
    QUrlQuery query(url), clean;
    for(const auto &p:query.queryItems()) {
        const QString key=p.first.toLower();
        const bool secret=key=="token" || key=="access_token" || key=="password" || key=="secret" || key=="api_key" || key=="apikey" || key=="key" || key=="auth" || key=="client_secret";
        clean.addQueryItem(p.first,secret?QStringLiteral("[已隐藏]"):p.second);
    }
    url.setQuery(clean);
    return url.toString(QUrl::FullyEncoded);
}
QVariantMap header(const QByteArray &name,const QByteArray &value) {
    return {{"name",QString::fromLatin1(name)}, {"value",sensitive(name)?QStringLiteral("[已隐藏]"):name.toLower()=="location"?safeUrl(QUrl::fromEncoded(value)):QString::fromLatin1(value)}};
}
QString headerText(const QVariantList &headers) {
    QStringList lines;
    for(const auto &h:headers) { auto m=h.toMap(); lines<<m["name"].toString()+": "+m["value"].toString(); }
    return lines.join('\n');
}
QString bodyText(const QByteArray &bytes,const QByteArray &type) {
    const auto mime=type.toLower();
    if(mime.startsWith("text/") || mime.contains("json") || mime.contains("xml") || mime.contains("javascript") || mime.contains("form-urlencoded"))
        return QString::fromUtf8(bytes.left(PreviewLimit));
    return bytes.isEmpty()?QString():QStringLiteral("二进制正文 · %1 字节\n%2").arg(bytes.size()).arg(QString::fromLatin1(bytes.left(256).toHex(' ')));
}
}

struct CaptureService::Connection {
    QPointer<QTcpSocket> client, upstream;
    QByteArray input, method, target, requestBody, responseBody, requestType, responseType;
    QList<QPair<QByteArray,QByteArray>> rawHeaders;
    QVariantList requestHeaders, responseHeaders;
    QUrl url;
    QElapsedTimer elapsed;
    QDateTime started=QDateTime::currentDateTimeUtc();
    QString id, statusText;
    int status=0;
    qint64 completedAt=-1;
    qint64 contentLength=0, upBytes=0, downBytes=0;
    bool dispatched=false, tunnel=false, recorded=false, counted=false, truncated=false, updatePending=false;
    QVariantList rewrites;
    QString originalUrl,tlsHost,connectionId;
    int tlsPort=443;
    bool decrypted=false,limitCounted=false,streaming=false;
    QByteArray streamPending;
    qint64 accountedBytes=0;
    QPointer<Http2Session> h2;int streamId=0;
};

CaptureService::CaptureService(QObject *parent,QString tlsPath):QObject(parent),m_tls(tlsPath,this) {
    m_autoMitmEnabled=QSettings().value("Capture/autoMitm",true).toBool();
    m_captureDeadline.setSingleShot(true);
    connect(&m_captureDeadline,&QTimer::timeout,this,[this]{setError(QStringLiteral("已达到捕获时间限制。"));stop();});
    QJsonParseError parseError;
    const auto document=QJsonDocument::fromJson(QSettings().value("Capture/rewriteRules").toByteArray(),&parseError);
    if(parseError.error==QJsonParseError::NoError&&document.isArray()&&document.array().size()<=500)m_rules=document.array().toVariantList();
    m_server.setProxy(QNetworkProxy::NoProxy);
    m_network.setProxy(QNetworkProxy::NoProxy);
    connect(&m_server,&QTcpServer::newConnection,this,&CaptureService::acceptClients);
}
CaptureService::~CaptureService() {
    m_rewriteEnabled=false;synchronizeForwarders();stop();
    for(auto *reply:m_network.findChildren<QNetworkReply *>())QObject::disconnect(reply,nullptr,this,nullptr);
    for(auto *child:children())QObject::disconnect(child,nullptr,this,nullptr);
    QObject::disconnect(&m_server,nullptr,this,nullptr);
    QObject::disconnect(&m_network,nullptr,this,nullptr);
}
void CaptureService::setAutoMitmEnabled(bool enabled) {
    if(enabled==m_autoMitmEnabled)return;m_autoMitmEnabled=enabled;QSettings().setValue("Capture/autoMitm",enabled);emit stateChanged();
}
void CaptureService::setError(const QString &message) { m_error=message; emit stateChanged(); }
bool CaptureService::start(int requestedPort) {
    if(running())return true;
    if(m_limitPending){setError(QStringLiteral("正在停止上一捕获会话，请稍后重试。"));return false;}
    if(requestedPort<0 || requestedPort>65535){setError(QStringLiteral("端口必须在 0–65535 范围内。"));return false;}
    m_error.clear();
    if(!m_server.listen(QHostAddress::LocalHost,static_cast<quint16>(requestedPort))){setError(QStringLiteral("监听失败：")+m_server.errorString());return false;}
    m_captureFirstId=m_nextId;m_limitPending=false;m_captureRequests=0;m_captureBytes=0;
    if(m_minutes>0)m_captureDeadline.start(m_minutes*60000);
    emit stateChanged(); return true;
}
void CaptureService::stop() {
    m_captureDeadline.stop();m_server.close();
    const auto replies=m_replies;
    for(auto *reply:replies)reply->abort();
    for(auto *socket:findChildren<QTcpSocket *>(QString(),Qt::FindDirectChildrenOnly))socket->abort();
    emit stateChanged();
}
void CaptureService::clear() { m_sessions.clear();emit sessionsChanged(); }
void CaptureService::acceptClients() {
    while(m_server.hasPendingConnections()) {
        auto *client=m_server.nextPendingConnection(); client->setParent(this);
        if(m_activeCount>=ConnectionLimit){client->write("HTTP/1.1 503 Busy\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");client->disconnectFromHost();connect(client,&QTcpSocket::disconnected,client,&QObject::deleteLater);continue;}
        auto c=std::make_shared<Connection>(); c->client=client;c->id=QString::number(m_nextId++);c->elapsed.start();c->counted=true;
        ++m_activeCount;emit stateChanged();
        client->setReadBufferSize(RequestLimit+HeaderLimit);
        connect(client,&QTcpSocket::readyRead,this,[this,c]{consume(c);});
        connect(client,&QTcpSocket::disconnected,this,[this,c]{
            if(c->completedAt<0)c->completedAt=c->elapsed.elapsed();
            if(c->upstream)c->upstream->abort();
            if(c->counted){c->counted=false;--m_activeCount;emit stateChanged();}
            if(c->recorded)update(c);
            checkLimits();
            if(c->client)c->client->deleteLater();
        });
        QTimer::singleShot(15000,client,[this,c]{if(!c->dispatched)fail(c,408,"Request header timeout");});
        consume(c);
    }
}
void CaptureService::fail(const std::shared_ptr<Connection> &c,int status,const QByteArray &message) {
    c->dispatched=true;c->status=status;c->statusText=QStringLiteral("本机捕获错误：")+QString::fromLatin1(message);
    const auto body=message+'\n';
    c->responseBody=body;c->responseType="text/plain";c->downBytes=body.size();
    if(!c->recorded && !c->method.isEmpty()) {
        if(c->url.isEmpty())c->url=QUrl::fromEncoded(c->target);
        if(c->url.isValid() && !c->url.host().isEmpty()) {
            c->recorded=true;
            if(m_sessions.size()>=SessionLimit)m_sessions.removeLast();
            m_sessions.prepend(QVariantMap{{"id",c->id}});
        }
    }
    if(c->recorded)update(c);
    if(!c->client)return;
    if(c->h2){c->completedAt=c->elapsed.elapsed();c->h2->respond(c->streamId,status,{{"content-type","text/plain"},{"content-length",QByteArray::number(body.size())}},body);return;}
    c->client->write("HTTP/1.1 "+QByteArray::number(status)+" Capture Error\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);
    c->client->disconnectFromHost();
}
void CaptureService::consume(const std::shared_ptr<Connection> &c) {
    if(c->dispatched || c->h2 || !c->client)return;
    c->input+=c->client->readAll();
    const auto end=c->input.indexOf("\r\n\r\n");
    if(end<0){if(c->input.size()>HeaderLimit)fail(c,431,"Request headers too large");return;}
    if(end>HeaderLimit){fail(c,431,"Request headers too large");return;}
    auto lines=c->input.left(end).split('\n');
    if(lines.isEmpty()){fail(c,400,"Missing request line");return;}
    const auto first=lines.takeFirst().trimmed().split(' ');
    if(first.size()!=3 || (first[2]!="HTTP/1.1" && first[2]!="HTTP/1.0")){fail(c,400,"Invalid HTTP request");return;}
    c->method=first[0];c->target=first[1];c->rawHeaders.clear();c->requestHeaders.clear();
    bool lengthSeen=false; c->contentLength=0;
    for(auto line:lines) {
        if(line.endsWith('\r'))line.chop(1);
        const auto colon=line.indexOf(':');
        if(colon<=0 || line.startsWith(' ') || line.startsWith('\t')){fail(c,400,"Invalid header");return;}
        const auto name=line.left(colon),value=line.mid(colon+1).trimmed();
        for(char ch:name)if(!((ch>='A'&&ch<='Z')||(ch>='a'&&ch<='z')||(ch>='0'&&ch<='9')||QByteArray("!#$%&'*+-.^_`|~").contains(ch))){fail(c,400,"Invalid header name");return;}
        if(value.contains('\r') || value.contains('\0')){fail(c,400,"Invalid header value");return;}
        if(name.toLower()=="transfer-encoding"){fail(c,501,"Chunked request bodies are not supported");return;}
        if(name.toLower()=="upgrade"){fail(c,501,"HTTP Upgrade is not supported");return;}
        if(name.toLower()=="expect"){fail(c,417,"Expect is not supported");return;}
        if(name.toLower()=="content-length"){
            bool valid=!value.isEmpty();for(char ch:value)valid=valid&&ch>='0'&&ch<='9';
            bool numeric=false;const auto length=value.toLongLong(&numeric);
            if(!valid || !numeric || lengthSeen || length>RequestLimit){fail(c,length>RequestLimit?413:400,"Invalid or oversized request body");return;}
            lengthSeen=true;c->contentLength=length;
        }
        if(name.toLower()=="content-type")c->requestType=value;
        c->rawHeaders.append({name,value});c->requestHeaders.append(header(name,value));
    }
    if(c->input.size()<end+4+c->contentLength)return;
    c->requestBody=c->input.mid(end+4,c->contentLength);
    c->input=c->input.mid(end+4+c->contentLength);
    handle(c);
}
void CaptureService::handle(const std::shared_ptr<Connection> &c) {
    c->dispatched=true; c->tunnel=c->method=="CONNECT";
    if(c->tunnel) {
        if(c->contentLength!=0){fail(c,400,"CONNECT must not have an HTTP body");return;}
        c->url=QUrl::fromEncoded("https://"+c->target);
    } else {
        const QList<QByteArray> supported={"GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"};
        if(!supported.contains(c->method)){fail(c,405,"Unsupported HTTP method");return;}
        c->url=QUrl::fromEncoded(c->target);
        if(c->target.startsWith('/')){
            QByteArray host;for(const auto &h:c->rawHeaders)if(h.first.toLower()=="host")host=h.second;
            if(c->decrypted){const auto authority=c->tlsHost.contains(':')?"["+c->tlsHost+"]":c->tlsHost;c->url=QUrl("https://"+authority+":"+QString::number(c->tlsPort)+QString::fromLatin1(c->target));}
            else c->url=QUrl::fromEncoded("http://"+host+c->target);
        }
        if(c->url.scheme()!=(c->decrypted?"https":"http")){fail(c,400,"Invalid request protocol");return;}
    }
    if(!c->url.isValid() || c->url.host().isEmpty() || !c->url.userInfo().isEmpty() || c->url.hasFragment() || c->url.port(c->tunnel?443:80)<1){fail(c,400,"Invalid target URL");return;}
    const auto host=c->url.host().toLower();
    if((host=="localhost" || host=="127.0.0.1" || host=="::1") && c->url.port(c->tunnel?443:80)==port()){fail(c,400,"Capture proxy cannot forward to itself");return;}
    if(c->decrypted&&(c->url.host().compare(c->tlsHost,Qt::CaseInsensitive)!=0||c->url.port(443)!=c->tlsPort)){fail(c,421,"Request target differs from CONNECT target");return;}
    if(c->tunnel&&m_tls.ready()&&(m_tls.enabled()||m_autoMitmEnabled)&&m_tls.matchesHost(c->url.host())) {
        auto *socket=qobject_cast<QSslSocket *>(c->client.data());const auto identity=m_tls.identityFor(c->url.host());
        if(!socket||identity.certificate.isNull()||identity.key.isNull()||!c->input.isEmpty()){fail(c,502,"TLS interception is unavailable");return;}
        c->tlsHost=c->url.host();c->tlsPort=c->url.port(443);
        auto configuration=QSslConfiguration::defaultConfiguration();configuration.setLocalCertificateChain({identity.certificate,m_tls.certificate()});
        configuration.setPrivateKey(identity.key);configuration.setPeerVerifyMode(QSslSocket::VerifyNone);configuration.setAllowedNextProtocols(m_tls.http2Enabled()?QList<QByteArray>{"h2","http/1.1"}:QList<QByteArray>{"http/1.1"});socket->setSslConfiguration(configuration);
        connect(socket,&QSslSocket::encrypted,this,[this,c]{
            auto *ssl=qobject_cast<QSslSocket *>(c->client.data());
            if(ssl&&ssl->sslConfiguration().nextNegotiatedProtocol()=="h2") {
                c->h2=new Http2Session(ssl,[this,c](const Http2Session::Request &request){
                    auto stream=std::make_shared<Connection>();stream->client=c->client;stream->h2=c->h2;stream->streamId=request.id;stream->decrypted=true;
                    stream->tlsHost=c->tlsHost;stream->tlsPort=c->tlsPort;stream->id=QString::number(m_nextId++);stream->connectionId=c->id;stream->elapsed.start();
                    stream->method=request.method;stream->target=request.path;stream->requestBody=request.body;stream->contentLength=request.body.size();stream->rawHeaders=request.headers;
                    if(request.scheme!="https"||request.path.isEmpty()||!request.path.startsWith('/')){fail(stream,400,"Invalid HTTP/2 target");return;}
                    const QUrl authority=QUrl::fromEncoded("https://"+request.authority);
                    if(authority.host().compare(c->tlsHost,Qt::CaseInsensitive)!=0||authority.port(443)!=c->tlsPort){fail(stream,421,"HTTP/2 authority differs from CONNECT target");return;}
                    for(const auto &h:request.headers){stream->requestHeaders.append(header(h.first,h.second));if(h.first=="content-type")stream->requestType=h.second;}
                    handle(stream);
                });c->h2->receive();return;
            }
            c->decrypted=true;c->dispatched=false;c->tunnel=false;c->method.clear();c->target.clear();c->url.clear();c->contentLength=0;c->input.clear();consume(c);});
        connect(socket,&QSslSocket::sslErrors,this,[this,c](const QList<QSslError> &errors){Q_UNUSED(errors);setError(QStringLiteral("客户端未信任 Swirl CA 或 TLS 协商失败。"));if(c->client)c->client->abort();});
        socket->write("HTTP/1.1 200 Connection Established\r\n\r\n");socket->flush();socket->startServerEncryption();return;
    }
    c->limitCounted=true;++m_captureRequests;
    c->recorded=m_filter.isEmpty()||c->url.toString().contains(m_filter,Qt::CaseInsensitive);
    c->upBytes=c->requestBody.size();c->statusText=QStringLiteral("进行中");
    c->originalUrl=safeUrl(c->url);
    if(!c->tunnel&&m_rewriteEnabled) {
        for(const auto &entry:m_rules) {
            const auto rule=entry.toMap();const QRegularExpression regex(rule.value("pattern").toString());
            if(rule.value("kind")=="forward"||!regex.isValid()||!regex.match(c->url.toString()).hasMatch())continue;
            c->rewrites.append(rule);
            const auto kind=rule.value("kind").toString();
            if(kind=="redirect") {
                auto target=c->url.toString();target.replace(regex,rule.value("replacement").toString());
                const QUrl redirect(target);
                if(!redirect.isValid()||!QStringList{"http","https"}.contains(redirect.scheme())||redirect.host().isEmpty()||!redirect.userInfo().isEmpty()) {fail(c,502,"Invalid rewrite redirect");return;}
                if(c->recorded){if(m_sessions.size()>=SessionLimit)m_sessions.removeLast();m_sessions.prepend(QVariantMap{{"id",c->id}});}
                localResponse(c,rule.value("status",302).toInt(),{},"text/plain",redirect.toEncoded());return;
            }
            if(kind=="mock") {
                if(c->recorded){if(m_sessions.size()>=SessionLimit)m_sessions.removeLast();m_sessions.prepend(QVariantMap{{"id",c->id}});}
                localResponse(c,rule.value("status",200).toInt(),rule.value("replacement").toString().toUtf8(),rule.value("contentType","application/json").toString().toUtf8());return;
            }
            if(kind=="body"&&rule.value("direction").toString()=="request") {
                auto body=QString::fromUtf8(c->requestBody);body.replace(QRegularExpression(rule.value("search").toString()),rule.value("replacement").toString());c->requestBody=body.toUtf8();
                if(c->requestBody.size()>RequestLimit){fail(c,413,"Rewritten body exceeds limit");return;}
            }
        }
    }
    if(m_sessions.size()>=SessionLimit)m_sessions.removeLast();
    if(c->recorded)m_sessions.prepend(QVariantMap{{"id",c->id}});update(c);
    if(c->tunnel) {
        auto *upstream=new QTcpSocket(this);c->upstream=upstream;upstream->setProxy(m_upstreamProxyPort>0?QNetworkProxy(QNetworkProxy::Socks5Proxy,"127.0.0.1",m_upstreamProxyPort):QNetworkProxy(QNetworkProxy::NoProxy));upstream->setReadBufferSize(64*1024);
        const auto pump=[this,c](QTcpSocket *from,QTcpSocket *to,bool upload){
            if(!from || !to)return;
            if(to->bytesToWrite()>4*1024*1024){c->statusText=QStringLiteral("隧道缓冲达到上限，已停止");from->abort();to->abort();update(c);return;}
            const auto bytes=from->readAll();to->write(bytes);
            if(upload)c->upBytes+=bytes.size();else c->downBytes+=bytes.size();
            // Keep byte counts exact while limiting scene/model churn for
            // long-lived HTTPS tunnels. Final closure still updates at once.
            if(!c->updatePending){c->updatePending=true;QTimer::singleShot(150,this,[this,c]{c->updatePending=false;update(c);});}
        };
        connect(upstream,&QTcpSocket::connected,this,[this,c,pump]{
            c->status=200;c->statusText=QStringLiteral("CONNECT 隧道 · 未解密");
            if(c->client){c->client->write("HTTP/1.1 200 Connection Established\r\n\r\n");
                if(!c->input.isEmpty()){c->upstream->write(c->input);c->upBytes+=c->input.size();c->input.clear();}
                pump(c->client,c->upstream,true);
            }
            update(c);
        });
        connect(c->client,&QTcpSocket::readyRead,this,[c,pump]{if(c->upstream && c->upstream->state()==QAbstractSocket::ConnectedState)pump(c->client,c->upstream,true);});
        connect(upstream,&QTcpSocket::readyRead,this,[c,pump]{pump(c->upstream,c->client,false);});
        connect(upstream,&QTcpSocket::disconnected,this,[this,c]{if(c->client)c->client->disconnectFromHost();update(c);if(c->upstream)c->upstream->deleteLater();});
        connect(upstream,&QTcpSocket::errorOccurred,this,[this,c](QAbstractSocket::SocketError){if(!c->status)fail(c,502,"CONNECT upstream failed");else {c->statusText=QStringLiteral("CONNECT 隧道已关闭 · 未解密");update(c);if(c->client)c->client->disconnectFromHost();}if(c->upstream)c->upstream->deleteLater();});
        upstream->connectToHost(c->url.host(),c->url.port(443));
        QTimer::singleShot(15000,upstream,[this,c]{if(!c->status)fail(c,504,"CONNECT timeout");});
        return;
    }
    QNetworkRequest request(c->url);request.setTransferTimeout(20000);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    request.setAttribute(QNetworkRequest::Http2AllowedAttribute,c->decrypted&&m_tls.http2Enabled());
    QList<QByteArray> connectionTokens;
    for(const auto &h:c->rawHeaders)if(h.first.toLower()=="connection")for(auto name:h.second.split(','))connectionTokens<<name.trimmed().toLower();
    for(const auto &h:c->rawHeaders)if(!hopHeader(h.first) && h.first.toLower()!="host" && h.first.toLower()!="content-length" && !connectionTokens.contains(h.first.toLower()))request.setRawHeader(h.first,h.second);
    for(const auto &entry:c->rewrites) {
        const auto rule=entry.toMap();
        if(rule.value("kind")=="header"&&rule.value("direction")=="request")request.setRawHeader(rule.value("name").toByteArray(),rule.value("replacement").toByteArray());
    }
    request.setRawHeader("Connection","close");
    // Ask for uncompressed payloads so previews and HAR are consistent with
    // byte accounting. If an origin sends encoded data anyway, preserve its
    // Content-Encoding header when forwarding it to the caller.
    request.setRawHeader("Accept-Encoding","identity");
    auto *reply=m_network.sendCustomRequest(request,c->method,c->requestBody);m_replies.insert(reply);
    if(c->h2)c->h2->setCancelHandler(c->streamId,[guard=QPointer<QNetworkReply>(reply)]{if(guard&&!guard->isFinished())guard->abort();});
    if(c->decrypted&&m_tls.skipServerVerification())connect(reply,&QNetworkReply::sslErrors,reply,[reply](const QList<QSslError> &){reply->ignoreSslErrors();});
    reply->setReadBufferSize(64*1024);
    connect(reply,&QNetworkReply::readyRead,this,[this,c,reply]{
        if(c->streaming){pumpResponseStream(c,reply);return;}
        const auto part=reply->readAll();c->responseBody+=part;
        if(c->responseBody.size()>ResponseLimit){
            bool bodyRewrite=false;for(const auto &entry:c->rewrites){const auto rule=entry.toMap();if(rule.value("kind")=="body"&&rule.value("direction")!="request")bodyRewrite=true;}
            if(bodyRewrite||!beginResponseStream(c,reply)){c->truncated=true;reply->abort();}
        }
    });
    connect(reply,&QNetworkReply::finished,this,[this,c,reply]{if(c->streaming)pumpResponseStream(c,reply);else finishHttp(c,reply);});
    connect(c->client,&QTcpSocket::disconnected,reply,[reply]{if(!reply->isFinished())reply->abort();});
}
bool CaptureService::beginResponseStream(const std::shared_ptr<Connection> &c,QNetworkReply *reply) {
    const int status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();if(!status||!c->client)return false;
    c->status=status;c->responseType=reply->rawHeader("Content-Type");auto pairs=reply->rawHeaderPairs();
    for(const auto &entry:c->rewrites){const auto rule=entry.toMap();if(rule.value("kind")!="header"||rule.value("direction")=="request")continue;
        const auto name=rule.value("name").toByteArray();for(int i=pairs.size()-1;i>=0;--i)if(pairs[i].first.toLower()==name.toLower())pairs.removeAt(i);pairs.append({name,rule.value("replacement").toByteArray()});}
    QList<QByteArray> connectionTokens;for(const auto &h:reply->rawHeaderPairs())if(h.first.toLower()=="connection")for(auto name:h.second.split(','))connectionTokens<<name.trimmed().toLower();
    Http2Session::Headers forwarded;c->responseHeaders.clear();
    for(const auto &h:pairs){c->responseHeaders.append(header(h.first,h.second));if(!hopHeader(h.first)&&!connectionTokens.contains(h.first.toLower()))forwarded.append(h);}
    if(c->h2){if(!c->h2->beginStreaming(c->streamId,status,forwarded))return false;}
    else {QByteArray response="HTTP/1.1 "+QByteArray::number(status)+" "+reply->attribute(QNetworkRequest::HttpReasonPhraseAttribute).toByteArray()+"\r\n";
        for(const auto &h:forwarded)response+=h.first+": "+h.second+"\r\n";response+="Connection: close\r\n\r\n";c->client->write(response);}
    c->streaming=true;c->truncated=true;c->streamPending=std::move(c->responseBody);c->downBytes=c->streamPending.size();c->responseBody=c->streamPending.left(PreviewLimit);
    auto timer=new QTimer(reply);timer->setInterval(25);connect(timer,&QTimer::timeout,this,[this,c,reply]{pumpResponseStream(c,reply);});timer->start();pumpResponseStream(c,reply);return true;
}
void CaptureService::pumpResponseStream(const std::shared_ptr<Connection> &c,QNetworkReply *reply) {
    if(!m_replies.contains(reply))return;
    const auto abandon=[&]{m_replies.remove(reply);if(!reply->isFinished())reply->abort();
        if(c->h2)c->h2->resetStream(c->streamId);else if(c->client)c->client->abort();
        c->statusText=QStringLiteral("响应流中断");c->completedAt=c->elapsed.elapsed();update(c);reply->deleteLater();};
    if(!c->client||c->client->state()!=QAbstractSocket::ConnectedState){abandon();return;}
    if(reply->isFinished()&&reply->error()!=QNetworkReply::NoError&&(c->status<400||reply->error()<QNetworkReply::ContentAccessDenied)){abandon();return;}
    for(int i=0;i<8;++i){
        const int capacity=c->h2?c->h2->writableBytes(c->streamId):qMax(qint64(0),512*1024-c->client->bytesToWrite());
        if(capacity<=0)break;
        if(c->streamPending.isEmpty()&&reply->bytesAvailable()>0){const auto part=reply->read(qMin(capacity,64*1024));c->streamPending=part;c->downBytes+=part.size();
            if(c->responseBody.size()<PreviewLimit)c->responseBody+=part.left(PreviewLimit-c->responseBody.size());}
        if(c->streamPending.isEmpty())break;const auto part=c->streamPending.left(qMin(capacity,64*1024));
        if(c->h2){if(!c->h2->appendStreaming(c->streamId,part)){abandon();return;}}
        else if(c->client->write(part)!=part.size()){abandon();return;}
        c->streamPending.remove(0,part.size());
    }
    update(c);
    if(reply->isFinished()&&reply->bytesAvailable()==0&&c->streamPending.isEmpty()){
        if(c->h2){if(!c->h2->appendStreaming(c->streamId,{},true))return;}
        else c->client->disconnectFromHost();
        m_replies.remove(reply);c->statusText=QStringLiteral("已完成");c->completedAt=c->elapsed.elapsed();update(c);reply->deleteLater();
    }
}
void CaptureService::finishHttp(const std::shared_ptr<Connection> &c,QNetworkReply *reply) {
    m_replies.remove(reply);
    if(!c->truncated){const auto remainder=reply->readAll();if(c->responseBody.size()+remainder.size()<=ResponseLimit)c->responseBody+=remainder;else c->truncated=true;}
    c->status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    c->responseType=reply->rawHeader("Content-Type");c->downBytes=c->responseBody.size();
    const auto reason=reply->attribute(QNetworkRequest::HttpReasonPhraseAttribute).toByteArray();
    // A received 200 header is not proof of a complete response. Transport
    // failures (e.g. premature EOF/timeout) must not become successful captures.
    const bool transportFailure=reply->error()!=QNetworkReply::NoError &&
        (c->status<400 || reply->error()<QNetworkReply::ContentAccessDenied);
    if(c->truncated || !c->status || transportFailure) {
        fail(c,502,c->truncated?"Response exceeds 2 MiB capture limit":"HTTP upstream failed");
        reply->deleteLater();return;
    }
    auto responsePairs=reply->rawHeaderPairs();
    for(const auto &entry:c->rewrites) {
        const auto rule=entry.toMap();
        if(rule.value("direction")=="request")continue;
        if(rule.value("kind")=="header") {
            const auto name=rule.value("name").toByteArray();
            for(int i=responsePairs.size()-1;i>=0;--i)if(responsePairs[i].first.toLower()==name.toLower())responsePairs.removeAt(i);
            responsePairs.append({name,rule.value("replacement").toByteArray()});
        } else if(rule.value("kind")=="body"&&reply->rawHeader("Content-Encoding").isEmpty()) {
            auto body=QString::fromUtf8(c->responseBody);body.replace(QRegularExpression(rule.value("search").toString()),rule.value("replacement").toString());c->responseBody=body.toUtf8();
            if(c->responseBody.size()>ResponseLimit){fail(c,502,"Rewritten response exceeds limit");reply->deleteLater();return;}
        }
    }
    c->downBytes=c->responseBody.size();
    QByteArray response="HTTP/1.1 "+QByteArray::number(c->status)+" "+reason+"\r\n";
    QList<QByteArray> connectionTokens;
    for(const auto &h:reply->rawHeaderPairs())if(h.first.toLower()=="connection")for(auto name:h.second.split(','))connectionTokens<<name.trimmed().toLower();
    c->responseHeaders.clear();
    for(const auto &h:responsePairs) {
        c->responseHeaders.append(header(h.first,h.second));
        if(!hopHeader(h.first) && h.first.toLower()!="content-length" && !connectionTokens.contains(h.first.toLower()))response+=h.first+": "+h.second+"\r\n";
    }
    const auto length=c->method=="HEAD" && !reply->rawHeader("Content-Length").isEmpty()?reply->rawHeader("Content-Length"):QByteArray::number(c->responseBody.size());
    response+="Content-Length: "+length+"\r\nConnection: close\r\n\r\n";
    if(c->h2){Http2Session::Headers headers;for(const auto &h:responsePairs)if(!hopHeader(h.first)&&h.first.toLower()!="content-length"&&!connectionTokens.contains(h.first.toLower()))headers.append(h);headers.append({"content-length",length});c->h2->respond(c->streamId,c->status,headers,c->responseBody,c->method=="HEAD");c->completedAt=c->elapsed.elapsed();}
    else if(c->client){c->client->write(response);if(c->method!="HEAD")c->client->write(c->responseBody);c->client->disconnectFromHost();}
    c->statusText=QStringLiteral("已完成");update(c);reply->deleteLater();
}
void CaptureService::update(const std::shared_ptr<Connection> &c) {
    if(c->limitCounted&&c->id.toULongLong()>=m_captureFirstId){const auto total=c->upBytes+c->downBytes;
        m_captureBytes+=qMax(qint64(0),total-c->accountedBytes);c->accountedBytes=total;checkLimits();}
    for(qsizetype i=0;i<m_sessions.size();++i)if(m_sessions[i].toMap()["id"].toString()==c->id) {
        QVariantMap row{{"id",c->id},{"method",QString::fromLatin1(c->method)},{"url",safeUrl(c->url)},{"host",c->url.host()},
            {"status",c->status?QString::number(c->status):QStringLiteral("…")},{"statusCode",c->status},{"statusText",c->statusText},
            {"protocol",c->tunnel?QStringLiteral("CONNECT 隧道"):c->h2?QStringLiteral("HTTPS · HTTP/2 MitM"):c->decrypted?QStringLiteral("HTTPS · MitM"):QStringLiteral("HTTP")},{"tunnel",c->tunnel},
            {"time",c->started.toLocalTime().toString("HH:mm:ss")},{"started",c->started.toString(Qt::ISODateWithMs)},
            {"duration",QString::number(c->completedAt>=0?c->completedAt:c->elapsed.elapsed())+" ms"},{"elapsed",c->completedAt>=0?c->completedAt:c->elapsed.elapsed()},
            {"upBytes",c->upBytes},{"downBytes",c->downBytes},{"size",QString::number(c->downBytes)+" B"},
            {"requestHeaders",headerText(c->requestHeaders)},{"responseHeaders",headerText(c->responseHeaders)},
            {"requestHeaderList",c->requestHeaders},{"responseHeaderList",c->responseHeaders},
            {"requestBody",bodyText(c->requestBody,c->requestType)},{"responseBody",c->tunnel?QStringLiteral("CONNECT 仅记录目标、字节数与耗时；TLS 内容没有解密。"):bodyText(c->responseBody,c->responseType)},
            {"requestBase64",QString::fromLatin1(c->requestBody.left(PreviewLimit).toBase64())},
            {"responseBase64",QString::fromLatin1(c->responseBody.left(PreviewLimit).toBase64())},
            {"requestMime",QString::fromLatin1(c->requestType)},{"responseMime",QString::fromLatin1(c->responseType)},
            {"truncated",c->truncated || c->requestBody.size()>PreviewLimit || c->responseBody.size()>PreviewLimit}};
        row["httpVersion"]=c->h2?"HTTP/2":"HTTP/1.1";row["policy"]=m_upstreamProxyPort>0?"SWIRL":"DIRECT";row["connectionId"]=c->connectionId.isEmpty()?c->id:c->connectionId;row["http2StreamId"]=c->streamId;row["tlsDecrypted"]=c->decrypted;row["rewriteCount"]=c->rewrites.size();row["originalUrl"]=c->originalUrl;
        m_sessions[i]=row;emit sessionsChanged();checkLimits();return;
    }
}
bool CaptureService::exportHar(const QUrl &url) {
    if(!url.isLocalFile()){setError(QStringLiteral("请选择本地 HAR 文件。"));return false;}
    QJsonArray entries;
    for(const auto &v:m_sessions) {
        const auto r=v.toMap();const bool tunnel=r["tunnel"].toBool();
        QJsonObject request{{"method",r["method"].toString()},{"url",r["url"].toString()},{"httpVersion",r.value("httpVersion","HTTP/1.1").toString()},
            {"headers",QJsonArray::fromVariantList(r["requestHeaderList"].toList())},{"queryString",QJsonArray{}},{"cookies",QJsonArray{}},{"headersSize",-1},{"bodySize",tunnel?0:r["upBytes"].toInt()}};
        QJsonArray query;
        for(const auto &pair:QUrlQuery(QUrl(r["url"].toString())).queryItems())query.append(QJsonObject{{"name",pair.first},{"value",pair.second}});
        request["queryString"]=query;
        if(!tunnel && !r["requestBase64"].toString().isEmpty()) {
            const auto mime=r["requestMime"].toString().toLower();
            request["_swirlBodyBase64"]=r["requestBase64"].toString();
            if(mime.startsWith("text/") || mime.contains("json") || mime.contains("xml") || mime.contains("form-urlencoded"))
                request["postData"]=QJsonObject{{"mimeType",r["requestMime"].toString()},{"text",QString::fromUtf8(QByteArray::fromBase64(r["requestBase64"].toByteArray()))}};
        }
        QJsonObject content{{"size",tunnel?0:r["downBytes"].toInt()},{"mimeType",tunnel?"application/octet-stream":r["responseMime"].toString()}};
        if(!tunnel){content["text"]=r["responseBase64"].toString();content["encoding"]="base64";}
        QJsonObject response{{"status",r["statusCode"].toInt()},{"statusText",r["statusText"].toString()},{"httpVersion",r.value("httpVersion","HTTP/1.1").toString()},
            {"headers",QJsonArray::fromVariantList(r["responseHeaderList"].toList())},{"cookies",QJsonArray{}},{"content",content},{"redirectURL",""},{"headersSize",-1},{"bodySize",tunnel?0:r["downBytes"].toInt()}};
        entries.append(QJsonObject{{"startedDateTime",r["started"].toString()},{"time",r["elapsed"].toDouble()},
            {"request",request},{"response",response},{"cache",QJsonObject{}},
            {"timings",QJsonObject{{"send",0},{"wait",r["elapsed"].toDouble()},{"receive",0}}},
            {"_swirl",QJsonObject{{"connectTunnel",tunnel},{"tlsDecrypted",r["tlsDecrypted"].toBool()},{"previewTruncated",r["truncated"].toBool()},{"transportUpBytes",r["upBytes"].toDouble()},{"transportDownBytes",r["downBytes"].toDouble()}}}});
    }
    const QJsonDocument doc(QJsonObject{{"log",QJsonObject{{"version","1.2"},{"creator",QJsonObject{{"name","Swirl"},{"version","0.1"}}},{"entries",entries}}}});
    QSaveFile file(url.toLocalFile());
    if(!file.open(QIODevice::WriteOnly)){setError(file.errorString());return false;}
    const auto bytes=doc.toJson(QJsonDocument::Indented);
    if(file.write(bytes)!=bytes.size() || !file.commit()){setError(file.errorString());return false;}
    m_error.clear();emit stateChanged();return true;
}

void CaptureService::setLimits(int minutes,int megabytes,int requests) {
    m_minutes=qBound(0,minutes,1440);m_megabytes=qBound(0,megabytes,4096);m_requestLimit=qBound(0,requests,1000);
    if(running()){if(m_minutes>0)m_captureDeadline.start(m_minutes*60000);else m_captureDeadline.stop();checkLimits();}
}
void CaptureService::setFilter(const QString &filter) {m_filter=filter.left(512).trimmed();emit stateChanged();}
void CaptureService::checkLimits() {
    if(!running()||m_limitPending)return;
    const bool countExceeded=m_requestLimit>0&&m_captureRequests>=quint64(m_requestLimit);
    if((m_megabytes>0&&m_captureBytes>=qint64(m_megabytes)*1024*1024)||countExceeded){
        m_limitPending=true;
        // Stop accepting new requests immediately. Let the last response drain,
        // then close ongoing tunnels; never abort a just-written response inline.
        m_server.close();
        QTimer::singleShot(200,this,[this]{setError(QStringLiteral("已达到捕获尺寸或数量限制。"));stop();m_limitPending=false;});
    }
}
bool CaptureService::persistRules() {
    QSettings settings;settings.setValue("Capture/rewriteRules",QJsonDocument(QJsonArray::fromVariantList(m_rules)).toJson(QJsonDocument::Compact));settings.sync();
    if(settings.status()!=QSettings::NoError){setError(QStringLiteral("无法保存重写规则。"));return false;}emit rulesChanged();return true;
}
void CaptureService::setRewriteEnabled(bool enabled) {m_rewriteEnabled=enabled;synchronizeForwarders();emit rulesChanged();}
bool CaptureService::saveRewriteRule(const QVariantMap &input) {
    const auto kind=input.value("kind").toString();const auto pattern=input.value("pattern").toString();
    const auto replacement=input.value("replacement").toString();
    bool valid=QStringList{"redirect","mock","header","body"}.contains(kind)&&!pattern.isEmpty()&&pattern.size()<=512&&QRegularExpression(pattern).isValid()&&replacement.toUtf8().size()<=PreviewLimit;
    const auto direction=input.value("direction","response").toString();valid=valid&&(direction=="request"||direction=="response");
    const auto status=input.value("status",kind=="redirect"?302:200).toInt();
    if(kind=="redirect")valid=valid&&(status==301||status==302||status==307||status==308);
    if(kind=="mock")valid=valid&&status>=200&&status<=599;
    if(kind=="header") {const auto name=input.value("name").toString();valid=valid&&!name.isEmpty()&&QRegularExpression("^[A-Za-z0-9-]+$").match(name).hasMatch()&&!replacement.contains('\r')&&!replacement.contains('\n')&&!replacement.contains(QChar(0))&&!hopHeader(name.toLatin1())&&name.compare("content-length",Qt::CaseInsensitive)!=0&&name.compare("host",Qt::CaseInsensitive)!=0;}
    if(kind=="body")valid=valid&&!input.value("search").toString().isEmpty()&&QRegularExpression(input.value("search").toString()).isValid();
    const auto mime=input.value("contentType","application/json").toString();valid=valid&&!mime.contains('\r')&&!mime.contains('\n');
    if(kind=="forward") {
        bool listenOk=false,targetOk=false;
        const auto listenPort=input.value("listenPort").toInt(&listenOk),targetPort=input.value("targetPort").toInt(&targetOk);
        const auto host=input.value("targetHost").toString().trimmed();
        valid=listenOk&&targetOk&&listenPort>=0&&listenPort<=65535&&targetPort>0&&targetPort<=65535&&!host.isEmpty()&&host.size()<=253&&QRegularExpression("^[A-Za-z0-9_.:-]+$").match(host).hasMatch();
        if(listenPort==targetPort&&QStringList{"localhost","127.0.0.1","::1"}.contains(host))valid=false;
    }
    if(!valid||m_rules.size()>=500){setError(QStringLiteral("重写规则格式无效或超出数量限制。"));return false;}
    QVariantMap rule{{"id",input.value("id",QUuid::createUuid().toString(QUuid::WithoutBraces))},{"kind",kind},{"pattern",pattern},{"replacement",replacement},{"direction",direction},{"status",status},{"name",input.value("name")},{"search",input.value("search")},{"contentType",mime}};
    if(kind=="forward") {rule["listenPort"]=input.value("listenPort");rule["targetPort"]=input.value("targetPort");rule["targetHost"]=input.value("targetHost");rule["pattern"]=QStringLiteral("127.0.0.1:%1").arg(input.value("listenPort").toInt());rule["replacement"]=input.value("targetHost").toString()+":"+input.value("targetPort").toString();}
    const auto before=m_rules;int index=-1;for(int i=0;i<m_rules.size();++i)if(m_rules[i].toMap().value("id")==rule.value("id"))index=i;
    if(index>=0)m_rules[index]=rule;else m_rules.append(rule);
    if(persistRules()){synchronizeForwarders();return true;}m_rules=before;return false;
}
bool CaptureService::removeRewriteRule(const QString &id) {
    const auto before=m_rules;for(int i=m_rules.size()-1;i>=0;--i)if(m_rules[i].toMap().value("id")==id)m_rules.removeAt(i);
    if(persistRules()){synchronizeForwarders();return true;}m_rules=before;return false;
}
void CaptureService::localResponse(const std::shared_ptr<Connection> &c,int status,const QByteArray &body,const QByteArray &type,const QByteArray &location) {
    c->status=status;c->responseBody=body;c->responseType=type;c->downBytes=body.size();c->completedAt=c->elapsed.elapsed();c->statusText=QStringLiteral("重写响应");
    c->responseHeaders={header("Content-Type",type)};
    if(!location.isEmpty())c->responseHeaders.append(header("Location",location));
    QByteArray response="HTTP/1.1 "+QByteArray::number(status)+" Rewrite\r\nContent-Type: "+type+"\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n";
    if(!location.isEmpty())response+="Location: "+location+"\r\n";
    if(c->h2){Http2Session::Headers headers{{"content-type",type},{"content-length",QByteArray::number(body.size())}};if(!location.isEmpty())headers.append({"location",location});c->h2->respond(c->streamId,status,headers,body,c->method=="HEAD");}
    else if(c->client){c->client->write(response+"\r\n");if(c->method!="HEAD")c->client->write(body);c->client->disconnectFromHost();}update(c);
}

void CaptureService::synchronizeForwarders() {
    for(auto *server:m_forwardServers){server->close();delete server;}
    m_forwardServers.clear();m_forwardPorts.clear();
    if(!m_rewriteEnabled){emit rulesChanged();return;}
    for(const auto &entry:m_rules) {
        const auto rule=entry.toMap();if(rule.value("kind")!="forward")continue;
        auto *server=new QTcpServer(this);server->setProxy(QNetworkProxy::NoProxy);
        const auto host=rule.value("targetHost").toString();const auto targetPort=rule.value("targetPort").toInt();
        if(!server->listen(QHostAddress::LocalHost,quint16(rule.value("listenPort").toInt()))) {setError(QStringLiteral("端口转发监听失败：")+server->errorString());delete server;continue;}
        m_forwardServers.append(server);m_forwardPorts[rule.value("id").toString()]=server->serverPort();
        connect(server,&QTcpServer::newConnection,this,[server,host,targetPort]{
            while(server->hasPendingConnections()) {
                auto *client=server->nextPendingConnection();client->setParent(server);
                if(server->findChildren<QTcpSocket *>(QString(),Qt::FindDirectChildrenOnly).size()>64){client->abort();client->deleteLater();continue;}
                auto *upstream=new QTcpSocket(client);upstream->setProxy(QNetworkProxy::NoProxy);
                client->setReadBufferSize(64*1024);upstream->setReadBufferSize(64*1024);
                const auto pump=[](QTcpSocket *from,QTcpSocket *to){if(to->bytesToWrite()>1024*1024){from->abort();to->abort();return;}to->write(from->readAll());};
                connect(upstream,&QTcpSocket::connected,client,[client,upstream,pump]{pump(client,upstream);});
                connect(client,&QTcpSocket::readyRead,upstream,[client,upstream,pump]{if(upstream->state()==QAbstractSocket::ConnectedState)pump(client,upstream);});
                connect(upstream,&QTcpSocket::readyRead,client,[client,upstream,pump]{pump(upstream,client);});
                connect(client,&QTcpSocket::disconnected,client,[client,upstream]{upstream->abort();client->deleteLater();});
                connect(upstream,&QTcpSocket::disconnected,client,[client]{client->disconnectFromHost();});
                connect(upstream,&QTcpSocket::errorOccurred,client,[client]{client->abort();});
                QTimer::singleShot(15000,client,[client,upstream]{if(upstream->state()!=QAbstractSocket::ConnectedState)client->abort();});
                upstream->connectToHost(host,quint16(targetPort));
            }
        });
    }
    emit rulesChanged();
}

void CaptureService::setUpstreamProxyPort(int port) {
    if(port<0||port>65535||port==m_upstreamProxyPort)return;
    m_upstreamProxyPort=port;
    m_network.setProxy(port>0?QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",port):QNetworkProxy(QNetworkProxy::NoProxy));
    emit stateChanged();
}

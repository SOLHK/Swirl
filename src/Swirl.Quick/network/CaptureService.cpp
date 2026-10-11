#include "CaptureService.h"
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
};

CaptureService::CaptureService(QObject *parent):QObject(parent) {
    m_server.setProxy(QNetworkProxy::NoProxy);
    m_network.setProxy(QNetworkProxy::NoProxy);
    connect(&m_server,&QTcpServer::newConnection,this,&CaptureService::acceptClients);
}
CaptureService::~CaptureService() {
    stop();
    for(auto *reply:m_network.findChildren<QNetworkReply *>())QObject::disconnect(reply,nullptr,this,nullptr);
    for(auto *child:children())QObject::disconnect(child,nullptr,this,nullptr);
    QObject::disconnect(&m_server,nullptr,this,nullptr);
    QObject::disconnect(&m_network,nullptr,this,nullptr);
}
void CaptureService::setError(const QString &message) { m_error=message; emit stateChanged(); }
bool CaptureService::start(int requestedPort) {
    if(running())return true;
    if(requestedPort<0 || requestedPort>65535){setError(QStringLiteral("端口必须在 0–65535 范围内。"));return false;}
    m_error.clear();
    if(!m_server.listen(QHostAddress::LocalHost,static_cast<quint16>(requestedPort))){setError(QStringLiteral("监听失败：")+m_server.errorString());return false;}
    emit stateChanged(); return true;
}
void CaptureService::stop() {
    m_server.close();
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
            if(m_sessions.size()>=SessionLimit)m_sessions.removeFirst();
            m_sessions.prepend(QVariantMap{{"id",c->id}});
        }
    }
    if(c->recorded)update(c);
    if(!c->client)return;
    c->client->write("HTTP/1.1 "+QByteArray::number(status)+" Capture Error\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);
    c->client->disconnectFromHost();
}
void CaptureService::consume(const std::shared_ptr<Connection> &c) {
    if(c->dispatched || !c->client)return;
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
            c->url=QUrl::fromEncoded("http://"+host+c->target);
        }
        if(c->url.scheme()!="http"){fail(c,400,"Use CONNECT for HTTPS");return;}
    }
    if(!c->url.isValid() || c->url.host().isEmpty() || !c->url.userInfo().isEmpty() || c->url.hasFragment() || c->url.port(c->tunnel?443:80)<1){fail(c,400,"Invalid target URL");return;}
    const auto host=c->url.host().toLower();
    if((host=="localhost" || host=="127.0.0.1" || host=="::1") && c->url.port(c->tunnel?443:80)==port()){fail(c,400,"Capture proxy cannot forward to itself");return;}
    c->recorded=true;c->upBytes=c->requestBody.size();c->statusText=QStringLiteral("进行中");
    if(m_sessions.size()>=SessionLimit)m_sessions.removeFirst();
    m_sessions.prepend(QVariantMap{{"id",c->id}});update(c);
    if(c->tunnel) {
        auto *upstream=new QTcpSocket(this);c->upstream=upstream;upstream->setProxy(QNetworkProxy::NoProxy);upstream->setReadBufferSize(64*1024);
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
    request.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);
    QList<QByteArray> connectionTokens;
    for(const auto &h:c->rawHeaders)if(h.first.toLower()=="connection")for(auto name:h.second.split(','))connectionTokens<<name.trimmed().toLower();
    for(const auto &h:c->rawHeaders)if(!hopHeader(h.first) && h.first.toLower()!="host" && h.first.toLower()!="content-length" && !connectionTokens.contains(h.first.toLower()))request.setRawHeader(h.first,h.second);
    request.setRawHeader("Connection","close");
    // Ask for uncompressed payloads so previews and HAR are consistent with
    // byte accounting. If an origin sends encoded data anyway, preserve its
    // Content-Encoding header when forwarding it to the caller.
    request.setRawHeader("Accept-Encoding","identity");
    auto *reply=m_network.sendCustomRequest(request,c->method,c->requestBody);m_replies.insert(reply);
    reply->setReadBufferSize(64*1024);
    connect(reply,&QNetworkReply::readyRead,this,[c,reply]{
        const auto part=reply->readAll();
        if(c->responseBody.size()+part.size()>ResponseLimit){c->truncated=true;reply->abort();return;}
        c->responseBody+=part;
    });
    connect(reply,&QNetworkReply::finished,this,[this,c,reply]{finishHttp(c,reply);});
    connect(c->client,&QTcpSocket::disconnected,reply,[reply]{if(!reply->isFinished())reply->abort();});
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
    QByteArray response="HTTP/1.1 "+QByteArray::number(c->status)+" "+reason+"\r\n";
    QList<QByteArray> connectionTokens;
    for(const auto &h:reply->rawHeaderPairs())if(h.first.toLower()=="connection")for(auto name:h.second.split(','))connectionTokens<<name.trimmed().toLower();
    c->responseHeaders.clear();
    for(const auto &h:reply->rawHeaderPairs()) {
        c->responseHeaders.append(header(h.first,h.second));
        if(!hopHeader(h.first) && h.first.toLower()!="content-length" && !connectionTokens.contains(h.first.toLower()))response+=h.first+": "+h.second+"\r\n";
    }
    const auto length=c->method=="HEAD" && !reply->rawHeader("Content-Length").isEmpty()?reply->rawHeader("Content-Length"):QByteArray::number(c->responseBody.size());
    response+="Content-Length: "+length+"\r\nConnection: close\r\n\r\n";
    if(c->client){c->client->write(response);if(c->method!="HEAD")c->client->write(c->responseBody);c->client->disconnectFromHost();}
    c->statusText=QStringLiteral("已完成");update(c);reply->deleteLater();
}
void CaptureService::update(const std::shared_ptr<Connection> &c) {
    for(qsizetype i=0;i<m_sessions.size();++i)if(m_sessions[i].toMap()["id"].toString()==c->id) {
        QVariantMap row{{"id",c->id},{"method",QString::fromLatin1(c->method)},{"url",safeUrl(c->url)},{"host",c->url.host()},
            {"status",c->status?QString::number(c->status):QStringLiteral("…")},{"statusCode",c->status},{"statusText",c->statusText},
            {"protocol",c->tunnel?QStringLiteral("CONNECT 隧道"):QStringLiteral("HTTP")},{"tunnel",c->tunnel},
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
        m_sessions[i]=row;emit sessionsChanged();return;
    }
}
bool CaptureService::exportHar(const QUrl &url) {
    if(!url.isLocalFile()){setError(QStringLiteral("请选择本地 HAR 文件。"));return false;}
    QJsonArray entries;
    for(const auto &v:m_sessions) {
        const auto r=v.toMap();const bool tunnel=r["tunnel"].toBool();
        QJsonObject request{{"method",r["method"].toString()},{"url",r["url"].toString()},{"httpVersion","HTTP/1.1"},
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
        QJsonObject response{{"status",r["statusCode"].toInt()},{"statusText",r["statusText"].toString()},{"httpVersion","HTTP/1.1"},
            {"headers",QJsonArray::fromVariantList(r["responseHeaderList"].toList())},{"cookies",QJsonArray{}},{"content",content},{"redirectURL",""},{"headersSize",-1},{"bodySize",tunnel?0:r["downBytes"].toInt()}};
        entries.append(QJsonObject{{"startedDateTime",r["started"].toString()},{"time",r["elapsed"].toDouble()},
            {"request",request},{"response",response},{"cache",QJsonObject{}},
            {"timings",QJsonObject{{"send",0},{"wait",r["elapsed"].toDouble()},{"receive",0}}},
            {"_swirl",QJsonObject{{"connectTunnel",tunnel},{"tlsDecrypted",false},{"previewTruncated",r["truncated"].toBool()},{"transportUpBytes",r["upBytes"].toDouble()},{"transportDownBytes",r["downBytes"].toDouble()}}}});
    }
    const QJsonDocument doc(QJsonObject{{"log",QJsonObject{{"version","1.2"},{"creator",QJsonObject{{"name","Swirl"},{"version","0.1"}}},{"entries",entries}}}});
    QSaveFile file(url.toLocalFile());
    if(!file.open(QIODevice::WriteOnly)){setError(file.errorString());return false;}
    const auto bytes=doc.toJson(QJsonDocument::Indented);
    if(file.write(bytes)!=bytes.size() || !file.commit()){setError(file.errorString());return false;}
    m_error.clear();emit stateChanged();return true;
}

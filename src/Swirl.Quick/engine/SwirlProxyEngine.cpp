#include "SwirlProxyEngine.h"
#include "SwirlProtocolRegistry.h"
#include "NativeDuplexRelay.h"
#include <QTcpServer>
#include <QTcpSocket>
#include <QSslSocket>
#include <QSslConfiguration>
#include <QNetworkProxy>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QPointer>
#include <QTimer>
#include <QElapsedTimer>
#include <QDateTime>
#include <QCryptographicHash>
#include <QCoreApplication>
#include <QJsonArray>
#include <QUuid>
#include <QSet>
#include <QRegularExpression>
#include <functional>
#include <algorithm>
#include <cstring>

namespace {
constexpr qint64 ReadLimit=64*1024,WriteLimit=256*1024;
QByteArray address(const QString &host,quint16 port){
    QByteArray result;QHostAddress ip;
    if(ip.setAddress(host)&&ip.protocol()==QAbstractSocket::IPv4Protocol){result.append(char(1));const auto v=ip.toIPv4Address();for(int shift:{24,16,8,0})result.append(char(v>>shift));}
    else if(ip.protocol()==QAbstractSocket::IPv6Protocol){result.append(char(4));const auto v=ip.toIPv6Address();result.append(reinterpret_cast<const char *>(v.c),16);}
    else {const auto name=QUrl::toAce(host);if(name.isEmpty()||name.size()>255)return {};result.append(char(3));result.append(char(name.size()));result.append(name);}
    result.append(char(port>>8));result.append(char(port));return result;
}
// 0 means incomplete, -1 means malformed, positive is total address length.
int readAddress(const QByteArray &b,QString &host,quint16 &port){
    if(b.isEmpty())return 0;int end=0;
    switch(quint8(b[0])){
    case 1:if(b.size()<7)return 0;host=QHostAddress((quint32(quint8(b[1]))<<24)|(quint32(quint8(b[2]))<<16)|(quint32(quint8(b[3]))<<8)|quint8(b[4])).toString();end=5;break;
    case 4:{if(b.size()<19)return 0;Q_IPV6ADDR v{};memcpy(v.c,b.constData()+1,16);host=QHostAddress(v).toString();end=17;break;}
    case 3:{if(b.size()<2)return 0;const int len=quint8(b[1]);if(!len)return -1;if(b.size()<len+4)return 0;host=QString::fromLatin1(b.mid(2,len));end=2+len;break;}
    default:return -1;
    }
    port=quint16((quint16(quint8(b[end]))<<8)|quint8(b[end+1]));return end+2;
}
QByteArray authority(const QString &host,quint16 port){return (host.contains(':')?"["+host.toUtf8()+"]":QUrl::toAce(host))+":"+QByteArray::number(port);}
bool equalSecret(const QByteArray &a,const QByteArray &b){unsigned diff=unsigned(a.size()^b.size());for(qsizetype i=0;i<qMax(a.size(),b.size());++i)diff|=quint8(i<a.size()?a[i]:0)^quint8(i<b.size()?b[i]:0);return diff==0;}
bool headerToken(const QByteArray &value){if(value.isEmpty())return false;for(unsigned char c:value)if(!((c>='0'&&c<='9')||(c>='A'&&c<='Z')||(c>='a'&&c<='z')||QByteArray("!#$%&'*+-.^_`|~").contains(char(c))))return false;return true;}

class NativeSession final:public QObject {
public:
    enum Stage{Detect,SocksHello,SocksAuth,SocksRequest,HttpRequest,Waiting,Streaming};
    QTcpSocket *client,*upstream=nullptr;
    ProxyNode node;
    bool direct=false,closing=false,http=false,tunnel=true,upgrade=false,remoteEnded=false,notified=false;
    NativeDuplexRelay *relay=nullptr;
    QString endReason;
    Stage stage=Detect;
    int outboundStage=0;
    QByteArray buffer,upBuffer,initial,username,password;
    QString host,sourceIp,id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    quint16 port=0;
    qint64 uploaded=0,downloaded=0,upDebt=0,downDebt=0,bodyRemaining=0;
    QTimer deadline;
    QString started=QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
    std::function<void(qint64,qint64)> bytes;
    std::function<void(NativeSession *,const QString &)> ended;
    NativeSession(QTcpSocket *socket,ProxyNode selected,bool bypass,const EngineStartOptions &options,QObject *parent):QObject(parent),client(socket),node(std::move(selected)),direct(bypass),username(options.inboundUsername.toUtf8()),password(options.inboundPassword.toUtf8()){
        client->setParent(this);client->setProxy(QNetworkProxy::NoProxy);client->setReadBufferSize(ReadLimit);
        sourceIp=client->peerAddress().toString();client->setSocketOption(QAbstractSocket::KeepAliveOption,1);client->setSocketOption(QAbstractSocket::LowDelayOption,1);
        deadline.setSingleShot(true);deadline.setInterval(qBound(100,options.startupTimeoutMs,30000));
        connect(&deadline,&QTimer::timeout,this,[this]{fail("ConnectionTimeout",504,6);});
        connect(client,&QTcpSocket::readyRead,this,[this]{consume();});
        connect(client,&QTcpSocket::bytesWritten,this,[this](qint64 count){const auto skip=qMin(count,downDebt);downDebt-=skip;downloaded+=count-skip;if(bytes)bytes(0,count-skip);if(stage==Streaming&&tunnel)attachRelay();else pumpDown();});
        connect(client,&QTcpSocket::disconnected,this,[this]{if(!closing)finish({});notifyEnd();deleteLater();});
        connect(client,&QTcpSocket::errorOccurred,this,[this](auto error){if(!closing&&error!=QAbstractSocket::RemoteHostClosedError)finish("ClientDisconnected");});
        deadline.start();
    }
    QVariantMap snapshot(bool closed=false)const{return {{"id",id},{"host",host},{"ip",host},{"port",port},{"sourceIp",sourceIp},{"process","未知进程"},{"policy",direct?QString("DIRECT"):node.name},{"category",direct?QString("direct"):QString("proxy")},{"network","TCP"},{"uploadBytes",uploaded},{"downloadBytes",downloaded},{"time",started},{"closed",closed}};}
    void notifyEnd(){if(notified)return;notified=true;if(ended)ended(this,endReason);}
    void cancel(){finish({});client->abort();notifyEnd();}
    void sendClientHandshake(const QByteArray &value){downDebt+=value.size();client->write(value);}
    void sendUpHandshake(const QByteArray &value){upDebt+=value.size();upstream->write(value);}
    void finish(const QString &reason){
        if(closing)return;closing=true;endReason=reason;deadline.stop();if(relay)relay->cancel();if(upstream)upstream->abort();
        if(client->state()==QAbstractSocket::UnconnectedState){notifyEnd();deleteLater();}else client->disconnectFromHost();
        QTimer::singleShot(1000,this,[this]{client->abort();notifyEnd();deleteLater();});
    }
    void fail(const QString &reason,int code=502,int socksCode=1){
        if(closing)return;
        if(stage!=Streaming){
            if(http){const auto status=QByteArray::number(code);sendClientHandshake("HTTP/1.1 "+status+" Proxy failure\r\n"+(code==407?QByteArray("Proxy-Authenticate: Basic realm=\"Swirl\"\r\n"):QByteArray())+"Content-Length: 0\r\nConnection: close\r\n\r\n");}
            else if(stage>=SocksRequest)sendClientHandshake(QByteArray::fromHex("05000001000000000000").replace(1,1,QByteArray(1,char(socksCode))));
        }
        finish(reason);
    }
    void consume(){
        if(closing||stage==Waiting)return;if(stage==Streaming){pumpUp();return;}
        buffer+=client->read(ReadLimit-buffer.size());
        if(buffer.isEmpty())return;
        if(stage==Detect){http=quint8(buffer[0])!=5;stage=http?HttpRequest:SocksHello;}
        if(stage==SocksHello){
            if(buffer.size()<2)return;const int len=quint8(buffer[1]);if(!len){fail("InvalidSocksGreeting");return;}if(buffer.size()<len+2)return;
            const char method=username.isEmpty()?0:2;
            if(quint8(buffer[0])!=5||!buffer.mid(2,len).contains(method)){sendClientHandshake(QByteArray::fromHex("05ff"));finish("AuthenticationMethodRejected");return;}
            sendClientHandshake(QByteArray(1,char(5))+QByteArray(1,method));buffer.remove(0,len+2);stage=method==2?SocksAuth:SocksRequest;
        }
        if(stage==SocksAuth){
            if(buffer.size()<2)return;const int u=quint8(buffer[1]);if(buffer.size()<u+3)return;const int p=quint8(buffer[u+2]);if(buffer.size()<u+p+3)return;
            const bool ok=quint8(buffer[0])==1&&u>0&&p>0&&equalSecret(buffer.mid(2,u),username)&&equalSecret(buffer.mid(u+3,p),password);
            sendClientHandshake(QByteArray(1,char(1))+QByteArray(1,char(ok?0:1)));
            if(!ok){finish("InboundAuthenticationFailed");return;}buffer.remove(0,u+p+3);stage=SocksRequest;
        }
        if(stage==SocksRequest){
            if(buffer.size()<4)return;
            if(quint8(buffer[0])!=5||buffer[2]!=0){fail("InvalidSocksRequest");return;}
            if(buffer[1]!=1){fail("SocksCommandUnsupported",501,7);return;}
            const auto n=readAddress(buffer.mid(3),host,port);if(n==0)return;if(n<0||port==0){fail("InvalidSocksAddress",400,8);return;}
            buffer.remove(0,3+n);initial=std::move(buffer);connectOutbound();return;
        }
        if(stage==HttpRequest){
            const auto end=buffer.indexOf("\r\n\r\n");if(end<0){if(buffer.size()>=ReadLimit)fail("HttpHeaderTooLarge",431);return;}
            auto lines=buffer.left(end).split('\n');const auto request=lines.takeFirst().trimmed().split(' ');
            if(request.size()!=3||(request[2]!="HTTP/1.1"&&request[2]!="HTTP/1.0")){fail("InvalidHttpRequest",400);return;}
            tunnel=request[0]=="CONNECT";const QUrl target(QString::fromUtf8((tunnel?QByteArray("http://"):QByteArray())+request[1]),QUrl::StrictMode);
            host=target.host();const int targetPort=target.port(tunnel?-1:80);
            if(!target.isValid()||host.isEmpty()||targetPort<1||targetPort>65535||!target.userInfo().isEmpty()||target.hasFragment()||(!tunnel&&target.scheme()!="http")||(tunnel&&(!target.path().isEmpty()||target.hasQuery()))){fail("InvalidHttpTarget",400);return;}port=quint16(targetPort);
            QByteArray auth,headers,upgradeHeader;bool lengthSeen=false,hostSeen=false;QStringList hopHeaders;
            for(const auto &line:lines){const auto at=line.indexOf(':');if(at<1){fail("InvalidHttpHeader",400);return;}if(line.left(at).trimmed().toLower()=="connection")for(const auto &key:line.mid(at+1).trimmed().toLower().split(','))hopHeaders.append(QString::fromLatin1(key.trimmed()));}
            for(const auto &key:QStringList{"content-length","transfer-encoding","host","proxy-authorization"})if(hopHeaders.contains(key)){fail("InvalidHopByHopHeader",400);return;}
            for(const auto &line:lines){
                const auto at=line.indexOf(':');const auto key=line.left(at).trimmed().toLower(),value=line.mid(at+1).trimmed();
                if(!headerToken(line.left(at))){fail("InvalidHttpHeader",400);return;}for(unsigned char c:value)if((c<32&&c!=9)||c==127){fail("InvalidHttpHeader",400);return;}
                if(key=="proxy-authorization"){if(!auth.isEmpty()){fail("DuplicateProxyAuthentication",400);return;}auth=value;continue;}
                if(key=="host"){if(hostSeen){fail("DuplicateHost",400);return;}hostSeen=true;continue;}
                if(key=="transfer-encoding"){fail("HttpExtensionUnsupported",501);return;}
                if(key=="upgrade"){if(!upgradeHeader.isEmpty()||value.toLower()!="websocket"){fail("HttpUpgradeUnsupported",501);return;}upgradeHeader=value;continue;}
                if(key=="content-length"){bool ok=false;const auto length=value.toLongLong(&ok);if(!ok||!QRegularExpression("^[0-9]+$").match(QString::fromLatin1(value)).hasMatch()||length<0||length>1024LL*1024*1024||lengthSeen){fail("InvalidContentLength",400);return;}lengthSeen=true;bodyRemaining=length;}
                if(key=="proxy-connection"||key=="connection"||key=="keep-alive"||hopHeaders.contains(QString::fromLatin1(key)))continue;
                headers+=line.trimmed()+"\r\n";
            }
            if(!username.isEmpty()&&!equalSecret(auth,"Basic "+(username+":"+password).toBase64())){fail("InboundAuthenticationFailed",407);return;}
            upgrade=!upgradeHeader.isEmpty();
            if(upgrade&&(tunnel||request[0]!="GET"||!hopHeaders.contains("upgrade")||bodyRemaining>0)){fail("InvalidWebSocketUpgrade",400);return;}
            const auto tail=buffer.mid(end+4);
            if(tunnel)initial=tail;
            else {
                if(!upgrade&&tail.size()>bodyRemaining){fail("HttpPipeliningUnsupported",400);return;}
                if(!upgrade)bodyRemaining-=tail.size();auto path=target.path(QUrl::FullyEncoded).toUtf8();if(path.isEmpty())path="/";if(target.hasQuery())path+="?"+target.query(QUrl::FullyEncoded).toUtf8();
                initial=request[0]+" "+path+" HTTP/1.1\r\nHost: "+authority(host,port)+"\r\n"+
                    (upgrade?QByteArray("Connection: Upgrade\r\nUpgrade: websocket\r\n"):QByteArray("Connection: close\r\n"))+headers+"\r\n"+tail;
            }
            buffer.clear();connectOutbound();
        }
    }
    void connectOutbound(){
        stage=Waiting;const bool tls=!direct&&(node.protocol=="trojan"||node.parameters.value("tls").toBool());
        if(tls){auto ssl=new QSslSocket(this);ssl->setProtocol(QSsl::TlsV1_2OrLater);auto config=QSslConfiguration::defaultConfiguration();QList<QByteArray> alpn;for(const auto &v:node.parameters.value("alpn").toArray())alpn.append(v.toString().toUtf8());if(!alpn.isEmpty())config.setAllowedNextProtocols(alpn);ssl->setSslConfiguration(config);upstream=ssl;connect(ssl,&QSslSocket::encrypted,this,[this]{beginHandshake();});connect(ssl,&QSslSocket::sslErrors,this,[this](const QList<QSslError> &){fail("TlsVerificationFailed");});}
        else {upstream=new QTcpSocket(this);connect(upstream,&QTcpSocket::connected,this,[this]{beginHandshake();});}
        upstream->setProxy(QNetworkProxy::NoProxy);upstream->setReadBufferSize(ReadLimit);
        upstream->setSocketOption(QAbstractSocket::KeepAliveOption,1);upstream->setSocketOption(QAbstractSocket::LowDelayOption,1);
        connect(upstream,&QTcpSocket::readyRead,this,[this]{if(stage==Streaming)pumpDown();else consumeUpstream();});
        connect(upstream,&QTcpSocket::bytesWritten,this,[this](qint64 count){const auto skip=qMin(count,upDebt);upDebt-=skip;uploaded+=count-skip;if(bytes)bytes(count-skip,0);if(stage==Streaming&&tunnel)attachRelay();else pumpUp();});
        connect(upstream,&QTcpSocket::errorOccurred,this,[this](auto error){if(!closing&&error!=QAbstractSocket::RemoteHostClosedError)fail(error==QAbstractSocket::HostNotFoundError?"DnsLookupFailed":error==QAbstractSocket::ConnectionRefusedError?"UpstreamConnectionRefused":"UpstreamNetworkError");});
        connect(upstream,&QTcpSocket::disconnected,this,[this]{if(closing)return;if(stage!=Streaming){fail("UpstreamHandshakeClosed");return;}remoteEnded=true;pumpDown();});
        if(tls)static_cast<QSslSocket *>(upstream)->connectToHostEncrypted(node.host,node.port,node.serverName.isEmpty()?node.host:node.serverName);
        else upstream->connectToHost(direct?host:node.host,direct?port:node.port);
    }
    void beginHandshake(){
        if(closing)return;
        NativeDuplexRelay::configureKeepAlive(upstream);
        if(direct){ready();return;}
        if(node.protocol=="http"){
            const auto dest=authority(host,port);QByteArray headers="CONNECT "+dest+" HTTP/1.1\r\nHost: "+dest+"\r\n";
            if(!node.username.isEmpty()||!node.password.isEmpty())headers+="Proxy-Authorization: Basic "+(node.username+":"+node.password).toUtf8().toBase64()+"\r\n";
            outboundStage=3;sendUpHandshake(headers+"\r\n");
        }else if(node.protocol=="socks5"){
            outboundStage=0;sendUpHandshake(node.username.isEmpty()?QByteArray::fromHex("050100"):QByteArray::fromHex("050102"));
        }else if(node.protocol=="trojan"){
            const auto dest=address(host,port);if(dest.isEmpty()){fail("InvalidDestination");return;}
            sendUpHandshake(QCryptographicHash::hash(node.password.toUtf8(),QCryptographicHash::Sha224).toHex()+"\r\n"+QByteArray(1,char(1))+dest+"\r\n");ready();
        }else fail("NativeProtocolUnsupported",501);
    }
    void consumeUpstream(){
        if(closing||!upstream)return;upBuffer+=upstream->read(ReadLimit-upBuffer.size());
        if(node.protocol=="http"){
            const auto end=upBuffer.indexOf("\r\n\r\n");if(end<0){if(upBuffer.size()>=ReadLimit)fail("UpstreamHeaderTooLarge");return;}
            const auto line=upBuffer.left(upBuffer.indexOf("\r\n")).split(' ');const auto status=line.size()>1?line[1].toInt():0;
            if(line.size()<2||(!line[0].startsWith("HTTP/1."))||status!=200){fail(status==407?"UpstreamAuthenticationFailed":"UpstreamConnectRejected");return;}
            upBuffer.remove(0,end+4);ready();return;
        }
        if(node.protocol!="socks5")return;
        if(outboundStage==0){
            if(upBuffer.size()<2)return;const char expected=node.username.isEmpty()?0:2;
            if(upBuffer[0]!=5||upBuffer[1]!=expected){fail("UpstreamAuthenticationRejected");return;}upBuffer.remove(0,2);
            if(expected==2){const auto u=node.username.toUtf8(),p=node.password.toUtf8();sendUpHandshake(QByteArray(1,char(1))+QByteArray(1,char(u.size()))+u+QByteArray(1,char(p.size()))+p);outboundStage=1;}
            else sendSocksConnect();
        }
        if(outboundStage==1){if(upBuffer.size()<2)return;if(upBuffer[0]!=1||upBuffer[1]!=0){fail("UpstreamAuthenticationFailed");return;}upBuffer.remove(0,2);sendSocksConnect();}
        if(outboundStage==2){
            if(upBuffer.size()<4)return;if(upBuffer[0]!=5||upBuffer[1]!=0||upBuffer[2]!=0){fail("UpstreamConnectRejected");return;}
            QString bound;quint16 bindPort;const auto length=readAddress(upBuffer.mid(3),bound,bindPort);if(length==0)return;if(length<0){fail("InvalidUpstreamReply");return;}upBuffer.remove(0,3+length);ready();
        }
    }
    void sendSocksConnect(){const auto dest=address(host,port);if(dest.isEmpty()){fail("InvalidDestination");return;}outboundStage=2;sendUpHandshake(QByteArray::fromHex("050100")+dest);}
    void ready(){
        if(closing)return;stage=Streaming;deadline.stop();
        if(http&&tunnel)sendClientHandshake("HTTP/1.1 200 Connection Established\r\n\r\n");
        else if(!http)sendClientHandshake(QByteArray::fromHex("050000")+address(upstream->localAddress().toString(),upstream->localPort()));
        // CONNECT/SOCKS and a forwarded WebSocket Upgrade are opaque streams.
        // The origin's actual 101 or rejection passes through unchanged.
        // No idle deadline is applied: a quiet Codex task may legitimately wait.
        if(upgrade)tunnel=true;
        if(tunnel){attachRelay();return;}
        if(!initial.isEmpty()){upstream->write(initial);initial.clear();}
        if(!upBuffer.isEmpty()){client->write(upBuffer);upBuffer.clear();}
        pumpUp();pumpDown();
    }
    void pumpUp(){
        if(closing||stage!=Streaming||!upstream)return;
        if(tunnel){attachRelay();return;}
        const auto room=WriteLimit-upstream->bytesToWrite();if(room<=0)return;
        if(http&&!tunnel&&bodyRemaining==0){client->read(ReadLimit);return;}
        const auto amount=qMin(qMin(room,ReadLimit),http&&!tunnel?bodyRemaining:ReadLimit);
        const auto data=client->read(amount);if(data.isEmpty())return;upstream->write(data);if(http&&!tunnel)bodyRemaining-=data.size();
    }
    void pumpDown(){
        if(closing||stage!=Streaming||!upstream)return;if(tunnel){attachRelay();return;}const auto room=WriteLimit-client->bytesToWrite();
        if(room>0){const auto data=upstream->read(qMin(room,ReadLimit));if(!data.isEmpty())client->write(data);}
        if(remoteEnded&&upstream->bytesAvailable()==0)finish({});
    }
    void attachRelay(){
        if(closing||relay||stage!=Streaming||!upstream||client->bytesToWrite()>0||upstream->bytesToWrite()>0)return;
        auto stream=new NativeDuplexRelay(this);
        // Disable session callbacks before closing the old duplicated handles.
        client->disconnect(this);upstream->disconnect(this);
        stream->transferred=[this](qint64 up,qint64 down){uploaded+=up;downloaded+=down;if(bytes)bytes(up,down);};
        stream->finished=[this](const QString &reason){closing=true;endReason=reason;notifyEnd();deleteLater();};
        if(!stream->attach(client,upstream,std::move(initial),std::move(upBuffer))){delete stream;fail("StreamRelayOwnershipFailed");return;}
        relay=stream;initial.clear();upBuffer.clear();
    }
};
}

struct SwirlProxyEngine::Private {
    SwirlProxyEngine *q;QTcpServer listener;QTimer poll;QElapsedTimer uptime,rateClock;
    QNetworkAccessManager network;QPointer<QNetworkReply> reply;QSet<NativeSession *> sessions;QVariantList completed;
    EngineStartOptions options;Status status;qint64 lastUp=0,lastDown=0;quint64 generation=0;
    explicit Private(SwirlProxyEngine *owner):q(owner){poll.setInterval(250);QObject::connect(&poll,&QTimer::timeout,q,&SwirlProxyEngine::refresh);network.setProxy(QNetworkProxy::NoProxy);
        QObject::connect(&listener,&QTcpServer::newConnection,q,[this]{while(listener.hasPendingConnections()){
            auto socket=listener.nextPendingConnection();if(sessions.size()>=256){socket->abort();socket->deleteLater();emit q->diagnostic("SwirlNative","CapacityExceeded","原生连接数达到 256 上限，新连接已拒绝。");continue;}
            ProxyNode node;for(const auto &n:options.nodes)if(n.id==options.selectedNodeId)node=n;
            auto session=new NativeSession(socket,node,options.directSession||options.routingMode=="direct",options,q);sessions.insert(session);
            session->bytes=[this](qint64 up,qint64 down){status.uploadTotal+=up;status.downloadTotal+=down;};
            session->ended=[this](NativeSession *s,const QString &reason){sessions.remove(s);completed.append(s->snapshot(true));while(completed.size()>256)completed.removeFirst();if(!reason.isEmpty())emit q->diagnostic("SwirlNative",reason,QStringLiteral("原生连接失败：%1；未切换为直连。").arg(reason));};
            if(socket->bytesAvailable())session->consume();
        }});
    }
};
SwirlProxyEngine::SwirlProxyEngine(QObject *parent):ProxyEngine(parent),d(std::make_unique<Private>(this)){}
SwirlProxyEngine::~SwirlProxyEngine(){stop();}
ProxyEngine::Status SwirlProxyEngine::status()const{return d->status;}
qsizetype SwirlProxyEngine::activeStreamCount()const{return std::count_if(d->sessions.cbegin(),d->sessions.cend(),[](const NativeSession *s){return s->stage==NativeSession::Streaming&&!s->closing;});}
QString SwirlProxyEngine::configurationSummary()const{return QStringLiteral("Swirl 原生 · 本机混合 HTTP/SOCKS5 监听 · TCP 流量转发 · 内存控制接口；凭据已隐藏。");}
void SwirlProxyEngine::start(const EngineStartOptions &o){
    if(d->listener.isListening())return;stop();d->options=o;d->status={};d->status.engineName="Swirl 原生";d->status.engineKind="native";d->status.sessionId=QUuid::createUuid().toString(QUuid::WithoutBraces);d->status.mode=o.routingMode;
    auto fail=[&](Error error,const QString &reason){d->status.state=State::Failed;d->status.error=error;d->status.message=reason;emit statusChanged();};
    const auto reason=SwirlProtocolRegistry::nativeSessionReason(o);if(!reason.isEmpty()){fail(Error::InvalidOptions,reason);return;}
    if(o.proxyPort==0||o.startupTimeoutMs<100||o.inboundUsername.isEmpty()!=o.inboundPassword.isEmpty()||o.inboundUsername.toUtf8().size()>255||o.inboundPassword.toUtf8().size()>255||o.inboundUsername.contains(':')||o.inboundUsername.contains(QRegularExpression("[\\x00-\\x1f]"))||o.inboundPassword.contains(QRegularExpression("[\\x00-\\x1f]"))){fail(Error::InvalidOptions,"原生端口、超时或入站认证参数无效。");return;}
    if(!d->listener.listen(QHostAddress::LocalHost,o.proxyPort)){fail(Error::PortConflict,"原生代理端口被占用或不能监听。");return;}
    d->status.state=State::Running;d->status.processAlive=true;d->status.apiHealthy=true;d->status.processId=QCoreApplication::applicationPid();d->status.version="Swirl native TCP 0.1";d->status.proxyPort=d->listener.serverPort();d->status.selectedNodeId=o.selectedNodeId;d->status.directSession=o.directSession;d->status.controlEndpoint="in-process://Swirl";
    d->uptime.start();d->rateClock.start();d->lastUp=d->lastDown=0;d->poll.start();refresh();
}
void SwirlProxyEngine::stop(){
    ++d->generation;d->poll.stop();d->listener.close();if(d->reply){d->reply->disconnect(this);d->reply->abort();d->reply->deleteLater();d->reply=nullptr;}d->network.clearAccessCache();
    const auto sessions=d->sessions;for(auto session:sessions){session->cancel();delete session;}d->sessions.clear();d->completed.clear();
    d->status.state=State::Stopped;d->status.processAlive=false;d->status.apiHealthy=false;d->status.proxyPort=0;d->status.connections.clear();d->status.nodeBusy=false;d->status.requestState=RequestState::NotTested;d->status.selectedNodeId.clear();emit statusChanged();
}
void SwirlProxyEngine::refresh(){
    if(!d->listener.isListening())return;const auto now=qMax(QDateTime::currentMSecsSinceEpoch(),d->status.connectionsAt+1);d->status.connections=d->completed;d->completed.clear();for(auto session:d->sessions)d->status.connections.append(session->snapshot());
    d->status.connectionsAt=d->status.trafficAt=now;d->status.uptimeSeconds=d->uptime.elapsed()/1000;
    const auto elapsed=d->rateClock.restart();if(elapsed>0){d->status.uploadRate=double(d->status.uploadTotal-d->lastUp)*1000/elapsed;d->status.downloadRate=double(d->status.downloadTotal-d->lastDown)*1000/elapsed;}d->lastUp=d->status.uploadTotal;d->lastDown=d->status.downloadTotal;emit statusChanged();
}
void SwirlProxyEngine::selectNode(const QString &id){
    if(!d->listener.isListening())return;auto options=d->options;options.selectedNodeId=id;options.directSession=false;
    const auto reason=SwirlProtocolRegistry::nativeSessionReason(options);
    if(!reason.isEmpty()){emit diagnostic("SwirlNative","SelectionUnsupported",reason);return;}
    d->options=options;d->status.selectedNodeId=id;d->status.directSession=false;d->status.nodeHealth=NodeHealth::Unknown;
    d->status.requestState=RequestState::NotTested;d->status.latencyMs=-1;d->status.nodeMessage.clear();
    emit diagnostic("SwirlNative","NodeSelectedPreservingStreams","节点已切换：新连接使用新节点，已建立连接保留原出口。");refresh();
}
void SwirlProxyEngine::setRoutingMode(const QString &mode){
    auto options=d->options;options.routingMode=mode;
    const auto reason=SwirlProtocolRegistry::nativeSessionReason(options);if(!reason.isEmpty()){emit diagnostic("SwirlNative","RoutingUnsupported",reason);return;}
    d->options=options;d->status.mode=mode;emit diagnostic("SwirlNative","RoutingChangedPreservingStreams","路由模式仅用于新连接；现有隧道继续运行。");refresh();
}
void SwirlProxyEngine::probeNode(const QUrl &url){
    if(!d->listener.isListening()||d->reply)return;
    if(!url.isValid()||(url.scheme()!="http"&&url.scheme()!="https")||url.host().isEmpty()||!url.userInfo().isEmpty()||url.hasFragment()){d->status.requestState=RequestState::Failed;d->status.nodeMessage="测试地址必须为不含凭据的 HTTP/HTTPS URL。";emit statusChanged();return;}
    d->network.clearAccessCache();d->network.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",d->status.proxyPort,d->options.inboundUsername,d->options.inboundPassword));
    QNetworkRequest request(url);request.setTransferTimeout(qBound(1000,d->options.startupTimeoutMs,30000));request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);request.setRawHeader("Connection","close");
    auto timer=std::make_shared<QElapsedTimer>();timer->start();const auto generation=d->generation;auto reply=d->network.get(request);d->reply=reply;reply->setReadBufferSize(ReadLimit);d->status.nodeBusy=true;d->status.nodeHealth=NodeHealth::Checking;d->status.requestState=RequestState::InProgress;d->status.nodeMessage.clear();emit statusChanged();
    connect(reply,&QNetworkReply::readyRead,this,[reply]{const auto count=reply->property("readCount").toLongLong()+reply->readAll().size();reply->setProperty("readCount",count);if(count>256*1024)reply->abort();});
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation,timer]{reply->deleteLater();if(generation!=d->generation)return;d->reply=nullptr;d->status.nodeBusy=false;const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&code>=200&&code<400;d->status.responseCode=code;d->status.latencyMs=ok?int(timer->elapsed()):-1;d->status.nodeHealth=ok?NodeHealth::Available:NodeHealth::Unavailable;d->status.requestState=ok?RequestState::Succeeded:RequestState::Failed;d->status.nodeMessage=ok?QString("原生代理实际请求成功 · HTTP %1").arg(code):QString("原生代理实际请求失败 · 网络错误 %1 · HTTP %2").arg(int(reply->error())).arg(code);refresh();});
}

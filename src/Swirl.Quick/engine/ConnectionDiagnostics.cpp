#include "ConnectionDiagnostics.h"
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QNetworkProxy>
#include <QRandomGenerator>
#include <QSaveFile>
#include <QStandardPaths>

ConnectionDiagnostics::ConnectionDiagnostics(QObject *parent):QObject(parent) {
    m_deadline.setSingleShot(true);m_observation.setSingleShot(true);
    connect(&m_deadline,&QTimer::timeout,this,[this]{
        const auto stage=m_phase==Phase::Port?QStringLiteral("本机代理端口"):m_phase==Phase::Connect?QStringLiteral("CONNECT"):m_phase==Phase::Tls?QStringLiteral("TLS"):QStringLiteral("HTTP / WebSocket 握手");
        finish(stage+QStringLiteral("在 15 秒内未完成；仅凭此结果不能区分节点、DNS 或服务端超时。"),m_phase==Phase::Port?QStringLiteral("本机入口异常"):QStringLiteral("通道超时 · 原因未确定"));
    });
    connect(&m_observation,&QTimer::timeout,this,[this]{
        if(m_pongReceived)finish(QStringLiteral("WebSocket Upgrade 与随机 Ping/Pong 双向通信已验证，观察 10 秒未收到关闭；长期稳定性须由用户实测。"),QStringLiteral("短时诊断完成"));
        else finish(QStringLiteral("WebSocket Upgrade 已验证，但 10 秒内未收到匹配的 Pong；尚不能确认双向心跳，原因需结合上游与服务端日志。"),QStringLiteral("WebSocket 心跳未确认"));
    });
}
void ConnectionDiagnostics::noteEvent(const QString &category,const QString &message) {
    m_entries.append(QVariantMap{{"time",QDateTime::currentDateTime().toString(Qt::ISODateWithMs)},{"category",category},{"message",message}});
    while(m_entries.size()>100)m_entries.removeFirst();emit changed();
}
QString ConnectionDiagnostics::report() const {
    QString text=QStringLiteral("Swirl 本地连接诊断\n不包含节点凭据、请求正文或 Codex 密钥。\n");
    for(const auto &item:m_entries){const auto row=item.toMap();text+=row.value("time").toString()+" ["+row.value("category").toString()+"] "+row.value("message").toString()+"\n";}
    return text;
}
QString ConnectionDiagnostics::saveReport() {
    const auto dir=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/diagnostics";
    if(!QDir().mkpath(dir))return {};
    const auto path=dir+"/connection-"+QDateTime::currentDateTime().toString("yyyyMMdd-HHmmss-zzz")+".txt";
    QSaveFile file(path);if(!file.open(QIODevice::WriteOnly))return {};
    file.setPermissions(QFile::ReadOwner|QFile::WriteOwner);const auto bytes=report().toUtf8();
    return file.write(bytes)==bytes.size() && file.commit()?path:QString();
}
void ConnectionDiagnostics::resetSocket() {
    m_deadline.stop();m_observation.stop();
    if(m_socket){auto *socket=m_socket.data();m_socket=nullptr;socket->disconnect(this);socket->abort();socket->deleteLater();}
}
void ConnectionDiagnostics::finish(const QString &message,const QString &category) {
    m_busy=false;m_state=message;resetSocket();noteEvent(category,message);emit changed();
}
void ConnectionDiagnostics::cancel(){if(m_busy)finish(QStringLiteral("用户取消诊断；仅关闭本次诊断连接。"),QStringLiteral("Swirl 操作"));}
void ConnectionDiagnostics::clear(){m_entries.clear();emit changed();}
void ConnectionDiagnostics::run(const QUrl &url) {
    if(m_busy)return;
    if(m_port<1 || m_port>65535){finish(QStringLiteral("未连接节点，本机代理端口未就绪。"),QStringLiteral("本机入口异常"));return;}
    if(!url.isValid() || !QStringList{"http","https","ws","wss"}.contains(url.scheme()) || url.host().isEmpty() ||
        !url.userInfo().isEmpty() || url.hasFragment() || url.toString().size()>2048 || url.toEncoded().contains('\r') || url.toEncoded().contains('\n')) {
        finish(QStringLiteral("请输入不含凭据或片段的 HTTP、HTTPS、WS 或 WSS 地址。"),QStringLiteral("输入无效"));return;
    }
    resetSocket();m_busy=true;m_url=url;m_buffer.clear();m_frameRemaining=0;m_frameOpcode=-1;
    m_fragmented=false;m_pongReceived=false;m_controlPayload.clear();m_pingToken.clear();m_phase=Phase::Port;m_state=QStringLiteral("正在检查本机代理端口…");
    noteEvent(QStringLiteral("用户发起诊断"),QStringLiteral("经 127.0.0.1:%1 检查 %2://%3:%4；未记录路径与查询参数。")
        .arg(m_port).arg(url.scheme(),url.host()).arg(url.port(url.scheme()=="https"||url.scheme()=="wss"?443:80)));
    auto *socket=new QSslSocket(this);m_socket=socket;socket->setProxy(QNetworkProxy::NoProxy);
    connect(socket,&QSslSocket::connected,this,[this,socket]{
        socket->setSocketOption(QAbstractSocket::KeepAliveOption,1);socket->setSocketOption(QAbstractSocket::LowDelayOption,1);
        noteEvent(QStringLiteral("本机入口正常"),QStringLiteral("本机代理 TCP 连接成功。"));
        const auto host=QUrl::toAce(m_url.host());const auto authority=(host.contains(':')?"["+host+"]":host)+":"+QByteArray::number(m_url.port(m_url.scheme()=="https"||m_url.scheme()=="wss"?443:80));
        m_phase=Phase::Connect;m_state=QStringLiteral("正在协商 CONNECT 隧道…");m_deadline.start(15000);
        socket->write("CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\nProxy-Connection: keep-alive\r\n\r\n");emit changed();
    });
    connect(socket,&QSslSocket::encrypted,this,[this]{
        noteEvent(QStringLiteral("TLS 正常"),QStringLiteral("目标证书与主机名校验成功；TLS 内容由本次诊断客户端处理。"));sendRequest();
    });
    connect(socket,&QSslSocket::sslErrors,this,[this](const QList<QSslError>&){finish(QStringLiteral("目标 TLS 证书或主机名校验失败；未忽略证书错误。"),QStringLiteral("TLS 验证失败"));});
    connect(socket,&QSslSocket::readyRead,this,&ConnectionDiagnostics::consume);
    connect(socket,&QSslSocket::errorOccurred,this,[this,socket](QAbstractSocket::SocketError error){
        if(!m_busy)return;
        const auto category=m_phase==Phase::Port?QStringLiteral("本机入口异常"):QStringLiteral("远端通道中断 · 来源未确定");
        // A TCP FIN/RST observed behind an encrypted proxy is not evidence that
        // the destination, the upstream node or Swirl itself caused it.
        finish(QStringLiteral("通道发生套接字错误 %1（%2）；需结合同时段 Swirl 操作与上游日志定位。").arg(int(error)).arg(socket->errorString()),category);
    });
    connect(socket,&QSslSocket::disconnected,this,[this]{if(m_busy)finish(QStringLiteral("通道被对端关闭；没有足够证据区分上游节点与服务端。"),QStringLiteral("远端通道关闭 · 来源未确定"));});
    m_deadline.start(15000);socket->connectToHost(QStringLiteral("127.0.0.1"),quint16(m_port));emit changed();
}
void ConnectionDiagnostics::sendRequest() {
    if(!m_socket)return;
    const bool websocket=m_url.scheme()=="ws"||m_url.scheme()=="wss";
    m_phase=websocket?Phase::WebSocket:Phase::Http;m_buffer.clear();m_deadline.start(15000);
    auto path=m_url.path(QUrl::FullyEncoded).toUtf8();if(path.isEmpty())path="/";
    if(m_url.hasQuery())path+="?"+m_url.query(QUrl::FullyEncoded).toUtf8();
    auto host=QUrl::toAce(m_url.host());if(host.contains(':'))host="["+host+"]";
    if(m_url.port()>0)host+=":"+QByteArray::number(m_url.port());
    QByteArray headers="GET "+path+" HTTP/1.1\r\nHost: "+host+"\r\nUser-Agent: Swirl-Local-Diagnostics/1\r\n";
    if(websocket){QByteArray key(16,Qt::Uninitialized);for(int i=0;i<16;++i)key[i]=char(QRandomGenerator::system()->generate());m_wsKey=key.toBase64();headers+="Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: "+m_wsKey+"\r\n";}
    else headers+="Connection: keep-alive\r\n";
    m_state=websocket?QStringLiteral("正在验证 WebSocket Upgrade…"):QStringLiteral("正在验证 HTTP 响应…");
    m_socket->write(headers+"\r\n");emit changed();
}
void ConnectionDiagnostics::consume() {
    if(!m_socket || !m_busy)return;
    if(m_phase==Phase::Observe) {
        // Bounded chunks plus remaining-length state preserve frame boundaries
        // across arbitrary TCP segmentation without retaining data payloads.
        do {m_buffer+=m_socket->read(32768);consumeWebSocket();}
        while(m_socket && m_busy && m_socket->bytesAvailable()>0);
        return;
    }
    m_buffer+=m_socket->read(65536-m_buffer.size());
    if(m_buffer.size()>=65536 && !m_buffer.contains("\r\n\r\n")){finish(QStringLiteral("诊断响应头超出 64 KiB 上限。"),QStringLiteral("响应限制"));return;}
    const auto end=m_buffer.indexOf("\r\n\r\n");if(end<0)return;
    const auto lines=m_buffer.left(end).split('\n');const auto first=lines.value(0).trimmed().split(' ');const int code=first.value(1).toInt();
    if(m_phase==Phase::Connect) {
        if(code!=200){finish(QStringLiteral("本机代理返回 CONNECT HTTP %1；可能为目标 DNS、上游拨号或协议错误，尚未建立隧道。").arg(code),QStringLiteral("CONNECT 拒绝"));return;}
        noteEvent(QStringLiteral("CONNECT 正常"),QStringLiteral("本机代理已确认 CONNECT 200，双向字节隧道建立。"));m_buffer.clear();
        if(m_url.scheme()=="https"||m_url.scheme()=="wss") {m_phase=Phase::Tls;m_state=QStringLiteral("正在验证目标 TLS…");m_socket->setPeerVerifyName(m_url.host());m_socket->setProtocol(QSsl::TlsV1_2OrLater);m_deadline.start(15000);m_socket->startClientEncryption();emit changed();}
        else sendRequest();
        return;
    }
    if(m_phase==Phase::Http) {
        if(code<100 || code>599){finish(QStringLiteral("隧道中的 HTTP 响应格式无效。"),QStringLiteral("HTTP 响应异常"));return;}
        finish(QStringLiteral("CONNECT 与 %1 响应已验证（HTTP %2）；状态码为服务端实际返回，不能据此推断 Codex 登录或长期稳定性。").arg(m_url.scheme().toUpper()).arg(code),QStringLiteral("HTTP 通道正常"));return;
    }
    if(m_phase==Phase::WebSocket) {
        QByteArray accept,upgrade,connection;
        for(const auto &line:lines){const auto colon=line.indexOf(':');if(colon<0)continue;const auto key=line.left(colon).trimmed().toLower(),value=line.mid(colon+1).trimmed();if(key=="sec-websocket-accept")accept=value;if(key=="upgrade")upgrade=value.toLower();if(key=="connection")connection=value.toLower();}
        const auto expected=QCryptographicHash::hash(m_wsKey+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11",QCryptographicHash::Sha1).toBase64();
        if(code!=101 || accept!=expected || upgrade!="websocket" || !connection.contains("upgrade")) {finish(QStringLiteral("WebSocket Upgrade 未完成（HTTP %1）；该地址可能需要登录、子协议或特定路径，不能据此断定代理故障。").arg(code),QStringLiteral("WebSocket 未确认"));return;}
        noteEvent(QStringLiteral("WebSocket 正常"),QStringLiteral("已验证 HTTP 101 和 Sec-WebSocket-Accept；发送随机掩码 Ping 并观察 10 秒。"));
        m_buffer.remove(0,end+4);m_phase=Phase::Observe;m_state=QStringLiteral("WebSocket 已升级 · 正在观察双向心跳 10 秒…");
        m_pingToken.resize(8);for(int i=0;i<m_pingToken.size();++i)m_pingToken[i]=char(QRandomGenerator::system()->generate());
        sendControlFrame(9,m_pingToken);m_deadline.stop();m_observation.start(10000);
        consumeWebSocket();if(m_socket && m_busy && m_socket->bytesAvailable()>0)consume();emit changed();
    }
}

void ConnectionDiagnostics::sendControlFrame(quint8 opcode,const QByteArray &payload) {
    if(!m_socket || payload.size()>125)return;
    QByteArray mask(4,Qt::Uninitialized);for(int i=0;i<4;++i)mask[i]=char(QRandomGenerator::system()->generate());
    auto encoded=payload;for(int i=0;i<encoded.size();++i)encoded[i]=encoded[i]^mask[i%4];
    // RFC 6455 requires all client frames, including ping/pong, to be masked.
    m_socket->write(QByteArray(1,char(0x80|opcode))+QByteArray(1,char(0x80|payload.size()))+mask+encoded);
}

void ConnectionDiagnostics::consumeWebSocket() {
    while(m_busy && m_socket) {
        if(m_frameOpcode<0) {
            if(m_buffer.size()<2)return;
            const quint8 first=quint8(m_buffer[0]),second=quint8(m_buffer[1]);
            const int opcode=first&15;const bool final=first&0x80;quint64 length=second&127;int header=2;
            if((first&0x70) || (second&0x80) || !QList<int>{0,1,2,8,9,10}.contains(opcode)) {
                finish(QStringLiteral("WebSocket 帧包含不支持的 RSV、服务端掩码或无效操作码；未协商任何扩展。"),QStringLiteral("WebSocket 协议异常"));return;
            }
            if(length==126) {
                if(m_buffer.size()<4)return;length=(quint64(quint8(m_buffer[2]))<<8)|quint8(m_buffer[3]);header=4;
                if(length<126){finish(QStringLiteral("WebSocket 16 位长度编码不规范。"),QStringLiteral("WebSocket 协议异常"));return;}
            }else if(length==127) {
                if(m_buffer.size()<10)return;if(quint8(m_buffer[2])&0x80){finish(QStringLiteral("WebSocket 64 位长度超出协议范围。"),QStringLiteral("WebSocket 协议异常"));return;}
                length=0;for(int i=2;i<10;++i)length=(length<<8)|quint8(m_buffer[i]);header=10;
                if(length<=65535){finish(QStringLiteral("WebSocket 64 位长度编码不规范。"),QStringLiteral("WebSocket 协议异常"));return;}
            }
            if(length>8*1024*1024){finish(QStringLiteral("WebSocket 单帧超过本次诊断的 8 MiB 安全上限；仅关闭诊断连接。"),QStringLiteral("诊断帧长度限制"));return;}
            if(opcode>=8 && (!final || length>125)) {finish(QStringLiteral("WebSocket 控制帧分片或长度无效。"),QStringLiteral("WebSocket 协议异常"));return;}
            if(opcode==0) {
                if(!m_fragmented){finish(QStringLiteral("WebSocket 收到无起始帧的续帧。"),QStringLiteral("WebSocket 协议异常"));return;}
                if(final)m_fragmented=false;
            }else if(opcode==1 || opcode==2) {
                if(m_fragmented){finish(QStringLiteral("WebSocket 上一条分片消息尚未结束。"),QStringLiteral("WebSocket 协议异常"));return;}
                if(!final)m_fragmented=true;
            }
            m_buffer.remove(0,header);m_frameOpcode=opcode;m_frameRemaining=length;m_controlPayload.clear();
        }
        const auto count=qsizetype(qMin<quint64>(m_frameRemaining,quint64(m_buffer.size())));
        if(m_frameOpcode>=8)m_controlPayload+=m_buffer.first(count);
        m_buffer.remove(0,count);m_frameRemaining-=quint64(count);if(m_frameRemaining>0)return;
        const int opcode=m_frameOpcode;m_frameOpcode=-1;
        if(opcode==8) {
            if(m_controlPayload.size()==1){finish(QStringLiteral("WebSocket 关闭帧状态码不完整。"),QStringLiteral("WebSocket 协议异常"));return;}
            const auto code=m_controlPayload.size()>=2?QString::number((int(quint8(m_controlPayload[0]))<<8)|quint8(m_controlPayload[1])):QStringLiteral("未提供");
            sendControlFrame(8,m_controlPayload.first(2));
            finish(QStringLiteral("WebSocket 握手后收到关闭帧（代码 %1，关闭原因文本未记录）；仅凭该帧无法区分节点与服务端原因。").arg(code),QStringLiteral("WebSocket 关闭帧 · 来源未确定"));return;
        }
        if(opcode==9)sendControlFrame(10,m_controlPayload);
        else if(opcode==10 && !m_pongReceived && m_controlPayload==m_pingToken) {
            m_pongReceived=true;noteEvent(QStringLiteral("WebSocket 双向心跳正常"),QStringLiteral("收到与随机 Ping 完全匹配的 Pong；未记录帧载荷。"));
        }
    }
}

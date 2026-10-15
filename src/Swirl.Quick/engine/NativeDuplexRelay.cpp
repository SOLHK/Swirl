#include "NativeDuplexRelay.h"
#include <QTcpSocket>
#include <QSslSocket>
#include <QSocketNotifier>
#include <QTimer>
#include <algorithm>
#ifdef Q_OS_WIN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mstcpip.h>
#else
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#endif

namespace {
constexpr qint64 QueueLimit=256*1024,Chunk=32*1024;
#ifdef Q_OS_WIN
using Handle=SOCKET;constexpr Handle Invalid=INVALID_SOCKET;
int socketError(){return WSAGetLastError();}
bool wouldBlock(int error){return error==WSAEWOULDBLOCK;}
void closeHandle(Handle handle){closesocket(handle);}
bool shutWrite(Handle handle){return shutdown(handle,SD_SEND)==0;}
void tuneKeepAlive(Handle handle){
    const BOOL keepalive=TRUE;setsockopt(handle,SOL_SOCKET,SO_KEEPALIVE,reinterpret_cast<const char *>(&keepalive),sizeof(keepalive));
    tcp_keepalive timing{1,30000,15000};DWORD returned=0;
    WSAIoctl(handle,SIO_KEEPALIVE_VALS,&timing,sizeof(timing),nullptr,0,&returned,nullptr,nullptr);
}
Handle duplicate(qintptr source){
    WSAPROTOCOL_INFOW information{};
    if(WSADuplicateSocketW(SOCKET(source),GetCurrentProcessId(),&information)!=0)return Invalid;
    const auto result=WSASocketW(FROM_PROTOCOL_INFO,FROM_PROTOCOL_INFO,FROM_PROTOCOL_INFO,&information,0,WSA_FLAG_OVERLAPPED);
    if(result==Invalid)return Invalid;u_long nonblocking=1;
    if(ioctlsocket(result,FIONBIO,&nonblocking)!=0){closeHandle(result);return Invalid;}
    tuneKeepAlive(result);
    return result;
}
#else
using Handle=int;constexpr Handle Invalid=-1;
int socketError(){return errno;}
bool wouldBlock(int error){return error==EAGAIN || error==EWOULDBLOCK;}
void closeHandle(Handle handle){::close(handle);}
bool shutWrite(Handle handle){return ::shutdown(handle,SHUT_WR)==0;}
void tuneKeepAlive(Handle handle){const int on=1;setsockopt(handle,SOL_SOCKET,SO_KEEPALIVE,&on,sizeof(on));}
Handle duplicate(qintptr source){const auto result=::dup(int(source));if(result>=0){fcntl(result,F_SETFL,fcntl(result,F_GETFL)|O_NONBLOCK);const int on=1;setsockopt(result,SOL_SOCKET,SO_KEEPALIVE,&on,sizeof(on));}return result;}
#endif
}

struct NativeDuplexRelay::Private {
    NativeDuplexRelay *q;
    struct Side {Handle handle=Invalid;QSocketNotifier *read=nullptr,*write=nullptr;bool eof=false,writeClosed=false;};
    Side client,server;QPointer<QSslSocket> tls;
    QByteArray toClient,toServer;bool stopped=false,pumping=false,continuationPending=false;
    explicit Private(NativeDuplexRelay *owner):q(owner){}
    ~Private(){close();}
    void close(){
        stopped=true;
        for(auto *side:{&client,&server}){
            if(side->read)side->read->setEnabled(false);if(side->write)side->write->setEnabled(false);
            if(side->handle!=Invalid){closeHandle(side->handle);side->handle=Invalid;}
        }
        if(tls){tls->disconnect(q);tls->abort();tls=nullptr;}
    }
    void end(const QString &reason){if(stopped)return;if(!reason.isEmpty())q->observedError=reason;close();if(q->finished)q->finished(q->observedError);}
    void watch(Side &side){
        side.read=new QSocketNotifier(qintptr(side.handle),QSocketNotifier::Read,q);
        side.write=new QSocketNotifier(qintptr(side.handle),QSocketNotifier::Write,q);side.write->setEnabled(false);
        QObject::connect(side.read,&QSocketNotifier::activated,q,[this]{pump();});
        QObject::connect(side.write,&QSocketNotifier::activated,q,[this]{pump();});
    }
    bool receive(Side &side,QByteArray &queue,const QString &label){
        if(side.eof || side.handle==Invalid)return true;
        const auto room=QueueLimit-queue.size();if(room<=0)return true;
        char data[Chunk];const int amount=::recv(side.handle,data,int(qMin<qint64>(room,Chunk)),0);
        if(amount>0)queue.append(data,amount);
        else if(amount==0){side.eof=true;if(q->closeInitiator.isEmpty())q->closeInitiator=label;}
        else {const auto error=socketError();if(!wouldBlock(error)){end(label+QStringLiteral("SocketError:%1").arg(error));return false;}}
        return true;
    }
    bool send(Side &side,QByteArray &queue,bool upload,const QString &label){
        if(queue.isEmpty() || side.writeClosed)return true;
#ifdef Q_OS_WIN
        const auto amount=::send(side.handle,queue.constData(),int(qMin<qint64>(queue.size(),Chunk)),0);
#else
        const auto amount=::send(side.handle,queue.constData(),size_t(qMin<qint64>(queue.size(),Chunk)),MSG_NOSIGNAL);
#endif
        if(amount>0){queue.remove(0,amount);if(q->transferred)q->transferred(upload?amount:0,upload?0:amount);}
        else if(amount<0){const auto error=socketError();if(!wouldBlock(error)){end(label+QStringLiteral("SocketError:%1").arg(error));return false;}}
        return true;
    }
    void pump(){
        if(stopped || pumping)return;pumping=true;
        // One bounded chunk per wakeup keeps the Qt event loop responsive.
        if(!receive(client,toServer,"Client") || (!tls&&!receive(server,toClient,"Upstream"))){pumping=false;return;}
        if(tls){
            const auto room=QueueLimit-toClient.size();if(room>0)toClient+=tls->read(qMin<qint64>(room,Chunk));
            const auto sendRoom=QueueLimit-tls->bytesToWrite();
            if(sendRoom>0 && !toServer.isEmpty()) {const auto written=tls->write(toServer.constData(),qMin<qint64>(sendRoom,toServer.size()));if(written<0){pumping=false;end("UpstreamTlsWriteFailed");return;}toServer.remove(0,written);}
        }else if(!send(server,toServer,true,"Upstream")){pumping=false;return;}
        if(!send(client,toClient,false,"Client")){pumping=false;return;}
        if(client.eof && toServer.isEmpty() && !tls && !server.writeClosed) {
            if(!shutWrite(server.handle)){pumping=false;end("UpstreamHalfCloseFailed");return;}server.writeClosed=true;
        }
        if(server.eof && toClient.isEmpty() && (!tls||tls->bytesAvailable()==0) && !client.writeClosed) {
            if(!shutWrite(client.handle)){pumping=false;end("ClientHalfCloseFailed");return;}client.writeClosed=true;
        }
        client.read->setEnabled(!client.eof && toServer.size()+(tls?tls->bytesToWrite():0)<QueueLimit);
        client.write->setEnabled(!toClient.isEmpty());
        if(!tls){server.read->setEnabled(!server.eof && toClient.size()<QueueLimit);server.write->setEnabled(!toServer.isEmpty());}
        const bool complete=client.eof && server.eof && toClient.isEmpty() && toServer.isEmpty() && (!tls || (tls->bytesAvailable()==0&&tls->bytesToWrite()==0));
        // A QSslSocket cannot independently send close_notify and retain its
        // read side. Retain reads after client EOF; an EOF-delimited TLS request
        // requires the compatibility engine. Framed HTTP/WS does not need it.
        const bool tlsComplete=tls && server.eof && tls->bytesAvailable()==0 && tls->bytesToWrite()==0 && toClient.isEmpty() && toServer.isEmpty();
        pumping=false;if(complete || tlsComplete){end({});return;}
        // Qt emits readyRead for newly decrypted data, not for every read of an
        // existing buffer. Continue bounded work while that buffer can advance;
        // if output is full, wait for the native writable notification instead.
        const bool bufferedTls=tls&&tls->bytesAvailable()>0&&toClient.size()<QueueLimit;
        const bool queuedTls=tls&&!server.eof&&!toServer.isEmpty()&&tls->bytesToWrite()<QueueLimit;
        if((bufferedTls||queuedTls)&&!continuationPending){continuationPending=true;QTimer::singleShot(0,q,[this]{continuationPending=false;pump();});}
    }
};
NativeDuplexRelay::NativeDuplexRelay(QObject *parent):QObject(parent),d(std::make_unique<Private>(this)){}
NativeDuplexRelay::~NativeDuplexRelay()=default;
bool NativeDuplexRelay::attach(QTcpSocket *client,QTcpSocket *upstream,QByteArray initialUp,QByteArray initialDown){
    if(d->client.handle!=Invalid || !client || !upstream || client->bytesToWrite()>0 || upstream->bytesToWrite()>0)return false;
    d->client.handle=duplicate(client->socketDescriptor());if(d->client.handle==Invalid)return false;
    d->tls=qobject_cast<QSslSocket *>(upstream);
    if(!d->tls){d->server.handle=duplicate(upstream->socketDescriptor());if(d->server.handle==Invalid){d->close();return false;}}
    initialUp+=client->readAll();initialDown+=upstream->readAll();
    if(initialUp.size()>QueueLimit || initialDown.size()>QueueLimit){d->close();return false;}
    client->disconnect();client->abort();
    if(!d->tls){upstream->disconnect();upstream->abort();}
    d->toServer=std::move(initialUp);d->toClient=std::move(initialDown);d->watch(d->client);if(!d->tls)d->watch(d->server);
    if(d->tls){
        connect(d->tls,&QTcpSocket::readyRead,this,[this]{d->pump();});
        connect(d->tls,&QTcpSocket::bytesWritten,this,[this](qint64 count){if(transferred)transferred(count,0);d->pump();});
        connect(d->tls,&QTcpSocket::disconnected,this,[this]{if(closeInitiator.isEmpty())closeInitiator="Upstream";d->server.eof=true;d->pump();});
        connect(d->tls,&QTcpSocket::errorOccurred,this,[this](auto error){observedError=QStringLiteral("UpstreamTlsSocketError:%1").arg(int(error));if(error!=QAbstractSocket::RemoteHostClosedError)d->end(observedError);});
    }
    QTimer::singleShot(0,this,[this]{d->pump();});return true;
}
void NativeDuplexRelay::cancel(){d->close();}
void NativeDuplexRelay::configureKeepAlive(QTcpSocket *socket){if(socket&&socket->socketDescriptor()>=0)tuneKeepAlive(Handle(socket->socketDescriptor()));}

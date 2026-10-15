#pragma once
#include <QCoreApplication>
#include <QLocalServer>
#include <QLocalSocket>
#include <QTimer>
#include <QCryptographicHash>
#include <functional>
#ifdef Q_OS_WIN
#include <windows.h>
#include <sddl.h>
#endif

// One production owner per Windows user/session, independent of install path
// and elevation. IPC accepts only activation, never paths or commands.
class SingleInstance final : public QObject {
public:
    enum Result { Primary, Activated, Unavailable };
    std::function<void()> activate;
    Result acquire(const QString &scope = QStringLiteral("production")) {
#ifdef Q_OS_WIN
        HANDLE token=nullptr;
        if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return Unavailable;
        DWORD size=0;GetTokenInformation(token,TokenUser,nullptr,0,&size);
        QByteArray bytes(size,0);
        const bool ok=GetTokenInformation(token,TokenUser,bytes.data(),size,&size);
        CloseHandle(token);
        LPWSTR sid=nullptr;
        if(!ok || !ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER *>(bytes.data())->User.Sid,&sid))return Unavailable;
        const QString user=QString::fromWCharArray(sid);LocalFree(sid);
        const QString key=QString::fromLatin1(QCryptographicHash::hash((user+scope).toUtf8(),QCryptographicHash::Sha256).toHex());
        const QString name="Local\\SOLHK.Swirl."+key;
        PSECURITY_DESCRIPTOR descriptor=nullptr;
        const QString acl="D:(A;;GA;;;"+user+")S:(ML;;NW;;;ME)";
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(reinterpret_cast<LPCWSTR>(acl.utf16()),SDDL_REVISION_1,&descriptor,nullptr))return Unavailable;
        SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES),descriptor,FALSE};
        m_mutex=CreateMutexW(&attributes,FALSE,reinterpret_cast<LPCWSTR>(name.utf16()));
        LocalFree(descriptor);
        if(!m_mutex)return Unavailable;
        const auto lock=WaitForSingleObject(m_mutex,0);
        m_owned=lock==WAIT_OBJECT_0 || lock==WAIT_ABANDONED;
        m_endpoint="SOLHK.Swirl."+key;
        if(!m_owned){
            QLocalSocket socket;socket.connectToServer(m_endpoint);
            if(!socket.waitForConnected(1200))return Unavailable;
            if(!socket.bytesAvailable())socket.waitForReadyRead(500);
            const auto pid=socket.readLine(32).trimmed().toULong();
            if(pid)AllowSetForegroundWindow(pid);
            socket.write("ACTIVATE\n");socket.flush();
            if(socket.bytesToWrite())socket.waitForBytesWritten(500);
            return Activated;
        }
        m_server.setSocketOptions(QLocalServer::UserAccessOption);
        if(!m_server.listen(m_endpoint))return Unavailable;
        connect(&m_server,&QLocalServer::newConnection,this,[this]{
            while(auto *socket=m_server.nextPendingConnection()){
                socket->setReadBufferSize(32);
                socket->write(QByteArray::number(QCoreApplication::applicationPid())+'\n');
                connect(socket,&QLocalSocket::readyRead,socket,[this,socket]{
                    auto data=socket->property("activationBytes").toByteArray()+socket->readAll();
                    if(data.size()>16){socket->abort();return;}
                    socket->setProperty("activationBytes",data);
                    if(data=="ACTIVATE\n") {if(activate)activate();socket->disconnectFromServer();}
                    else if(data.contains('\n'))socket->abort();
                });
                connect(socket,&QLocalSocket::disconnected,socket,&QObject::deleteLater);
                QTimer::singleShot(1500,socket,[socket]{socket->abort();socket->deleteLater();});
            }
        });
        return Primary;
#else
        Q_UNUSED(scope);return Primary;
#endif
    }
    ~SingleInstance() override {
        m_server.close();
#ifdef Q_OS_WIN
        if(m_owned)ReleaseMutex(m_mutex);
        if(m_mutex)CloseHandle(m_mutex);
#endif
    }
private:
    QLocalServer m_server;
    QString m_endpoint;
#ifdef Q_OS_WIN
    HANDLE m_mutex=nullptr;
    bool m_owned=false;
#endif
};

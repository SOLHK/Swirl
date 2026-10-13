#include "SystemProxy.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QSaveFile>
#include <QStandardPaths>
#include <QTimer>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wininet.h>
#endif
QJsonObject SystemProxyState::json() const {return {{"flags",int(flags)},{"server",server},{"bypass",bypass},{"pac",pac}};}
SystemProxyState SystemProxyState::fromJson(const QJsonObject &o) {return {quint32(o["flags"].toInt(1)),o["server"].toString(),o["bypass"].toString(),o["pac"].toString()};}
namespace {
class MemoryBackend final : public SystemProxyBackend {
    SystemProxyState state;
public:
    bool read(SystemProxyState &s,QString &) override {s=state;return true;}
    bool write(const SystemProxyState &s,QString &) override {state=s;return true;}
};
class NativeBackend final : public SystemProxyBackend {
public:
    bool read(SystemProxyState &s,QString &error) override {
#ifdef Q_OS_WIN
        INTERNET_PER_CONN_OPTIONW opts[4]{};
        opts[0].dwOption=INTERNET_PER_CONN_FLAGS;
        opts[1].dwOption=INTERNET_PER_CONN_PROXY_SERVER;
        opts[2].dwOption=INTERNET_PER_CONN_PROXY_BYPASS;
        opts[3].dwOption=INTERNET_PER_CONN_AUTOCONFIG_URL;
        INTERNET_PER_CONN_OPTION_LISTW list{sizeof(list),nullptr,4,0,opts};
        DWORD bytes=sizeof(list);
        if(!InternetQueryOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,&bytes)) {
            error=QStringLiteral("读取系统代理失败（%1）").arg(GetLastError());return false;
        }
        s={opts[0].Value.dwValue,QString::fromWCharArray(opts[1].Value.pszValue),QString::fromWCharArray(opts[2].Value.pszValue),QString::fromWCharArray(opts[3].Value.pszValue)};
        for(int i=1;i<4;++i)if(opts[i].Value.pszValue)GlobalFree(opts[i].Value.pszValue);
        return true;
#else
        Q_UNUSED(s);error=QStringLiteral("当前平台不支持 Windows 系统代理");return false;
#endif
    }
    bool write(const SystemProxyState &s,QString &error) override {
#ifdef Q_OS_WIN
        auto server=s.server.toStdWString(),bypass=s.bypass.toStdWString(),pac=s.pac.toStdWString();
        INTERNET_PER_CONN_OPTIONW opts[4]{};
        opts[0].dwOption=INTERNET_PER_CONN_FLAGS;opts[0].Value.dwValue=s.flags;
        opts[1].dwOption=INTERNET_PER_CONN_PROXY_SERVER;opts[1].Value.pszValue=server.data();
        opts[2].dwOption=INTERNET_PER_CONN_PROXY_BYPASS;opts[2].Value.pszValue=bypass.data();
        opts[3].dwOption=INTERNET_PER_CONN_AUTOCONFIG_URL;opts[3].Value.pszValue=pac.data();
        INTERNET_PER_CONN_OPTION_LISTW list{sizeof(list),nullptr,4,0,opts};
        if(!InternetSetOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,sizeof(list))) {
            error=QStringLiteral("设置系统代理失败（%1）").arg(GetLastError());return false;
        }
        InternetSetOptionW(nullptr,INTERNET_OPTION_SETTINGS_CHANGED,nullptr,0);
        InternetSetOptionW(nullptr,INTERNET_OPTION_REFRESH,nullptr,0);
        return true;
#else
        Q_UNUSED(s);error=QStringLiteral("当前平台不支持 Windows 系统代理");return false;
#endif
    }
};
}
SystemProxy::SystemProxy(bool native,QObject *parent,std::unique_ptr<SystemProxyBackend> backend,QString journal):QObject(parent),m_backend(std::move(backend)),m_journal(std::move(journal)) {
    if(!m_backend) {
        if(native)m_backend=std::make_unique<NativeBackend>();
        else m_backend=std::make_unique<MemoryBackend>();
    }
    if(native && m_journal.isEmpty())m_journal=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/system-proxy-lease.json";
    if(!m_journal.isEmpty()) {
        QDir().mkpath(QFileInfo(m_journal).absolutePath());
        m_lock=std::make_unique<QLockFile>(m_journal+".lock");
        m_lock->setStaleLockTime(0);
        if(m_lock->tryLock(0)){recover();m_lock->unlock();}
    }
    auto *timer=new QTimer(this);timer->setInterval(2000);
    connect(timer,&QTimer::timeout,this,&SystemProxy::refresh);timer->start();
}
SystemProxy::~SystemProxy(){disable();}
bool SystemProxy::recover() {
    QFile file(m_journal);
    if(!file.exists())return true;
    if(!file.open(QIODevice::ReadOnly)){m_error=QStringLiteral("无法读取系统代理恢复记录");return false;}
    QJsonParseError parse;
    const auto doc=QJsonDocument::fromJson(file.readAll(),&parse);file.close();
    if(parse.error!=QJsonParseError::NoError || !doc.object()["before"].isObject() || !doc.object()["applied"].isObject()) {
        m_error=QStringLiteral("系统代理恢复记录损坏，请检查系统代理设置");return false;
    }
    SystemProxyState current;
    if(!m_backend->read(current,m_error))return false;
    const auto o=doc.object();
    if(current==SystemProxyState::fromJson(o["applied"].toObject()) && !m_backend->write(SystemProxyState::fromJson(o["before"].toObject()),m_error))return false;
    QFile::remove(m_journal);return true;
}
bool SystemProxy::saveJournal() {
    if(m_journal.isEmpty())return true;
    QSaveFile file(m_journal);
    if(!file.open(QIODevice::WriteOnly)){m_error=QStringLiteral("无法保存系统代理恢复记录");return false;}
    const QByteArray data=QJsonDocument(QJsonObject{{"before",m_before->json()},{"applied",m_applied.json()}}).toJson();
    if(file.write(data)!=data.size() || !file.commit()){m_error=QStringLiteral("无法保存系统代理恢复记录");return false;}
    return true;
}
bool SystemProxy::enable(int port) {
    m_error.clear();
    if(port<1 || port>65535){m_error=QStringLiteral("代理端口尚未就绪");emit changed();return false;}
    if(m_before) {refresh();if(m_enabled && m_applied.server==QStringLiteral("127.0.0.1:%1").arg(port))return true;if(!disable())return false;}
    m_error.clear();
    if(m_lock && !m_lock->tryLock(0)){m_error=QStringLiteral("另一 Swirl 实例正在管理系统代理");emit changed();return false;}
    if(!recover()){if(m_lock)m_lock->unlock();emit changed();return false;}
    SystemProxyState before;
    if(!m_backend->read(before,m_error)){if(m_lock)m_lock->unlock();emit changed();return false;}
    m_before=before;
    m_applied={3,QStringLiteral("127.0.0.1:%1").arg(port),QStringLiteral("<local>;localhost;127.*;[::1]"),{}};
    if(!saveJournal()){m_before.reset();if(m_lock)m_lock->unlock();emit changed();return false;}
    if(!m_backend->write(m_applied,m_error)){disable();emit changed();return false;}
    SystemProxyState current;
    m_enabled=m_backend->read(current,m_error) && current==m_applied;
    if(!m_enabled){m_error=QStringLiteral("系统代理设置未生效");disable();}
    emit changed();return m_enabled;
}
void SystemProxy::release() {m_before.reset();m_enabled=false;if(!m_journal.isEmpty())QFile::remove(m_journal);if(m_lock)m_lock->unlock();}
bool SystemProxy::disable() {
    if(!m_before)return true;
    SystemProxyState current;
    if(!m_backend->read(current,m_error)){emit changed();return false;}
    // An external client owns changes it made after Swirl. Never overwrite them.
    if(current==m_applied) {
        if(!m_backend->write(*m_before,m_error)){emit changed();return false;}
        SystemProxyState restored;
        if(!m_backend->read(restored,m_error) || !(restored==*m_before)) {
            if(m_error.isEmpty())m_error=QStringLiteral("原系统代理设置未完全恢复");
            emit changed();return false;
        }
    }
    release();emit changed();return true;
}
void SystemProxy::refresh() {
    if(!m_before)return;
    SystemProxyState current;
    const bool enabled=m_backend->read(current,m_error) && current==m_applied;
    if(enabled!=m_enabled){m_enabled=enabled;if(!enabled && m_error.isEmpty())m_error=QStringLiteral("系统代理已被其他程序修改，可重新开启");emit changed();}
}

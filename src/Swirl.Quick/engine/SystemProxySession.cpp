#include "SystemProxySession.h"
#include <QCoreApplication>
#include <QStandardPaths>
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include <QJsonDocument>
#include <QLockFile>
#include <QThread>
#include <QFileInfo>
#include <cstdio>
#include <QUuid>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wininet.h>
#include <wincrypt.h>
#endif

namespace {
QByteArray crypt(const QByteArray &bytes, bool decrypt) {
#ifdef Q_OS_WIN
    DATA_BLOB src{DWORD(bytes.size()),reinterpret_cast<BYTE *>(const_cast<char *>(bytes.constData()))}, out{};
    QByteArray context("Swirl.SystemProxy.v1");
    DATA_BLOB entropy{DWORD(context.size()),reinterpret_cast<BYTE *>(context.data())};
    bool ok=decrypt?CryptUnprotectData(&src,nullptr,&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out)
        :CryptProtectData(&src,L"Swirl proxy recovery",&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out);
    if(!ok)return {};
    QByteArray result(reinterpret_cast<char *>(out.pbData),out.cbData);
    SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);return result;
#else
    Q_UNUSED(bytes);Q_UNUSED(decrypt);return {};
#endif
}
QJsonObject read(const QString &path) {
    QFile f(path);if(!f.open(QIODevice::ReadOnly)||f.size()>65536)return {};
    auto plain=crypt(f.readAll(),true);auto result=QJsonDocument::fromJson(plain).object();plain.fill(0);return result;
}
bool write(const QString &path, const QJsonObject &object) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    auto plain=QJsonDocument(object).toJson(QJsonDocument::Compact);auto bytes=crypt(plain,false);plain.fill(0);
    QSaveFile f(path);return !bytes.isEmpty()&&f.open(QIODevice::WriteOnly)&&f.write(bytes)==bytes.size()&&f.commit();
}
#ifdef Q_OS_WIN
QString stamp(HANDLE process) {
    FILETIME created{},exit{},kernel{},user{};
    if(!GetProcessTimes(process,&created,&exit,&kernel,&user))return {};
    return QString::number((quint64(created.dwHighDateTime)<<32)|created.dwLowDateTime);
}
bool alive(const QJsonObject &record, const char *key, const char *timeKey) {
    auto h=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(record.value(key).toDouble()));
    if(!h)return false;
    const bool result=stamp(h)==record.value(timeKey).toString()&&WaitForSingleObject(h,0)==WAIT_TIMEOUT;
    CloseHandle(h);return result;
}
QString nativeError() { return QStringLiteral("Windows 系统代理操作失败（错误 %1）。").arg(GetLastError()); }
#endif
}
QString SystemProxySession::journalPath() { return QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/system-proxy.dpapi"; }
SystemProxySession::SystemProxySession(QObject *parent, QString journal):QObject(parent),m_journal(journal.isEmpty()?journalPath():journal) {
    recover(m_journal,&m_error);refresh();m_poll.setInterval(500);
    connect(&m_poll,&QTimer::timeout,this,&SystemProxySession::refresh);m_poll.start();
    connect(QCoreApplication::instance(),&QCoreApplication::aboutToQuit,this,&SystemProxySession::disable);
}
SystemProxySession::~SystemProxySession() { disable(); }
QJsonObject SystemProxySession::snapshot(QString *error) {
#ifdef Q_OS_WIN
    INTERNET_PER_CONN_OPTIONW options[4]{};
    options[0].dwOption=INTERNET_PER_CONN_FLAGS_UI;
    options[1].dwOption=INTERNET_PER_CONN_PROXY_SERVER;
    options[2].dwOption=INTERNET_PER_CONN_PROXY_BYPASS;
    options[3].dwOption=INTERNET_PER_CONN_AUTOCONFIG_URL;
    INTERNET_PER_CONN_OPTION_LISTW list{};list.dwSize=sizeof(list);list.dwOptionCount=4;list.pOptions=options;
    DWORD size=sizeof(list);
    if(!InternetQueryOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,&size)) {
        options[0].dwOption=INTERNET_PER_CONN_FLAGS;size=sizeof(list);
        if(!InternetQueryOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,&size)){if(error)*error=nativeError();return {};}
    }
    QJsonObject result{{"flags",int(options[0].Value.dwValue)}};
    const char *keys[]={"server","bypass","pac"};
    for(int i=1;i<4;++i){result.insert(keys[i-1],QString::fromWCharArray(options[i].Value.pszValue?options[i].Value.pszValue:L""));if(options[i].Value.pszValue)GlobalFree(options[i].Value.pszValue);}
    return result;
#else
    if(error)*error=QStringLiteral("系统代理仅支持 Windows。");return {};
#endif
}
bool SystemProxySession::apply(const QJsonObject &value, QString *error) {
#ifdef Q_OS_WIN
    if(!value.contains("flags")||!value.contains("server")||!value.contains("bypass")||!value.contains("pac"))return false;
    // Machine-wide or disabled settings must be reported, never changed.
    for(auto hive:{HKEY_CURRENT_USER,HKEY_LOCAL_MACHINE}) {
        DWORD data=1,size=sizeof(data);
        if(RegGetValueW(hive,L"Software\\Policies\\Microsoft\\Windows\\CurrentVersion\\Internet Settings",L"ProxySettingsPerUser",RRF_RT_REG_DWORD,nullptr,&data,&size)==ERROR_SUCCESS&&data==0){if(error)*error=QStringLiteral("系统策略要求计算机级代理；Swirl 只管理当前用户代理。");return false;}
        data=0;size=sizeof(data);
        if(RegGetValueW(hive,L"Software\\Policies\\Microsoft\\Internet Explorer\\Control Panel",L"Proxy",RRF_RT_REG_DWORD,nullptr,&data,&size)==ERROR_SUCCESS&&data){if(error)*error=QStringLiteral("系统策略禁止修改代理。");return false;}
    }
    const auto server=value.value("server").toString(),bypass=value.value("bypass").toString(),pac=value.value("pac").toString();
    INTERNET_PER_CONN_OPTIONW options[4]{};options[0].dwOption=INTERNET_PER_CONN_FLAGS;options[0].Value.dwValue=value.value("flags").toInt();
    options[1].dwOption=INTERNET_PER_CONN_PROXY_SERVER;options[1].Value.pszValue=const_cast<wchar_t *>(reinterpret_cast<const wchar_t *>(server.utf16()));
    options[2].dwOption=INTERNET_PER_CONN_PROXY_BYPASS;options[2].Value.pszValue=const_cast<wchar_t *>(reinterpret_cast<const wchar_t *>(bypass.utf16()));
    options[3].dwOption=INTERNET_PER_CONN_AUTOCONFIG_URL;options[3].Value.pszValue=const_cast<wchar_t *>(reinterpret_cast<const wchar_t *>(pac.utf16()));
    INTERNET_PER_CONN_OPTION_LISTW list{};list.dwSize=sizeof(list);list.dwOptionCount=4;list.pOptions=options;
    if(!InternetSetOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,sizeof(list))){if(error)*error=nativeError();return false;}
    InternetSetOptionW(nullptr,INTERNET_OPTION_SETTINGS_CHANGED,nullptr,0);InternetSetOptionW(nullptr,INTERNET_OPTION_REFRESH,nullptr,0);
    if(snapshot()!=value){if(error)*error=QStringLiteral("Windows 实际代理配置与写入值不一致。");return false;}return true;
#else
    Q_UNUSED(value);if(error)*error=QStringLiteral("系统代理仅支持 Windows。");return false;
#endif
}
bool SystemProxySession::recover(const QString &journal, QString *error, bool requireDeadOwner, const QString &expectedSession) {
    QLockFile lock(journal+".lock");if(!lock.tryLock(1000)){if(error)*error=QStringLiteral("系统代理恢复正在由另一进程处理。");return false;}
    if(!QFile::exists(journal))return true;
    const auto record=read(journal);
    if(record.value("schema").toInt()!=1){if(error)*error=QStringLiteral("无法解密代理恢复记录；已保留记录。");return false;}
    if(!expectedSession.isEmpty()&&record.value("session").toString()!=expectedSession)return true;
#ifdef Q_OS_WIN
    if(requireDeadOwner&&alive(record,"owner","ownerTime")){if(error)*error=QStringLiteral("另一个 Swirl 正在管理系统代理。");return false;}
#endif
    const auto current=snapshot(error);if(current.isEmpty())return false;
    if(current==record.value("applied").toObject()&&!apply(record.value("original").toObject(),error))return false;
    // If any setting changed externally, relinquish ownership without writing.
    return QFile::remove(journal);
}
bool SystemProxySession::enable(int port, qint64 enginePid) {
    m_error.clear();
    if(port<1||port>65535||enginePid<=0){m_error=QStringLiteral("真实引擎与代理端口尚未就绪。");emit changed();return false;}
    if(m_owned){refresh();return m_owned;}
    if(!recover(m_journal,&m_error)){emit changed();return false;}
    QLockFile lock(m_journal+".lock");
    if(!lock.tryLock(1000)||QFile::exists(m_journal)){m_error=QStringLiteral("另一个 Swirl 正在启用代理。");emit changed();return false;}
    const auto original=snapshot(&m_error);if(original.isEmpty()){emit changed();return false;}
    const QJsonObject applied{{"flags",3},{"server",QStringLiteral("127.0.0.1:%1").arg(port)},
        {"bypass","localhost;127.*;10.*;192.168.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;[::1];<local>"},{"pac",""}};
    QJsonObject record{{"schema",1},{"session",QUuid::createUuid().toString()},{"owner",double(QCoreApplication::applicationPid())},{"engine",double(enginePid)},{"original",original},{"applied",applied}};
#ifdef Q_OS_WIN
    record.insert("ownerTime",stamp(GetCurrentProcess()));
    auto h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(enginePid));if(!h){m_error=QStringLiteral("无法验证引擎进程身份。");emit changed();return false;}
    record.insert("engineTime",stamp(h));CloseHandle(h);
#endif
    if(!write(m_journal,record)){m_error=QStringLiteral("无法安全保存 DPAPI 代理恢复记录。");emit changed();return false;}
    // Start the guard and receive its readiness acknowledgement BEFORE writing.
    m_guard.setProgram(QCoreApplication::applicationDirPath()+"/SwirlProxyGuard.exe");m_guard.setArguments({m_journal});
#ifdef Q_OS_WIN
    m_guard.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *args){args->flags|=CREATE_NO_WINDOW;});
#endif
    QFile::remove(m_journal+".ready");
    const bool started=m_guard.startDetached();
    for(int i=0;started&&!QFile::exists(m_journal+".ready")&&i<80;++i)QThread::msleep(25);
    if(!started||!QFile::exists(m_journal+".ready")) {
        m_error=QStringLiteral("安全恢复守护进程未就绪，未启用系统代理。");QFile::remove(m_journal);emit changed();return false;
    }
    if(snapshot()!=original){m_error=QStringLiteral("其他软件刚刚修改了系统代理，请重试。");QFile::remove(m_journal);emit changed();return false;}
    if(!apply(applied,&m_error)){lock.unlock();recover(m_journal,nullptr,false);emit changed();return false;}
    m_session=record.value("session").toString();m_owned=true;m_enabled=true;emit changed();return true;
}
bool SystemProxySession::disable() {
    if(!m_owned)return true;
    m_error.clear();bool ok=recover(m_journal,&m_error,false,m_session);
    if(ok)m_owned=false;refresh();emit changed();return ok;
}
void SystemProxySession::refresh() {
    const auto record=read(m_journal);const auto current=snapshot();
    // A transient WinINET read failure is not an external ownership change.
    // Retain the encrypted recovery record so the independent guard can act.
    if(current.isEmpty())return;
    const bool ownSession=!m_session.isEmpty()&&record.value("session").toString()==m_session;
    const bool same=ownSession&&current==record.value("applied").toObject();
    if(m_owned&&!same){m_owned=false;if(ownSession)QFile::remove(m_journal);m_error=QStringLiteral("系统代理已由外部修改或安全恢复，Swirl 已放弃控制。");}
    const bool enabled=m_owned&&same;
    if(enabled!=m_enabled){m_enabled=enabled;emit changed();}
}
int SystemProxySession::guard(const QString &journal) {
#ifdef Q_OS_WIN
    const auto record=read(journal);if(record.value("schema").toInt()!=1||!alive(record,"owner","ownerTime"))return 2;
    auto owner=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(record.value("owner").toDouble()));
    if(!owner)return 3;
    QFile ready(journal+".ready");
    if(!ready.open(QIODevice::WriteOnly)){CloseHandle(owner);return 5;}ready.write("ready");ready.close();
    // Handle GUI death AND engine death. No fixed delay leaves a dead localhost
    // proxy behind while the GUI still appears alive.
    while(read(journal).value("session")==record.value("session")&&WaitForSingleObject(owner,250)==WAIT_TIMEOUT&&alive(record,"engine","engineTime")) {}
    CloseHandle(owner);
    if(read(journal).value("session")==record.value("session")) {
        QFile::remove(journal+".ready");
        return recover(journal,nullptr,false,record.value("session").toString())?0:4;
    }
    return 0;
#else
    Q_UNUSED(journal);return 2;
#endif
}

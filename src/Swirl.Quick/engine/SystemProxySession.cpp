#include "SystemProxySession.h"
#include <QCoreApplication>
#include "../app/StoragePaths.h"
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include <QJsonDocument>
#include <QLockFile>
#include <QThread>
#include <QFileInfo>
#include <cstdio>
#include <QUuid>
#include <limits>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wininet.h>
#include <wincrypt.h>
#endif
#include "SystemProxyState.h"

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
constexpr auto internetKey=L"Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings";
constexpr const wchar_t *registryNames[]={L"ProxyEnable",L"ProxyServer",L"ProxyOverride",L"AutoConfigURL"};
constexpr const char *registryKeys[]={"ProxyEnable","ProxyServer","ProxyOverride","AutoConfigURL"};
bool validRegistry(const QJsonObject &values) {
    if(values.size()!=4)return false;
    for(const auto name:registryKeys) {
        if(!values.value(name).isObject())return false;
        const auto v=values.value(name).toObject();if(!v.value("present").isBool())return false;
        if(!v.value("present").toBool())continue;
        const double type=v.value("type").toDouble(-1);
        if(type<0||type>std::numeric_limits<DWORD>::max()||type!=double(DWORD(type))||!v.value("data").isString())return false;
        const auto encoded=v.value("data").toString().toLatin1();const auto bytes=QByteArray::fromBase64(encoded);
        if(bytes.size()>65536||bytes.toBase64()!=encoded)return false;
    }
    return true;
}
LONG writeRegistry(const QJsonObject &values) {
    HKEY key{};auto status=RegOpenKeyExW(HKEY_CURRENT_USER,internetKey,0,KEY_SET_VALUE,&key);
    if(status!=ERROR_SUCCESS)return status;
    for(int i=0;i<4;++i) {
        const auto v=values.value(registryKeys[i]).toObject();
        if(!v.value("present").toBool()) {
            status=RegDeleteValueW(key,registryNames[i]);if(status==ERROR_FILE_NOT_FOUND)status=ERROR_SUCCESS;
        } else {
            const auto bytes=QByteArray::fromBase64(v.value("data").toString().toLatin1());
            status=RegSetValueExW(key,registryNames[i],0,DWORD(v.value("type").toDouble()),reinterpret_cast<const BYTE *>(bytes.constData()),DWORD(bytes.size()));
        }
        if(status!=ERROR_SUCCESS)break;
    }
    RegCloseKey(key);return status;
}
QJsonObject proxyRegistry(const QString &server,const QString &bypass) {
    QJsonObject result;DWORD enabled=1;
    result.insert("ProxyEnable",QJsonObject{{"present",true},{"type",int(REG_DWORD)},{"data",QString::fromLatin1(QByteArray(reinterpret_cast<const char *>(&enabled),sizeof(enabled)).toBase64())}});
    const QString strings[]={server,bypass,QString()};
    for(int i=1;i<4;++i)result.insert(registryKeys[i],QJsonObject{{"present",true},{"type",int(REG_SZ)},
        {"data",QString::fromLatin1(QByteArray(reinterpret_cast<const char *>(strings[i-1].utf16()),(strings[i-1].size()+1)*sizeof(wchar_t)).toBase64())}});
    return result;
}
bool writeConnection(const QJsonObject &value) {
    const auto server=value.value("server").toString(),bypass=value.value("bypass").toString(),pac=value.value("pac").toString();
    INTERNET_PER_CONN_OPTIONW options[4]{};options[0].dwOption=INTERNET_PER_CONN_FLAGS;options[0].Value.dwValue=value.value("flags").toInt();
    options[1].dwOption=INTERNET_PER_CONN_PROXY_SERVER;options[1].Value.pszValue=const_cast<wchar_t *>(reinterpret_cast<const wchar_t *>(server.utf16()));
    options[2].dwOption=INTERNET_PER_CONN_PROXY_BYPASS;options[2].Value.pszValue=const_cast<wchar_t *>(reinterpret_cast<const wchar_t *>(bypass.utf16()));
    options[3].dwOption=INTERNET_PER_CONN_AUTOCONFIG_URL;options[3].Value.pszValue=const_cast<wchar_t *>(reinterpret_cast<const wchar_t *>(pac.utf16()));
    INTERNET_PER_CONN_OPTION_LISTW list{};list.dwSize=sizeof(list);list.dwOptionCount=4;list.pOptions=options;
    return InternetSetOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,sizeof(list));
}
bool notifyProxyChange() {
    const bool changed=InternetSetOptionW(nullptr,INTERNET_OPTION_SETTINGS_CHANGED,nullptr,0);
    const bool refreshed=InternetSetOptionW(nullptr,INTERNET_OPTION_REFRESH,nullptr,0);
    return changed&&refreshed;
}
QString stamp(HANDLE process) {
    FILETIME created{},exit{},kernel{},user{};
    if(!GetProcessTimes(process,&created,&exit,&kernel,&user))return {};
    return QString::number((quint64(created.dwHighDateTime)<<32)|created.dwLowDateTime);
}
bool alive(const QJsonObject &record, const char *key, const char *timeKey) {
    auto h=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(record.value(key).toDouble()));
    // Access denied/query failure is not proof that the GUI/engine died. Be
    // conservative and retain ownership until a process can be proven dead.
    if(!h)return GetLastError()!=ERROR_INVALID_PARAMETER;
    const auto identity=stamp(h);const auto waited=WaitForSingleObject(h,0);
    const bool result=identity.isEmpty()||waited==WAIT_FAILED||(identity==record.value(timeKey).toString()&&waited==WAIT_TIMEOUT);
    CloseHandle(h);return result;
}
QString nativeError() { return QStringLiteral("Windows 系统代理操作失败（错误 %1）。").arg(GetLastError()); }
#endif
bool matchesSettings(QJsonObject current,const QJsonObject &expected) {
    // Schema 1 journals predate registry ownership. Never claim those values.
    if(!expected.contains("registry"))current.remove("registry");
    return current==expected;
}
}
QString SystemProxySession::journalPath() { return SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/system-proxy.dpapi"; }
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
        for(int i=1;i<4;++i){if(options[i].Value.pszValue)GlobalFree(options[i].Value.pszValue);options[i].Value.pszValue=nullptr;}
        options[0].dwOption=INTERNET_PER_CONN_FLAGS;size=sizeof(list);
        if(!InternetQueryOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,&size)){for(int i=1;i<4;++i)if(options[i].Value.pszValue)GlobalFree(options[i].Value.pszValue);if(error)*error=nativeError();return {};}
    }
    QJsonObject result{{"flags",int(options[0].Value.dwValue)}};
    const char *keys[]={"server","bypass","pac"};
    for(int i=1;i<4;++i){result.insert(keys[i-1],QString::fromWCharArray(options[i].Value.pszValue?options[i].Value.pszValue:L""));if(options[i].Value.pszValue)GlobalFree(options[i].Value.pszValue);}
    const auto registry=SystemProxyState::readRegistry(HKEY_CURRENT_USER,internetKey,error);if(registry.isEmpty())return {};
    result.insert("registry",registry);
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
    const auto original=snapshot(error);if(original.isEmpty())return false;
    const auto registry=value.contains("registry")?value.value("registry").toObject():original.value("registry").toObject();
    if(!validRegistry(registry)){if(error)*error=QStringLiteral("代理注册表恢复记录无效。");return false;}
    if(!writeConnection(value)){if(error)*error=nativeError();return false;}
    const auto status=writeRegistry(registry);
    if(status!=ERROR_SUCCESS) {
        // A partial update must not strand native clients on a different port.
        const bool connectionRestored=writeConnection(original);
        const bool registryRestored=writeRegistry(original.value("registry").toObject())==ERROR_SUCCESS;
        notifyProxyChange();
        if(error)*error=QStringLiteral("代理注册表写入失败（错误 %1）；恢复%2。").arg(status).arg(connectionRestored&&registryRestored?QStringLiteral("成功"):QStringLiteral("失败，请检查系统代理"));
        return false;
    }
    // Publish only after both representations agree.
    if(!notifyProxyChange()){if(error)*error=QStringLiteral("代理设置已写入，但 Windows 刷新通知失败；恢复记录已保留。");return false;}
    if(!matchesSettings(snapshot(),value)){if(error)*error=QStringLiteral("Windows 实际代理配置与写入值不一致。");return false;}return true;
#else
    Q_UNUSED(value);if(error)*error=QStringLiteral("系统代理仅支持 Windows。");return false;
#endif
}
bool SystemProxySession::recover(const QString &journal, QString *error, bool requireDeadOwner, const QString &expectedSession) {
    QLockFile lock(journal+".lock");if(!lock.tryLock(1000)){if(error)*error=QStringLiteral("系统代理恢复正在由另一进程处理。");return false;}
    if(!QFile::exists(journal))return true;
    const auto record=read(journal);
    const auto schema=record.value("schema").toInt();
    if(schema!=1&&schema!=2){if(error)*error=QStringLiteral("无法解密代理恢复记录；已保留记录。");return false;}
    if(!expectedSession.isEmpty()&&record.value("session").toString()!=expectedSession)return true;
#ifdef Q_OS_WIN
    if(requireDeadOwner&&alive(record,"owner","ownerTime")){if(error)*error=QStringLiteral("另一个 Swirl 正在管理系统代理。");return false;}
#endif
    const auto current=snapshot(error);if(current.isEmpty())return false;
    if(record.value("applyUnconfirmed").toBool()&&!matchesSettings(current,record.value("applied").toObject())&&!matchesSettings(current,record.value("original").toObject())) {
        if(error)*error=QStringLiteral("代理写入曾中途失败，当前配置既非原始值也非完整接管值；已保留恢复快照，请检查 Windows 代理，未覆盖来源不明的修改。");
        return false;
    }
    if(matchesSettings(current,record.value("applied").toObject())&&!apply(record.value("original").toObject(),error))return false;
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
    QJsonObject applied{{"flags",3},{"server",QStringLiteral("127.0.0.1:%1").arg(port)},
        {"bypass","localhost;127.*;10.*;192.168.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;[::1];<local>"},{"pac",""}};
    #ifdef Q_OS_WIN
    applied.insert("registry",proxyRegistry(applied.value("server").toString(),applied.value("bypass").toString()));
    #endif
    QJsonObject record{{"schema",2},{"session",QUuid::createUuid().toString()},{"owner",double(QCoreApplication::applicationPid())},{"engine",double(enginePid)},{"original",original},{"applied",applied},{"applyUnconfirmed",true}};
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
    if(!apply(applied,&m_error)){
        lock.unlock();const bool recovered=recover(m_journal,nullptr,false,record.value("session").toString());
        if(!recovered&&QFile::exists(m_journal)) {
            // Writes can land before refresh/readback fails. Keep a recoverable
            // owner state instead of discarding the original PAC snapshot.
            m_session=record.value("session").toString();m_owned=true;m_enabled=false;
            m_error+=QStringLiteral(" 当前状态未确认，恢复快照与守护进程已保留；可重试释放代理。");
        }
        emit changed();return false;
    }
    record.insert("applyUnconfirmed",false);
    if(!write(m_journal,record))m_error=QStringLiteral("代理已确认启用，但恢复记录确认标记未能更新；原始快照与守护仍保留。");
    m_session=record.value("session").toString();m_owned=true;m_enabled=true;refresh();emit changed();return true;
}
bool SystemProxySession::disable() {
    if(!m_owned)return true;
    m_error.clear();bool ok=recover(m_journal,&m_error,false,m_session);
    if(ok)m_owned=false;refresh();emit changed();return ok;
}
bool SystemProxySession::turnOffSystemProxy() {
    m_error.clear();
    // Release our recovery lease first. The subsequent explicit off action
    // must not be undone by the old guard restoring another application's proxy.
    if(m_owned&&!disable())return false;
    const auto original=snapshot(&m_error);
    if(original.isEmpty()){emit changed();return false;}
    auto off=original;
    off.insert("flags",1); // PROXY_TYPE_DIRECT: manual, PAC and auto-detect are off.
    off.insert("pac",QString());
#ifdef Q_OS_WIN
    auto registry=original.value("registry").toObject();
    const DWORD disabled=0;
    registry.insert("ProxyEnable",QJsonObject{{"present",true},{"type",int(REG_DWORD)},
        {"data",QString::fromLatin1(QByteArray(reinterpret_cast<const char *>(&disabled),sizeof(disabled)).toBase64())}});
    registry.insert("AutoConfigURL",QJsonObject{{"present",false}});
    off.insert("registry",registry);
#endif
    const bool ok=apply(off,&m_error);
    refresh();emit changed();return ok;
}
void SystemProxySession::refresh() {
    const auto record=read(m_journal);QString readError;const auto current=snapshot(&readError);
    bool observationChanged=m_readError!=readError;m_readError=readError;
    if(!current.isEmpty()) {
        const auto state=SystemProxyState::inspect(current);
        const bool systemEnabled=SystemProxyState::configuredEnabled(current);
        observationChanged=observationChanged||m_systemEnabled!=systemEnabled||m_stateDiffers!=state.differs();
        m_systemEnabled=systemEnabled;m_stateDiffers=state.differs();
    }
    // A transient WinINET read failure is not an external ownership change.
    // Retain the encrypted recovery record so the independent guard can act.
    if(current.isEmpty()||(m_owned&&record.isEmpty()&&QFile::exists(m_journal))) {
        const bool wasEnabled=m_enabled;m_enabled=false;
        if(m_owned)m_error=readError.isEmpty()?QStringLiteral("恢复记录暂时无法读取；接管状态未确认，快照已保留。"):readError;
        if(observationChanged||wasEnabled||m_owned)emit changed();return;
    }
    const bool ownSession=!m_session.isEmpty()&&record.value("session").toString()==m_session;
    const bool same=ownSession&&matchesSettings(current,record.value("applied").toObject());
    if(m_owned&&ownSession&&record.value("applyUnconfirmed").toBool()&&!same&&!matchesSettings(current,record.value("original").toObject())) {
        m_enabled=false;m_error=QStringLiteral("代理部分写入或外部修改的来源尚未确认；恢复快照已保留，请检查 Windows 代理。");emit changed();return;
    }
    if(m_owned&&!same){m_owned=false;if(ownSession)QFile::remove(m_journal);m_error=QStringLiteral("系统代理已由外部修改或安全恢复，Swirl 已放弃控制。");observationChanged=true;}
    const bool enabled=m_owned&&same;
    if(enabled!=m_enabled){m_enabled=enabled;observationChanged=true;}
    if(observationChanged)emit changed();
}
QVariantMap SystemProxySession::diagnosticState() const {
    QString readError;
    auto state=SystemProxyState::inspect(snapshot(&readError)).diagnostics();
    state.insert("swirlEnabled",m_enabled);state.insert("owned",m_owned);
    state.insert("readError",readError);state.insert("recoveryError",m_error);
    const bool journalPresent=QFile::exists(m_journal);
    state.insert("recoveryJournalPresent",journalPresent);
    state.insert("guardAcknowledged",m_owned&&journalPresent&&QFile::exists(m_journal+".ready"));
    return state;
}
int SystemProxySession::guard(const QString &journal) {
#ifdef Q_OS_WIN
    const auto record=read(journal);const auto schema=record.value("schema").toInt();
    if((schema!=1&&schema!=2)||!alive(record,"owner","ownerTime"))return 2;
    auto owner=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(record.value("owner").toDouble()));
    if(!owner)return 3;
    QFile ready(journal+".ready");
    if(!ready.open(QIODevice::WriteOnly)){CloseHandle(owner);return 5;}ready.write("ready");ready.close();
    // Handle GUI death AND engine death. No fixed delay leaves a dead localhost
    // proxy behind while the GUI still appears alive.
    for(;;) {
        const auto snapshot=read(journal);
        if(!QFile::exists(journal)){CloseHandle(owner);QFile::remove(journal+".ready");return 0;}
        if(!snapshot.isEmpty()&&snapshot.value("session")!=record.value("session")){CloseHandle(owner);return 0;}
        const auto waited=WaitForSingleObject(owner,250);
        if(waited==WAIT_FAILED){CloseHandle(owner);return 3;}
        if(waited==WAIT_OBJECT_0||!alive(record,"engine","engineTime"))break;
    }
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

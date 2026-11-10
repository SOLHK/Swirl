#include "GatewayRouting.h"
#include <QJsonDocument>
#include <QFile>
#include <QFileInfo>
#include <QCoreApplication>
#include <QHostAddress>
#include <QRegularExpression>
#ifdef Q_OS_WIN
#include <windows.h>
#endif
bool GatewayRouting::validJournal(const QJsonObject &j) {
    const auto prefix=QHostAddress::parseSubnet(j.value("prefix").toString());
    return j.value("schema").toInt()==1&&QRegularExpression("^SwirlGateway-[0-9a-f]{32}$").match(j.value("name").toString()).hasMatch()
        &&prefix.first.protocol()==QAbstractSocket::IPv4Protocol&&prefix.second>=8&&prefix.second<=30
        &&j.value("lanIndex").toInt()>0&&j.value("tunIndex").toInt()>0&&j.value("lanIndex")!=j.value("tunIndex")
        &&QHostAddress(j.value("gateway").toString()).protocol()==QAbstractSocket::IPv4Protocol
        &&j.value("ownerPid").toDouble()>0&&QRegularExpression("^[0-9]{12,20}$").match(j.value("ownerCreation").toString()).hasMatch();
}
QString GatewayRouting::startScript(const QString &path) {
    Q_UNUSED(path);
    // Schema 1 stores only an interface index and alias in user-writable data.
    // Neither identifies a Windows interface nor proves ownership of a write.
    // New activation belongs exclusively to the elevated native transaction.
    return QStringLiteral("throw 'Legacy gateway activation is unavailable; use the native helper transaction'");
}
QString GatewayRouting::cleanupScript(const QString &path) {
    Q_UNUSED(path);
    // A valid legacy JSON shape is evidence for manual review, not authority
    // to overwrite shared Forwarding flags on a possibly recycled interface.
    return QStringLiteral("throw 'Legacy gateway recovery requires ownership review; the journal has been retained'");
}
void GatewayRouting::prepareProcess(QProcess &process,const QString &script) {
#ifdef Q_OS_WIN
    const auto encoded=QByteArray(reinterpret_cast<const char *>(script.utf16()),script.size()*2).toBase64();
    wchar_t directory[32768];const UINT length=GetSystemDirectoryW(directory,32768);
    process.setProgram(length>0&&length<32768
        ?QString::fromWCharArray(directory,int(length))+"/WindowsPowerShell/v1.0/powershell.exe"
        :QString());
    process.setArguments({"-NoProfile","-NonInteractive","-WindowStyle","Hidden","-EncodedCommand",QString::fromLatin1(encoded)});
    process.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *args){args->flags|=CREATE_NO_WINDOW;});
#else
    Q_UNUSED(process);Q_UNUSED(script);
#endif
}
bool GatewayRouting::cleanup(const QString &path,QString *error) {
    QFile file(path);if(!file.exists())return true;
    if(!file.open(QIODevice::ReadOnly)||file.size()>16384){if(error)*error=QStringLiteral("网关恢复记录无法读取。");return false;}
    const auto object=QJsonDocument::fromJson(file.readAll()).object();file.close();
    if(!validJournal(object)){if(error)*error=QStringLiteral("网关恢复记录无效，未修改系统网络。");return false;}
    if(error)*error=QStringLiteral("旧版网关恢复记录缺少接口 GUID 和可验证的变更所有权，已保留记录；请核验 Windows 接口状态后手动恢复，未自动修改网络。");
    return false;
}
int GatewayRouting::guard(const QString &path) {
#ifdef Q_OS_WIN
    QFile file(path);if(!file.open(QIODevice::ReadOnly)||file.size()>16384)return 2;const auto object=QJsonDocument::fromJson(file.readAll()).object();file.close();if(!validJournal(object))return 3;
    const auto owner=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(object.value("ownerPid").toDouble()));
    if(owner){wchar_t executable[32768];DWORD length=32768;
        if(!QueryFullProcessImageNameW(owner,0,executable,&length)||QFileInfo(QString::fromWCharArray(executable,length)).canonicalFilePath().compare(QFileInfo(QCoreApplication::applicationDirPath()+"/Swirl.exe").canonicalFilePath(),Qt::CaseInsensitive)){CloseHandle(owner);return 4;}
        FILETIME creation{},exit{},kernel{},user{};const bool same=GetProcessTimes(owner,&creation,&exit,&kernel,&user)
            &&QString::number((quint64(creation.dwHighDateTime)<<32)|creation.dwLowDateTime)==object.value("ownerCreation").toString();
        if(same)WaitForSingleObject(owner,INFINITE);CloseHandle(owner);}
    // Wait for an interrupted startup transaction before restoring its snapshot.
    if(file.open(QIODevice::ReadOnly)){const auto latest=QJsonDocument::fromJson(file.readAll()).object();file.close();const auto helperPid=DWORD(latest.value("helperPid").toDouble());if(helperPid){const auto helper=OpenProcess(SYNCHRONIZE,FALSE,helperPid);if(helper){WaitForSingleObject(helper,35000);CloseHandle(helper);}}}
    return cleanup(path)?0:5;
#else
    Q_UNUSED(path);return 2;
#endif
}

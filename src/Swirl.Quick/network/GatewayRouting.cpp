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
namespace {
QString quoted(QString value){return "'"+value.replace("'","''")+"'";}
QString preamble(const QString &path){return QStringLiteral(
    "$ErrorActionPreference='Stop'; function Save-SwirlJournal($journal,$path){ $tmp=$path+'.tmp'; "
    "[IO.File]::WriteAllText($tmp,($journal|ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false)); [IO.File]::Replace($tmp,$path,$null) }; "
    "$j=Get-Content -Raw -LiteralPath %1 | ConvertFrom-Json; "
).arg(quoted(QFileInfo(path).absoluteFilePath()));}
}
bool GatewayRouting::validJournal(const QJsonObject &j) {
    const auto prefix=QHostAddress::parseSubnet(j.value("prefix").toString());
    return j.value("schema").toInt()==1&&QRegularExpression("^SwirlGateway-[0-9a-f]{32}$").match(j.value("name").toString()).hasMatch()
        &&prefix.first.protocol()==QAbstractSocket::IPv4Protocol&&prefix.second>=8&&prefix.second<=30
        &&j.value("lanIndex").toInt()>0&&j.value("tunIndex").toInt()>0&&j.value("lanIndex")!=j.value("tunIndex")
        &&QHostAddress(j.value("gateway").toString()).protocol()==QAbstractSocket::IPv4Protocol
        &&j.value("ownerPid").toDouble()>0&&QRegularExpression("^[0-9]{12,20}$").match(j.value("ownerCreation").toString()).hasMatch();
}
QString GatewayRouting::startScript(const QString &path) {
    return preamble(path)+QStringLiteral(
        "$mutex=New-Object Threading.Mutex($false,('Local\\'+$j.name)); try { $locked=$mutex.WaitOne(30000) } catch [Threading.AbandonedMutexException] { $locked=$true }; if(-not $locked){throw 'Gateway transaction is busy'}; try { "
        "$j=Get-Content -Raw -LiteralPath %1 | ConvertFrom-Json; "
        "$owner=Get-Process -Id $j.ownerPid -ErrorAction Stop; if($owner.StartTime.ToUniversalTime().ToFileTimeUtc().ToString() -ne $j.ownerCreation){throw 'Gateway owner exited'}; "
        "$j | Add-Member -Force -NotePropertyName helperPid -NotePropertyValue $PID; "
        "$lan=Get-NetIPInterface -InterfaceIndex $j.lanIndex -AddressFamily IPv4 -ErrorAction Stop; "
        "$tun=Get-NetIPInterface -InterfaceIndex $j.tunIndex -AddressFamily IPv4 -ErrorAction Stop; "
        "if($tun.InterfaceAlias -ne 'Swirl'){throw 'Selected tunnel is not the Swirl interface'}; "
        "if(-not (Get-NetIPAddress -InterfaceIndex $j.lanIndex -AddressFamily IPv4 | Where-Object IPAddress -EQ $j.gateway)){throw 'LAN interface address changed'}; "
        "$j | Add-Member -Force -NotePropertyName oldLanForwarding -NotePropertyValue ([string]$lan.Forwarding); "
        "$j | Add-Member -Force -NotePropertyName oldTunForwarding -NotePropertyValue ([string]$tun.Forwarding); "
        "$j | Add-Member -Force -NotePropertyName phase -NotePropertyValue 'prepared'; Save-SwirlJournal $j %1; "
        "try { Set-NetIPInterface -InterfaceIndex $j.lanIndex -AddressFamily IPv4 -Forwarding Enabled; "
        "Set-NetIPInterface -InterfaceIndex $j.tunIndex -AddressFamily IPv4 -Forwarding Enabled; "
        "if((Get-NetIPInterface -InterfaceIndex $j.lanIndex -AddressFamily IPv4).Forwarding -ne 'Enabled' -or "
        "(Get-NetIPInterface -InterfaceIndex $j.tunIndex -AddressFamily IPv4).Forwarding -ne 'Enabled'){throw 'IPv4 forwarding did not activate'}; "
        "$j.phase='active'; Save-SwirlJournal $j %1; Write-Output 'Swirl gateway routing active' "
        "} catch { Set-NetIPInterface -InterfaceIndex $j.lanIndex -AddressFamily IPv4 -Forwarding $j.oldLanForwarding; "
        "Set-NetIPInterface -InterfaceIndex $j.tunIndex -AddressFamily IPv4 -Forwarding $j.oldTunForwarding; throw } "
        "} finally { $mutex.ReleaseMutex(); $mutex.Dispose() }"
    ).arg(quoted(QFileInfo(path).absoluteFilePath()));
}
QString GatewayRouting::cleanupScript(const QString &path) {
    return preamble(path)+QStringLiteral(
        "$mutex=New-Object Threading.Mutex($false,('Local\\'+$j.name)); try { $locked=$mutex.WaitOne(30000) } catch [Threading.AbandonedMutexException] { $locked=$true }; if(-not $locked){throw 'Gateway transaction is busy'}; try { "
        "$j=Get-Content -Raw -LiteralPath %1 | ConvertFrom-Json; "
        "if($j.oldLanForwarding -in @('Enabled','Disabled')){ "
        "if(-not (Get-NetIPAddress -InterfaceIndex $j.lanIndex -AddressFamily IPv4 | Where-Object IPAddress -EQ $j.gateway)){throw 'LAN interface changed; forwarding state retained for manual recovery'}; "
        "Set-NetIPInterface -InterfaceIndex $j.lanIndex -AddressFamily IPv4 -Forwarding $j.oldLanForwarding }; "
        "if($j.oldTunForwarding -in @('Enabled','Disabled')){ "
        "$tun=Get-NetIPInterface -InterfaceIndex $j.tunIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue; "
        "if($tun -and $tun.InterfaceAlias -eq 'Swirl'){Set-NetIPInterface -InterfaceIndex $j.tunIndex -AddressFamily IPv4 -Forwarding $j.oldTunForwarding} }; "
        "Remove-Item -LiteralPath %1 -Force } finally { $mutex.ReleaseMutex(); $mutex.Dispose() }"
    ).arg(quoted(QFileInfo(path).absoluteFilePath()));
}
void GatewayRouting::prepareProcess(QProcess &process,const QString &script) {
#ifdef Q_OS_WIN
    const auto encoded=QByteArray(reinterpret_cast<const char *>(script.utf16()),script.size()*2).toBase64();
    process.setProgram(qEnvironmentVariable("SystemRoot")+"/System32/WindowsPowerShell/v1.0/powershell.exe");
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
#ifdef Q_OS_WIN
    QProcess process;prepareProcess(process,cleanupScript(path));process.start();
    if(!process.waitForStarted(3000)||!process.waitForFinished(45000)||process.exitCode()!=0){if(process.state()!=QProcess::NotRunning){process.kill();process.waitForFinished(2000);}if(error)*error=QStringLiteral("Windows 网关恢复失败：")+QString::fromUtf8(process.readAllStandardError().left(2048));return false;}
    return !QFileInfo::exists(path);
#else
    if(error)*error=QStringLiteral("网关路由需要 Windows。");return false;
#endif
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

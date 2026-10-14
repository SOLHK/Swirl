#include "ExtensionService.h"
#include "engine/EngineController.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSaveFile>
#include <QStandardPaths>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QJsonParseError>
#include <QUuid>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif
namespace {
QByteArray protect(QByteArray bytes,bool decrypt){
#ifdef Q_OS_WIN
    DATA_BLOB input{DWORD(bytes.size()),reinterpret_cast<BYTE *>(bytes.data())},output{};
    const bool ok=decrypt?CryptUnprotectData(&input,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output):CryptProtectData(&input,L"Swirl local extensions",nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output);
    if(!ok)return {};QByteArray result(reinterpret_cast<const char *>(output.pbData),output.cbData);SecureZeroMemory(output.pbData,output.cbData);LocalFree(output.pbData);return result;
#else
    Q_UNUSED(bytes);Q_UNUSED(decrypt);return {};
#endif
}
bool enabled(const QVariantList &rows){for(const auto &row:rows)if(row.toMap().value("enabled").toBool())return true;return false;}
}
ExtensionService::ExtensionService(EngineController *engine,QString path,QObject *parent):QObject(parent),m_engine(engine),m_path(std::move(path)){
    if(m_path.isEmpty())m_path=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/extensions.dpapi";load();
    // Complete the durable intent before exposing a configuration after a crash.
    if(m_configurationPending)finishConfigurationTransaction();
    else if(enabled(m_modules)&&m_baseCaptured){if(!m_engine->replaceNetworkConfiguration(merged(m_modules,m_base)))m_error=m_engine->networkConfigurationError();}
    m_engine->setModuleOverlayActive(m_baseCaptured||m_configurationPending);
    m_timeout.setSingleShot(true);connect(&m_timeout,&QTimer::timeout,this,[this]{m_timedOut=true;m_process.kill();});
#ifdef Q_OS_WIN
    m_process.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *arguments){arguments->flags|=CREATE_NO_WINDOW;});
#endif
    connect(&m_process,&QProcess::started,this,[this]{
#ifdef Q_OS_WIN
        const auto job=CreateJobObjectW(nullptr,nullptr);JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        const auto process=OpenProcess(PROCESS_SET_QUOTA|PROCESS_TERMINATE,FALSE,DWORD(m_process.processId()));
        if(!job||!process||!SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limits,sizeof(limits))||!AssignProcessToJobObject(job,process)){if(job)CloseHandle(job);m_error=QStringLiteral("无法建立脚本进程生命周期约束。");m_process.kill();}
        else m_workerJob=job;if(process)CloseHandle(process);
#endif
        emit changed();
    });
    connect(&m_process,&QProcess::readyReadStandardOutput,this,[this]{m_stdout+=m_process.readAllStandardOutput();if(m_stdout.size()>64*1024){m_outputExceeded=true;m_process.kill();}});
    connect(&m_process,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart){m_timeout.stop();fail(QStringLiteral("本地脚本运行器无法启动，请修复安装。"));}});
    connect(&m_process,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus){m_timeout.stop();m_stdout+=m_process.readAllStandardOutput();
#ifdef Q_OS_WIN
        if(m_workerJob){CloseHandle(HANDLE(m_workerJob));m_workerJob=nullptr;}
#endif
        QJsonParseError parse;const auto result=QJsonDocument::fromJson(m_stdout,&parse).object();
        if(m_timedOut)m_error=QStringLiteral("脚本超过 5 秒，已终止独立运行进程。");else if(m_outputExceeded||code==4)m_error=QStringLiteral("脚本输出超过 64 KB。");
        else if(code!=0||parse.error!=QJsonParseError::NoError||!result.value("ok").toBool())m_error=result.value("error").toString(QStringLiteral("脚本执行失败或触及资源限制。"));
        else {m_error.clear();m_output=QString::fromUtf8(QJsonDocument(QJsonObject{{"result",result.value("result")},{"logs",result.value("logs")}}).toJson(QJsonDocument::Indented));}emit changed();});
}
ExtensionService::~ExtensionService(){m_timeout.stop();if(busy()){m_process.kill();m_process.waitForFinished(2000);}
#ifdef Q_OS_WIN
    if(m_workerJob)CloseHandle(HANDLE(m_workerJob));
#endif
}
bool ExtensionService::fail(const QString &error){m_error=error;emit changed();return false;}
bool ExtensionService::persist(){
    if(!m_storageReadable)return fail(QStringLiteral("扩展库读取失败，已保留原文件，请先恢复有效备份。"));
    const auto plain=QJsonDocument(QJsonObject{{"schema",1},{"configurationPending",m_configurationPending},{"pendingConfiguration",QJsonObject::fromVariantMap(m_pendingConfiguration)},{"pendingMode",m_pendingMode},{"profiles",QJsonArray::fromVariantList(m_profiles)},{"activeProfile",m_activeProfile},{"profileBase",QJsonObject::fromVariantMap(m_profileBase)},{"profileBaseMode",m_profileBaseMode},{"scripts",QJsonArray::fromVariantList(m_scripts)},{"modules",QJsonArray::fromVariantList(m_modules)},{"base",QJsonObject::fromVariantMap(m_base)},{"baseCaptured",m_baseCaptured}}).toJson(QJsonDocument::Compact);
    if(plain.size()>4*1024*1024)return fail(QStringLiteral("本地扩展库超过 4 MB。"));const auto encrypted=protect(plain,false);if(encrypted.isEmpty())return fail(QStringLiteral("无法保护本地脚本和模块配置。"));
    QDir().mkpath(QFileInfo(m_path).absolutePath());QSaveFile file(m_path);const auto bytes=QByteArray("SWIRLEXT1\n")+encrypted;
    if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit())return fail(QStringLiteral("本地扩展库保存失败。"));return true;
}
void ExtensionService::load(){QFile file(m_path);if(!file.exists())return;if(!file.open(QIODevice::ReadOnly)||file.size()>5*1024*1024){m_storageReadable=false;fail(QStringLiteral("本地扩展库无法读取。"));return;}
    const auto bytes=file.readAll();if(!bytes.startsWith("SWIRLEXT1\n")){m_storageReadable=false;fail(QStringLiteral("本地扩展库格式无效。"));return;}const auto object=QJsonDocument::fromJson(protect(bytes.mid(10),true)).object();
    if(object.value("schema").toInt()!=1||!object.value("scripts").isArray()||!object.value("modules").isArray()||object.value("scripts").toArray().size()>100||object.value("modules").toArray().size()>100||object.value("profiles").toArray().size()>100){m_storageReadable=false;fail(QStringLiteral("本地扩展库损坏或无法解密。"));return;}
    m_configurationPending=object.value("configurationPending").toBool();m_pendingConfiguration=object.value("pendingConfiguration").toObject().toVariantMap();m_pendingMode=object.value("pendingMode").toString();
    m_profiles=object.value("profiles").toArray().toVariantList();m_activeProfile=object.value("activeProfile").toString();m_profileBase=object.value("profileBase").toObject().toVariantMap();m_profileBaseMode=object.value("profileBaseMode").toString("rule");m_scripts=object.value("scripts").toArray().toVariantList();m_modules=object.value("modules").toArray().toVariantList();m_base=object.value("base").toObject().toVariantMap();m_baseCaptured=object.value("baseCaptured").toBool();}
bool ExtensionService::saveScript(const QString &id,const QString &name,const QString &source){
    if(busy())return fail(QStringLiteral("请等待脚本执行结束。"));if(name.trimmed().isEmpty()||name.size()>100||source.toUtf8().size()>256*1024)return fail(QStringLiteral("脚本需要名称，源码不能超过 256 KB。"));
    const auto before=m_scripts;auto row=QVariantMap{{"id",id.isEmpty()?QUuid::createUuid().toString(QUuid::WithoutBraces):id},{"name",name.trimmed()},{"source",source},{"type","本地 JavaScript"}};int position=-1;
    for(const auto &existing:m_scripts)if(existing.toMap().value("id")!=id&&existing.toMap().value("name").toString().compare(name.trimmed(),Qt::CaseInsensitive)==0)return fail(QStringLiteral("脚本名称已存在，请使用其他名称。"));
    for(int i=0;i<m_scripts.size();++i)if(m_scripts[i].toMap().value("id")==id)position=i;
    if(position>=0)m_scripts[position]=row;else {if(m_scripts.size()>=100)return fail(QStringLiteral("最多保存 100 个脚本。"));m_scripts.append(row);}
    if(!persist()){m_scripts=before;return false;}m_error.clear();emit changed();return true;
}
bool ExtensionService::importScript(const QUrl &source){QFile file(source.toLocalFile());if(!source.isLocalFile()||!file.open(QIODevice::ReadOnly)||file.size()>256*1024)return fail(QStringLiteral("请选择不超过 256 KB 的本地 JavaScript 文件。"));return saveScript({},QFileInfo(file.fileName()).completeBaseName(),QString::fromUtf8(file.readAll()));}
bool ExtensionService::removeScript(const QString &id){if(busy())return fail(QStringLiteral("请等待脚本执行结束。"));const auto before=m_scripts;for(int i=m_scripts.size()-1;i>=0;--i)if(m_scripts[i].toMap().value("id")==id)m_scripts.removeAt(i);if(!persist()){m_scripts=before;return false;}m_error.clear();emit changed();return true;}
bool ExtensionService::runScript(const QString &id,const QString &json){if(busy())return fail(QStringLiteral("已有脚本正在执行。"));QJsonParseError parse;const auto input=QJsonDocument::fromJson(json.toUtf8(),&parse);if(parse.error!=QJsonParseError::NoError||json.toUtf8().size()>64*1024)return fail(QStringLiteral("输入需要不超过 64 KB 的 JSON 对象或数组。"));
    QVariantMap selected;for(const auto &row:m_scripts)if(row.toMap().value("id")==id)selected=row.toMap();if(selected.isEmpty())return fail(QStringLiteral("请选择一个已保存脚本。"));
    m_error.clear();m_output.clear();m_stdout.clear();m_timedOut=false;m_outputExceeded=false;
    m_process.setProgram(QCoreApplication::applicationDirPath()+"/SwirlScriptRunner.exe");m_process.start();
    const auto bytes=QJsonDocument(QJsonObject{{"source",selected.value("source").toString()},{"input",input.isObject()?QJsonValue(input.object()):QJsonValue(input.array())}}).toJson(QJsonDocument::Compact);
    m_process.write(bytes);m_process.closeWriteChannel();m_timeout.start(5000);emit changed();return true;
}
QVariantMap ExtensionService::merged(const QVariantList &modules,const QVariantMap &base) const {auto result=base;for(const auto &entry:modules){const auto module=entry.toMap();if(!module.value("enabled").toBool())continue;const auto overrides=module.value("overrides").toMap();for(auto it=overrides.cbegin();it!=overrides.cend();++it)result[it.key()]=it.value();}return result;}
bool ExtensionService::finishConfigurationTransaction(){
    if(!m_configurationPending)return true;
    if(!m_pendingMode.isEmpty()&&!QStringList{"rule","global","direct"}.contains(m_pendingMode))return fail(QStringLiteral("配置恢复记录中的出站模式无效。"));
    if(!m_engine->replaceNetworkConfiguration(m_pendingConfiguration))return fail(m_engine->networkConfigurationError());
    if(!m_pendingMode.isEmpty())m_engine->setRoutingMode(m_pendingMode);
    m_configurationPending=false;
    if(!persist()){m_configurationPending=true;return false;}
    m_pendingConfiguration.clear();m_pendingMode.clear();
    m_engine->setModuleOverlayActive(m_baseCaptured);return true;
}
bool ExtensionService::applyModules(const QVariantList &next){if(!m_engine->canStart())return fail(QStringLiteral("请先断开引擎，再改变配置模块。"));const auto base=m_baseCaptured?m_base:m_engine->networkConfigurationSnapshot();const auto desired=merged(next,base);QVariantMap canonical;if(!m_engine->validateNetworkConfiguration(desired,&canonical))return fail(m_engine->networkConfigurationError());
    if(m_configurationPending)return fail(QStringLiteral("上次配置切换尚未完成，请重新启动以恢复。"));
    const auto oldModules=m_modules;const auto oldBase=m_base;const bool oldCaptured=m_baseCaptured;m_modules=next;m_baseCaptured=enabled(next);m_base=m_baseCaptured?base:QVariantMap();
    m_pendingConfiguration=canonical;m_pendingMode.clear();m_configurationPending=true;
    if(!persist()){m_modules=oldModules;m_base=oldBase;m_baseCaptured=oldCaptured;m_configurationPending=false;m_pendingConfiguration.clear();return false;}
    if(!finishConfigurationTransaction()){m_engine->setModuleOverlayActive(true);emit changed();return false;}
    m_engine->setModuleOverlayActive(m_baseCaptured);m_error.clear();emit changed();return true;
}
bool ExtensionService::importModule(const QUrl &source){QFile file(source.toLocalFile());if(!source.isLocalFile()||!file.open(QIODevice::ReadOnly)||file.size()>1024*1024)return fail(QStringLiteral("请选择不超过 1 MB 的 Swirl 模块 JSON 文件。"));QJsonParseError parse;auto object=QJsonDocument::fromJson(file.readAll(),&parse).object();
    if(parse.error!=QJsonParseError::NoError||object.value("schema").toInt()!=1||object.value("kind")!="swirl-module"||object.value("name").toString().trimmed().isEmpty()||object.value("name").toString().size()>100||!object.value("overrides").isObject()||object.value("overrides").toObject().isEmpty())return fail(QStringLiteral("文件需要 schema=1、kind=swirl-module、name 和 overrides。"));
    QVariantMap candidate=m_engine->networkConfigurationSnapshot();const auto overrides=object.value("overrides").toObject().toVariantMap();for(auto it=overrides.cbegin();it!=overrides.cend();++it)candidate[it.key()]=it.value();if(!m_engine->validateNetworkConfiguration(candidate))return fail(m_engine->networkConfigurationError());
    if(m_modules.size()>=100)return fail(QStringLiteral("最多安装 100 个模块。"));const auto before=m_modules;m_modules.append(QVariantMap{{"id",QUuid::createUuid().toString(QUuid::WithoutBraces)},{"name",object.value("name").toString()},{"description",object.value("description").toString().left(1000)},{"enabled",false},{"overrides",overrides}});
    if(!persist()){m_modules=before;return false;}m_error.clear();emit changed();return true;}
bool ExtensionService::setModuleEnabled(const QString &id,bool active){auto next=m_modules;for(auto &entry:next){auto row=entry.toMap();if(row.value("id")==id){row["enabled"]=active;entry=row;return applyModules(next);}}return fail(QStringLiteral("模块不存在。"));}
bool ExtensionService::moveModule(const QString &id,int step){auto next=m_modules;for(int i=0;i<next.size();++i)if(next[i].toMap().value("id")==id){const int target=i+(step<0?-1:1);if(target<0||target>=next.size())return false;next.swapItemsAt(i,target);return applyModules(next);}return false;}
bool ExtensionService::removeModule(const QString &id){auto next=m_modules;for(int i=next.size()-1;i>=0;--i)if(next[i].toMap().value("id")==id)next.removeAt(i);return applyModules(next);}

QString ExtensionService::profileName() const {for(const auto &value:m_profiles)if(value.toMap().value("id")==m_activeProfile)return value.toMap().value("name").toString();return QStringLiteral("Default");}
bool ExtensionService::saveProfile(const QString &id,const QString &name,const QString &json,const QString &mode){
    if(name.trimmed().isEmpty()||name.size()>100||json.toUtf8().size()>1024*1024||!QStringList{"rule","global","direct"}.contains(mode))return fail(QStringLiteral("配置名称、出站模式或配置长度无效。"));
    QJsonParseError parse;const auto document=QJsonDocument::fromJson(json.toUtf8(),&parse);QVariantMap canonical;
    if(parse.error!=QJsonParseError::NoError||!document.isObject())return fail(QStringLiteral("网络配置需要有效的 JSON 对象。"));
    if(!m_engine->validateNetworkConfiguration(document.object().toVariantMap(),&canonical))return fail(m_engine->networkConfigurationError());
    const auto before=m_profiles;QVariantMap row{{"id",id.isEmpty()?QUuid::createUuid().toString(QUuid::WithoutBraces):id},{"name",name.trimmed()},{"network",canonical},{"mode",mode}};int position=-1;
    for(int i=0;i<m_profiles.size();++i)if(m_profiles[i].toMap().value("id")==id)position=i;
    if(position>=0)m_profiles[position]=row;else {if(m_profiles.size()>=100)return fail(QStringLiteral("最多保存 100 个配置。"));m_profiles.append(row);}
    if(!persist()){m_profiles=before;return false;}m_error.clear();emit changed();return true;
}
bool ExtensionService::importProfile(const QUrl &source){QFile file(source.toLocalFile());if(!source.isLocalFile()||!file.open(QIODevice::ReadOnly)||file.size()>1024*1024)return fail(QStringLiteral("请选择不超过 1 MB 的本地配置 JSON 文件。"));const auto object=QJsonDocument::fromJson(file.readAll()).object();
    if(object.value("schema").toInt()!=1||object.value("kind")!="swirl-profile"||!object.value("network").isObject())return fail(QStringLiteral("文件需要 schema=1、kind=swirl-profile 和 network。"));
    return saveProfile({},object.value("name").toString(),QString::fromUtf8(QJsonDocument(object.value("network").toObject()).toJson()),object.value("mode").toString("rule"));}
bool ExtensionService::exportProfile(const QString &id,const QUrl &destination){if(!destination.isLocalFile())return false;QVariantMap selected;for(const auto &value:m_profiles)if(value.toMap().value("id")==id)selected=value.toMap();if(selected.isEmpty())return fail(QStringLiteral("请选择一个保存的配置。"));
    selected.remove("id");selected["schema"]=1;selected["kind"]="swirl-profile";QSaveFile file(destination.toLocalFile());const auto bytes=QJsonDocument(QJsonObject::fromVariantMap(selected)).toJson(QJsonDocument::Indented);
    if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit())return fail(QStringLiteral("配置导出失败。"));m_error.clear();emit changed();return true;}
bool ExtensionService::useProfile(const QString &id){if(m_baseCaptured)return fail(QStringLiteral("请先停用配置模块，再切换基础配置。"));if(!m_engine->canStart())return fail(QStringLiteral("请先断开引擎，再切换配置。"));
    if(m_configurationPending)return fail(QStringLiteral("上次配置切换尚未完成，请重新启动以恢复。"));
    QVariantMap selected;for(const auto &value:m_profiles)if(value.toMap().value("id")==id)selected=value.toMap();if(!id.isEmpty()&&selected.isEmpty())return fail(QStringLiteral("配置不存在。"));
    if(id.isEmpty()&&m_activeProfile.isEmpty())return true;const auto before=m_engine->networkConfigurationSnapshot();const auto oldMode=m_engine->routingMode();const auto oldId=m_activeProfile;const auto oldBase=m_profileBase;const auto oldBaseMode=m_profileBaseMode;
    const auto next=id.isEmpty()?m_profileBase:selected.value("network").toMap();const auto mode=id.isEmpty()?m_profileBaseMode:selected.value("mode").toString();if(m_engine->meteredEnabled()&&mode!="rule")return fail(QStringLiteral("请先关闭计费网络模式，再切换到其他出站模式。"));
    QVariantMap canonical;if(!m_engine->validateNetworkConfiguration(next,&canonical))return fail(m_engine->networkConfigurationError());
    if(m_activeProfile.isEmpty()){m_profileBase=before;m_profileBaseMode=oldMode;}m_activeProfile=id;if(id.isEmpty())m_profileBase.clear();
    m_pendingConfiguration=canonical;m_pendingMode=mode;m_configurationPending=true;
    if(!persist()){m_activeProfile=oldId;m_profileBase=oldBase;m_profileBaseMode=oldBaseMode;m_configurationPending=false;m_pendingConfiguration.clear();m_pendingMode.clear();return false;}
    if(!finishConfigurationTransaction()){m_engine->setModuleOverlayActive(true);emit changed();return false;}m_error.clear();emit changed();return true;}
bool ExtensionService::removeProfile(const QString &id){if(id==m_activeProfile)return fail(QStringLiteral("请先切换到 Default 或其他配置，再移除当前配置。"));const auto before=m_profiles;for(int i=m_profiles.size()-1;i>=0;--i)if(m_profiles[i].toMap().value("id")==id)m_profiles.removeAt(i);if(!persist()){m_profiles=before;return false;}m_error.clear();emit changed();return true;}

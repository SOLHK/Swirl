#include "DiagnosticService.h"
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include "StoragePaths.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QRegularExpression>
#include <QDataStream>
#include <QSysInfo>
#include <QUuid>
#include <QMutexLocker>
#include <QFileInfo>
#include <cstdio>
#include <functional>
#include <exception>
#include <cstdlib>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif
namespace {
DiagnosticService *active=nullptr;
#ifdef Q_OS_WIN
wchar_t crashPath[32768]{};
void recordTerminate(){
 HANDLE file=CreateFileW(crashPath,FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
 if(file!=INVALID_HANDLE_VALUE){const char message[]="Unhandled C++ exception or std::terminate\r\n";DWORD written;WriteFile(file,message,sizeof(message)-1,&written,nullptr);CloseHandle(file);}std::abort();
}
LONG WINAPI recordCrash(EXCEPTION_POINTERS *exception){
 HANDLE file=CreateFileW(crashPath,FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
 if(file!=INVALID_HANDLE_VALUE){char message[80]{};const auto n=snprintf(message,sizeof(message),"Unhandled Windows exception: 0x%08lx\r\n",exception->ExceptionRecord->ExceptionCode);DWORD written;WriteFile(file,message,n,&written,nullptr);CloseHandle(file);}return EXCEPTION_CONTINUE_SEARCH;
}
#endif
void qtHandler(QtMsgType type,const QMessageLogContext &context,const QString &message){
 if(!active)return;active->record(type==QtFatalMsg||type==QtCriticalMsg?"ERROR":type==QtWarningMsg?"WARN":type==QtDebugMsg?"DEBUG":"INFO",context.category?QString::fromUtf8(context.category):QStringLiteral("Qt"),"QtMessage",message);
}
quint32 crc32(const QByteArray &bytes){quint32 crc=0xffffffff;for(const auto byte:bytes){crc^=quint8(byte);for(int n=0;n<8;++n)crc=(crc>>1)^(0xedb88320u&quint32(-int(crc&1)));}return crc^0xffffffff;}
QByteArray makeZip(const QList<QPair<QByteArray,QByteArray>> &files){
 QByteArray zip,central;QDataStream out(&zip,QIODevice::WriteOnly),directory(&central,QIODevice::WriteOnly);out.setByteOrder(QDataStream::LittleEndian);directory.setByteOrder(QDataStream::LittleEndian);
 for(const auto &file:files){const auto name=file.first,data=file.second;const auto crc=crc32(data);const auto offset=quint32(zip.size());out<<quint32(0x04034b50)<<quint16(20)<<quint16(0)<<quint16(0)<<quint16(0)<<quint16(0)<<crc<<quint32(data.size())<<quint32(data.size())<<quint16(name.size())<<quint16(0);out.writeRawData(name.data(),name.size());out.writeRawData(data.data(),data.size());directory<<quint32(0x02014b50)<<quint16(20)<<quint16(20)<<quint16(0)<<quint16(0)<<quint16(0)<<quint16(0)<<crc<<quint32(data.size())<<quint32(data.size())<<quint16(name.size())<<quint16(0)<<quint16(0)<<quint16(0)<<quint16(0)<<quint32(0)<<offset;directory.writeRawData(name.data(),name.size());}
 const auto offset=quint32(zip.size());out.writeRawData(central.data(),central.size());out<<quint32(0x06054b50)<<quint16(0)<<quint16(0)<<quint16(files.size())<<quint16(files.size())<<quint32(central.size())<<offset<<quint16(0);return zip;
}
}
DiagnosticService::DiagnosticService(QString directory,QObject *parent):QObject(parent),m_directory(directory){
 if(m_directory.isEmpty())m_directory=SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/diagnostics";QDir().mkpath(m_directory);
 // The last append can take a rotated file slightly beyond 1 MiB.
 QFile recent(m_directory+"/events.jsonl");if(recent.open(QIODevice::ReadOnly)&&recent.size()<=2*1024*1024){for(const auto &line:recent.readAll().split('\n')){auto row=QJsonDocument::fromJson(line).object();if(row.isEmpty())continue;
  if(row.value("source")=="Diagnostics"&&row.value("code")=="EventsCleared"){m_records.clear();m_events=0;continue;}
  m_records.prepend(row.toVariantMap());if(QStringList{"INFO","WARN","ERROR"}.contains(row.value("level").toString()))m_events=qMin(500,m_events+1);if(row.value("source")=="Diagnostics"&&row.value("code")=="EventsAcknowledged")m_events=0;while(m_records.size()>500)m_records.removeLast();}}
}
DiagnosticService::~DiagnosticService(){if(active==this){qInstallMessageHandler(nullptr);active=nullptr;}}
QString DiagnosticService::redact(QString text){
 text=text.left(8192);
 text.replace(QRegularExpression("-----BEGIN [^-]*PRIVATE KEY-----[\\s\\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)"),"[private key removed]");
 text.replace(QRegularExpression("[A-Za-z][A-Za-z0-9+.-]*://[^\\s\\\"<>]+"),"[URL removed]");
 text.replace(QRegularExpression("(authorization|cookie|set-cookie)\\s*[:=]\\s*[^\\r\\n]+",QRegularExpression::CaseInsensitiveOption),"\\1: [removed]");
 text.replace(QRegularExpression("[\\\"']?(?:user(?:name)?|password|passwd|passphrase|token|secret|uuid|psk|auth(?:entication)?(?:[-_]?str)?|short[-_]?id|api[-_]?key|private[-_]?key(?:[-_]?passphrase)?|pre[-_]?shared[-_]?key|subscription)[\\\"']?\\s*[:=]\\s*(?:\\\"[^\\\"]*\\\"|'[^']*'|[^,;\\s}]+)",QRegularExpression::CaseInsensitiveOption),"[credential removed]");
 text.replace(QRegularExpression("\\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\\b",QRegularExpression::CaseInsensitiveOption),"[UUID removed]");
 text.replace(QRegularExpression("\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b"),"[IP removed]");
 text.replace(QRegularExpression("\\b[0-9a-f]{0,4}:[0-9a-f:]{2,}\\b",QRegularExpression::CaseInsensitiveOption),"[IP removed]");
 text.replace(QRegularExpression("[A-Za-z]:[\\\\/][^\\r\\n\\\"]*"),"[local path removed]");
 text.replace(QRegularExpression("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b"),"[email removed]");
 // Bare DNS names in TLS/network errors are browsing metadata too.
 text.replace(QRegularExpression("(?:[\\p{L}\\p{M}\\p{N}-]+\\.)+[\\p{L}]{2,63}"),"[hostname removed]");
 text.replace(QRegularExpression("\\b[A-Za-z0-9_-]{32,}={0,2}\\b"),"[opaque value removed]");
 return text;
}
void DiagnosticService::record(const QString &level,const QString &module,const QString &code,const QString &message,const QString &correlation){
 const auto row=QVariantMap{{"time",QDateTime::currentDateTime().toString(Qt::ISODateWithMs)},{"level",level},{"source",redact(module)},{"code",redact(code)},{"correlation",correlation.isEmpty()?QUuid::createUuid().toString(QUuid::Id128).left(12):redact(correlation)},{"message",redact(message)}};
 {QMutexLocker lock(&m_mutex);
  // Serialize clear/acknowledge with producers, including their durable marker.
  if(module=="Diagnostics"&&code=="EventsCleared"){m_records.clear();m_events=0;}
  else {m_records.prepend(row);while(m_records.size()>500)m_records.removeLast();if(level=="INFO"||level=="WARN"||level=="ERROR")m_events=qMin(500,m_events+1);if(module=="Diagnostics"&&code=="EventsAcknowledged")m_events=0;}
  const auto path=m_directory+"/events.jsonl";if(QFileInfo(path).size()>1024*1024){QFile::remove(path+".3");for(int n=2;n>=1;--n)QFile::rename(path+"."+QString::number(n),path+"."+QString::number(n+1));QFile::rename(path,path+".1");}
  QFile file(path);if(file.open(QIODevice::WriteOnly|QIODevice::Append)){file.write(QJsonDocument(QJsonObject::fromVariantMap(row)).toJson(QJsonDocument::Compact));file.write("\n");}
 }emit changed();
}
QVariantList DiagnosticService::records() const {QMutexLocker lock(&m_mutex);return m_records;}
int DiagnosticService::eventCount() const {QMutexLocker lock(&m_mutex);return m_events;}
void DiagnosticService::acknowledge(){record("INFO","Diagnostics","EventsAcknowledged","已将当前事件标记为已读");}
void DiagnosticService::clearView(){record("INFO","Diagnostics","EventsCleared","已清空事件列表与未读计数");}
void DiagnosticService::installQtHandler(){active=this;qInstallMessageHandler(qtHandler);
#ifdef Q_OS_WIN
 const auto path=QDir::toNativeSeparators(m_directory+"/crash-code.txt").left(32767);path.toWCharArray(crashPath);crashPath[path.size()]=0;SetUnhandledExceptionFilter(recordCrash);std::set_terminate(recordTerminate);
#endif
}
bool DiagnosticService::exportReport(const QUrl &file,const QVariantMap &snapshot){
 if(!file.isLocalFile()||!file.host().isEmpty()||file.toLocalFile().startsWith("\\\\")){m_exportMessage="请选择本机 ZIP 文件";emit changed();return false;}
 QList<QPair<QByteArray,QByteArray>> entries;QByteArray logs;
 for(const auto &row:records()){auto safe=row.toMap();safe["message"]=redact(safe.value("message").toString());logs+=QJsonDocument(QJsonObject::fromVariantMap(safe)).toJson(QJsonDocument::Compact)+"\n";}
 entries.append({"logs.jsonl",logs});
 // Snapshot is constructed from an allowlist; it includes the Swirl.exe path,
 // hash, build SHA, actual engine and PID, but no node or credential fields.
 auto environment=QJsonObject{{"version",QCoreApplication::applicationVersion()},{"qt",qVersion()},{"os",QSysInfo::prettyProductName()},{"architecture",QSysInfo::currentCpuArchitecture()},{"created",QDateTime::currentDateTime().toString(Qt::ISODate)}};
 entries.append({"environment.json",QJsonDocument(environment).toJson()});
 const auto sourceSha=snapshot.value("sourceSha").toString(),binarySha=snapshot.value("executableSha256").toString();
 const auto engine=snapshot.value("actualEngineType").toString();
 const auto isHex=[](const QString &value,int length){return value.size()==length&&QRegularExpression(QStringLiteral("^[0-9a-fA-F]+$")).match(value).hasMatch();};
 const auto actualEngine=QStringList{"rust","compatibility","native","not-running"}.contains(engine)?engine:QStringLiteral("unknown");
 const QJsonObject identity{{"sourceSha",isHex(sourceSha,40)?sourceSha:QStringLiteral("source-archive")},
  {"executablePath",QCoreApplication::applicationFilePath()},{"executableSha256",isHex(binarySha,64)?binarySha:QString()},
  {"actualEngineType",actualEngine},{"engineProcessId",snapshot.value("engineProcessId").toString().toLongLong()}};
 entries.append({"identity.json",QJsonDocument(identity).toJson()});
 std::function<QVariant(const QVariant &)> sanitize=[&](const QVariant &value)->QVariant {
  if(value.metaType().id()==QMetaType::QString)return redact(value.toString());
  if(value.metaType().id()==QMetaType::QVariantMap){auto map=value.toMap();for(auto it=map.begin();it!=map.end();++it)it.value()=sanitize(it.value());return map;}
  if(value.metaType().id()==QMetaType::QVariantList){auto list=value.toList();for(auto &v:list)v=sanitize(v);return list;}return value;
 };
 entries.append({"state.json",QJsonDocument(QJsonObject::fromVariantMap(sanitize(snapshot).toMap())).toJson()});
 QFile crash(m_directory+"/crash-code.txt");if(crash.open(QIODevice::ReadOnly))entries.append({"crash-code.txt",crash.read(4096)});
 entries.append({"README.txt",QStringLiteral("本报告仅包含 Swirl 可观测状态与已脱敏的诊断事件。没有节点配置、订阅地址、凭据、原始连接、Cookie 或请求正文。不会自动上传。日志轮转上限约 4 MiB。\n").toUtf8()});
 QSaveFile output(file.toLocalFile());const auto bytes=makeZip(entries);const bool ok=output.open(QIODevice::WriteOnly)&&output.write(bytes)==bytes.size()&&output.commit();m_exportMessage=ok?"诊断报告已保存":"诊断报告保存失败";emit changed();return ok;
}

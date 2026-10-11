#include "ModuleDraftStore.h"
#include <QDir>
#include <QSettings>
#include <QStandardPaths>
#include <QSaveFile>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
ModuleDraftStore::ModuleDraftStore(QObject *parent):QObject(parent) {
    m_path=QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation)+"/Swirl/qt-ui/module-drafts.ini";
}
bool ModuleDraftStore::fail(const QString &message) {m_error=message;emit errorChanged();return false;}
QVariantMap ModuleDraftStore::load(const QString &id) const {
    QSettings settings(m_path,QSettings::IniFormat);
    return QJsonDocument::fromJson(settings.value(id).toByteArray()).object().toVariantMap();
}
bool ModuleDraftStore::save(const QString &id,const QVariantMap &draft) {
    if(!id.startsWith("feature-")||id.contains('/')||id.contains('\\'))return fail("无效的模块标识");
    const auto data=QJsonDocument::fromVariant(draft).toJson(QJsonDocument::Compact);
    if(data.size()>1024*1024)return fail("草稿超过 1 MB 上限");
    QDir().mkpath(QFileInfo(m_path).absolutePath());
    QSettings settings(m_path,QSettings::IniFormat);settings.setValue(id,data);settings.sync();
    if(settings.status()!=QSettings::NoError)return fail("无法保存模块草稿");
    m_error.clear();emit errorChanged();return true;
}
bool ModuleDraftStore::exportFile(const QUrl &url,const QString &id,const QVariantMap &draft) {
    if(!url.isLocalFile())return fail("请选择本地文件");
    QJsonObject object{{"format","Swirl UI draft"},{"version",1},{"module",id},{"draft",QJsonObject::fromVariantMap(draft)}};
    QSaveFile file(url.toLocalFile());if(!file.open(QIODevice::WriteOnly))return fail(file.errorString());
    const auto data=QJsonDocument(object).toJson();
    if(file.write(data)!=data.size()||!file.commit())return fail(file.errorString());
    m_error.clear();emit errorChanged();return true;
}
QVariantMap ModuleDraftStore::importFile(const QUrl &url,const QString &id) {
    QFile file(url.toLocalFile());
    if(!url.isLocalFile()||!file.open(QIODevice::ReadOnly)||file.size()>1024*1024){fail("无法读取草稿，或文件超过 1 MB");return {};}
    QJsonParseError error;const auto object=QJsonDocument::fromJson(file.readAll(),&error).object();
    if(error.error!=QJsonParseError::NoError||object.value("format")!="Swirl UI draft"||object.value("version").toInt()!=1||object.value("module")!=id||!object.value("draft").isObject()){fail("文件不是此模块的 Swirl 界面草稿");return {};}
    const auto draft=object.value("draft").toObject().toVariantMap();
    if(!draft.value("settings").canConvert<QVariantMap>()||!draft.value("records").canConvert<QVariantList>()){fail("草稿结构不完整");return {};}
    const auto records=draft.value("records").toList();
    if(records.size()>500){fail("最多导入 500 条草稿记录");return {};}
    for(const auto &record:records){const auto row=record.toMap();if(!record.canConvert<QVariantMap>()||!row.value("name").canConvert<QString>()||!row.value("value").canConvert<QString>()){fail("草稿记录格式不正确");return {};}}
    m_error.clear();emit errorChanged();return draft;
}

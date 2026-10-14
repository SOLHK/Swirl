#include "FontManager.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QSaveFile>
#include <QSettings>
#include <QStandardPaths>

FontManager::FontManager(QObject *parent, const QString &storageDirectory) : QObject(parent)
{
    for(const auto &weight : {"Regular", "Medium", "Bold"}) {
        const int id=QFontDatabase::addApplicationFont(QStringLiteral(":/swirl/fonts/HarmonyOS_Sans_SC_%1.ttf").arg(weight));
        const auto names=QFontDatabase::applicationFontFamilies(id);
        if(m_defaultFamily.isEmpty()&&!names.isEmpty())m_defaultFamily=names.first();
    }
    if(m_defaultFamily.isEmpty())qFatal("Bundled HarmonyOS Sans font could not be loaded");
    m_directory=storageDirectory.isEmpty()?QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/fonts":storageDirectory;
    QDir directory(m_directory);
    for(const auto &file:directory.entryList({"*.ttf","*.otf","*.ttc"},QDir::Files))
        QFontDatabase::addApplicationFont(directory.filePath(file));
    const auto requested=QSettings().value("Fonts/family",m_defaultFamily).toString();
    apply(families().contains(requested)?requested:m_defaultFamily);
}

QStringList FontManager::families() const
{
    auto list=QFontDatabase::families();
    list.sort(Qt::CaseInsensitive);
    list.removeAll(m_defaultFamily);
    list.prepend(m_defaultFamily);
    return list;
}

QString FontManager::licenseText() const
{
    QFile file(":/swirl/fonts/LICENSE_HarmonyOS_Sans.txt");
    if(!file.open(QIODevice::ReadOnly))return {};
    return QString::fromUtf8(file.readAll());
}

bool FontManager::fail(const QString &message)
{
    m_error=message;emit errorChanged();return false;
}

void FontManager::apply(const QString &family)
{
    m_error.clear();emit errorChanged();
    QFont font=QGuiApplication::font();font.setFamily(family);
    font.setHintingPreference(QFont::PreferFullHinting);
    font.setStyleStrategy(QFont::PreferAntialias);
    QGuiApplication::setFont(font);
    if(m_family!=family){m_family=family;emit currentFamilyChanged();}
}

bool FontManager::selectFamily(const QString &family)
{
    if(!families().contains(family))return fail(QStringLiteral("找不到此字体，请先安装或导入字体文件。"));
    QSettings settings;settings.setValue("Fonts/family",family);settings.sync();
    if(settings.status()!=QSettings::NoError)return fail(QStringLiteral("无法保存字体设置，请检查本地数据目录。"));
    apply(family);return true;
}

bool FontManager::importFont(const QUrl &url)
{
    if(!url.isLocalFile())return fail(QStringLiteral("请选择本地 TTF、OTF 或 TTC 字体文件。"));
    QFile input(url.toLocalFile());
    const auto suffix=QFileInfo(input).suffix().toLower();
    if(!QStringList{"ttf","otf","ttc"}.contains(suffix)||!input.open(QIODevice::ReadOnly)||input.size()>64*1024*1024)
        return fail(QStringLiteral("无法读取字体，请选择不超过 64 MiB 的 TTF、OTF 或 TTC 文件。"));
    const auto bytes=input.readAll();
    const int id=QFontDatabase::addApplicationFontFromData(bytes);
    const auto names=QFontDatabase::applicationFontFamilies(id);
    if(id<0||names.isEmpty())return fail(QStringLiteral("该文件不是可用的字体，当前字体未更改。"));
    const auto path=m_directory+"/"+QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex())+"."+suffix;
    QSaveFile output(path);
    if(!QDir().mkpath(m_directory)||!output.open(QIODevice::WriteOnly)||output.write(bytes)!=bytes.size()||!output.commit()){
        QFontDatabase::removeApplicationFont(id);
        return fail(QStringLiteral("无法保存导入的字体，当前字体未更改。"));
    }
    emit familiesChanged();
    return selectFamily(names.first());
}

void FontManager::reset(){selectFamily(m_defaultFamily);}

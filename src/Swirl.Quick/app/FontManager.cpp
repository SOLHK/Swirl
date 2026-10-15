#include "FontManager.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QFontDatabase>
#include <QFontInfo>
#include <QFontVariableAxis>
#include <QGuiApplication>
#include <QSaveFile>
#include <QSettings>
#include <QStandardPaths>

namespace {
QString canonicalFamily(const QString &family, const QStringList &available)
{
    const QStringList regions{"SC","TC","HK","MO","JA"};
    const QStringList localized{QStringLiteral("苹方UI-简"),QStringLiteral("苹方UI-繁"),QStringLiteral("苹方UI-港"),QStringLiteral("苹方UI-澳"),QStringLiteral("苹方UI-日")};
    const QStringList traditional{QStringLiteral("蘋方UI-簡"),QStringLiteral("蘋方UI-繁"),QStringLiteral("蘋方UI-港"),QStringLiteral("蘋方UI-澳"),QStringLiteral("蘋方UI-日")};
    for(int i=0;i<regions.size();++i){
        const auto base=QStringLiteral("PingFang UI ")+regions[i];
        if(!available.contains(base))continue;
        for(const auto &alias:QStringList{base,localized[i],traditional[i]})
            if(family==alias||family.startsWith(alias+" "))return base;
    }
    return family;
}
}

FontManager::FontManager(QObject *parent, const QString &storageDirectory) : QObject(parent)
{
    for(const auto &weight : {"Regular", "Medium", "Bold"}) {
        const int id=QFontDatabase::addApplicationFont(QStringLiteral(":/swirl/fonts/HarmonyOS_Sans_SC_%1.ttf").arg(weight));
        const auto names=QFontDatabase::applicationFontFamilies(id);
        if(id>=0)m_fontIds.append(id);
        if(m_defaultFamily.isEmpty()&&!names.isEmpty())m_defaultFamily=names.first();
    }
    m_harmonyFamily=m_defaultFamily;
    m_directory=storageDirectory.isEmpty()?QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/fonts":storageDirectory;
    QDir directory(m_directory);
    for(const auto &file:directory.entryList({"*.ttf","*.otf","*.ttc"},QDir::Files)){
        const int id=QFontDatabase::addApplicationFont(directory.filePath(file));
        if(id>=0)m_fontIds.append(id);
    }
    const auto available=QFontDatabase::families();
    // Bundled HarmonyOS is the stable UI default; manual choices are retained.
    QStringList preferred;
#ifdef Q_OS_WIN
    preferred={m_harmonyFamily,QStringLiteral("Microsoft YaHei UI"),
               QStringLiteral("Microsoft YaHei"),QStringLiteral("Segoe UI")};
#elif defined(Q_OS_MACOS)
    preferred={m_harmonyFamily,QStringLiteral("PingFang SC")};
#else
    preferred={m_harmonyFamily};
#endif
    preferred.append(QFontDatabase::systemFont(QFontDatabase::GeneralFont).family());
    for(const auto &candidate : preferred) {
        if(!candidate.isEmpty() && available.contains(candidate,Qt::CaseInsensitive)) {
            for(const auto &name:available)
                if(name.compare(candidate,Qt::CaseInsensitive)==0){m_defaultFamily=name;break;}
            break;
        }
    }
    if(m_defaultFamily.isEmpty())m_defaultFamily=QGuiApplication::font().family();
    const auto requested=canonicalFamily(QSettings().value("Fonts/family",m_defaultFamily).toString(),available);
    apply(families().contains(requested)?requested:m_defaultFamily);
}

FontManager::~FontManager()
{
    for(const int id:m_fontIds)QFontDatabase::removeApplicationFont(id);
}

QStringList FontManager::families() const
{
    const auto available=QFontDatabase::families();
    QStringList list;
    for(const auto &family:available)list.append(canonicalFamily(family,available));
    list.removeDuplicates();
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
    QFont font=QGuiApplication::font();
    font.setStyleName(QString());
    font.clearVariableAxes();
    font.setWeight(QFont::Medium);
    font.setStretch(QFont::Unstretched);
    QStringList fallbacks{family};
#ifdef Q_OS_WIN
    fallbacks << QStringLiteral("Microsoft YaHei UI") << m_harmonyFamily
              << QStringLiteral("Microsoft YaHei") << QStringLiteral("Segoe UI");
#elif defined(Q_OS_MACOS)
    fallbacks << QStringLiteral("PingFang SC") << m_harmonyFamily;
#else
    fallbacks << m_harmonyFamily;
#endif
    fallbacks.removeAll(QString());fallbacks.removeDuplicates();font.setFamilies(fallbacks);
    font.setHintingPreference(QFont::PreferFullHinting);
    font.setStyleStrategy(QFont::PreferAntialias);
    QGuiApplication::setFont(font);
    if(m_family!=family){m_family=family;emit currentFamilyChanged();}
}

QVariantMap FontManager::variableAxesFor(const QString &family, int weight) const
{
    if(!family.startsWith("PingFang UI ")&&!family.startsWith(QStringLiteral("苹方UI-"))&&!family.startsWith(QStringLiteral("蘋方UI-")))return {};
    const auto canonical=canonicalFamily(family,QFontDatabase::families());
    if(!canonical.startsWith(QStringLiteral("PingFang UI ")))return {};
    if(!m_variablePingFang.contains(canonical)){
        bool wght=false,wdth=false;
        for(const auto &axis:QFontInfo(QFont(canonical)).variableAxes()){
            wght|=axis.tag()==QFont::Tag("wght");wdth|=axis.tag()==QFont::Tag("wdth");
        }
        m_variablePingFang.insert(canonical,wght&&wdth);
    }
    if(!m_variablePingFang.value(canonical))return {};
    // Use the actual variable Medium outline for body text, matching the
    // bundled HarmonyOS Medium. Preserve explicit heading weights.
    return {{"wght",weight==QFont::Normal?500:weight},{"wdth",100}};
}

bool FontManager::selectFamily(const QString &requestedFamily)
{
    const auto family=canonicalFamily(requestedFamily,QFontDatabase::families());
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
    constexpr qint64 maxFontBytes=128LL*1024*1024;
    if(!QStringList{"ttf","otf","ttc"}.contains(suffix)||!input.open(QIODevice::ReadOnly)||input.size()<=0||input.size()>maxFontBytes)
        return fail(QStringLiteral("无法读取字体，请选择不超过 128 MiB 的 TTF、OTF 或 TTC 文件。"));
    const int sourceId=QFontDatabase::addApplicationFont(input.fileName());
    const auto names=QFontDatabase::applicationFontFamilies(sourceId);
    if(sourceId<0||names.isEmpty()){
        if(sourceId>=0)QFontDatabase::removeApplicationFont(sourceId);
        return fail(QStringLiteral("该文件不是可用的字体，当前字体未更改。"));
    }
    // A collection can expose multiple regional families. Prefer its SC face
    // for this PingFang UI collection without changing the platform default.
    QString selected=names.first();
    for(const auto &name:names)
        if(name.compare(QStringLiteral("PingFang UI SC"),Qt::CaseInsensitive)==0){selected=name;break;}
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if(!input.seek(0)||!hash.addData(&input)){
        QFontDatabase::removeApplicationFont(sourceId);
        return fail(QStringLiteral("无法读取字体文件，当前字体未更改。"));
    }
    const auto path=m_directory+"/"+QString::fromLatin1(hash.result().toHex())+"."+suffix;
    const bool alreadySaved=QFile::exists(path);
    bool saved=alreadySaved;
    if(!saved && QDir().mkpath(m_directory) && input.seek(0)){
        QSaveFile output(path);
        if(output.open(QIODevice::WriteOnly)){
            saved=true;
            while(!input.atEnd()){
                const auto chunk=input.read(1024*1024);
                if(chunk.isEmpty()||output.write(chunk)!=chunk.size()){saved=false;break;}
            }
            if(saved)saved=output.commit();
        }
    }
    if(!saved){
        QFontDatabase::removeApplicationFont(sourceId);
        return fail(QStringLiteral("无法保存导入的字体，当前字体未更改。"));
    }
    const int savedId=QFontDatabase::addApplicationFont(path);
    QFontDatabase::removeApplicationFont(sourceId);
    if(savedId<0){
        if(!alreadySaved)QFile::remove(path);
        return fail(QStringLiteral("无法加载已保存的字体，当前字体未更改。"));
    }
    m_fontIds.append(savedId);
    m_variablePingFang.clear();
    emit familiesChanged();
    return selectFamily(selected);
}

void FontManager::reset()
{
    QSettings settings;settings.remove("Fonts/family");settings.sync();
    if(settings.status()!=QSettings::NoError){fail(QStringLiteral("无法保存自动字体设置。"));return;}
    apply(m_defaultFamily);
}

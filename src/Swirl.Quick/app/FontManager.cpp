#include "FontManager.h"
#include "FontAxisPolicy.h"
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
#include <QDataStream>
#include <cmath>
#include <QtEndian>
#include "StoragePaths.h"

namespace {
QString profileKey(const QString &family)
{
    return QStringLiteral("Fonts/profiles/")
        + QString::fromLatin1(QCryptographicHash::hash(family.toUtf8(), QCryptographicHash::Sha256).toHex())
        + QLatin1Char('/');
}
// Validate container and fvar bounds before passing untrusted bytes to a font engine.
// This is a structural guard, not a replacement for the engine's complete sanitizer.
bool validSfntFile(QFile &file)
{
    const quint64 length=file.size();
    auto read=[&](quint64 offset,quint64 size){
        if(offset>length||size>length-offset||!file.seek(qint64(offset)))return QByteArray();
        return file.read(qint64(size));
    };
    auto u16=[](const QByteArray &data,int at){return qFromBigEndian<quint16>(data.constData()+at);};
    auto u32=[](const QByteArray &data,int at){return qFromBigEndian<quint32>(data.constData()+at);};
    const auto header=read(0,12);if(header.size()!=12)return false;
    QList<quint32> faces;
    if(header.first(4)=="ttcf"){
        const auto version=u32(header,4),count=u32(header,8);
        if((version!=0x10000&&version!=0x20000)||!count||quint64(count)>((length-12)/4))return false;
        const auto offsets=read(12,quint64(count)*4);if(quint64(offsets.size())!=quint64(count)*4)return false;
        for(quint32 i=0;i<count;++i)faces.append(u32(offsets,int(i*4)));
    }else faces.append(0);
    for(const auto face:faces){
        const auto sfnt=read(face,12);if(sfnt.size()!=12)return false;
        const auto signature=u32(sfnt,0);
        if(signature!=0x10000&&signature!=0x4f54544f&&signature!=0x74727565&&signature!=0x74797031)return false;
        const auto count=u16(sfnt,4);if(!count)return false;
        const auto directory=read(quint64(face)+12,quint64(count)*16);if(directory.size()!=count*16)return false;
        for(int i=0;i<count;++i){
            const quint64 offset=u32(directory,i*16+8),size=u32(directory,i*16+12);
            if(offset>length||size>length-offset)return false;
            if(directory.mid(i*16,4)!="fvar")continue;
            const auto variable=read(offset,qMin(size,quint64(16)));
            if(variable.size()!=16||u16(variable,0)!=1)return false;
            const quint64 start=u16(variable,4),axes=u16(variable,8),axisSize=u16(variable,10),instances=u16(variable,12),instanceSize=u16(variable,14);
            if(start<16||!axes||axisSize<20||start>size||axes*axisSize>size-start)return false;
            if(instances&&(instanceSize<4+axes*4||instances*instanceSize>size-start-axes*axisSize))return false;
        }
    }
    return file.seek(0);
}

QString canonicalFamily(const QString &family, const QStringList &available)
{
    const QStringList regions{"SC","TC","HK","MO","JA"};
    const QStringList localized{QStringLiteral("苹方UI-简"),QStringLiteral("苹方UI-繁"),QStringLiteral("苹方UI-港"),QStringLiteral("苹方UI-澳"),QStringLiteral("苹方UI-日")};
    const QStringList spaced{QStringLiteral("苹方 UI 简"),QStringLiteral("苹方 UI 繁"),QStringLiteral("苹方 UI 港"),QStringLiteral("苹方 UI 澳"),QStringLiteral("苹方 UI 日")};
    const QStringList traditional{QStringLiteral("蘋方UI-簡"),QStringLiteral("蘋方UI-繁"),QStringLiteral("蘋方UI-港"),QStringLiteral("蘋方UI-澳"),QStringLiteral("蘋方UI-日")};
    for(int i=0;i<regions.size();++i){
        const auto base=QStringLiteral("PingFang UI ")+regions[i];
        if(!available.contains(base))continue;
        for(const auto &alias:QStringList{base,localized[i],traditional[i],spaced[i]})
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
    m_directory=storageDirectory.isEmpty()?SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/fonts":storageDirectory;
    QDir directory(m_directory);
    for(const auto &file:directory.entryList({"*.ttf","*.otf","*.ttc"},QDir::Files)){
        const int id=QFontDatabase::addApplicationFont(directory.filePath(file));
        if(id>=0){
            m_fontIds.append(id);
            m_loadedPaths.insert(QFileInfo(directory.filePath(file)).absoluteFilePath(),id);
            m_importedFamilies.append(QFontDatabase::applicationFontFamilies(id));
        }
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
    refreshFamilies();
    m_saveTimer.setSingleShot(true);
    m_saveTimer.setInterval(200);
    connect(&m_saveTimer,&QTimer::timeout,this,&FontManager::savePreview);
    migrateSettings();
    const auto requested=canonicalFamily(QSettings().value("Fonts/family",m_defaultFamily).toString(),available);
    m_family=families().contains(requested)?requested:m_defaultFamily;
    const auto profile=profileFor(m_family);
    m_automatic=profile.automatic;
    m_values=normalizedAxes(m_family,profile.values);
    apply(m_family,false);
    const auto draft=canonicalFamily(QSettings().value("Fonts/previewFamily",m_family).toString(),available);
    m_previewFamily=families().contains(draft)?draft:m_family;
    const auto draftProfile=profileFor(m_previewFamily);
    const bool savedDraft=draft==m_previewFamily;
    m_previewAutomatic=savedDraft?QSettings().value("Fonts/previewAutomatic",draftProfile.automatic).toBool():draftProfile.automatic;
    m_previewValues=normalizedAxes(m_previewFamily,savedDraft
        ?QSettings().value("Fonts/previewAxes",draftProfile.values).toMap():draftProfile.values);
    m_databaseTimer.setSingleShot(true);
    m_databaseTimer.setInterval(0);
    connect(&m_databaseTimer,&QTimer::timeout,this,&FontManager::refreshFontDatabase);
    connect(qGuiApp,&QGuiApplication::fontDatabaseChanged,this,[this]{
        // Invalidate immediately, then coalesce multiple add/remove events from
        // an import into one notification after the final registration settles.
        m_axisMetadata.clear();m_resolvedAxes.clear();m_databaseTimer.start();
    });
}

FontManager::~FontManager()
{
    if(m_saveTimer.isActive())savePreview();
    disconnect(qGuiApp,nullptr,this,nullptr);
    m_databaseTimer.stop();
    for(const int id:m_fontIds)QFontDatabase::removeApplicationFont(id);
}

void FontManager::migrateSettings()
{
    QSettings settings;
    if(settings.value("Fonts/schemaVersion",0).toInt()>=2)return;
    const auto family=canonicalFamily(settings.value("Fonts/family",m_defaultFamily).toString(),m_availableFamilies);
    const auto values=settings.value("Fonts/axes").toMap();
    const auto draft=canonicalFamily(settings.value("Fonts/previewFamily",family).toString(),m_availableFamilies);
    const auto draftValues=settings.value("Fonts/previewAxes",draft==family?values:QVariantMap()).toMap();
    // V1 stored exact coordinates without recording whether they were defaults
    // or intentionally edited. Preserve every nonempty saved selection as manual.
    // Keep a verbatim settings backup, even for a font temporarily unavailable.
    QVariantMap backup;
    for(const auto &key:QStringList{"family","axes","previewFamily","previewAxes"})
        if(settings.contains("Fonts/"+key))backup.insert(key,settings.value("Fonts/"+key));
    settings.setValue("Fonts/legacyV1",backup);
    writeProfile(settings,family,values,values.isEmpty());
    settings.setValue("Fonts/automatic",values.isEmpty());
    settings.setValue("Fonts/previewAutomatic",draftValues.isEmpty());
    settings.setValue("Fonts/schemaVersion",2);
    settings.sync();
    if(settings.status()!=QSettings::NoError)fail(tr("Could not migrate the font settings; the original values are retained."));
}

FontManager::Profile FontManager::profileFor(const QString &family) const
{
    QSettings settings;const auto key=profileKey(family);
    if(settings.value(key+"family").toString()!=family)return {};
    return {settings.value(key+"automatic",true).toBool(),settings.value(key+"manualAxes").toMap()};
}

void FontManager::writeProfile(QSettings &settings,const QString &family,
                               const QVariantMap &values,bool automatic) const
{
    const auto key=profileKey(family);
    settings.setValue(key+"family",family);
    settings.setValue(key+"automatic",automatic);
    settings.setValue(key+"manualAxes",values);
}

void FontManager::writePreview(QSettings &settings) const
{
    settings.setValue("Fonts/previewFamily",m_previewFamily);
    settings.setValue("Fonts/previewAxes",m_previewValues);
    settings.setValue("Fonts/previewAutomatic",m_previewAutomatic);
}

void FontManager::refreshFontDatabase()
{
    const auto previousFamilies=m_availableFamilies;
    m_axisMetadata.clear();m_resolvedAxes.clear();refreshFamilies();
    // Preserve the selected family and its saved profile when a resource goes
    // away: QFont's existing fallback chain renders it until it is available.
    if(m_availableFamilies.contains(m_previewFamily))
        m_previewValues=normalizedAxes(m_previewFamily,m_previewValues);
    apply(m_family,false);
    if(previousFamilies!=m_availableFamilies)emit familiesChanged();
    emit previewAxesChanged();emit previewValuesChanged();
}

void FontManager::refreshFamilies()
{
    const auto available=QFontDatabase::families();
    QStringList list;
    for(const auto &family:available)list.append(canonicalFamily(family,available));
    list.removeDuplicates();
    list.sort(Qt::CaseInsensitive);
    list.removeAll(m_defaultFamily);
    list.prepend(m_defaultFamily);
    m_availableFamilies=list;
    QStringList imported;
    for(const auto &family:m_importedFamilies)imported.append(canonicalFamily(family,available));
    imported.removeDuplicates();imported.sort(Qt::CaseInsensitive);
    m_importedFamilies=imported;
}

QStringList FontManager::families() const { return m_availableFamilies; }

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

void FontManager::apply(const QString &family,bool clearError)
{
    const bool familyChanged=m_family!=family;
    m_family=family;
    m_resolvedAxes.clear();
    if(clearError){m_error.clear();emit errorChanged();}
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
    // Automatic axes are resolved per text item. Putting wght/opsz on the
    // inherited application font would override descendants' weight/size.
    const auto applied=m_automatic?QVariantMap():normalizedAxes(family,m_values);
    for(auto it=applied.cbegin();it!=applied.cend();++it)
        if(const auto tag=QFont::Tag::fromString(it.key().toLatin1()))font.setVariableAxis(*tag,it.value().toFloat());
    QGuiApplication::setFont(font);
    if(familyChanged)emit currentFamilyChanged();
    ++m_revision;emit configurationChanged();
}

QVariantList FontManager::axesFor(const QString &family) const
{
    if(!m_availableFamilies.contains(family))return {};
    if(m_axisMetadata.contains(family))return m_axisMetadata.value(family);
    QFont font(family);font.setStyleName(QString());font.clearVariableAxes();
    const QFontInfo info(font);
    if(canonicalFamily(info.family(),m_availableFamilies)!=family)return {};
    QVariantList result;
    for(const auto &axis:info.variableAxes()) {
        const auto low=axis.minimumValue(),high=axis.maximumValue(),value=axis.defaultValue();
        if(!std::isfinite(low)||!std::isfinite(high)||!std::isfinite(value)||low>value||value>high)continue;
        result.append(QVariantMap{{"tag",QString::fromLatin1(axis.tag().toString())},{"name",axis.name()},
            {"minimum",low},{"maximum",high},{"defaultValue",value}});
    }
    // Cache metadata per family, never QFont objects per slider position.
    if(m_axisMetadata.size()>=64)m_axisMetadata.clear();
    m_axisMetadata.insert(family,result);
    return result;
}

QVariantMap FontManager::normalizedAxes(const QString &family,const QVariantMap &values) const
{
    return FontAxisPolicy::normalized(axesFor(family),values);
}

QVariantMap FontManager::variableAxesFor(const QString &family,int weight) const
{
    return resolvedAxes(family,weight,-1,-1,96,1,QString());
}

QVariantMap FontManager::resolvedAxes(const QString &family,int weight,
    double pixelSize,double pointSize,double logicalDpi,double dpr,const QString &role) const
{
    QByteArray key;QDataStream stream(&key,QIODevice::WriteOnly);
    stream<<family<<weight<<pixelSize<<pointSize<<logicalDpi<<dpr<<role;
    if(const auto *cached=m_resolvedAxes.object(key))return *cached;
    FontAxisPolicy::Request request;
    request.family=family;request.role=role;request.weight=weight;
    request.pixelSize=pixelSize;request.pointSize=pointSize;
    request.logicalDpi=logicalDpi;request.devicePixelRatio=dpr;
    request.manual=family==m_family&&!m_automatic;
    const auto result=FontAxisPolicy::resolve(axesFor(family),request,request.manual?m_values:QVariantMap());
    m_resolvedAxes.insert(key,new QVariantMap(result));
    return result;
}

QVariantMap FontManager::previewResolvedAxes(int weight,double pixelSize,
    double pointSize,double logicalDpi,double dpr,const QString &role) const
{
    FontAxisPolicy::Request request;
    request.family=m_previewFamily;request.role=role;request.weight=weight;
    request.pixelSize=pixelSize;request.pointSize=pointSize;
    request.logicalDpi=logicalDpi;request.devicePixelRatio=dpr;
    request.manual=!m_previewAutomatic;
    return FontAxisPolicy::resolve(axesFor(m_previewFamily),request,m_previewValues);
}

QVariantMap FontManager::resolvedAxesForFont(const QFont &font,
    double logicalDpi,double dpr,const QString &role) const
{
    // QML's size getters synthesize the other unit. Only the native QFont
    // retains which unit was specified; never infer that from two QML numbers.
    return resolvedAxes(font.family(),int(font.weight()),font.pixelSize(),
                        font.pointSizeF(),logicalDpi,dpr,role);
}

QVariantMap FontManager::previewResolvedAxesForFont(const QFont &font,
    double logicalDpi,double dpr,const QString &role) const
{
    return previewResolvedAxes(int(font.weight()),font.pixelSize(),font.pointSizeF(),
                               logicalDpi,dpr,role);
}

bool FontManager::choosePreviewFamily(const QString &family)
{
    if(!families().contains(family))return fail(tr("Font family is unavailable."));
    if(m_previewFamily==family)return true;
    m_previewFamily=family;
    const auto profile=profileFor(family);
    m_previewValues=normalizedAxes(family,family==m_family?m_values:profile.values);
    m_previewAutomatic=family==m_family?m_automatic:profile.automatic;
    m_error.clear();emit errorChanged();
    emit previewFamilyChanged();emit previewAxesChanged();emit previewValuesChanged();
    emit previewAutomaticChanged();m_saveTimer.start();return true;
}

bool FontManager::setPreviewAxis(const QString &tag,double value)
{
    if(!std::isfinite(value))return fail(tr("Axis value must be finite."));
    for(const auto &entry:previewAxes()) {
        const auto axis=entry.toMap();if(axis.value("tag").toString()!=tag)continue;
        if(value<axis.value("minimum").toDouble()||value>axis.value("maximum").toDouble())
            return fail(tr("Axis value is outside the font's range."));
        // Editing a valid coordinate is an explicit manual action, including
        // entering the current default value. Invalid input never changes mode.
        setPreviewAutomatic(false);
        if(m_previewValues.value(tag).toDouble()==value)return true;
        m_previewValues.insert(tag,value);
        if(!m_error.isEmpty()){m_error.clear();emit errorChanged();}
        emit previewValuesChanged();m_saveTimer.start();return true;
    }
    return fail(tr("This font does not contain the requested axis."));
}

void FontManager::setPreviewAutomatic(bool automatic)
{
    if(m_previewAutomatic==automatic)return;
    m_previewAutomatic=automatic;
    emit previewAutomaticChanged();m_saveTimer.start();
}

void FontManager::resetPreviewAxes()
{
    m_previewValues=normalizedAxes(m_previewFamily,{});
    emit previewValuesChanged();m_saveTimer.start();
}

void FontManager::savePreview()
{
    m_saveTimer.stop();QSettings settings;
    writePreview(settings);settings.sync();
    if(settings.status()!=QSettings::NoError)fail(tr("Could not save the font preview."));
}

bool FontManager::applyPreview()
{
    QSettings settings;
    settings.setValue("Fonts/family",m_previewFamily);
    settings.setValue("Fonts/axes",m_previewValues);
    settings.setValue("Fonts/automatic",m_previewAutomatic);
    writeProfile(settings,m_previewFamily,m_previewValues,m_previewAutomatic);
    writePreview(settings);settings.sync();
    if(settings.status()!=QSettings::NoError)return fail(tr("Could not save the font configuration."));
    m_saveTimer.stop();m_values=m_previewValues;m_automatic=m_previewAutomatic;
    apply(m_previewFamily);return true;
}

void FontManager::discardPreview()
{
    m_previewFamily=m_family;m_previewValues=normalizedAxes(m_family,m_values);
    m_previewAutomatic=m_automatic;
    emit previewFamilyChanged();emit previewAxesChanged();emit previewValuesChanged();
    emit previewAutomaticChanged();savePreview();
}

bool FontManager::selectFamily(const QString &requestedFamily)
{
    const auto family=canonicalFamily(requestedFamily,QFontDatabase::families());
    if(!families().contains(family))return fail(QStringLiteral("找不到此字体，请先安装或导入字体文件。"));
    if(!choosePreviewFamily(family))return false;
    return applyPreview();
}

bool FontManager::importFont(const QUrl &url)
{
    if(!url.isLocalFile())return fail(QStringLiteral("请选择本地 TTF、OTF 或 TTC 字体文件。"));
    QFile input(url.toLocalFile());
    const auto suffix=QFileInfo(input).suffix().toLower();
    constexpr qint64 maxFontBytes=128LL*1024*1024;
    if(!QStringList{"ttf","otf","ttc"}.contains(suffix)||!input.open(QIODevice::ReadOnly)||input.size()<=0||input.size()>maxFontBytes)
        return fail(QStringLiteral("无法读取字体，请选择不超过 128 MiB 的 TTF、OTF 或 TTC 文件。"));
    if(!validSfntFile(input))return fail(tr("The font container or variation table is truncated or invalid. The active font was preserved."));
    const auto stageCollection=[this](const QStringList &names){
        QStringList collection;
        const auto available=QFontDatabase::families();
        for(const auto &name:names)collection.append(canonicalFamily(name,available));
        collection.removeDuplicates();collection.sort(Qt::CaseInsensitive);
        if(collection.contains(m_previewFamily))return true; // preserve this collection's unsaved draft
        const auto preferred=collection.contains("PingFang UI SC")?QStringLiteral("PingFang UI SC"):collection.value(0);
        return choosePreviewFamily(preferred);
    };
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if(!hash.addData(&input))return fail(tr("Could not read the font file."));
    const auto path=m_directory+"/"+QString::fromLatin1(hash.result().toHex())+"."+suffix;
    const auto absolutePath=QFileInfo(path).absoluteFilePath();
    if(m_loadedPaths.contains(absolutePath)) {
        const auto names=QFontDatabase::applicationFontFamilies(m_loadedPaths.value(absolutePath));
        if(!names.isEmpty())return stageCollection(names);
    }
    const int sourceId=QFontDatabase::addApplicationFont(input.fileName());
    const auto names=QFontDatabase::applicationFontFamilies(sourceId);
    if(sourceId<0||names.isEmpty()){
        if(sourceId>=0)QFontDatabase::removeApplicationFont(sourceId);
        return fail(tr("The file is not a usable font. The active font was preserved."));
    }
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
    m_loadedPaths.insert(absolutePath,savedId);
    m_importedFamilies.append(names);m_axisMetadata.clear();m_resolvedAxes.clear();refreshFamilies();
    // Registration can change metadata without changing the selected family name.
    m_previewValues=normalizedAxes(m_previewFamily,m_previewValues);
    emit familiesChanged();emit previewAxesChanged();emit previewValuesChanged();m_saveTimer.start();
    return stageCollection(names);
}

void FontManager::reset()
{
    // Reset the active selection, keeping other families' manual profiles.
    if(!choosePreviewFamily(m_defaultFamily))return;
    setPreviewAutomatic(true);
    applyPreview();
}

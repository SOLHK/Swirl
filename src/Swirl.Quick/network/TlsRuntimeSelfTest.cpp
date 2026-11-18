#include "TlsRuntimeSelfTest.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSet>
#include <QSslSocket>
#include <iterator>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

#ifdef Q_OS_WIN
namespace {
#ifdef __MINGW32__
bool inspectMingwRuntime(QJsonObject *output)
{
    QJsonObject result{{"required",true},{"success",false}};
    const auto fail=[&](const char *code){result["error"]=QString::fromLatin1(code);*output=result;return false;};
    const auto root=QFileInfo(QCoreApplication::applicationDirPath()).canonicalFilePath();
    const auto path=QDir(root).filePath(QStringLiteral("mingw-runtime.json"));
    const QFileInfo metadataInfo(path);
    if(root.isEmpty()||sizeof(void *)!=8||metadataInfo.isSymLink()
        ||metadataInfo.canonicalFilePath().compare(path,Qt::CaseInsensitive)!=0)
        return fail("mingw-metadata-missing-or-outside-application");
    QFile metadataFile(path);
    if(!metadataFile.open(QIODevice::ReadOnly)||metadataFile.size()<=0||metadataFile.size()>65536)
        return fail("mingw-metadata-unreadable-or-oversized");
    QJsonParseError parseError;
    const auto bytes=metadataFile.readAll();
    const auto document=QJsonDocument::fromJson(bytes,&parseError);
    const auto metadata=document.object();
    const auto compiler=QStringLiteral("%1.%2.%3").arg(__GNUC__).arg(__GNUC_MINOR__).arg(__GNUC_PATCHLEVEL__);
    if(parseError.error!=QJsonParseError::NoError||!document.isObject()
        ||metadata.value("schema")!=QJsonValue(1)||metadata.value("kind")!="mingw-runtime"
        ||metadata.value("target")!="x86_64-w64-mingw32"||metadata.value("compiler_version")!=compiler
        ||!metadata.value("files").isArray()||metadata.value("files").toArray().size()!=3)
        return fail("mingw-metadata-contract");
    QSet<QString> remaining{QStringLiteral("libgcc_s_seh-1.dll"),QStringLiteral("libstdc++-6.dll"),QStringLiteral("libwinpthread-1.dll")};
    const QRegularExpression hashPattern(QStringLiteral("^[0-9a-f]{64}$"));
    QJsonObject modules;
    for(const auto &value:metadata.value("files").toArray()){
        const auto entry=value.toObject();const auto name=entry.value("path").toString();
        if(!remaining.remove(name)||!hashPattern.match(entry.value("sha256").toString()).hasMatch())
            return fail("mingw-file-inventory");
        const auto expectedPath=QDir(root).filePath(name);const QFileInfo expected(expectedPath);
        const auto canonicalExpected=expected.canonicalFilePath();
        const auto module=GetModuleHandleW(reinterpret_cast<LPCWSTR>(name.utf16()));
        wchar_t loadedPath[32768]{};
        const DWORD length=module?GetModuleFileNameW(module,loadedPath,DWORD(std::size(loadedPath))):0;
        const auto canonicalLoaded=length&&length<std::size(loadedPath)
            ?QFileInfo(QString::fromWCharArray(loadedPath,int(length))).canonicalFilePath():QString();
        QFile file(expectedPath);QCryptographicHash hash(QCryptographicHash::Sha256);
        const bool inside=expected.isFile()&&!expected.isSymLink()&&!canonicalExpected.isEmpty()
            &&canonicalExpected.compare(expectedPath,Qt::CaseInsensitive)==0
            &&canonicalLoaded.compare(canonicalExpected,Qt::CaseInsensitive)==0;
        const bool hashed=inside&&file.open(QIODevice::ReadOnly)&&hash.addData(&file);
        const auto actual=hashed?QString::fromLatin1(hash.result().toHex()):QString();
        const bool matches=hashed&&actual==entry.value("sha256").toString();
        modules[name]=QJsonObject{{"loaded",module!=nullptr},{"inside_application",inside},{"sha256",actual},{"hash_matches",matches}};
        if(!matches){result["modules"]=modules;return fail("mingw-file-or-loaded-module-verification");}
    }
    result["modules"]=modules;result["compiler_version"]=compiler;result["metadata_valid"]=true;
    result["metadata_sha256"]=QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex());
    result["success"]=true;*output=result;return true;
}
#endif
bool inspectMsvcRuntime(QJsonObject *output)
{
    QJsonObject result{{"required",true},{"metadata_present",false},{"metadata_valid",false},{"success",false}};
    const auto fail = [&](const char *code) {
        result["error"] = QString::fromLatin1(code);
        *output = result;
        return false;
    };
    const auto appDirectory = QFileInfo(QCoreApplication::applicationDirPath()).canonicalFilePath();
    if (appDirectory.isEmpty() || sizeof(void *) != 8) return fail("msvc-application-directory-or-architecture");
    const auto metadataPath = QDir(appDirectory).filePath(QStringLiteral("msvc-runtime.json"));
    const QFileInfo metadataInfo(metadataPath);
    result["metadata_present"] = metadataInfo.isFile();
    if (!metadataInfo.isFile() || metadataInfo.isSymLink()
        || metadataInfo.canonicalFilePath().compare(metadataPath,Qt::CaseInsensitive)!=0)
        return fail("msvc-metadata-missing-or-outside-application");
    QFile metadataFile(metadataPath);
    if (!metadataFile.open(QIODevice::ReadOnly) || metadataFile.size()<=0 || metadataFile.size()>65536)
        return fail("msvc-metadata-unreadable-or-oversized");
    const auto metadataBytes = metadataFile.readAll();
    result["metadata_sha256"] = QString::fromLatin1(QCryptographicHash::hash(metadataBytes,QCryptographicHash::Sha256).toHex());
    QJsonParseError parseError;
    const auto document = QJsonDocument::fromJson(metadataBytes,&parseError);
    if (parseError.error!=QJsonParseError::NoError || !document.isObject()) return fail("msvc-metadata-json");
    const auto metadata = document.object();
    if (metadata.value("schema")!=QJsonValue(1)
        || metadata.value("kind").toString()!=QStringLiteral("msvc-app-local")
        || metadata.value("architecture").toString()!=QStringLiteral("x64")
        || !metadata.value("source").isObject() || !metadata.value("files").isObject())
        return fail("msvc-metadata-contract");
    const QRegularExpression filePattern(QStringLiteral(R"(^(?:msvcp[0-9][a-z0-9_]*|vcruntime[0-9][a-z0-9_]*|concrt[0-9][a-z0-9_]*|vccorlib[0-9][a-z0-9_]*)\.dll$)"));
    const QRegularExpression hashPattern(QStringLiteral("^[0-9a-f]{64}$"));
    const auto readNames = [&](const char *key,QSet<QString> *names) {
        const auto value = metadata.value(QLatin1String(key));
        if (!value.isArray() || value.toArray().size()>128) return false;
        for (const auto &item : value.toArray()) {
            if (!item.isString()) return false;
            const auto name = item.toString();
            if (!filePattern.match(name).hasMatch() || names->contains(name)) return false;
            names->insert(name);
        }
        return true;
    };
    QSet<QString> imports,required,optional;
    if (!readNames("required_imports",&imports) || imports.isEmpty()
        || !readNames("required_modules",&required) || required.isEmpty()
        || !readNames("optional_modules",&optional)) return fail("msvc-module-lists");
    for (const auto &name : required) if (!imports.contains(name)) return fail("msvc-required-module-not-deployed");
    auto remaining = imports;
    remaining.subtract(required);
    if (optional!=remaining) return fail("msvc-optional-module-partition");
    // These are actual eager imports of the supported Qt 6.12 x64 product.
    // Metadata must not reclassify a missing core module as optional.
    for (const auto &name : {QStringLiteral("msvcp140.dll"),QStringLiteral("msvcp140_1.dll"),
                             QStringLiteral("msvcp140_2.dll"),QStringLiteral("vcruntime140.dll"),
                             QStringLiteral("vcruntime140_1.dll")})
        if (!required.contains(name)) return fail("msvc-core-module-omitted");
    const auto entries = metadata.value("files").toObject();
    QSet<QString> entryNames;
    for (auto entry=entries.constBegin();entry!=entries.constEnd();++entry) entryNames.insert(entry.key());
    if (entryNames!=imports) return fail("msvc-file-inventory-mismatch");
    result["required_imports"] = metadata.value("required_imports");
    result["required_modules"] = metadata.value("required_modules");
    result["optional_modules"] = metadata.value("optional_modules");
    bool success = true;
    bool metadataEntriesValid = true;
    QJsonObject modules;
    for (const auto &value : metadata.value("required_imports").toArray()) {
        const auto name = value.toString();
        const auto entry = entries.value(name).toObject();
        const auto expectedHash = entry.value("sha256").toString();
        const auto expectedSize = entry.value("size").toInteger(-1);
        const bool entryValid = entries.value(name).isObject() && hashPattern.match(expectedHash).hasMatch()
            && expectedSize>0 && entry.value("size").toDouble(-1)==double(expectedSize)
            && entry.value("machine").toString()==QStringLiteral("0x8664");
        metadataEntriesValid = metadataEntriesValid && entryValid;
        const auto expectedPath = QDir(appDirectory).filePath(name);
        const QFileInfo expected(expectedPath);
        const auto canonicalExpected = expected.canonicalFilePath();
        const bool fileInside = expected.isFile() && !expected.isSymLink() && !canonicalExpected.isEmpty()
            && canonicalExpected.compare(expectedPath,Qt::CaseInsensitive)==0;
        QFile file(expectedPath);
        QCryptographicHash hash(QCryptographicHash::Sha256);
        const bool hashed = fileInside && file.open(QIODevice::ReadOnly) && hash.addData(&file);
        const auto actualHash = hashed ? QString::fromLatin1(hash.result().toHex()) : QString();
        const bool hashMatches = entryValid && hashed && actualHash==expectedHash;
        const bool sizeMatches = entryValid && expected.size()==expectedSize;
        // Observe the real loader result. Loading the expected file here would
        // hide a missing eager dependency or an earlier system-directory load.
        const auto module = GetModuleHandleW(reinterpret_cast<LPCWSTR>(name.utf16()));
        wchar_t path[32768]{};
        const DWORD length = module ? GetModuleFileNameW(module,path,DWORD(std::size(path))) : 0;
        const auto canonicalLoaded = length && length<std::size(path)
            ? QFileInfo(QString::fromWCharArray(path,int(length))).canonicalFilePath() : QString();
        const bool inside = fileInside && !canonicalLoaded.isEmpty()
            && canonicalLoaded.compare(canonicalExpected,Qt::CaseInsensitive)==0;
        const bool requiredLoaded = required.contains(name);
        const bool verified = fileInside && hashMatches && sizeMatches
            && (!requiredLoaded || module) && (!module || inside);
        success = success && verified;
        modules[name] = QJsonObject{{"required_loaded",requiredLoaded},{"loaded",module!=nullptr},
            {"inside_application",inside},{"file_inside_application",fileInside},
            {"load_observation",module?QStringLiteral("already-loaded"):QStringLiteral("not-loaded")},
            {"metadata_entry_valid",entryValid},{"expected_sha256",expectedHash},{"file_sha256",actualHash},
            {"expected_size",double(expectedSize)},{"file_size",double(expected.size())},
            {"hash_matches",hashMatches},{"size_matches",sizeMatches},{"success",verified}};
    }
    result["modules"] = modules;
    result["metadata_valid"] = metadataEntriesValid;
    result["success"] = success;
    if (!success) result["error"] = QStringLiteral("msvc-file-or-loaded-module-verification");
    *output = result;
    return success;
}
}
#endif

int runTlsRuntimeSelfTest(const QString &reportPath)
{
    const bool available = QSslSocket::supportsSsl();
    const auto backend = QSslSocket::activeBackend();
    const auto version = QSslSocket::sslLibraryVersionString();
    const bool alpn = QSslSocket::isFeatureSupported(QSsl::SupportedFeature::ClientSideAlpn);
    QJsonObject report{{"schema",1},{"expected_version",QStringLiteral(SWIRL_OPENSSL_VERSION)},
                       {"backend",backend},{"runtime_version",version},{"client_alpn_supported",alpn},
                       {"qt_runtime_version",QString::fromLatin1(qVersion())},{"qt_build_version",QStringLiteral(QT_VERSION_STR)}};
    bool ownLibraries = true;
    bool ownCompilerRuntime = false;
    QJsonObject libraries;
    QJsonObject compilerRuntime;
    QString compilerRuntimeKey=QStringLiteral("msvc_runtime");
#ifdef Q_OS_WIN
#ifdef __MINGW32__
    compilerRuntimeKey=QStringLiteral("mingw_runtime");
    ownCompilerRuntime=inspectMingwRuntime(&compilerRuntime);
#else
    ownCompilerRuntime = inspectMsvcRuntime(&compilerRuntime);
#endif
    for (const auto &relative : {QStringLiteral("libssl-3-x64.dll"),QStringLiteral("libcrypto-3-x64.dll"),
                                QStringLiteral("Qt6Network.dll"),QStringLiteral("tls/qopensslbackend.dll")}) {
        const auto name = QFileInfo(relative).fileName();
        const auto module = GetModuleHandleW(reinterpret_cast<LPCWSTR>(name.utf16()));
        wchar_t path[32768]{};
        const DWORD length = module ? GetModuleFileNameW(module,path,DWORD(std::size(path))) : 0;
        const QFileInfo loaded(length && length < std::size(path) ? QString::fromWCharArray(path,int(length)) : QString());
        const auto expected = QFileInfo(QCoreApplication::applicationDirPath()+QLatin1Char('/')+relative);
        const bool inside = !loaded.canonicalFilePath().isEmpty()
            && loaded.canonicalFilePath().compare(expected.canonicalFilePath(),Qt::CaseInsensitive)==0;
        QFile file(loaded.absoluteFilePath());
        QCryptographicHash hash(QCryptographicHash::Sha256);
        const bool hashed = inside && file.open(QIODevice::ReadOnly) && hash.addData(&file);
        ownLibraries = ownLibraries && hashed;
        libraries[relative] = QJsonObject{{"inside_application",inside},
            {"sha256",hashed?QString::fromLatin1(hash.result().toHex()):QString()}};
    }
#else
    ownLibraries = false;
#endif
    const bool success = available && backend==QStringLiteral("openssl") && alpn && ownLibraries && ownCompilerRuntime
        && QString::fromLatin1(qVersion())==QStringLiteral(QT_VERSION_STR)
        && version.startsWith(QStringLiteral("OpenSSL " SWIRL_OPENSSL_VERSION " "));
    report["libraries"] = libraries;
    report[compilerRuntimeKey] = compilerRuntime;
    report["success"] = success;
    report["network_requests"] = 0;
    QSaveFile file(reportPath);
    const auto bytes = QJsonDocument(report).toJson();
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes)!=bytes.size() || !file.commit()) return 2;
    return success ? 0 : 1;
}

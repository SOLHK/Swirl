#pragma once
#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>
#include <cstdio>
#include <cstdlib>

// Explicit test storage only. Normal application paths are always Qt defaults.
// Windows QStandardPaths test mode adds /qttest to Known Folders; changing
// APPDATA or USERPROFILE does not reliably move those folders to a test drive.
namespace SwirlPaths {
[[noreturn]] inline void invalidTestRoot() {
    std::fputs("Swirl: SWIRL_TEST_ROOT must name an existing absolute local directory.\n", stderr);
    std::exit(2);
}
inline QString testRoot() {
    if (!QStandardPaths::isTestModeEnabled() || !qEnvironmentVariableIsSet("SWIRL_TEST_ROOT"))
        return {};
    const auto requested = QDir::fromNativeSeparators(qEnvironmentVariable("SWIRL_TEST_ROOT"));
#ifdef Q_OS_WIN
    if (requested.size() < 3 || !requested[0].isLetter() || requested[1] != ':' || requested[2] != '/')
        invalidTestRoot();
#endif
    const QFileInfo directory(requested);
    if (requested.isEmpty() || !QDir::isAbsolutePath(requested) || requested.startsWith("//")
        || !directory.isDir() || directory.canonicalFilePath().isEmpty())
        invalidTestRoot();
    return directory.canonicalFilePath();
}
inline QString writableLocation(QStandardPaths::StandardLocation type) {
    const auto root = testRoot();
    if (root.isEmpty()) return QStandardPaths::writableLocation(type);
    switch (type) {
    case QStandardPaths::AppLocalDataLocation:
    case QStandardPaths::AppDataLocation: return root + "/data";
    case QStandardPaths::ConfigLocation:
    case QStandardPaths::AppConfigLocation:
    case QStandardPaths::GenericConfigLocation: return root + "/config";
    case QStandardPaths::GenericDataLocation: return root + "/shared";
    case QStandardPaths::CacheLocation:
    case QStandardPaths::GenericCacheLocation: return root + "/cache";
    case QStandardPaths::StateLocation:
    case QStandardPaths::GenericStateLocation: return root + "/state";
    case QStandardPaths::TempLocation: return root + "/tmp";
    default: return QStandardPaths::writableLocation(type);
    }
}
inline void initializeTestStorage() {
    const auto root = testRoot();
    if (root.isEmpty()) return;
    for (const auto *suffix : {"/data", "/config", "/shared", "/cache/qml", "/state", "/tmp"}) {
        if (!QDir().mkpath(root + QString::fromLatin1(suffix))) invalidTestRoot();
    }
    // QProcess inherits these paths, including appearance restoration checks.
    qputenv("SWIRL_TEST_ROOT", root.toUtf8());
    qputenv("TEMP", (root + "/tmp").toUtf8());
    qputenv("TMP", (root + "/tmp").toUtf8());
    qputenv("TMPDIR", (root + "/tmp").toUtf8());
    qputenv("QML_DISK_CACHE_PATH", (root + "/cache/qml").toUtf8());
    // Explicit Qt Quick pipeline files prevent its automatic Known Folder cache.
    qputenv("QSG_RHI_DISABLE_DISK_CACHE", "1");
    const auto pipeline = root + "/cache/pipeline.bin";
    qputenv("QSG_RHI_PIPELINE_CACHE_SAVE", pipeline.toUtf8());
    qputenv("QSG_RHI_PIPELINE_CACHE_LOAD", QFileInfo::exists(pipeline) ? pipeline.toUtf8() : QByteArray());
}
inline void initializeQmlCache(const QString &revision, const QString &flavor) {
    // Preserve explicit production overrides. An isolated test root already
    // owns its cache environment and must never reuse another build's bytecode.
    if (testRoot().isEmpty() && !qEnvironmentVariableIsEmpty("QML_DISK_CACHE_PATH")) return;
    const auto cache = writableLocation(QStandardPaths::CacheLocation)
        + QStringLiteral("/qmlcache/%1-qt%2-%3")
              .arg(revision, QString::fromLatin1(qVersion()), flavor);
    // Keep old versions intact so switching back to an earlier build is safe.
    qputenv("QML_DISK_CACHE_PATH", cache.toUtf8());
}
}

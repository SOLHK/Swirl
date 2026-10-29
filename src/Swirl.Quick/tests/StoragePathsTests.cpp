#include "../app/StoragePaths.h"
#include <QCoreApplication>
#include <QProcess>
#include <QProcessEnvironment>
#include <QSettings>
#include <QTemporaryDir>
#include <QTextStream>

// Qt Core only: this test does not construct windows or touch system settings.
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    app.setOrganizationName("SwirlStorageTests");
    app.setApplicationName("SwirlStorageTests");
    const auto arguments = app.arguments();
    if (arguments.contains("--probe")) {
        QStandardPaths::setTestModeEnabled(true);
        SwirlPaths::initializeTestStorage();
        return 0;
    }
    if (arguments.contains("--qml-cache")) {
        QStandardPaths::setTestModeEnabled(true);
        SwirlPaths::initializeTestStorage();
        SwirlPaths::initializeQmlCache(QStringLiteral("0123456789abcdef"), QStringLiteral("qa"));
        return qEnvironmentVariable("QML_DISK_CACHE_PATH")
            == SwirlPaths::testRoot() + QStringLiteral("/cache/qmlcache/0123456789abcdef-qt%1-qa")
                                          .arg(QString::fromLatin1(qVersion())) ? 0 : 4;
    }
    if (arguments.contains("--read-settings")) {
        QStandardPaths::setTestModeEnabled(true);
        SwirlPaths::initializeTestStorage();
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope,
                           SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));
        return QSettings().value("Appearance/savedMode").toString() == "Dark" ? 0 : 3;
    }
    QTemporaryDir directory(QDir::tempPath() + "/swirl-storage-XXXXXX");
    if (!directory.isValid()) return 1;
    int failures = 0;
    auto check = [&](bool ok, const char *name) {
        QTextStream(stdout) << (ok ? "PASS " : "FAIL ") << name << Qt::endl;
        if (!ok) ++failures;
    };
    const auto root = QFileInfo(directory.path()).canonicalFilePath();
    const auto production = QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation);
    qputenv("SWIRL_TEST_ROOT", root.toUtf8());
    check(SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation) == production,
          "production ignores a test root");
    QStandardPaths::setTestModeEnabled(true);
    qunsetenv("SWIRL_TEST_ROOT");
    check(SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation)
              == QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation),
          "test mode without an explicit root keeps existing Qt behavior");
    qputenv("SWIRL_TEST_ROOT", root.toUtf8());
    SwirlPaths::initializeTestStorage();
    for (auto type : {QStandardPaths::AppLocalDataLocation, QStandardPaths::AppDataLocation,
                      QStandardPaths::AppConfigLocation, QStandardPaths::GenericConfigLocation,
                      QStandardPaths::GenericDataLocation, QStandardPaths::CacheLocation,
                      QStandardPaths::GenericCacheLocation, QStandardPaths::StateLocation,
                      QStandardPaths::GenericStateLocation, QStandardPaths::TempLocation})
        check(SwirlPaths::writableLocation(type).startsWith(root + '/'), "test write location stays in the root");
    check(QDir::fromNativeSeparators(QDir::tempPath()) == root + "/tmp", "temporary files use the explicit root");
    check(qEnvironmentVariable("QML_DISK_CACHE_PATH") == root + "/cache/qml",
          "QML disk cache uses the explicit root");
    SwirlPaths::initializeQmlCache(QStringLiteral("0123456789abcdef"), QStringLiteral("qa"));
    const auto firstCache = qEnvironmentVariable("QML_DISK_CACHE_PATH");
    check(firstCache == root + QStringLiteral("/cache/qmlcache/0123456789abcdef-qt%1-qa")
                                  .arg(QString::fromLatin1(qVersion())),
          "QML content and Qt version stay within the explicit test root");
    QDir().mkpath(firstCache);
    SwirlPaths::initializeQmlCache(QStringLiteral("0123456789abcdef"), QStringLiteral("release"));
    check(qEnvironmentVariable("QML_DISK_CACHE_PATH") != firstCache && QFileInfo::exists(firstCache),
          "production and QA caches are separate without deleting rollback caches");
    const auto releaseCache = qEnvironmentVariable("QML_DISK_CACHE_PATH");
    SwirlPaths::initializeQmlCache(QStringLiteral("fedcba9876543210"), QStringLiteral("release"));
    check(qEnvironmentVariable("QML_DISK_CACHE_PATH") != releaseCache,
          "a changed QML revision cannot reuse earlier bytecode");
    QProcess cacheRestart;
    cacheRestart.start(QCoreApplication::applicationFilePath(), {"--qml-cache"});
    check(cacheRestart.waitForFinished(5000) && cacheRestart.exitStatus() == QProcess::NormalExit
              && cacheRestart.exitCode() == 0,
          "fresh process derives its own QML cache from the inherited isolated root");
    QStandardPaths::setTestModeEnabled(false);
    qputenv("QML_DISK_CACHE_PATH", (root + "/explicit-production-cache").toUtf8());
    SwirlPaths::initializeQmlCache(QStringLiteral("0123456789abcdef"), QStringLiteral("release"));
    check(qEnvironmentVariable("QML_DISK_CACHE_PATH") == root + "/explicit-production-cache",
          "production respects an explicit QML disk cache override");
    QStandardPaths::setTestModeEnabled(true);
    SwirlPaths::initializeQmlCache(QStringLiteral("0123456789abcdef"), QStringLiteral("qa"));
    check(qEnvironmentVariable("QSG_RHI_PIPELINE_CACHE_SAVE") == root + "/cache/pipeline.bin",
          "pipeline cache uses the explicit root");
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope,
                       SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));
    {
        QSettings settings;
        settings.setValue("Appearance/savedMode", "Dark");
        settings.sync();
        check(settings.status() == QSettings::NoError && settings.fileName().startsWith(root + '/'),
              "settings persist inside the test root");
    }
    QProcess restore;
    restore.start(QCoreApplication::applicationFilePath(), {"--read-settings"});
    check(restore.waitForFinished(5000) && restore.exitStatus() == QProcess::NormalExit && restore.exitCode() == 0,
          "fresh process inherits the root and reads saved settings");
    for (const auto &invalid : {QString(), QString("relative-root"), root + "/missing", QString("/drive-relative")}) {
        QProcess child;
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert("SWIRL_TEST_ROOT", invalid);
        child.setProcessEnvironment(environment);
        child.start(QCoreApplication::applicationFilePath(), {"--probe"});
        check(child.waitForFinished(5000) && child.exitStatus() == QProcess::NormalExit && child.exitCode() == 2,
              "invalid explicit root fails instead of using user storage");
    }
    QTextStream(stdout) << "STORAGE_PATH_CHECKS failures " << failures << Qt::endl;
    return failures ? 1 : 0;
}

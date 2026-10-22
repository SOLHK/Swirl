// The fixture builds use this same source with SWIRL_LOADER_FIXTURE_KIND=1..10.
// They are real shared libraries, so the tests exercise the platform loader,
// symbol resolution and C ABI calls rather than a mocked QLibrary result.
#ifdef SWIRL_LOADER_FIXTURE_KIND

#include <QByteArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QtGlobal>
#include <cstddef>
#include <cstring>

#if SWIRL_LOADER_FIXTURE_KIND != 9
extern "C" Q_DECL_EXPORT quint32 swirl_core_abi_version()
{
    return SWIRL_LOADER_FIXTURE_KIND == 2 ? 99 : 1;
}
#endif

#if SWIRL_LOADER_FIXTURE_KIND != 6
extern "C" Q_DECL_EXPORT qintptr swirl_core_build_info(unsigned char *output, size_t capacity)
{
#if SWIRL_LOADER_FIXTURE_KIND == 7
    Q_UNUSED(output);
    Q_UNUSED(capacity);
    return 4097;
#else
#if SWIRL_LOADER_FIXTURE_KIND == 4
    const QByteArray body("{malformed-private-fixture-value");
#else
    QJsonObject info{
        {"abi_version", SWIRL_LOADER_FIXTURE_KIND == 10 ? 99 : 1},
        {"build_id", QString::fromLatin1(SWIRL_RUST_BUILD_ID)},
        {"source_sha", QString::fromLatin1(SWIRL_SOURCE_SHA)},
        {"package_version", QStringLiteral("0.1.2-fixture")},
        {"target", QStringLiteral("synthetic-test-target")},
        {"password", QStringLiteral("unlisted-private-fixture-value")}
    };
#if SWIRL_LOADER_FIXTURE_KIND == 5
    auto buildId = info.value("build_id").toString();
    buildId[0] = buildId[0] == QLatin1Char('a') ? QLatin1Char('b') : QLatin1Char('a');
    info["build_id"] = buildId;
#endif
#if SWIRL_LOADER_FIXTURE_KIND == 8
    auto source = info.value("source_sha").toString();
    if (source == QStringLiteral("source-archive"))
        source = QString(40, QLatin1Char('a'));
    else
        source[0] = source[0] == QLatin1Char('a') ? QLatin1Char('b') : QLatin1Char('a');
    info["source_sha"] = source;
#endif
    const auto body = QJsonDocument(info).toJson(QJsonDocument::Compact);
#endif
    if (!output || capacity < size_t(body.size()))
        return -1;
    std::memcpy(output, body.constData(), size_t(body.size()));
    return body.size();
#endif
}
#endif

#if SWIRL_LOADER_FIXTURE_KIND != 3
extern "C" Q_DECL_EXPORT qintptr swirl_core_command(const unsigned char *, size_t,
                                                    unsigned char *output, size_t capacity)
{
    const QByteArray body("{\"ok\":true,\"fixture\":1}");
    if (!output || capacity < size_t(body.size()))
        return -1;
    std::memcpy(output, body.constData(), size_t(body.size()));
    return body.size();
}
#endif

#else

#include "engine/RustCoreLibrary.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QTest>
#include <QtEndian>

namespace {
QByteArray peHeader(quint16 machine = 0x8664)
{
    QByteArray bytes(512, '\0');
    bytes[0] = 'M';
    bytes[1] = 'Z';
    qToLittleEndian<quint32>(128, bytes.data() + 0x3c);
    bytes.replace(128, 4, QByteArray("PE\0\0", 4));
    qToLittleEndian<quint16>(machine, bytes.data() + 132);
    qToLittleEndian<quint16>(240, bytes.data() + 148);
    qToLittleEndian<quint16>(0x2000, bytes.data() + 150);
    qToLittleEndian<quint16>(machine == 0x014c ? 0x010b : 0x020b, bytes.data() + 152);
    return bytes;
}

QString fixturePath(int kind)
{
    const auto base = QStringLiteral("swirl_loader_fixture_%1").arg(kind);
#ifdef Q_OS_WIN
    const auto filename = base + QStringLiteral(".dll");
#elif defined(Q_OS_MACOS)
    const auto filename = QStringLiteral("lib") + base + QStringLiteral(".dylib");
#else
    const auto filename = QStringLiteral("lib") + base + QStringLiteral(".so");
#endif
    return QDir(QCoreApplication::applicationDirPath()).absoluteFilePath(
        QStringLiteral("loader-fixtures/") + filename);
}

bool writeFile(const QString &path, const QByteArray &body)
{
    QFile file(path);
    return file.open(QIODevice::WriteOnly) && file.write(body) == body.size();
}
}

class RustCoreLibraryTests final : public QObject {
    Q_OBJECT

private slots:
    void defaultPathDoesNotDependOnWorkingDirectory()
    {
        const auto expected = RustCoreLibrary::defaultLibraryPath();
        QVERIFY(QDir::isAbsolutePath(expected));
        QCOMPARE(QFileInfo(expected).absolutePath(), QCoreApplication::applicationDirPath());
        QTemporaryDir elsewhere;
        QVERIFY(elsewhere.isValid());
        const auto previous = QDir::currentPath();
        QVERIFY(QDir::setCurrent(elsewhere.path()));
        const auto actual = RustCoreLibrary::defaultLibraryPath();
        const auto restored = QDir::setCurrent(previous);
        QVERIFY(restored);
        QCOMPARE(actual, expected);
    }

    void relativeLibraryPathIsRejected()
    {
        RustCoreLibrary library;
        QVERIFY(!library.load(QStringLiteral("swirl_api.dll")));
        QCOMPARE(library.diagnostics().value("code").toString(), QStringLiteral("RustLibraryPathInvalid"));
        QVERIFY(!library.command());
    }

    void missingLibraryDoesNotSearchForAnotherCopy()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QFileInfo(RustCoreLibrary::defaultLibraryPath()).fileName());
        // A real matching library is staged beside this test executable. The
        // explicit missing path must fail rather than discovering that copy.
        QVERIFY(QFileInfo::exists(RustCoreLibrary::defaultLibraryPath()));
        RustCoreLibrary library;
        QVERIFY(!library.load(path));
        const auto report = library.diagnostics();
        QCOMPARE(report.value("code").toString(), QStringLiteral("RustLibraryMissing"));
        QCOMPARE(report.value("path").toString(), path);
        QCOMPARE(report.value("exists").toBool(), false);
        QCOMPARE(report.value("qt_error").toString(), QStringLiteral("not_attempted"));
        QVERIFY(library.errorString().contains(path));
        QVERIFY(!library.command());
    }

    void directoryCannotBeLoaded()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        RustCoreLibrary library;
        QVERIFY(!library.load(directory.path()));
        QCOMPARE(library.diagnostics().value("code").toString(), QStringLiteral("RustLibraryMissing"));
    }

    void portableExecutableArchitectures_data()
    {
        QTest::addColumn<quint16>("machine");
        QTest::addColumn<QString>("architecture");
        QTest::newRow("x64") << quint16(0x8664) << QStringLiteral("x86_64");
        QTest::newRow("x86") << quint16(0x014c) << QStringLiteral("i386");
        QTest::newRow("arm64") << quint16(0xaa64) << QStringLiteral("arm64");
    }

    void portableExecutableArchitectures()
    {
        QFETCH(quint16, machine);
        QFETCH(QString, architecture);
        const auto result = RustCoreLibrary::inspectPortableExecutable(peHeader(machine));
        QVERIFY2(result.valid, qPrintable(result.error));
        QCOMPARE(result.machine, machine);
        QCOMPARE(result.architecture, architecture);
    }

    void truncatedPortableExecutableIsRejected()
    {
        const auto complete = peHeader();
        // Every length below the end of the declared optional header is invalid.
        for (qsizetype length = 0; length < 128 + 24 + 240; ++length)
            QVERIFY2(!RustCoreLibrary::inspectPortableExecutable(QByteArrayView(complete).first(length)).valid,
                     qPrintable(QString::number(length)));
        QVERIFY(RustCoreLibrary::inspectPortableExecutable(QByteArrayView(complete).first(392)).valid);
    }

    void maliciousPeOffsetCannotOverflowOrAllocate()
    {
        for (const quint32 offset : {quint32(0), quint32(63), quint32(0x7fffffff), quint32(0xffffffff),
                                    quint32(RustCoreLibrary::MaximumPeHeaderBytes)}) {
            auto bytes = peHeader();
            qToLittleEndian<quint32>(offset, bytes.data() + 0x3c);
            const auto result = RustCoreLibrary::inspectPortableExecutable(bytes);
            QVERIFY(!result.valid);
            QCOMPARE(result.error, QStringLiteral("pe_header_offset_invalid"));
        }
    }

    void wrongImageTypeAndArchitectureFormatAreRejected()
    {
        auto bytes = peHeader();
        qToLittleEndian<quint16>(0, bytes.data() + 150);
        QCOMPARE(RustCoreLibrary::inspectPortableExecutable(bytes).error, QStringLiteral("image_is_not_a_dll"));
        bytes = peHeader();
        qToLittleEndian<quint16>(0x010b, bytes.data() + 152);
        QCOMPARE(RustCoreLibrary::inspectPortableExecutable(bytes).error, QStringLiteral("machine_optional_header_mismatch"));
        bytes = peHeader();
        bytes[128] = 'X';
        QCOMPARE(RustCoreLibrary::inspectPortableExecutable(bytes).error, QStringLiteral("pe_signature_invalid"));
    }

    void invalidLibraryReportsObservedFailure()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QFileInfo(RustCoreLibrary::defaultLibraryPath()).fileName());
        QVERIFY(writeFile(path, QByteArray("synthetic-not-a-library")));
        RustCoreLibrary library;
        QVERIFY(!library.load(path));
        const auto report = library.diagnostics();
        QVERIFY(report.value("exists").toBool());
        QCOMPARE(report.value("path").toString(), path);
#ifdef Q_OS_WIN
        QCOMPARE(report.value("code").toString(), QStringLiteral("RustLibraryImageInvalid"));
        QCOMPARE(report.value("image_error").toString(), QStringLiteral("dos_header_truncated"));
#else
        QCOMPARE(report.value("code").toString(), QStringLiteral("RustLibraryLoadFailed"));
        QVERIFY(!report.value("qt_error").toString().isEmpty());
        QCOMPARE(report.value("dependencies").toString(), QStringLiteral("load_failed_not_verified"));
#endif
        QVERIFY(!library.command());
        QVERIFY(!library.errorString().contains(QStringLiteral("synthetic-not-a-library")));
    }

    void brokenLibraries_data()
    {
        QTest::addColumn<int>("kind");
        QTest::addColumn<QString>("code");
        QTest::addColumn<QString>("missingExport");
        QTest::newRow("wrong-ABI") << 2 << QStringLiteral("RustAbiMismatch") << QString();
        QTest::newRow("missing-command") << 3 << QStringLiteral("RustLibraryExportMissing") << QStringLiteral("swirl_core_command");
        QTest::newRow("malformed-metadata") << 4 << QStringLiteral("RustBuildInfoInvalid") << QString();
        QTest::newRow("old-build") << 5 << QStringLiteral("RustBuildMismatch") << QString();
        QTest::newRow("missing-metadata") << 6 << QStringLiteral("RustLibraryExportMissing") << QStringLiteral("swirl_core_build_info");
        QTest::newRow("oversized-metadata") << 7 << QStringLiteral("RustBuildInfoInvalid") << QString();
        QTest::newRow("different-source") << 8 << QStringLiteral("RustSourceMismatch") << QString();
        QTest::newRow("missing-ABI") << 9 << QStringLiteral("RustLibraryExportMissing") << QStringLiteral("swirl_core_abi_version");
        QTest::newRow("inconsistent-metadata-ABI") << 10 << QStringLiteral("RustBuildInfoInvalid") << QString();
    }

    void brokenLibraries()
    {
        QFETCH(int, kind);
        QFETCH(QString, code);
        QFETCH(QString, missingExport);
        RustCoreLibrary library;
        const auto path = fixturePath(kind);
        QVERIFY2(QFileInfo::exists(path), qPrintable(path));
        QVERIFY(!library.load(path));
        const auto report = library.diagnostics();
        QCOMPARE(report.value("code").toString(), code);
        QVERIFY(!library.command());
        QVERIFY(!library.isReady());
        if (!missingExport.isEmpty()) {
            QVERIFY(report.value("missing_exports").toArray().contains(missingExport));
            QVERIFY(!report.value("export_errors").toObject().value(missingExport).toString().isEmpty());
        }
        QVERIFY(!library.errorString().contains(QStringLiteral("private-fixture-value")));
    }

    void goodFixtureActuallyCallsAnExportAndWhitelistsMetadata()
    {
        RustCoreLibrary library;
        QVERIFY2(library.load(fixturePath(1)), qPrintable(library.errorString()));
        QVERIFY(library.command());
        QByteArray output(128, '\0');
        const auto count = library.command()(nullptr, 0,
            reinterpret_cast<unsigned char *>(output.data()), size_t(output.size()));
        QVERIFY(count > 0 && count <= output.size());
        output.resize(count);
        QCOMPARE(QJsonDocument::fromJson(output).object().value("fixture").toInt(), 1);
        const auto report = library.diagnostics();
        QCOMPARE(report.value("code").toString(), QStringLiteral("Ok"));
        QCOMPARE(report.value("build_id").toString(), RustCoreLibrary::expectedBuildId());
        QCOMPARE(report.value("source_sha").toString(), RustCoreLibrary::expectedSourceSha());
        QVERIFY(!report.contains("password"));
        QVERIFY(!QJsonDocument(report).toJson().contains("private-fixture-value"));
        QVERIFY(library.errorString().isEmpty());
        QVERIFY(library.load(fixturePath(1)));
    }

    void productionRustLibraryLoadsAndExecutesCommand()
    {
        RustCoreLibrary library;
        QVERIFY2(library.load(), qPrintable(library.errorString()));
        QCOMPARE(library.diagnostics().value("actual_abi").toInt(), int(RustCoreLibrary::AbiVersion));
        QCOMPARE(library.diagnostics().value("build_id").toString(), RustCoreLibrary::expectedBuildId());
        QCOMPARE(library.diagnostics().value("source_sha").toString(), RustCoreLibrary::expectedSourceSha());
        // Handle zero is reserved and requires no proxy node, sockets or secrets.
        const QByteArray input("{\"op\":\"snapshot\",\"handle\":0}");
        QByteArray output(1024 * 1024, '\0');
        const auto count = library.command()(reinterpret_cast<const unsigned char *>(input.constData()),
            size_t(input.size()), reinterpret_cast<unsigned char *>(output.data()), size_t(output.size()));
        QVERIFY(count > 0 && count <= output.size());
        output.resize(count);
        const auto response = QJsonDocument::fromJson(output).object();
        QCOMPARE(response.value("ok").toBool(true), false);
        QCOMPARE(response.value("error").toString(), QStringLiteral("UnknownHandle"));
    }

#ifdef Q_OS_WIN
    void architectureMismatchIsDiagnosedBeforeExecution()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("wrong-machine.dll"));
#ifdef Q_PROCESSOR_X86_64
        const auto bytes = peHeader(0x014c);
#else
        const auto bytes = peHeader(0x8664);
#endif
        QVERIFY(writeFile(path, bytes));
        RustCoreLibrary library;
        QVERIFY(!library.load(path));
        QCOMPARE(library.diagnostics().value("code").toString(), QStringLiteral("RustLibraryArchitectureMismatch"));
        QCOMPARE(library.diagnostics().value("qt_error").toString(), QStringLiteral("not_attempted"));
        QVERIFY(!library.command());
    }

    void nativeErrorIsCapturedFromAnActualLoaderAttempt()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto path = directory.filePath(QStringLiteral("not-linkable.dll"));
#if defined(Q_PROCESSOR_X86_64)
        const auto bytes = peHeader(0x8664);
#elif defined(Q_PROCESSOR_X86_32)
        const auto bytes = peHeader(0x014c);
#else
        const auto bytes = peHeader(0xaa64);
#endif
        QVERIFY(writeFile(path, bytes));
        RustCoreLibrary library;
        QVERIFY(!library.load(path));
        const auto report = library.diagnostics();
        QCOMPARE(report.value("code").toString(), QStringLiteral("RustLibraryLoadFailed"));
        QVERIFY(!report.value("qt_error").toString().isEmpty());
        QVERIFY(report.value("windows_error").toInteger() != 0);
        QCOMPARE(report.value("windows_error_context").toString(), QStringLiteral("separate_LoadLibraryExW_diagnostic"));
        QCOMPARE(report.value("native_diagnostic_loaded").toBool(), false);
    }
#endif
};

QTEST_GUILESS_MAIN(RustCoreLibraryTests)
#include "RustCoreLibraryTests.moc"

#endif

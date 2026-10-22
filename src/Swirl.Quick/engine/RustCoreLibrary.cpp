#include "RustCoreLibrary.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSysInfo>
#include <QtEndian>
#include <iterator>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace {
QString architectureName(quint16 machine)
{
    switch (machine) {
    case 0x8664: return QStringLiteral("x86_64");
    case 0x014c: return QStringLiteral("i386");
    case 0xaa64: return QStringLiteral("arm64");
    default: return QStringLiteral("unknown-0x%1").arg(machine, 4, 16, QLatin1Char('0'));
    }
}

#ifdef Q_OS_WIN
quint16 processMachine()
{
#if defined(Q_PROCESSOR_X86_64)
    return 0x8664;
#elif defined(Q_PROCESSOR_X86_32)
    return 0x014c;
#elif defined(Q_PROCESSOR_ARM_64)
    return 0xaa64;
#else
    return 0;
#endif
}
#endif

bool matches(const QJsonValue &value, const char *pattern)
{
    return value.isString()
        && QRegularExpression(QString::fromLatin1(pattern)).match(value.toString()).hasMatch();
}
}

QString RustCoreLibrary::defaultLibraryPath()
{
#ifdef Q_OS_WIN
    const auto name = QStringLiteral("swirl_api.dll");
#elif defined(Q_OS_MACOS)
    const auto name = QStringLiteral("libswirl_api.dylib");
#else
    const auto name = QStringLiteral("libswirl_api.so");
#endif
    return QDir(QCoreApplication::applicationDirPath()).absoluteFilePath(name);
}

QString RustCoreLibrary::expectedBuildId()
{
#ifdef SWIRL_RUST_BUILD_ID
    return QString::fromLatin1(SWIRL_RUST_BUILD_ID);
#else
    return {};
#endif
}

QString RustCoreLibrary::expectedSourceSha()
{
#ifdef SWIRL_SOURCE_SHA
    return QString::fromLatin1(SWIRL_SOURCE_SHA);
#else
    return {};
#endif
}

RustCoreLibrary::PortableExecutable
RustCoreLibrary::inspectPortableExecutable(QByteArrayView header)
{
    PortableExecutable result;
    const auto invalid = [&result](const char *reason) {
        result.error = QString::fromLatin1(reason);
        return result;
    };
    if (header.size() < 64)
        return invalid("dos_header_truncated");
    if (header[0] != 'M' || header[1] != 'Z')
        return invalid("dos_signature_invalid");
    const quint32 offset = qFromLittleEndian<quint32>(header.data() + 0x3c);
    // Both the bounded-read limit and subtraction-first checks are intentional:
    // malformed offsets must not overflow or trigger unbounded file allocation.
    if (offset < 64 || offset > quint32(MaximumPeHeaderBytes - 26)
        || qsizetype(offset) > header.size() - 26)
        return invalid("pe_header_offset_invalid");
    const auto *pe = header.data() + offset;
    if (QByteArrayView(pe, 4) != QByteArrayView("PE\0\0", 4))
        return invalid("pe_signature_invalid");
    result.machine = qFromLittleEndian<quint16>(pe + 4);
    result.architecture = architectureName(result.machine);
    const auto optionalSize = qFromLittleEndian<quint16>(pe + 20);
    if (optionalSize < 2 || qsizetype(optionalSize) > header.size() - qsizetype(offset) - 24)
        return invalid("optional_header_truncated");
    const auto magic = qFromLittleEndian<quint16>(pe + 24);
    if (magic != 0x010b && magic != 0x020b)
        return invalid("optional_header_format_invalid");
    if ((result.machine == 0x014c && magic != 0x010b)
        || ((result.machine == 0x8664 || result.machine == 0xaa64) && magic != 0x020b))
        return invalid("machine_optional_header_mismatch");
    if (!(qFromLittleEndian<quint16>(pe + 22) & 0x2000))
        return invalid("image_is_not_a_dll");
    result.valid = true;
    return result;
}

bool RustCoreLibrary::fail(const char *stage, const char *code, const QString &message)
{
    m_command = nullptr;
    m_message = message;
    m_diagnostics["stage"] = QString::fromLatin1(stage);
    m_diagnostics["code"] = QString::fromLatin1(code);
    m_diagnostics["ready"] = false;
    return false;
}

QString RustCoreLibrary::errorString() const
{
    if (m_message.isEmpty())
        return {};
    return m_message + QLatin1Char('\n')
        + QString::fromUtf8(QJsonDocument(m_diagnostics).toJson(QJsonDocument::Compact));
}

void RustCoreLibrary::nativeLoadDiagnostic(const QString &path)
{
#ifdef Q_OS_WIN
    // QLibrary does not expose its captured DWORD. A second, explicitly labelled
    // native attempt gives a real error code without misattributing whatever
    // GetLastError happened to contain after Qt built its error string.
    const auto nativePath = QDir::toNativeSeparators(path);
    HMODULE handle = LoadLibraryExW(reinterpret_cast<LPCWSTR>(nativePath.utf16()), nullptr,
                                   LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    const DWORD code = handle ? ERROR_SUCCESS : GetLastError();
    m_diagnostics["windows_error"] = qint64(code);
    m_diagnostics["windows_error_context"] = QStringLiteral("separate_LoadLibraryExW_diagnostic");
    m_diagnostics["native_diagnostic_loaded"] = handle != nullptr;
    if (handle) {
        FreeLibrary(handle);
        m_diagnostics["dependencies"] = QStringLiteral("native_probe_loaded_but_Qt_failed");
        return;
    }
    wchar_t message[512] = {};
    const DWORD length = FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                                        nullptr, code, 0, message, DWORD(std::size(message)), nullptr);
    if (length)
        m_diagnostics["windows_message"] = QString::fromWCharArray(message, int(length)).trimmed();
    if (code == ERROR_MOD_NOT_FOUND && m_diagnostics.value("exists").toBool())
        m_diagnostics["dependencies"] = QStringLiteral("dependency_not_found_or_loader_resolution_failed");
#else
    Q_UNUSED(path);
#endif
}

bool RustCoreLibrary::load(const QString &absolutePath)
{
    if (m_command) {
        if (QDir::cleanPath(absolutePath) == m_library.fileName())
            return true;
        return fail("path", "RustLibraryReplacementRejected",
                    QStringLiteral("已加载的 Rust 内核库不能在同一实例中切换到其他文件。"));
    }
    m_message.clear();
    m_diagnostics = {
        {"path", absolutePath},
        {"exists", false},
        {"process_architecture", QSysInfo::buildCpuArchitecture()},
        {"expected_abi", int(AbiVersion)},
        {"expected_build_id", expectedBuildId()},
        {"expected_source_sha", expectedSourceSha()},
        {"qt_error", QStringLiteral("not_attempted")},
        {"windows_error", QJsonValue::Null},
        {"windows_error_context", QStringLiteral("not_attempted")},
        {"image_architecture", QStringLiteral("not_inspected")},
        {"dependencies", QStringLiteral("not_loaded")},
        {"missing_exports", QJsonArray{}},
        {"ready", false}
    };
    if (!QDir::isAbsolutePath(absolutePath) || absolutePath.contains(QChar::Null))
        return fail("path", "RustLibraryPathInvalid", QStringLiteral("Rust 内核库路径必须是绝对文件路径。"));
    const auto path = QDir::cleanPath(absolutePath);
    m_diagnostics["path"] = path;
    const QFileInfo file(path);
    m_diagnostics["exists"] = file.exists();
    if (!file.exists() || !file.isFile())
        return fail("file", "RustLibraryMissing", QStringLiteral("Rust 内核库文件缺失；请使用包含完整 DLL 的构建包。"));
    m_diagnostics["file_size"] = file.size();

#ifdef Q_OS_WIN
    QFile image(path);
    if (!image.open(QIODevice::ReadOnly))
        return fail("image", "RustLibraryUnreadable", QStringLiteral("无法读取 Rust DLL 文件。"));
    const auto inspected = inspectPortableExecutable(image.read(MaximumPeHeaderBytes));
    image.close();
    m_diagnostics["image_architecture"] = inspected.architecture;
    m_diagnostics["image_machine"] = QStringLiteral("0x%1").arg(inspected.machine, 4, 16, QLatin1Char('0'));
    if (!inspected.valid) {
        m_diagnostics["image_error"] = inspected.error;
        return fail("image", "RustLibraryImageInvalid", QStringLiteral("Rust DLL 的 PE 文件头无效或已损坏。"));
    }
    if (!processMachine() || inspected.machine != processMachine())
        return fail("architecture", "RustLibraryArchitectureMismatch", QStringLiteral("Rust DLL 与当前 Swirl.exe 的 CPU 架构不匹配。"));
#endif

    if (m_library.isLoaded())
        m_library.unload();
    m_library.setFileName(path);
    // Runtime workers and TLS destructors must never outlive executable code.
    // stop/destroy remain explicit engine responsibilities, independent of pinning.
    m_library.setLoadHints(QLibrary::PreventUnloadHint);
    if (!m_library.load()) {
        m_diagnostics["qt_error"] = m_library.errorString();
        m_diagnostics["dependencies"] = QStringLiteral("load_failed_not_verified");
        nativeLoadDiagnostic(path);
        return fail("load", "RustLibraryLoadFailed", QStringLiteral("Rust 内核库加载失败；下方记录 Qt 与系统加载器的实际诊断。"));
    }
    m_diagnostics["qt_error"] = QString();
    m_diagnostics["dependencies"] = QStringLiteral("load_time_dependencies_resolved");
#ifndef Q_OS_WIN
    m_diagnostics["image_architecture"] = QStringLiteral("accepted_by_platform_loader");
#endif

    using Version = quint32 (*)();
    using BuildInfo = qintptr (*)(unsigned char *, size_t);
    QJsonArray missing;
    QJsonObject exportErrors;
    QString lastExportError;
    const auto resolve = [&](const char *name) {
        const auto address = m_library.resolve(name);
        if (!address) {
            missing.append(QString::fromLatin1(name));
            lastExportError = m_library.errorString();
            exportErrors[QString::fromLatin1(name)] = lastExportError;
        }
        return address;
    };
    const auto version = reinterpret_cast<Version>(resolve("swirl_core_abi_version"));
    const auto buildInfo = reinterpret_cast<BuildInfo>(resolve("swirl_core_build_info"));
    const auto command = reinterpret_cast<Command>(resolve("swirl_core_command"));
    if (!missing.isEmpty()) {
        m_diagnostics["missing_exports"] = missing;
        m_diagnostics["export_errors"] = exportErrors;
        m_diagnostics["qt_error"] = lastExportError;
        return fail("exports", "RustLibraryExportMissing", QStringLiteral("Rust 内核库缺少必要导出函数；EXE 与 DLL 必须来自同一构建。"));
    }
    const auto actualAbi = version();
    m_diagnostics["actual_abi"] = qint64(actualAbi);
    if (actualAbi != AbiVersion)
        return fail("abi", "RustAbiMismatch", QStringLiteral("Rust 内核库 ABI 版本不兼容，未调用代理运行接口。"));

    QByteArray buffer(BuildInfoCapacity, '\0');
    const auto count = buildInfo(reinterpret_cast<unsigned char *>(buffer.data()), size_t(buffer.size()));
    if (count <= 0 || count > buffer.size())
        return fail("build_info", "RustBuildInfoInvalid", QStringLiteral("Rust 内核库构建信息长度无效。"));
    buffer.resize(qsizetype(count));
    QJsonParseError parseError;
    const auto document = QJsonDocument::fromJson(buffer, &parseError);
    buffer.fill('\0');
    if (parseError.error != QJsonParseError::NoError || !document.isObject())
        return fail("build_info", "RustBuildInfoInvalid", QStringLiteral("Rust 内核库构建信息不是有效 JSON 对象。"));
    const auto info = document.object();
    if (!info.value("abi_version").isDouble() || info.value("abi_version").toDouble() != AbiVersion
        || !matches(info.value("build_id"), "\\A[0-9a-f]{64}\\z")
        || !matches(info.value("source_sha"), "\\A(?:[0-9a-f]{40}|source-archive)\\z")
        || !matches(info.value("package_version"), "\\A[A-Za-z0-9][A-Za-z0-9.+-]{0,63}\\z")
        || !matches(info.value("target"), "\\A[a-z0-9_-]{1,80}\\z"))
        return fail("build_info", "RustBuildInfoInvalid", QStringLiteral("Rust 内核库构建信息字段无效；未记录未经校验的返回内容。"));
    // Whitelist metadata fields. Never print an arbitrary DLL-returned JSON blob.
    for (const auto &key : {"abi_version", "build_id", "source_sha", "package_version", "target"})
        m_diagnostics[QString::fromLatin1(key)] = info.value(QString::fromLatin1(key));
    m_diagnostics["source_revision_available"] = info.value("source_sha").toString() != QStringLiteral("source-archive");
    if (expectedBuildId().isEmpty() || expectedSourceSha().isEmpty())
        return fail("build", "RustBuildExpectationMissing", QStringLiteral("Swirl.exe 缺少内核构建标识，不能确认 DLL 是否匹配。"));
    if (info.value("build_id").toString() != expectedBuildId())
        return fail("build", "RustBuildMismatch", QStringLiteral("Rust DLL 与 Swirl.exe 的构建标识不一致；检测到旧文件或混合构建包。"));
    if (info.value("source_sha").toString() != expectedSourceSha())
        return fail("build", "RustSourceMismatch", QStringLiteral("Rust DLL 与 Swirl.exe 的源码提交不一致。"));

    m_command = command;
    m_diagnostics["stage"] = QStringLiteral("ready");
    m_diagnostics["code"] = QStringLiteral("Ok");
    m_diagnostics["ready"] = true;
    return true;
}

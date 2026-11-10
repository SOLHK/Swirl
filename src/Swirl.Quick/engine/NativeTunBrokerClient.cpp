#include "NativeTunBrokerClient.h"
#include "RustCoreLibrary.h"

#include <QCoreApplication>
#include <QDeadlineTimer>
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QUuid>
#include <algorithm>
#include <utility>
#include <vector>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>
#include <sddl.h>
#include <objbase.h>

namespace {
constexpr qsizetype MaximumFrame = 1024 * 1024; // Includes its terminating LF.
constexpr DWORD ChunkSize = 64 * 1024;
constexpr int ConnectTimeoutMs = 120000;
constexpr int CommandTimeoutMs = 120000;
constexpr int CloseTimeoutMs = 30000;
constexpr DWORD CancellationDrainMs = 2000;

class Handle final {
public:
    explicit Handle(HANDLE value = nullptr) : m_value(value) {}
    ~Handle() { reset(); }
    Handle(const Handle &) = delete;
    Handle &operator=(const Handle &) = delete;
    Handle(Handle &&other) noexcept : m_value(std::exchange(other.m_value, nullptr)) {}
    Handle &operator=(Handle &&other) noexcept {
        if (this != &other) reset(std::exchange(other.m_value, nullptr));
        return *this;
    }
    HANDLE get() const { return m_value; }
    explicit operator bool() const { return m_value && m_value != INVALID_HANDLE_VALUE; }
    void reset(HANDLE value = nullptr) {
        if (*this) CloseHandle(m_value);
        m_value = value;
    }
private:
    HANDLE m_value;
};

QString windowsError(const char *stage, DWORD code = GetLastError()) {
    return QStringLiteral("%1 (Windows %2)").arg(QString::fromLatin1(stage)).arg(code);
}
bool fail(QString *error, const QString &message) {
    if (error) *error = message;
    return false;
}
class ShellApartment final {
public:
    ShellApartment() : m_result(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE)) {}
    ~ShellApartment() { if (SUCCEEDED(m_result)) CoUninitialize(); }
    bool available() const { return SUCCEEDED(m_result) || m_result == RPC_E_CHANGED_MODE; }
private:
    HRESULT m_result;
};
DWORD remaining(QDeadlineTimer &deadline) {
    return DWORD(std::clamp<qint64>(deadline.remainingTime(), 0, MAXDWORD - 1));
}
bool fileIdentity(HANDLE file, BY_HANDLE_FILE_INFORMATION *identity) {
    return GetFileInformationByHandle(file, identity)
        && !(identity->dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY));
}
bool sameFile(const BY_HANDLE_FILE_INFORMATION &a, const BY_HANDLE_FILE_INFORMATION &b) {
    return a.dwVolumeSerialNumber == b.dwVolumeSerialNumber
        && a.nFileIndexHigh == b.nFileIndexHigh && a.nFileIndexLow == b.nFileIndexLow;
}
bool sameTime(const FILETIME &a, const FILETIME &b) {
    return a.dwLowDateTime == b.dwLowDateTime && a.dwHighDateTime == b.dwHighDateTime;
}
bool processCreation(HANDLE process, FILETIME *creation) {
    FILETIME exit{}, kernel{}, user{};
    return GetProcessTimes(process, creation, &exit, &kernel, &user);
}
QString imagePath(HANDLE process) {
    std::vector<wchar_t> path(32768);
    DWORD length = DWORD(path.size());
    if (!QueryFullProcessImageNameW(process, 0, path.data(), &length)) return {};
    return QString::fromWCharArray(path.data(), length);
}
bool processFileMatches(HANDLE process, const BY_HANDLE_FILE_INFORMATION &expected) {
    const auto path = imagePath(process);
    if (path.isEmpty()) return false;
    Handle file(CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()), GENERIC_READ,
        FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    BY_HANDLE_FILE_INFORMATION actual{};
    return file && fileIdentity(file.get(), &actual) && sameFile(expected, actual);
}
struct TokenIdentity {
    QByteArray sid;
    DWORD session = 0;
    bool elevated = false;
};
bool tokenIdentity(HANDLE process, TokenIdentity *identity, QString *error) {
    HANDLE raw = nullptr;
    if (!OpenProcessToken(process, TOKEN_QUERY, &raw)) return fail(error, windowsError("TunBrokerToken"));
    Handle token(raw);
    DWORD length = 0;
    GetTokenInformation(token.get(), TokenUser, nullptr, 0, &length);
    if (!length || GetLastError() != ERROR_INSUFFICIENT_BUFFER)
        return fail(error, windowsError("TunBrokerTokenUser"));
    QByteArray storage(qsizetype(length), Qt::Uninitialized);
    if (!GetTokenInformation(token.get(), TokenUser, storage.data(), length, &length))
        return fail(error, windowsError("TunBrokerTokenUser"));
    const auto user = reinterpret_cast<const TOKEN_USER *>(storage.constData());
    if (!IsValidSid(user->User.Sid)) return fail(error, QStringLiteral("TunBrokerInvalidUserSid"));
    identity->sid.resize(GetLengthSid(user->User.Sid));
    if (!CopySid(DWORD(identity->sid.size()), identity->sid.data(), user->User.Sid))
        return fail(error, windowsError("TunBrokerUserSid"));
    if (!GetTokenInformation(token.get(), TokenSessionId, &identity->session, sizeof(identity->session), &length))
        return fail(error, windowsError("TunBrokerTokenSession"));
    TOKEN_ELEVATION elevation{};
    if (!GetTokenInformation(token.get(), TokenElevation, &elevation, sizeof(elevation), &length))
        return fail(error, windowsError("TunBrokerTokenElevation"));
    identity->elevated = elevation.TokenIsElevated != 0;
    return true;
}
bool lockImage(const QString &path, Handle *file, BY_HANDLE_FILE_INFORMATION *identity,
               std::vector<Handle> *ancestors, QString *error) {
    const auto native = QDir::toNativeSeparators(QFileInfo(path).absoluteFilePath());
    if (native.size() < 3 || native.at(1) != QLatin1Char(':') || native.at(2) != QLatin1Char('\\'))
        return fail(error, QStringLiteral("TunBrokerLocalImageRequired"));
    // Keep path components alive too: locking a leaf alone must not permit a
    // directory rename to redirect ShellExecute to another executable.
    auto directory = QFileInfo(native).absolutePath();
    for (;;) {
        const auto name = QDir::toNativeSeparators(directory);
        Handle locked(CreateFileW(reinterpret_cast<LPCWSTR>(name.utf16()), FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        BY_HANDLE_FILE_INFORMATION info{};
        if (!locked || !GetFileInformationByHandle(locked.get(), &info))
            return fail(error, windowsError("TunBrokerImageDirectory"));
        if (!(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT))
            return fail(error, QStringLiteral("TunBrokerImageReparsePoint"));
        ancestors->push_back(std::move(locked));
        const auto parent = QFileInfo(directory).absolutePath();
        if (parent == directory) break;
        directory = parent;
    }
    file->reset(CreateFileW(reinterpret_cast<LPCWSTR>(native.utf16()), GENERIC_READ,
        FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    if (!*file || !fileIdentity(file->get(), identity))
        return fail(error, windowsError("TunBrokerImageIdentity"));
    return true;
}
struct Operation {
    OVERLAPPED state{};
    Handle event{CreateEventW(nullptr, TRUE, FALSE, nullptr)};
    QByteArray buffer;
    Operation() { state.hEvent = event.get(); }
};
DWORD WINAPI retireCancelledOperation(void *value) {
    std::unique_ptr<Operation> operation(static_cast<Operation *>(value));
    // Only a cancelled kernel operation owns this completion thread. It never
    // holds a broker/controller object or delays its caller's bounded return.
    WaitForSingleObject(operation->event.get(), INFINITE);
    return 0;
}
void retainUntilCancelled(std::unique_ptr<Operation> operation) {
    if (WaitForSingleObject(operation->event.get(), CancellationDrainMs) == WAIT_OBJECT_0) return;
    auto *pending = operation.release();
    Handle thread(CreateThread(nullptr, 0, retireCancelledOperation, pending, 0, nullptr));
    // If thread creation fails, retain this one poisoned operation until
    // process exit rather than free memory still referenced by kernel I/O.
}
bool schemaPair(const QJsonValue &value) {
    return value.isArray() && value.toArray().contains(1) && value.toArray().contains(2);
}
}

struct NativeTunBrokerClient::Impl {
    Handle pipe, process, brokerImage, guiImage;
    std::vector<Handle> directoryLocks;
    BY_HANDLE_FILE_INFORMATION brokerFile{}, guiFile{};
    TokenIdentity gui;
    FILETIME brokerCreation{};
    bool authenticated = false;

    void disconnect() { authenticated = false; pipe.reset(); }
    bool await(Operation *operation, QDeadlineTimer &deadline, DWORD *length, QString *error) {
        HANDLE events[] = {operation->event.get(), process.get()};
        const auto result = WaitForMultipleObjects(2, events, FALSE, remaining(deadline));
        if (result == WAIT_OBJECT_0) {
            if (GetOverlappedResult(pipe.get(), &operation->state, length, FALSE)) return true;
            return fail(error, windowsError("TunBrokerPipeCompletion"));
        }
        return fail(error, result == WAIT_TIMEOUT ? QStringLiteral("TunBrokerIoTimeout")
            : result == WAIT_OBJECT_0 + 1 ? QStringLiteral("TunBrokerExited") : windowsError("TunBrokerPipeWait"));
    }
    bool connect(QString *error) {
        auto operation = std::make_unique<Operation>();
        if (!operation->event) { const auto code = GetLastError(); disconnect(); return fail(error, windowsError("TunBrokerPipeEvent", code)); }
        if (ConnectNamedPipe(pipe.get(), &operation->state)) return true;
        const auto code = GetLastError();
        if (code == ERROR_PIPE_CONNECTED) return true;
        if (code != ERROR_IO_PENDING) return fail(error, windowsError("TunBrokerPipeConnect", code));
        QDeadlineTimer deadline(ConnectTimeoutMs);
        DWORD transferred = 0;
        if (await(operation.get(), deadline, &transferred, error)) return true;
        CancelIoEx(pipe.get(), &operation->state);
        disconnect();
        retainUntilCancelled(std::move(operation));
        return false;
    }
    bool transfer(bool writing, QByteArray *bytes, QDeadlineTimer &deadline, QString *error) {
        auto operation = std::make_unique<Operation>();
        if (!operation->event) { const auto code = GetLastError(); disconnect(); return fail(error, windowsError("TunBrokerPipeEvent", code)); }
        operation->buffer = writing ? *bytes : QByteArray(ChunkSize, Qt::Uninitialized);
        DWORD length = 0;
        const auto immediate = writing
            ? WriteFile(pipe.get(), operation->buffer.constData(), DWORD(operation->buffer.size()), &length, &operation->state)
            : ReadFile(pipe.get(), operation->buffer.data(), DWORD(operation->buffer.size()), &length, &operation->state);
        if (!immediate) {
            const auto code = GetLastError();
            if (code != ERROR_IO_PENDING) { disconnect(); return fail(error, windowsError("TunBrokerPipeIo", code)); }
            if (!await(operation.get(), deadline, &length, error)) {
                CancelIoEx(pipe.get(), &operation->state);
                disconnect();
                retainUntilCancelled(std::move(operation));
                return false;
            }
        }
        if (!length) { disconnect(); return fail(error, QStringLiteral("TunBrokerPipeEof")); }
        if (writing) bytes->remove(0, length);
        else *bytes = operation->buffer.first(length);
        return true;
    }
    bool exchange(const QJsonObject &request, QJsonObject *response, QString *error) {
        QByteArray pending = QJsonDocument(request).toJson(QJsonDocument::Compact);
        pending.append('\n');
        if (pending.size() > MaximumFrame) return fail(error, QStringLiteral("TunBrokerCommandTooLarge"));
        QDeadlineTimer deadline(CommandTimeoutMs);
        while (!pending.isEmpty()) {
            if (deadline.hasExpired()) { disconnect(); return fail(error, QStringLiteral("TunBrokerIoTimeout")); }
            QByteArray chunk = pending.first(std::min<qsizetype>(pending.size(), ChunkSize));
            const auto wanted = chunk.size();
            if (!transfer(true, &chunk, deadline, error)) return false;
            pending.remove(0, wanted - chunk.size());
        }
        QByteArray frame;
        while (frame.size() < MaximumFrame) {
            if (deadline.hasExpired()) { disconnect(); return fail(error, QStringLiteral("TunBrokerIoTimeout")); }
            QByteArray chunk;
            if (!transfer(false, &chunk, deadline, error)) return false;
            frame.append(chunk);
            const auto newline = frame.indexOf('\n');
            if (frame.size() > MaximumFrame || (newline >= 0 && newline != frame.size() - 1)) break;
            if (newline < 0) continue;
            QJsonParseError parsing;
            const auto document = QJsonDocument::fromJson(frame.first(newline), &parsing);
            if (parsing.error != QJsonParseError::NoError || !document.isObject()) break;
            *response = document.object();
            return true;
        }
        disconnect();
        return fail(error, QStringLiteral("TunBrokerResponseFrame"));
    }
    bool verifyClient(QString *error) {
        ULONG client = 0;
        const auto launched = GetProcessId(process.get());
        if (!GetNamedPipeClientProcessId(pipe.get(), &client) || !client || client != launched
            || WaitForSingleObject(process.get(), 0) != WAIT_TIMEOUT)
            return fail(error, QStringLiteral("TunBrokerClientProcessMismatch"));
        Handle observed(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, client));
        FILETIME created{};
        TokenIdentity actual;
        if (!observed || !processCreation(observed.get(), &created) || !sameTime(created, brokerCreation))
            return fail(error, QStringLiteral("TunBrokerClientIdentityUnavailable"));
        if (!tokenIdentity(observed.get(), &actual, error)) return false;
        if (!actual.elevated || actual.session != gui.session || !EqualSid(actual.sid.data(), gui.sid.data())
            || !processFileMatches(observed.get(), brokerFile))
            return fail(error, QStringLiteral("TunBrokerClientIdentityMismatch"));
        return true;
    }
};
#else
struct NativeTunBrokerClient::Impl {};
#endif

NativeTunBrokerClient::NativeTunBrokerClient() : m_impl(std::make_unique<Impl>()) {}
NativeTunBrokerClient::~NativeTunBrokerClient() { close(); }

bool NativeTunBrokerClient::launch(QString *error) {
    if (error) error->clear();
#ifdef Q_OS_WIN
    if (running() && m_impl->authenticated && m_impl->pipe) return true;
    if (m_impl->process && !close(error)) return false;
    ShellApartment apartment;
    if (!apartment.available()) return fail(error, QStringLiteral("TunBrokerShellApartmentUnavailable"));
    const auto build = RustCoreLibrary::expectedBuildId(), source = RustCoreLibrary::expectedSourceSha();
    if (build.size() != 64 || source.size() != 40)
        return fail(error, QStringLiteral("TunBrokerBuildIdentityUnavailable"));
    const auto directory = QCoreApplication::applicationDirPath();
    const auto guiPath = QDir(directory).filePath(QStringLiteral("Swirl.exe"));
    const auto brokerPath = QDir::toNativeSeparators(QDir(directory).filePath(QStringLiteral("swirl-tun-broker.exe")));
    if (!tokenIdentity(GetCurrentProcess(), &m_impl->gui, error)
        || !lockImage(guiPath, &m_impl->guiImage, &m_impl->guiFile, &m_impl->directoryLocks, error)
        || !processFileMatches(GetCurrentProcess(), m_impl->guiFile)
        || !lockImage(brokerPath, &m_impl->brokerImage, &m_impl->brokerFile, &m_impl->directoryLocks, error)) {
        close();
        if (error && error->isEmpty()) *error = QStringLiteral("TunBrokerGuiImageMismatch");
        return false;
    }
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(m_impl->gui.sid.data(), &sid)) { const auto code = GetLastError(); close(); return fail(error, windowsError("TunBrokerPipeSid", code)); }
    const auto descriptor = QStringLiteral("D:P(A;;GA;;;SY)(A;;GA;;;%1)").arg(QString::fromWCharArray(sid));
    LocalFree(sid);
    PSECURITY_DESCRIPTOR security = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(reinterpret_cast<LPCWSTR>(descriptor.utf16()),
            SDDL_REVISION_1, &security, nullptr)) { const auto code = GetLastError(); close(); return fail(error, windowsError("TunBrokerPipeSecurity", code)); }
    SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES), security, FALSE};
    const auto nonce = QUuid::createUuid().toString(QUuid::WithoutBraces).remove(QLatin1Char('-'));
    const auto pipeName = QStringLiteral("\\\\.\\pipe\\SwirlNativeTun-%1-%2").arg(QCoreApplication::applicationPid()).arg(nonce);
    m_impl->pipe.reset(CreateNamedPipeW(reinterpret_cast<LPCWSTR>(pipeName.utf16()),
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1, ChunkSize, ChunkSize, 0, &attributes));
    const auto pipeError = GetLastError();
    LocalFree(security);
    if (!m_impl->pipe) { close(); return fail(error, windowsError("TunBrokerPipeCreate", pipeError)); }
    const auto parameters = QStringLiteral("--pipe \"%1\" --gui-pid %2").arg(pipeName).arg(QCoreApplication::applicationPid());
    const auto nativeDirectory = QDir::toNativeSeparators(directory);
    SHELLEXECUTEINFOW launch{};
    launch.cbSize = sizeof(launch);
    launch.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
    launch.lpVerb = L"runas";
    launch.lpFile = reinterpret_cast<LPCWSTR>(brokerPath.utf16());
    launch.lpParameters = reinterpret_cast<LPCWSTR>(parameters.utf16());
    launch.lpDirectory = reinterpret_cast<LPCWSTR>(nativeDirectory.utf16());
    launch.nShow = SW_HIDE;
    if (!ShellExecuteExW(&launch)) {
        const auto code = GetLastError();
        close();
        return fail(error, code == ERROR_CANCELLED ? QStringLiteral("TunBrokerElevationCancelled") : windowsError("TunBrokerElevation", code));
    }
    m_impl->process.reset(launch.hProcess);
    QString failure;
    if (!m_impl->process || !processCreation(m_impl->process.get(), &m_impl->brokerCreation)
        || !m_impl->connect(&failure) || !m_impl->verifyClient(&failure)) {
        if (failure.isEmpty()) failure = QStringLiteral("TunBrokerLaunchIdentityUnavailable");
        close();
        return fail(error, failure);
    }
    const auto requestId = QUuid::createUuid().toString(QUuid::WithoutBraces);
    QJsonObject response;
    if (!m_impl->exchange({{"broker_schema", 1}, {"op", "hello"}, {"request_id", requestId},
            {"abi_version", int(RustCoreLibrary::AbiVersion)}, {"build_id", build}, {"source_sha", source}, {"role", "swirl_gui"}}, &response, &failure)) {
        close();
        return fail(error, failure);
    }
    const auto identity = response.value("identity").toObject();
    if (response.value("ok") != QJsonValue(true) || response.value("broker_schema") != QJsonValue(1)
        || response.value("request_id") != QJsonValue(requestId) || response.value("role") != QJsonValue("swirl_tun_broker")
        || response.value("pid") != QJsonValue(qint64(GetProcessId(m_impl->process.get())))
        || response.value("gui_pid") != QJsonValue(QCoreApplication::applicationPid())
        || identity.value("abi_version") != QJsonValue(int(RustCoreLibrary::AbiVersion))
        || identity.value("build_id") != QJsonValue(build) || identity.value("source_sha") != QJsonValue(source)
        || identity.value("package_version").toString().isEmpty() || identity.value("target").toString().isEmpty()
        || !schemaPair(identity.value("control_schemas")) || !schemaPair(identity.value("config_schemas"))
        || !identity.value("capabilities").isObject() || !identity.value("limits").isObject()
        || identity.value("limits").toObject().value("command_bytes") != QJsonValue(qint64(MaximumFrame))
        || identity.value("limits").toObject().value("response_bytes") != QJsonValue(qint64(MaximumFrame))
        || WaitForSingleObject(m_impl->process.get(), 0) != WAIT_TIMEOUT) {
        close();
        return fail(error, QStringLiteral("TunBrokerHelloIdentityMismatch"));
    }
    m_impl->authenticated = true;
    // The broker runs, its pipe owner and image identity were verified, and
    // every later GUI operation uses open handles only. The broker retains its
    // own ancestor locks until it has verified the package and launched the
    // helper, so releasing the GUI-side directory locks here loses no
    // anti-tamper coverage and stops an active TUN session from blocking
    // unrelated renames/deletions across the install tree.
    m_impl->directoryLocks.clear();
    return true;
#else
    if (error) *error = QStringLiteral("TunBrokerWindowsRequired");
    return false;
#endif
}

QJsonObject NativeTunBrokerClient::command(const QJsonObject &request) {
#ifdef Q_OS_WIN
    if (!running() || !m_impl->authenticated || !m_impl->pipe)
        return {{"ok", false}, {"error", "TunBrokerDisconnected"}};
    QJsonObject response;
    QString error;
    if (!m_impl->exchange(request, &response, &error)) return {{"ok", false}, {"error", error}};
    return response;
#else
    Q_UNUSED(request);
    return {{"ok", false}, {"error", "TunBrokerWindowsRequired"}};
#endif
}

bool NativeTunBrokerClient::close(QString *error) {
    if (error) error->clear();
#ifdef Q_OS_WIN
    m_impl->disconnect(); // EOF lets the independent supervisor restore first.
    if (m_impl->process) {
        const auto waited = WaitForSingleObject(m_impl->process.get(), CloseTimeoutMs);
        if (waited != WAIT_OBJECT_0)
            return fail(error, waited == WAIT_TIMEOUT ? QStringLiteral("TunBrokerRecoveryUnconfirmed") : windowsError("TunBrokerExitWait"));
        DWORD code = 0;
        const bool observed = GetExitCodeProcess(m_impl->process.get(), &code);
        const auto statusError = GetLastError();
        m_impl->process.reset();
        m_impl->brokerImage.reset();m_impl->guiImage.reset();m_impl->directoryLocks.clear();
        if (!observed) return fail(error, windowsError("TunBrokerExitStatus", statusError));
        if (code) return fail(error, QStringLiteral("TunBrokerRecoveryUnconfirmed (exit %1)").arg(code));
    }
    m_impl->brokerImage.reset();m_impl->guiImage.reset();m_impl->directoryLocks.clear();
    return true;
#else
    return true;
#endif
}

bool NativeTunBrokerClient::running() const {
#ifdef Q_OS_WIN
    return m_impl->process && WaitForSingleObject(m_impl->process.get(), 0) == WAIT_TIMEOUT;
#else
    return false;
#endif
}
qint64 NativeTunBrokerClient::processId() const {
#ifdef Q_OS_WIN
    return m_impl->process ? qint64(GetProcessId(m_impl->process.get())) : 0;
#else
    return 0;
#endif
}

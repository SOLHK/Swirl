#include "NativeTunBrokerChecks.h"
#include "engine/NativeTunBrokerClient.h"
#include "engine/RustCoreLibrary.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSaveFile>
#include <QSet>
#include <QTcpServer>
#include <QUuid>
#include <limits>
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shlobj.h>

namespace {
QString requestId() { return QUuid::createUuid().toString(QUuid::WithoutBraces); }
QByteArray fileBytes(const QString &path) {
    QFile file(path);
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
}
QString fileHash(const QString &path) {
    QFile file(path);
    QCryptographicHash hash(QCryptographicHash::Sha256);
    return file.open(QIODevice::ReadOnly) && hash.addData(&file) ? QString::fromLatin1(hash.result().toHex()) : QString();
}
bool writeBytes(const QString &path, const QByteArray &bytes) {
    QSaveFile file(path);
    return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
}
bool elevated() {
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    TOKEN_ELEVATION value{}; DWORD bytes = 0;
    const bool ok = GetTokenInformation(token, TokenElevation, &value, sizeof(value), &bytes);
    CloseHandle(token);
    return ok && value.TokenIsElevated;
}
QString journalDirectory() {
    PWSTR path = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_ProgramData, 0, nullptr, &path))) return {};
    const auto directory = QDir(QString::fromWCharArray(path)).filePath(QStringLiteral("Swirl/NativeTun"));
    CoTaskMemFree(path);
    return directory;
}
bool emptyJournal(const QString &directory) {
    if (directory.isEmpty()) return false;
    for (auto path = directory;;) {
        const auto native = QDir::toNativeSeparators(path);
        const auto attributes = GetFileAttributesW(reinterpret_cast<LPCWSTR>(native.utf16()));
        if (attributes == INVALID_FILE_ATTRIBUTES) {
            const auto error = GetLastError();
            if (error != ERROR_FILE_NOT_FOUND && error != ERROR_PATH_NOT_FOUND) return false;
        } else if (!(attributes & FILE_ATTRIBUTE_DIRECTORY) || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return false;
        const auto parent = QFileInfo(path).absolutePath();
        if (parent == path) break;
        path = parent;
    }
    const QDir state(directory);
    return !state.exists() || state.entryList(QDir::AllEntries | QDir::Hidden | QDir::System | QDir::NoDotAndDotDot).isEmpty();
}
QJsonObject errorSummary(const QString &message) {
    if (message.isEmpty()) return {};
    // Only fixed protocol/transport enums and numeric OS/exit codes belong in
    // CI evidence. Never copy arbitrary helper errors, configuration or paths.
    static const QSet<QString> allowed{
        "TunBrokerDisconnected", "TunBrokerWindowsRequired", "TunBrokerPipeEvent",
        "TunBrokerPipeIo", "TunBrokerPipeCompletion", "TunBrokerPipeWait",
        "TunBrokerIoTimeout", "TunBrokerExited", "TunBrokerPipeEof",
        "TunBrokerCommandTooLarge", "TunBrokerResponseFrame", "TunBrokerExitWait",
        "TunBrokerExitStatus", "TunBrokerRecoveryUnconfirmed", "CommandInvalidOrUnsupported",
        "CommandInvalid", "UnsupportedControlSchema", "InvalidRequestId", "UnknownHandle",
        "CoreLimit", "HandleLimit", "ReceiptMismatch", "TunHelperPermission",
        "TunNetworkConflict", "TunPhysicalNetworkUnavailable", "TunOwnedByAnotherHelper",
        "TunWindowsNetworkOperation", "TunJournalDirectory", "TunRecoveryJournalInvalid",
        "TunRecoveryJournalIdentity", "TunRecoveryFailed", "TunRecoveryConflict",
        "GatewayCaptureStillOwned", "TunEgressStillOwned", "BrokerOperationFailed",
        "BrokerHelperDirectory", "BrokerHelperStdin", "BrokerHelperStdout",
        "BrokerHelperEof", "BrokerHelperExited", "BrokerHelperTimeout",
        "BrokerHelperNotReady", "BrokerHelperResponseIdentity", "BrokerFrameLimit",
        "BrokerJsonInvalid", "BrokerResponseInvalid", "TunHelperOutputPoisoned",
        "TunHelperOutputClosed", "TunHelperOutputBlocked", "GatewayJournalDirectory",
        "GatewayRecoveryJournalInvalid", "GatewayRecoveryJournalIdentity",
        "GatewayHelperPermission", "GatewayNetworkConflict", "GatewayOwnedByAnotherHelper",
        "GatewayWindowsNetworkOperation", "GatewayQuiesceFailed", "GatewayQuiesceConflict",
        "GatewayForwardingStillEnabled", "GatewayRecoveryFailed", "GatewayRecoveryConflict"
    };
    const auto suffix = message.indexOf(" (");
    const auto code = suffix < 0 ? message : message.first(suffix);
    if (!allowed.contains(code)) return {{"error", "UnclassifiedError"}};
    QJsonObject summary{{"error", code}};
    if (suffix >= 0 && message.endsWith(')')) {
        const auto detail = message.mid(suffix + 2, message.size() - suffix - 3);
        for (const auto &prefix : {QStringLiteral("Windows "), QStringLiteral("exit ")}) {
            if (!detail.startsWith(prefix)) continue;
            bool valid = false;
            const auto number = detail.sliced(prefix.size()).toULongLong(&valid);
            if (valid && number <= MAXDWORD)
                summary.insert(prefix.startsWith("Windows") ? "windows_code" : "exit_code", double(number));
        }
    }
    return summary;
}
void includeRequestId(QJsonObject *summary, const char *key, const QJsonValue &value) {
    const auto text = value.toString();
    const QUuid id(text);
    if (!id.isNull() && id.toString(QUuid::WithoutBraces) == text) summary->insert(key, text);
}
}

int runNativeTunBrokerChecks(const QString &output) {
    QJsonArray checks;
    QJsonArray diagnostics;
    int failures = 0;
    NativeTunBrokerClient broker;
    QString state;
    bool journalGuard = false;
    const auto check = [&](const char *name, bool passed) {
        checks.append(QJsonObject{{"name", QString::fromLatin1(name)}, {"passed", passed}});
        if (!passed) ++failures;
        qInfo("NATIVE_TUN_BROKER_CHECK %s %s", name, passed ? "passed" : "failed");
        return passed;
    };
    const auto finish = [&] {
        QString error;
        const bool closed = broker.close(&error);
        auto closure = errorSummary(error);
        closure.insert("phase", "close");
        closure.insert("ok", closed);
        closure.insert("process_running", broker.running());
        diagnostics.append(closure);
        check("broker-transport-close-completes-with-no-live-process", closed && !broker.running());
        if (journalGuard) check("fixed-journal-empty-after-supervisor-exit", emptyJournal(state));
        const QJsonObject report{{"schema", 1}, {"kind", "native-tun-broker-control-test"},
            {"source_sha", RustCoreLibrary::expectedSourceSha()}, {"build_id", RustCoreLibrary::expectedBuildId()},
            {"ui_test_hooks", true}, {"native_tun_start_invoked", false},
            {"scope", "authenticated product broker and loopback Core control; empty journal recovery only; no TUN adapter or forwarding acceptance"},
            {"checks", checks}, {"diagnostics", diagnostics}, {"success", failures == 0}};
        if (output.isEmpty() || !QDir().mkpath(QFileInfo(output).absolutePath()) ||
            !writeBytes(output, QJsonDocument(report).toJson(QJsonDocument::Indented))) return 1;
        return failures ? 1 : 0;
    };
    if (!check("explicit-ci-opt-in", qEnvironmentVariable("SWIRL_NATIVE_TUN_ACCEPTANCE") == "1") ||
        !check("caller-already-elevated-no-uac-request-needed", elevated())) return finish();
    state = journalDirectory();
    if (!check("fixed-commonappdata-journal-empty-no-active-owner", emptyJournal(state))) return finish();
    journalGuard = true;
    const auto directory = QCoreApplication::applicationDirPath();
    const auto manifestPath = QDir(directory).filePath(QStringLiteral("package-manifest.json"));
    const auto originalManifest = fileBytes(manifestPath);
    const auto manifest = QJsonDocument::fromJson(originalManifest).object();
    if (!check("separate-ui-hooks-on-fixture-manifest", manifest.value("kind") == QJsonValue("native-tun-broker-control-test-fixture") &&
        manifest.value("ui_test_hooks") == QJsonValue(true) &&
        manifest.value("source_sha") == QJsonValue(RustCoreLibrary::expectedSourceSha()) &&
        manifest.value("rust").toObject().value("build_id") == QJsonValue(RustCoreLibrary::expectedBuildId()))) return finish();
    bool hashes = true;
    const auto files = manifest.value("files").toArray();
    for (const auto &name : QStringList{"Swirl.exe", "swirl_api.dll", "swirl-tun-broker.exe", "swirl-tun-helper.exe", "wintun.dll"}) {
        const auto digest = fileHash(QDir(directory).filePath(name));
        int matches = 0;
        for (const auto &entry : files) {
            const auto record = entry.toObject();
            if (record.value("path") == QJsonValue(name) && record.value("sha256") == QJsonValue(digest)) ++matches;
        }
        hashes = hashes && digest.size() == 64 && matches == 1;
    }
    if (!check("real-test-exe-dll-broker-helper-driver-hashes-match", hashes) ||
        !check("paired-dll-identity-loads", RustCoreLibrary::instance().load())) return finish();

    // Corrupt only this explicitly identified fixture's manifest. Restore it
    // before any valid broker may start its privileged supervisor.
    auto wrongSource = manifest;
    wrongSource.insert("source_sha", QString(40, QLatin1Char('0')));
    if (!check("write-negative-source-fixture", writeBytes(manifestPath, QJsonDocument(wrongSource).toJson()))) return finish();
    QString failure;
    const bool acceptedWrongSource = broker.launch(&failure);
    QString closeError;
    const bool negativeClosed = broker.close(&closeError);
    const bool restoredManifest = writeBytes(manifestPath, originalManifest);
    if (!check("different-source-manifest-rejected", !acceptedWrongSource && !failure.isEmpty() && negativeClosed) ||
        !check("original-fixture-manifest-restored", restoredManifest) ||
        !check("negative-authentication-keeps-journal-empty", emptyJournal(state))) return finish();
    if (!check("authenticated-same-source-broker-launch", broker.launch(&failure)) ||
        !check("authenticated-broker-has-live-process", broker.running() && broker.processId() > 0)) return finish();

    // This test never forwards a probe or a native_tun_start request.
    const QSet<QString> allowed{"validate_configuration_v2", "start_v2", "snapshot", "stop", "native_tun_status", "native_tun_recover"};
    const auto command = [&](QJsonObject request) {
        if (!check("control-only-command-allowlist", allowed.contains(request.value("op").toString()))) return QJsonObject{};
        const auto response = broker.command(request);
        auto detail = errorSummary(response.value("error").toString());
        detail.insert("phase", "command");
        detail.insert("op", request.value("op"));
        detail.insert("ok", response.value("ok").isBool() ? response.value("ok") : QJsonValue(QJsonValue::Null));
        includeRequestId(&detail, "request_id", request.value("request_id"));
        includeRequestId(&detail, "response_request_id", response.value("request_id"));
        detail.insert("request_id_matches", response.value("request_id") == request.value("request_id"));
        static const QSet<QString> phases{"parse", "validate", "start", "prepare", "activate", "finish", "rollback", "status"};
        if (phases.contains(response.value("phase").toString())) detail.insert("response_phase", response.value("phase"));
        static const QSet<QString> brokerPhases{"helper_start", "helper_command"};
        if (brokerPhases.contains(response.value("broker_phase").toString())) detail.insert("broker_phase", response.value("broker_phase"));
        if (response.value("os_error").isDouble()) {
            const auto number = response.value("os_error").toInteger();
            if (double(number) == response.value("os_error").toDouble() &&
                number >= std::numeric_limits<LONG>::min() && number <= std::numeric_limits<LONG>::max())
                detail.insert("os_error", double(number));
        }
        detail.insert("plan_digest_length", response.value("plan_digest").toString().size());
        diagnostics.append(detail);
        return response;
    };
    const auto node = requestId(), store = requestId();
    const QJsonObject candidate{{"schema", 2}, {"listen", "127.0.0.1:0"},
        {"nodes", QJsonArray{QJsonObject{{"id", node}, {"outbound", QJsonObject{{"type", "socks5"}, {"host", "127.0.0.1"}, {"port", 9}, {"auth", QJsonValue::Null}}}}}},
        {"policy", QJsonObject{{"schema", 2}, {"mode", "global"}, {"default_policy", QJsonObject{{"id", "policy:default"}, {"target", QJsonObject{{"kind", "node"}, {"id", node}}}}}}}};
    const auto validateId = requestId();
    const auto validated = command({{"control_schema", 2}, {"op", "validate_configuration_v2"}, {"request_id", validateId}, {"candidate", candidate}});
    if (!check("v2-validation-request-and-plan-receipt", validated.value("ok") == QJsonValue(true) &&
        validated.value("request_id") == QJsonValue(validateId) && validated.value("plan_digest").toString().size() == 64)) return finish();
    const auto startId = requestId();
    const auto started = command({{"control_schema", 2}, {"op", "start_v2"}, {"request_id", startId},
        {"store_id", store}, {"saved_revision", "1"}, {"candidate", candidate}, {"plan_digest", validated.value("plan_digest")}});
    if (!check("v2-loopback-start-has-matching-durable-identity", started.value("ok") == QJsonValue(true) &&
        started.value("request_id") == QJsonValue(startId) && started.value("store_id") == QJsonValue(store) &&
        started.value("applied_revision") == QJsonValue("1") && !started.value("handle").toString().isEmpty())) return finish();
    const auto handle = started.value("handle").toString(), epoch = started.value("engine_epoch").toString();
    const auto snapshot = command({{"op", "snapshot"}, {"handle", handle.toLongLong()}}).value("status").toObject();
    check("snapshot-proves-loopback-listener-with-zero-traffic", snapshot.value("running") == QJsonValue(true) &&
        snapshot.value("address").toString().startsWith("127.0.0.1:") && snapshot.value("accepted") == QJsonValue(0) &&
        snapshot.value("upload") == QJsonValue(0) && snapshot.value("download") == QJsonValue(0));
    const auto statusId = requestId();
    const auto tun = command({{"native_tun_schema", 1}, {"op", "native_tun_status"}, {"request_id", statusId}, {"handle", handle}, {"engine_epoch", epoch}});
    check("native-tun-remains-stopped", tun.value("ok") == QJsonValue(true) && tun.value("state") == QJsonValue("stopped") &&
        tun.value("desired_enabled") == QJsonValue(false) && tun.value("request_id") == QJsonValue(statusId));
    const auto stopped = command({{"op", "stop"}, {"handle", handle.toLongLong()}});
    check("core-stop-acknowledged", stopped.value("ok") == QJsonValue(true));
    const auto port = snapshot.value("address").toString().section(':', -1).toUInt();
    QTcpServer released;
    check("kernel-loopback-listener-released-after-stop", port > 0 && port <= 65535 &&
        released.listen(QHostAddress::LocalHost, quint16(port)));
    released.close();
    const auto ended = command({{"op", "snapshot"}, {"handle", handle.toLongLong()}});
    check("stopped-core-handle-revoked", ended.value("ok") == QJsonValue(false) && ended.value("error") == QJsonValue("UnknownHandle"));
    const auto recoveryId = requestId();
    const auto recovered = command({{"native_tun_schema", 1}, {"op", "native_tun_recover"}, {"request_id", recoveryId}});
    check("empty-journal-recovery-acknowledges-zero-network-owners", recovered.value("ok") == QJsonValue(true) &&
        recovered.value("request_id") == QJsonValue(recoveryId) && recovered.value("state") == QJsonValue("recovered") &&
        recovered.value("journals_restored") == QJsonValue(0) && recovered.value("gateway_journals_restored") == QJsonValue(0) &&
        recovered.value("active_owners") == QJsonValue(0));
    check("fixed-journal-still-empty-before-supervisor-exit", emptyJournal(state));
    return finish();
}

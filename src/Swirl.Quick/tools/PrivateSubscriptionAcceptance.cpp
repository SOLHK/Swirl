// Explicitly authorized, isolated QA only. Never included in the product package.
#include "engine/NodeImporter.h"
#include "engine/NodeStore.h"
#include "engine/NodeTestService.h"
#include "engine/RustCoreLibrary.h"
#include "network/HttpRequestPolicy.h"
#include "tests/ControlledNetwork.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QProcess>
#include <QQueue>
#include <QRegularExpression>
#include <QSaveFile>
#include <QScopeGuard>
#include <QSet>
#include <QStandardPaths>
#include <QSslConfiguration>
#include <QSslError>
#include <QSslSocket>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTextStream>
#include <QTimer>
#include <QUuid>
#include <memory>
#ifdef Q_OS_WIN
#include <windows.h>
#include <sddl.h>
#include <wincrypt.h>
#endif

namespace {
constexpr qint64 BodyLimit = 4 * 1024 * 1024;
const QByteArray Magic("SWIRLCAPTURE1\n");
const QUrl ProbeUrl(QStringLiteral("https://www.cloudflare.com/robots.txt"));

QByteArray crypt(QByteArray bytes, bool decrypt) {
#ifdef Q_OS_WIN
    DATA_BLOB input{DWORD(bytes.size()), reinterpret_cast<BYTE *>(bytes.data())}, result{};
    const bool ok = decrypt
        ? CryptUnprotectData(&input, nullptr, nullptr, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &result)
        : CryptProtectData(&input, L"Swirl private QA", nullptr, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &result);
    bytes.fill('\0');
    if (!ok) return {};
    QByteArray output(reinterpret_cast<char *>(result.pbData), result.cbData);
    SecureZeroMemory(result.pbData, result.cbData); LocalFree(result.pbData);
    return output;
#else
    Q_UNUSED(bytes); Q_UNUSED(decrypt); return {};
#endif
}
QByteArray readPrivate(const QString &path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 48 * 1024 * 1024) return {};
    auto bytes = file.readAll();
    if (bytes.startsWith(Magic)) bytes.remove(0, Magic.size());
    return crypt(bytes, true);
}
bool writeBytes(const QString &path, const QByteArray &bytes) {
    QSaveFile file(path);
    return !bytes.isEmpty() && file.open(QIODevice::WriteOnly)
        && file.write(bytes) == bytes.size() && file.commit();
}
bool writePrivate(const QString &path, const QJsonObject &value) {
    const auto bytes = crypt(QJsonDocument(value).toJson(QJsonDocument::Compact), false);
    return !bytes.isEmpty() && writeBytes(path, Magic + bytes);
}
bool sameParameters(const ProxyNode &a, const ProxyNode &b) {
    return a.id == b.id && a.host == b.host && a.port == b.port && a.protocol == b.protocol
        && a.username == b.username && a.password == b.password && a.cipher == b.cipher
        && a.serverName == b.serverName && a.parameters == b.parameters
        && a.originalConfiguration == b.originalConfiguration && a.sourceDocument == b.sourceDocument;
}
bool roundTrip(const QString &path, const QList<ProxyNode> &nodes, QList<ProxyNode> *loaded) {
    QList<ProxyNode> saved;
    {
        NodeStore store(path);
        if (!store.error().isEmpty() || !store.importNodes(nodes)) return false;
        saved = store.nodes();
    }
    NodeStore store(path);
    if (!store.error().isEmpty() || store.nodes().size() != saved.size()) return false;
    for (qsizetype i = 0; i < saved.size(); ++i)
        if (!sameParameters(saved[i], store.nodes()[i])) return false;
    *loaded = store.nodes(); return true;
}

// This fixed, offline installer fixture uses the product's persistence code.
// It is deliberately V1 preservation, not a V2 or previous-release migration.
QList<ProxyNode> installerNodes() {
    QList<ProxyNode> nodes;
    for (int i = 0; i < 2; ++i) {
        ProxyNode node;
        node.id = QStringLiteral("40000000-0000-4000-8000-00000000008%1").arg(i + 1);
        node.name = QStringLiteral("Installer synthetic node %1").arg(i + 1);
        node.protocol = "socks5"; node.host = "127.0.0.1"; node.port = quint16(9 + i);
        node.username = QStringLiteral("installer-fixture-user-%1").arg(i + 1);
        node.password = QStringLiteral("installer-fixture-secret-%1").arg(i + 1);
        node.importSource = "manual-import";
        nodes.append(node);
    }
    return nodes;
}
QJsonObject installerNetworkConfiguration() {
    return {{"schema", 1}, {"proxyPort", 17899}, {"tun", false}, {"allowLan", false},
        {"dns", QJsonObject{}}, {"rules", QJsonArray{}}, {"groups", QJsonArray{}}};
}
bool installerStandardUser(QString *sid) {
#ifdef Q_OS_WIN
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    const auto close = qScopeGuard([&] { CloseHandle(token); });
    TOKEN_ELEVATION elevation{}; DWORD length = 0;
    if (!GetTokenInformation(token, TokenElevation, &elevation, sizeof(elevation), &length)
        || elevation.TokenIsElevated) return false;
    SID_IDENTIFIER_AUTHORITY authority = SECURITY_NT_AUTHORITY; PSID administrators = nullptr;
    if (!AllocateAndInitializeSid(&authority, 2, SECURITY_BUILTIN_DOMAIN_RID, DOMAIN_ALIAS_RID_ADMINS,
                                  0, 0, 0, 0, 0, 0, &administrators)) return false;
    BOOL member = TRUE;
    const bool queried = CheckTokenMembership(nullptr, administrators, &member);
    FreeSid(administrators);
    if (!queried || member) return false;
    auto information = [&](TOKEN_INFORMATION_CLASS type) {
        DWORD size = 0; GetTokenInformation(token, type, nullptr, 0, &size);
        if (!size || size > 65536) return QByteArray{};
        QByteArray bytes(int(size), Qt::Uninitialized);
        return GetTokenInformation(token, type, bytes.data(), size, &size) ? bytes : QByteArray{};
    };
    const auto integrity = information(TokenIntegrityLevel);
    if (integrity.isEmpty()) return false;
    const auto level = reinterpret_cast<const TOKEN_MANDATORY_LABEL *>(integrity.constData())->Label.Sid;
    if (!IsValidSid(level) || !*GetSidSubAuthorityCount(level)
        || *GetSidSubAuthority(level, *GetSidSubAuthorityCount(level) - 1) != SECURITY_MANDATORY_MEDIUM_RID) return false;
    const auto user = information(TokenUser);
    if (user.isEmpty()) return false;
    LPWSTR text = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<const TOKEN_USER *>(user.constData())->User.Sid, &text)) return false;
    *sid = QString::fromWCharArray(text); LocalFree(text); return true;
#else
    Q_UNUSED(sid); return false;
#endif
}
bool installerLocalPath(const QString &path) {
#ifdef Q_OS_WIN
    auto current = QDir::cleanPath(QDir::fromNativeSeparators(path));
    if (current.size() < 3 || !current[0].isLetter() || current.mid(1, 2) != ":/") return false;
    while (!current.isEmpty()) {
        const auto native = QDir::toNativeSeparators(current);
        const DWORD attributes = GetFileAttributesW(reinterpret_cast<LPCWSTR>(native.utf16()));
        if (attributes != INVALID_FILE_ATTRIBUTES) {
            if (attributes & FILE_ATTRIBUTE_REPARSE_POINT) return false;
        } else if (const auto error = GetLastError(); error != ERROR_FILE_NOT_FOUND && error != ERROR_PATH_NOT_FOUND) return false;
        const auto parent = QFileInfo(current).absolutePath();
        if (parent == current) break;
        current = parent;
    }
    return true;
#else
    Q_UNUSED(path); return false;
#endif
}
int installerStoreFixture(const QStringList &args) {
    // --installer-store-fixture create|verify source-sha user-sid store-path receipt
    if (args.size() != 7) return 2;
    const auto mode = args[2], path = QDir::cleanPath(QDir::fromNativeSeparators(args[5]));
    const auto receipt = QDir::cleanPath(QDir::fromNativeSeparators(args[6]));
    // Receipts must never replace the store, one of its sidecars, or previous
    // evidence, including when a create request is correctly refused.
    if (!QDir::isAbsolutePath(receipt) || !installerLocalPath(receipt) || QFileInfo::exists(receipt)
        || receipt.startsWith(QFileInfo(path).absolutePath() + '/', Qt::CaseInsensitive)) return 2;
    bool receiptAllowed = false;
    QJsonObject report{{"schema", 1}, {"kind", "installer-node-store-fixture"},
        {"scope", "same-package-reinstall-synthetic-v1-node-store"}, {"operation", mode},
        {"source_sha", RustCoreLibrary::expectedSourceSha()}, {"success", false},
        {"network_requests", 0}, {"engine_started", false}, {"store_write_attempted", false}};
    auto finish = [&](const char *error) {
        if (error) report.insert("error_code", QString::fromLatin1(error));
        const auto bytes = QJsonDocument(report).toJson(QJsonDocument::Compact);
        // Scope rejections have no write side effect. Later phase receipts are
        // new-only even if another process creates the path after validation.
        if (receiptAllowed) {
            QFile file(receipt);
            if (!file.open(QIODevice::WriteOnly | QIODevice::NewOnly)
                || !file.setPermissions(QFile::ReadOwner | QFile::WriteOwner)
                || file.write(bytes) != bytes.size() || !file.flush()) return 2;
        }
        QTextStream(stdout) << bytes << Qt::endl;
        return report.value("success").toBool() ? 0 : 2;
    };
    if ((mode != "create" && mode != "verify")
        || !QRegularExpression("^[0-9a-f]{40}$").match(args[3]).hasMatch()
        || args[3] != RustCoreLibrary::expectedSourceSha()) return finish("FixtureSourceOrModeMismatch");
    if (qEnvironmentVariable("GITHUB_ACTIONS") != "true"
        || qEnvironmentVariable("RUNNER_ENVIRONMENT") != "github-hosted"
        || qEnvironmentVariable("SWIRL_DISPOSABLE_INSTALL_TEST") != "1"
        || qEnvironmentVariableIsSet("SWIRL_TEST_ROOT") || qEnvironmentVariableIsSet("SWIRL_ISOLATED_INSTALL_ROOT")
        || QStandardPaths::isTestModeEnabled()) return finish("DisposableOrdinaryProfileRequired");
    report.insert("host_scope_verified", true);
    QString sid;
    if (!installerStandardUser(&sid) || sid != args[4]) return finish("ExactStandardUserRequired");
    QCoreApplication::setOrganizationName("SOLHK"); QCoreApplication::setApplicationName("Swirl");
    const auto ordinary = QDir::cleanPath(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/nodes.dpapi");
    if (path.compare(ordinary, Qt::CaseInsensitive) != 0 || !installerLocalPath(path)
        || !installerLocalPath(path + ".selected")
        || receipt.startsWith(QDir::cleanPath(QStandardPaths::writableLocation(QStandardPaths::HomeLocation)) + '/', Qt::CaseInsensitive))
        return finish("OrdinaryNodeStorePathRequired");
    receiptAllowed = true;
    report.insert("user_sid", sid); report.insert("store_path", ordinary); report.insert("ordinary_profile", true);
    auto &library = RustCoreLibrary::instance();
    // Loading/build-info validation is offline; never invoke an engine command.
    if (!library.load()) return finish("PairedRustLibraryRequired");
    report.insert("rust_build_id", RustCoreLibrary::expectedBuildId());
    report.insert("qt_runtime_version", QString::fromLatin1(qVersion()));
    const auto expected = installerNodes();
    const QString subscriptionName = "Installer disabled synthetic subscription";
    const QUrl subscriptionUrl("http://127.0.0.1:9/installer-disabled-fixture");
    if (mode == "create") {
        for (const auto &suffix : QStringList{"", ".selected", ".lock", ".network.json"})
            if (QFileInfo::exists(path + suffix)) return finish("ExistingStoreRefused");
        NodeStore store(path);
        // A competing writer between the initial check and constructor must
        // also be refused. NodeStore's locked digest check rejects a changed
        // baseline from another cooperating NodeStore writer before every save.
        if (QFileInfo::exists(path) || !store.error().isEmpty()) return finish("ExistingStoreRefused");
        report.insert("store_write_attempted", true);
        if (!store.importNodes(expected)
            || !store.saveSubscription({}, subscriptionName, subscriptionUrl, 360, false, "clash", "nodes-only", "system")
            || !store.saveNetworkConfiguration(installerNetworkConfiguration())
            || !store.select(expected.last().id)) return finish("ProductionNodeStoreWriteFailed");
    }
    auto read = [](const QString &name, qint64 limit) {
        QFile file(name);
        if (!file.open(QIODevice::ReadOnly) || file.size() <= 0 || file.size() > limit) return QByteArray{};
        const auto bytes = file.read(limit + 1);
        return bytes.size() <= limit && file.error() == QFile::NoError ? bytes : QByteArray{};
    };
    const auto ciphertext = read(path, 1024 * 1024), selection = read(path + ".selected", 512);
    if (!ciphertext.startsWith("SWIRLNODE1\n") || selection.isEmpty()) return finish("V1EncryptedFixtureRequired");
    for (const auto &node : expected)
        for (const auto &value : {node.name, node.username, node.password})
            if (ciphertext.contains(value.toUtf8())) return finish("PlaintextFixtureRejected");
    if (ciphertext.contains(subscriptionName.toUtf8()) || ciphertext.contains(subscriptionUrl.toEncoded()))
        return finish("PlaintextFixtureRejected");
    NodeStore loaded(path);
    if (!loaded.error().isEmpty() || !loaded.configurationAvailable() || loaded.configurationV2()
        || loaded.nodes().size() != expected.size()) return finish("ProductionNodeStoreReloadFailed");
    const auto nodes = loaded.nodes();
    for (qsizetype i = 0; i < expected.size(); ++i) {
        const auto &a = nodes[i], &b = expected[i];
        if (!sameParameters(a, b) || a.name != b.name || a.sourceId != b.sourceId || a.sourceFormat != b.sourceFormat
            || a.importSource != b.importSource || a.providerAlias != b.providerAlias || a.conversionIssues != b.conversionIssues
            || a.certificateVerificationEnforced != b.certificateVerificationEnforced
            || a.transportType != b.transportType || a.securityType != b.securityType) return finish("FixtureNodeSemanticsChanged");
    }
    const auto subscriptions = loaded.subscriptions();
    if (subscriptions.size() != 1) return finish("FixtureSubscriptionChanged");
    const auto &subscription = subscriptions.first();
    if (QUuid(subscription.id).isNull() || subscription.name != subscriptionName || subscription.url != subscriptionUrl
        || subscription.enabled || subscription.lastSuccess != 0 || subscription.intervalMinutes != 360
        || subscription.formatHint != "clash" || subscription.importScope != "nodes-only" || subscription.downloadRoute != "system")
        return finish("FixtureSubscriptionChanged");
    if (loaded.selectedId() != expected.last().id || loaded.networkConfiguration() != installerNetworkConfiguration())
        return finish("FixtureSelectionOrConfigurationChanged");
    if (read(path, 1024 * 1024) != ciphertext || read(path + ".selected", 512) != selection)
        return finish("ReadOnlyReloadChangedStore");
    report.insert("node_count", nodes.size()); report.insert("subscription_count", subscriptions.size());
    report.insert("node_parameters_match", true); report.insert("selection_matches", true);
    report.insert("disabled_subscription_matches", true); report.insert("network_configuration_matches", true);
    report.insert("dpapi_roundtrip_verified", true); report.insert("plaintext_absent", true);
    report.insert("read_only_reload", true); report.insert("store_format", "SWIRLNODE1");
    report.insert("ciphertext_sha256", QString::fromLatin1(QCryptographicHash::hash(ciphertext, QCryptographicHash::Sha256).toHex()));
    report.insert("selection_sha256", QString::fromLatin1(QCryptographicHash::hash(selection, QCryptographicHash::Sha256).toHex()));
    report.insert("success", true); return finish(nullptr);
}
QJsonObject routeCommand(const QJsonObject &input) {
    auto &library = RustCoreLibrary::instance();
    if (!library.load() || !library.downloadRoute()) return {{"ok", false}};
    const auto request = QJsonDocument(input).toJson(QJsonDocument::Compact);
    QByteArray bytes(4096, '\0');
    const auto length = library.downloadRoute()(reinterpret_cast<const unsigned char *>(request.constData()),
        size_t(request.size()), reinterpret_cast<unsigned char *>(bytes.data()), size_t(bytes.size()));
    if (length <= 0 || length > bytes.size()) return {{"ok", false}};
    bytes.resize(length); return QJsonDocument::fromJson(bytes).object();
}
bool validWindow(const QDateTime &start, const QDateTime &end, const QDateTime &now) {
    return start.isValid() && end.isValid() && start.offsetFromUtc() == 0 && end.offsetFromUtc() == 0
        && start.msecsTo(end) > 0 && start.msecsTo(end) <= 600000 && now >= start && now < end;
}
bool newPrivateDirectory(const QString &path) {
    const QFileInfo info(path);
    if (!info.isAbsolute() || info.exists()) return false;
    QDir ancestor(info.absolutePath());
    do { if (ancestor.exists(".git")) return false; } while (ancestor.cdUp());
    return QDir().mkpath(path);
}

struct Source { int ordinal; QString id; QByteArray originalUrl; QUrl url; };
struct Attempt final : QObject {
    explicit Attempt(QObject *parent) : QObject(parent), client(this), timer(this) { timer.setSingleShot(true); }
    QNetworkAccessManager client; QTimer timer; QNetworkReply *reply = nullptr;
    Source source; QByteArray body; QString failure; QJsonArray sslErrors;
    QElapsedTimer elapsed; qint64 route = 0; bool done = false;
};

// This dedicated downloader deliberately omits the product downloader's format
// negotiation and redirects: the authorization counts exactly one GET/source.
class Acceptance final : public QObject {
public:
    Acceptance(QString directory, QDateTime end, qint64 remaining)
        : directory(std::move(directory)), end(std::move(end)), budget(remaining) {
        clock.start(); deadline.setSingleShot(true); deadline.setTimerType(Qt::PreciseTimer);
        connect(&deadline, &QTimer::timeout, this, [this] { expire(); });
        connect(&probes, &NodeTestService::changed, this, [this] {
            if (probeStarted && !probes.busy()) QTimer::singleShot(0, this, [this] { nextProbeBatch(); });
        });
    }
    bool open() const { return clock.elapsed() < budget && QDateTime::currentDateTimeUtc() < end; }
    int run(const QList<Source> &sources) {
        for (const auto &source : sources) pending.enqueue(source);
        totalSources = sources.size(); deadline.start(int(qMin<qint64>(budget, 600000)));
        QTimer::singleShot(0, this, [this] { pump(); }); loop.exec();
        return writeReport() ? (passed ? 0 : 1) : 3;
    }
    // The same bounded reply path is exercised by loopback self-tests, never by
    // an environment-variable URL or an implicit live mode.
    int fixture(const QUrl &url, int timeoutMs) {
        fixtureOnly = true; fixtureTimeout = timeoutMs; totalSources = 1;
        pending.enqueue(Source{1, "fixture", url.toEncoded(), url});
        deadline.start(int(qMax<qint64>(0, budget)));
        QTimer::singleShot(0, this, [this] { pump(); }); loop.exec();
        return rows.isEmpty() ? 0 : rows.first().toObject().value("httpStatus").toInt();
    }
    QJsonArray rows;
private:
    QString directory; QDateTime end; qint64 budget; QElapsedTimer clock;
    QTimer deadline; QEventLoop loop; QQueue<Source> pending; QSet<Attempt *> active;
    QList<ProxyNode> imported, nodes; QJsonArray privateResults;
    NodeTestService probes; int nextNode = 0, totalSources = 0;
    bool expired = false, probeStarted = false, fixtureOnly = false, durable = true, passed = false;
    int fixtureTimeout = 30000;
    void pump() {
        if (!open()) { expire(); return; }
        if (!durable) { pending.clear(); if (active.isEmpty()) captured(); return; }
        while (!pending.isEmpty() && active.size() < 3 && open()) {
            auto *attempt = new Attempt(this); attempt->source = pending.dequeue(); active.insert(attempt);
            if (!fixtureOnly) {
                const auto route = routeCommand({{"op", "start_once"}, {"host", attempt->source.url.host(QUrl::FullyEncoded)},
                    {"port", attempt->source.url.port(443)}});
                attempt->route = route.value("handle").toInteger();
                if (!route.value("ok").toBool() || attempt->route <= 0) {
                    attempt->failure = "PhysicalRouteUnavailable"; finish(attempt); continue;
                }
                attempt->client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy, "127.0.0.1",
                    quint16(route.value("port").toInt()), route.value("username").toString(), route.value("password").toString()));
            } else attempt->client.setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
            if (!open()) { attempt->failure = "AuthorizationDeadline"; finish(attempt); continue; }
            QNetworkRequest request(attempt->source.url); SwirlNetwork::applyHttp1OnlyPolicy(request);
            auto tls = QSslConfiguration::defaultConfiguration(); tls.setPeerVerifyMode(QSslSocket::VerifyPeer);
            request.setSslConfiguration(tls);
            request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
            request.setRawHeader("User-Agent", "Swirl/" + QCoreApplication::applicationVersion().toUtf8());
            request.setRawHeader("Accept", "application/json, application/yaml, text/yaml, text/plain, */*;q=0.5");
            request.setRawHeader("Accept-Encoding", "identity"); request.setTransferTimeout(30000);
            request.setRawHeader("Connection", "close");
            attempt->elapsed.start(); attempt->reply = attempt->client.get(request);
            attempt->reply->setReadBufferSize(64 * 1024);
            connect(attempt->reply, &QNetworkReply::sslErrors, attempt, [attempt](const QList<QSslError> &errors) {
                for (const auto &error : errors) attempt->sslErrors.append(int(error.error()));
            });
            connect(attempt->reply, &QIODevice::readyRead, attempt, [this, attempt] { read(attempt); });
            connect(attempt->reply, &QNetworkReply::finished, attempt, [this, attempt] { finish(attempt); });
            connect(&attempt->timer, &QTimer::timeout, attempt, [attempt] {
                attempt->failure = "ResponseTimeout"; attempt->reply->abort();
            });
            attempt->timer.start(fixtureTimeout);
        }
        if (pending.isEmpty() && active.isEmpty()) captured();
    }
    void read(Attempt *attempt) {
        if (attempt->done || attempt->body.size() > BodyLimit) return;
        auto *reply = attempt->reply;
        const auto bytes = reply->read(BodyLimit + 1 - attempt->body.size()); attempt->body.append(bytes);
        if (attempt->body.size() > BodyLimit) { attempt->failure = "ResponseBodyLimit"; reply->abort(); }
    }
    void finish(Attempt *attempt) {
        if (attempt->done) return;
        if (attempt->reply) read(attempt);
        if (attempt->done) return;
        attempt->done = true; attempt->timer.stop(); active.remove(attempt);
        int status = 0, networkError = -1; QJsonArray headers;
        if (attempt->reply) {
            attempt->reply->disconnect(attempt);
            status = attempt->reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            networkError = int(attempt->reply->error());
            for (const auto &pair : attempt->reply->rawHeaderPairs())
                headers.append(QJsonArray{QString::fromLatin1(pair.first.toBase64()), QString::fromLatin1(pair.second.toBase64())});
        }
        if (attempt->route > 0) routeCommand({{"op", "stop"}, {"handle", attempt->route}});
        if (attempt->failure.isEmpty()) attempt->failure = status >= 300 && status < 400 ? "RedirectNotFollowed"
            : networkError != 0 ? "NetworkOrTlsRejected" : status != 200 ? "HttpRejected" : "None";
        const auto receipt = QJsonObject{{"schema", 1}, {"sourceId", attempt->source.id},
            {"originalUrlUtf8Base64", QString::fromLatin1(attempt->source.originalUrl.toBase64())},
            {"bodyBase64", QString::fromLatin1(attempt->body.toBase64())}, {"headersBase64", headers},
            {"httpStatus", status}, {"qtError", networkError}, {"sslErrors", attempt->sslErrors},
            {"failureCode", attempt->failure}, {"completedUtc", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)}};
        const auto prefix = directory + QStringLiteral("/source-%1").arg(attempt->source.ordinal);
        const bool sealed = writePrivate(prefix + ".response.dpapi", receipt); durable = durable && sealed;
        int parsedCount = 0, storedCount = 0; bool roundTripOk = false;
        if (!fixtureOnly && sealed && attempt->failure == "None" && open()) {
            const auto parsed = NodeImporter::parse(attempt->body);
            parsedCount = parsed.nodes.size(); QList<ProxyNode> loaded;
            roundTripOk = parsed && roundTrip(prefix + ".nodes.dpapi", parsed.nodes, &loaded);
            if (roundTripOk) { storedCount = loaded.size(); imported.append(loaded); }
            else attempt->failure = parsed ? "EncryptedStoreRoundTripFailed" : "SubscriptionParseRejected";
        }
        rows.append(QJsonObject{{"source", attempt->source.ordinal}, {"attempts", attempt->reply ? 1 : 0},
            {"httpStatus", status}, {"qtError", networkError}, {"sslErrorCodes", attempt->sslErrors},
            {"bodyBytes", attempt->body.size()}, {"elapsedMs", attempt->elapsed.isValid() ? attempt->elapsed.elapsed() : 0},
            {"responseEncrypted", sealed}, {"parsedRecords", parsedCount}, {"storedNodes", storedCount},
            {"storeRoundTrip", roundTripOk}, {"code", sealed ? attempt->failure : "EncryptedReceiptFailed"}});
        attempt->body.fill('\0'); attempt->deleteLater();
        QTimer::singleShot(0, this, [this] { pump(); });
    }
    void captured() {
        if (fixtureOnly) { loop.quit(); return; }
        if (probeStarted) return;
        probeStarted = true;
        if (!imported.isEmpty() && !roundTrip(directory + "/aggregate.nodes.dpapi", imported, &nodes)) durable = false;
        nextProbeBatch();
    }
    void nextProbeBatch() {
        if (probes.busy()) return;
        if (!open() || nextNode >= nodes.size() || !durable) { loop.quit(); return; }
        // No hidden queued nodes: every next group passes the window gate.
        QStringList ids; for (int i = 0; i < 3 && nextNode < nodes.size(); ++i) ids.append(nodes[nextNode++].id);
        EngineStartOptions options; options.nodes = nodes; probes.start(options, ids, ProbeUrl);
    }
    void expire() {
        if (expired) return;
        expired = true; pending.clear();
        const auto running = active;
        for (auto *attempt : running) {
            attempt->failure = "AuthorizationDeadline";
            if (attempt->reply) attempt->reply->abort(); else finish(attempt);
        }
        probes.cancel();
        if (active.isEmpty() && !probes.busy()) loop.quit();
    }
    bool writeReport() {
        QJsonArray publicNodes; int completed = 0, succeeded = 0;
        const QSet<QString> phases{"configuration", "startup", "timeout", "availability", "request", "upstream", "connect", "tls", "http", "origin_tls", "probe_status", "probe_start",
            "input", "dns", "tcp_connect", "outbound_handshake", "outbound_connect", "request_write", "response_headers", "http_status", "cancelled"};
        for (qsizetype i = 0; i < nodes.size(); ++i) {
            const auto result = probes.result(nodes[i].id);
            completed += result.isEmpty() ? 0 : 1; succeeded += result.value("success").toBool() ? 1 : 0;
            privateResults.append(QJsonObject{{"node", i + 1}, {"result", QJsonObject::fromVariantMap(result)}});
            const auto phase = result.value("phase").toString();
            publicNodes.append(QJsonObject{{"node", i + 1}, {"tested", !result.isEmpty()},
                {"success", result.value("success").toBool()}, {"phase", result.isEmpty() ? "not-tested" : phases.contains(phase) ? phase : "other"},
                // The native control contract supplies fixed codes, unlike its
                // source-derived error/message text, which stays encrypted.
                {"failureCode", result.value("failureCode").toString()},
                {"httpStatus", result.value("http").toInt()}, {"httpHeadersMs", result.value("latency", -1).toLongLong()},
                {"outboundConnectMs", result.value("outboundConnectMs", -1).toLongLong()},
                {"originTlsMs", result.value("originTlsMs", -1).toLongLong()}});
        }
        bool allSources = rows.size() == totalSources;
        int getAttempts = 0, parsedRecords = 0, storedRecords = 0;
        for (const auto &row : rows) {
            allSources = allSources && row.toObject().value("storeRoundTrip").toBool();
            getAttempts += row.toObject().value("attempts").toInt();
            parsedRecords += row.toObject().value("parsedRecords").toInt();
            storedRecords += row.toObject().value("storedNodes").toInt();
        }
        durable = writePrivate(directory + "/node-results.dpapi", {{"schema", 1}, {"nodes", privateResults}}) && durable;
        passed = allSources && durable && !nodes.isEmpty() && completed == nodes.size() && succeeded == completed && !expired;
        QJsonObject summary{{"schema", 1}, {"passed", passed}, {"scope", "dedicated QA QNAM + native physical route; Qt NodeStore + NodeTestService"},
            {"sourceSha", RustCoreLibrary::expectedSourceSha()}, {"buildId", RustCoreLibrary::expectedBuildId()},
            {"authorizationExpired", expired || !open()}, {"maxConcurrent", 3}, {"sourceCount", totalSources},
            {"authorizedEndUtc", end.toString(Qt::ISODateWithMs)}, {"elapsedMs", clock.elapsed()},
            {"sourceGetAttempts", getAttempts}, {"sourcesNotAttempted", totalSources - getAttempts},
            {"sourceAttemptsCompleted", rows.size()}, {"sources", rows}, {"distinctNodes", nodes.size()},
            {"parsedNodeRecords", parsedRecords}, {"sourceStoredNodeRecords", storedRecords},
            {"aggregateCoalescedRecords", imported.size() - nodes.size()},
            {"nodesCompleted", completed}, {"nodesSucceeded", succeeded}, {"nodesFailed", completed - succeeded},
            {"nodesNotTested", nodes.size() - completed}, {"nodes", publicNodes},
            {"nodeEgress", "current network routes; no global egress ownership change"},
            {"privateDataEncrypted", durable}, {"automaticUpdates", false}, {"systemNetworkChanged", false},
            {"metric", "HTTP response headers, not RTT"}};
        const bool saved = writeBytes(directory + "/summary.json", QJsonDocument(summary).toJson());
        QTextStream(stdout) << QJsonDocument(summary).toJson(QJsonDocument::Compact) << Qt::endl;
        return saved && durable;
    }
};

int selfTest() {
    QTemporaryDir temporary; int checks = 0; bool ok = temporary.isValid(); QJsonArray failedChecks;
    auto check = [&](bool value) { ++checks; ok = ok && value; if (!value) failedChecks.append(checks); };
    check(QSslSocket::supportsSsl());
    const auto now = QDateTime::currentDateTimeUtc();
    check(validWindow(now.addSecs(-1), now.addSecs(10), now));
    check(!validWindow(now.addSecs(-601), now.addSecs(1), now));
    check(!validWindow(now.addSecs(-10), now, now));
    check(!validWindow(now.addSecs(1), now.addSecs(2), now));
    // Exercise the actual CLI boundary. Even a fresh authorization window
    // cannot replace authenticated billing and enforced wire accounting.
    const auto refusedOutput = temporary.filePath("refused-live-output");
    const auto absentManifest = temporary.filePath("absent-manifest.dpapi");
    const QList<QStringList> liveCommands{
        {"--live", absentManifest, now.addSecs(-1).toString(Qt::ISODateWithMs),
            now.addSecs(60).toString(Qt::ISODateWithMs), refusedOutput},
        {"--live", absentManifest, now.addSecs(-60).toString(Qt::ISODateWithMs),
            now.addSecs(-1).toString(Qt::ISODateWithMs), refusedOutput},
        {"--live"}
    };
    for (const auto &arguments : liveCommands) {
        QProcess process;
        process.start(QCoreApplication::applicationFilePath(), arguments);
        const bool finished = process.waitForFinished(5000);
        if (!finished) { process.kill(); process.waitForFinished(1000); }
        const auto response = QJsonDocument::fromJson(process.readAllStandardOutput()).object();
        check(finished && process.exitStatus() == QProcess::NormalExit && process.exitCode() == 2
            && response == QJsonObject{{"errorCode", "AuthenticatedBillingAndWireGuardRequired"}, {"networkStarted", false}}
            && !QFileInfo::exists(refusedOutput));
    }
    const QJsonObject privateFixture{{"secret", "synthetic-private-value"}};
    check(writePrivate(temporary.filePath("receipt.dpapi"), privateFixture));
    check(QJsonDocument::fromJson(readPrivate(temporary.filePath("receipt.dpapi"))).object() == privateFixture);
    QTcpServer server; check(server.listen(QHostAddress::LocalHost)); int requests = 0;
    QByteArray lastTarget; bool unexpectedBody = false;
    QObject::connect(&server, &QTcpServer::newConnection, &server, [&] {
        while (auto *socket = server.nextPendingConnection()) {
            QObject::connect(socket, &QTcpSocket::readyRead, socket, [socket, &requests, &lastTarget, &unexpectedBody] {
                if (socket->property("handled").toBool()) { unexpectedBody = unexpectedBody || !socket->readAll().isEmpty(); return; }
                const auto wire = socket->property("request").toByteArray() + socket->readAll();
                if (wire.size() > 16384 || (wire.size() >= 4 && !wire.startsWith("GET "))) { socket->disconnectFromHost(); return; }
                const auto headerEnd = wire.indexOf("\r\n\r\n");
                if (headerEnd < 0) { socket->setProperty("request", wire); return; }
                unexpectedBody = unexpectedBody || wire.size() > headerEnd + 4;
                lastTarget = wire.left(wire.indexOf("\r\n")).split(' ').value(1);
                socket->setProperty("handled", true);
                ++requests;
                if (wire.startsWith("GET /redirect ")) socket->write("HTTP/1.1 302 Found\r\nLocation: /second\r\nContent-Length: 0\r\n\r\n");
                else if (wire.startsWith("GET /large ")) { socket->write("HTTP/1.1 200 OK\r\nContent-Length: 4194305\r\n\r\n"); socket->write(QByteArray(BodyLimit + 1, 'x')); }
                else if (wire.startsWith("GET /hang ")) return;
                else if (wire.startsWith("GET /close ")) { socket->abort(); return; }
                else socket->write("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                socket->disconnectFromHost();
            });
            QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
        }
    });
    auto fixture = [&](const char *path, int budget = 5000, int timeout = 3000, bool tls = false, quint16 port = 0) {
        auto run = std::make_unique<Acceptance>(temporary.path(), QDateTime::currentDateTimeUtc().addMSecs(budget), budget);
        run->fixture(QUrl(QString("%1://127.0.0.1:%2%3").arg(tls ? "https" : "http").arg(port ? port : server.serverPort()).arg(path)), timeout);
        return run->rows.isEmpty() ? QJsonObject{} : run->rows.first().toObject();
    };
    const int before = requests; const auto redirect = fixture("/redirect");
    check(redirect.value("code") == "RedirectNotFollowed" && requests == before + 1 && redirect.value("attempts") == 1);
    check(fixture("/ok").value("httpStatus") == 200);
    check(fixture("/ok?token=synthetic%2Fopaque&value=%2B%3D").value("httpStatus") == 200
        && lastTarget == "/ok?token=synthetic%2Fopaque&value=%2B%3D" && !unexpectedBody);
    // This observable TCP gate models start_once's post-authentication upstream
    // permit. Native tests separately verify credentials, target and atomicity.
    QTcpServer gate; check(gate.listen(QHostAddress::LocalHost)); int gateAccepts = 0, upstreamsOpened = 0;
    bool upstreamPermitClaimed = false;
    QObject::connect(&gate, &QTcpServer::newConnection, &gate, [&] {
        while (auto *peer = gate.nextPendingConnection()) {
            ++gateAccepts;
            if (upstreamPermitClaimed) { peer->abort(); peer->deleteLater(); continue; }
            upstreamPermitClaimed = true; auto *upstream = new QTcpSocket(peer);
            QObject::connect(peer, &QTcpSocket::readyRead, peer, [peer, upstream] {
                auto bytes = peer->property("pending").toByteArray() + peer->readAll();
                if (bytes.size() > 16384) { peer->abort(); return; }
                if (upstream->state() == QAbstractSocket::ConnectedState) { upstream->write(bytes); bytes.clear(); }
                peer->setProperty("pending", bytes);
            });
            QObject::connect(upstream, &QTcpSocket::connected, peer, [peer, upstream, &upstreamsOpened] {
                ++upstreamsOpened;
                upstream->write(peer->property("pending").toByteArray()); peer->setProperty("pending", QByteArray());
            });
            QObject::connect(upstream, &QTcpSocket::readyRead, peer, [peer, upstream] { peer->write(upstream->readAll()); });
            QObject::connect(upstream, &QTcpSocket::disconnected, peer, [peer] { peer->disconnectFromHost(); });
            QObject::connect(upstream, &QTcpSocket::errorOccurred, peer, [peer](QAbstractSocket::SocketError error) {
                if (error != QAbstractSocket::RemoteHostClosedError) peer->abort();
            });
            QObject::connect(peer, &QTcpSocket::disconnected, peer, &QObject::deleteLater);
            upstream->connectToHost(QHostAddress::LocalHost, server.serverPort());
        }
    });
    const int beforeClosed = requests;
    const auto closed = fixture("/close", 5000, 3000, false, gate.serverPort());
    const int closeWireRequests = requests - beforeClosed;
    check(closed.value("code") == "NetworkOrTlsRejected" && closeWireRequests == 1 && upstreamsOpened == 1);
    check(fixture("/large").value("code") == "ResponseBodyLimit");
    check(fixture("/hang", 5000, 20).value("code") == "ResponseTimeout");
    check(fixture("/hang", 20, 5000).value("code") == "AuthorizationDeadline");
    check(fixture("/ok", 5000, 3000, true).value("code") == "NetworkOrTlsRejected");
    const int beforeExpired = requests; check(fixture("/ok", 0).isEmpty() && requests == beforeExpired);
    const auto parsed = NodeImporter::parse("ss://YWVzLTEyOC1nY206dGVzdA@fixture.invalid:443#test");
    QList<ProxyNode> reloaded; check(parsed && roundTrip(temporary.filePath("nodes.dpapi"), parsed.nodes, &reloaded) && reloaded.size() == 1);
    // Observe the real NodeTestService/Rust HEAD method and exact configured
    // path through an independent loopback SOCKS peer. No public node is used.
    QTcpServer probeOrigin; QHash<quint16, QString> exits; SocksPeer relay(&exits, "qa-method-fixture");
    check(probeOrigin.listen(QHostAddress::LocalHost) && relay.listen(QHostAddress::LocalHost));
    relay.targetPorts = {probeOrigin.serverPort()}; QByteArray probeLine;
    QObject::connect(&probeOrigin, &QTcpServer::newConnection, &probeOrigin, [&] {
        while (auto *socket = probeOrigin.nextPendingConnection()) {
            QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
            QObject::connect(socket, &QTcpSocket::readyRead, socket, [socket, &probeLine] {
                const auto wire = socket->property("headers").toByteArray() + socket->readAll();
                if (wire.size() > 16384) { socket->abort(); return; }
                if (!wire.contains("\r\n\r\n")) { socket->setProperty("headers", wire); return; }
                probeLine = wire.left(wire.indexOf("\r\n"));
                socket->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
                socket->disconnectFromHost();
            });
        }
    });
    ProxyNode node; node.id = QUuid::createUuid().toString(QUuid::WithoutBraces); node.name = "QA method fixture";
    node.protocol = "socks5"; node.host = "127.0.0.1"; node.port = relay.serverPort();
    EngineStartOptions options; options.nodes = {node}; NodeTestService probes;
    QEventLoop probeLoop; QTimer probeDeadline; probeDeadline.setSingleShot(true);
    QObject::connect(&probes, &NodeTestService::changed, &probeLoop, [&] { if (!probes.busy()) probeLoop.quit(); });
    QObject::connect(&probeDeadline, &QTimer::timeout, &probeLoop, &QEventLoop::quit);
    probes.start(options, {node.id}, QUrl(QString("http://127.0.0.1:%1%2").arg(probeOrigin.serverPort()).arg(ProbeUrl.path(QUrl::FullyEncoded))));
    if (probes.busy()) { probeDeadline.start(20000); probeLoop.exec(); }
    check(!probes.busy() && probes.result(node.id).value("success").toBool() && relay.forwarded == 1
        && probeLine == "HEAD " + ProbeUrl.path(QUrl::FullyEncoded).toUtf8() + " HTTP/1.1");
    probes.cancel(); if (probes.busy()) { probeDeadline.start(5000); probeLoop.exec(); }
    check(!probes.busy());
    QTextStream(stdout) << QJsonDocument(QJsonObject{{"selfTest", ok ? "passed" : "failed"},
        {"checks", checks}, {"failedChecks", failedChecks}, {"closeWireRequests", closeWireRequests},
        {"closeGateAccepts", gateAccepts}, {"closeGateUpstreamsOpened", upstreamsOpened},
        {"providerRequests", 0}, {"realNodeRequests", 0}}).toJson(QJsonDocument::Compact) << Qt::endl;
    return ok ? 0 : 1;
}
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv); QCoreApplication::setApplicationVersion(QStringLiteral(SWIRL_QA_APP_VERSION));
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext &, const QString &) {});
    const auto args = app.arguments();
    auto fail = [](const char *code) {
        QTextStream(stdout) << QJsonDocument(QJsonObject{{"errorCode", code}, {"networkStarted", false}})
            .toJson(QJsonDocument::Compact) << Qt::endl; return 2;
    };
    // The legacy live harness has no authenticated provider accounting,
    // persistent transport reservation or enforced wire-byte cancellation.
    // Refuse before reading private inputs or creating any network runtime.
    if (args.size() > 1 && args[1] == "--live") return fail("AuthenticatedBillingAndWireGuardRequired");
    if (args.size() > 1 && args[1] == "--installer-store-fixture") return installerStoreFixture(args);
    if (args.size() == 2 && args[1] == "--self-test") return selfTest();
    if (args.size() == 4 && args[1] == "--offline-body") {
        if (!newPrivateDirectory(args[3])) return fail("NewPrivateDirectoryRequired");
        auto body = readPrivate(args[2]); const auto parsed = NodeImporter::parse(body); body.fill('\0'); QList<ProxyNode> nodes;
        const bool ok = parsed && roundTrip(args[3] + "/offline.nodes.dpapi", parsed.nodes, &nodes);
        QTextStream(stdout) << QJsonDocument(QJsonObject{{"offlineOnly", true}, {"networkRequests", 0},
            {"passed", ok}, {"parsedRecords", parsed.nodes.size()}, {"storedNodes", nodes.size()}}).toJson(QJsonDocument::Compact) << Qt::endl;
        return ok ? 0 : 1;
    }
    if (args.size() != 6 || args[1] != "--live") return fail("DefaultOfflineExplicitLiveWindowRequired");
    const auto start = QDateTime::fromString(args[3], Qt::ISODateWithMs).toUTC();
    const auto end = QDateTime::fromString(args[4], Qt::ISODateWithMs).toUTC();
    const auto now = QDateTime::currentDateTimeUtc();
    if (!validWindow(start, end, now)) return fail("AuthorizationWindowInvalidOrExpired");
    if (!QSslSocket::supportsSsl()) return fail("TlsBackendUnavailable");
    if (QSslConfiguration::defaultConfiguration().peerVerifyMode() == QSslSocket::VerifyNone) return fail("TlsVerificationRequired");
    auto bytes = readPrivate(args[2]); const auto manifest = QJsonDocument::fromJson(bytes).object(); bytes.fill('\0');
    const auto entries = manifest.value("subscriptions").toArray();
    if (manifest.value("schema").toInt() != 1 || entries.size() != 6) return fail("SixSourceManifestRequired");
    QList<Source> sources; QSet<QString> ids;
    for (const auto &entry : entries) {
        const auto object = entry.toObject(); const auto id = object.value("id").toString();
        const auto raw = object.value("url").toString().toUtf8(); const auto url = QUrl::fromEncoded(raw, QUrl::StrictMode);
        if (!QRegularExpression("^[A-Za-z0-9_-]{1,64}$").match(id).hasMatch() || ids.contains(id)
            || raw.size() > 8192 || !url.isValid() || url.scheme() != "https" || url.host().isEmpty()
            || !url.userInfo().isEmpty() || url.hasFragment() || url.toEncoded() != raw) return fail("ManifestSourceRejected");
        ids.insert(id); sources.append(Source{int(sources.size() + 1), id, raw, url});
    }
    if (!newPrivateDirectory(args[5])) return fail("NewPrivateDirectoryRequired");
    if (!writePrivate(args[5] + "/manifest-snapshot.dpapi", {{"schema", 1}, {"manifest", manifest},
        {"windowStartUtc", start.toString(Qt::ISODateWithMs)}, {"windowEndUtc", end.toString(Qt::ISODateWithMs)}}))
        return fail("ManifestSnapshotFailed");
    const auto remaining = QDateTime::currentDateTimeUtc().msecsTo(end);
    if (remaining <= 0) return fail("AuthorizationWindowInvalidOrExpired");
    Acceptance acceptance(args[5], end, remaining); return acceptance.run(sources);
}

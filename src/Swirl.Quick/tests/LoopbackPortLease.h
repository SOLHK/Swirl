#pragma once

// Test-only reservations. TCP/UDP exclusion tables are independent on Windows.
// Filter only a successfully read snapshot, keep rejected owners bound, and
// never treat an unexplained access denial as an address collision.
#include <QCryptographicHash>
#include <QDebug>
#include <QDir>
#include <QElapsedTimer>
#include <QFileInfo>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkProxy>
#include <QProcess>
#include <QRegularExpression>
#include <QSet>
#include <QTcpServer>
#include <QUdpSocket>
#include <algorithm>
#include <memory>
#include <vector>
#ifdef Q_OS_WIN
#include <QtCore/qt_windows.h>
#endif

namespace SwirlFixturePorts {

inline bool parseExclusions(const QByteArray &output, QSet<quint16> &ports, QString &error) {
    ports.clear();
    error.clear();
    bool table = false;
    QSet<quint16> parsed;
    const QRegularExpression separator(QStringLiteral("^-+\\s+-+$"));
    const QRegularExpression row(QStringLiteral("^([0-9]+)\\s+([0-9]+)\\s*\\*?$"));
    for (const auto &bytes : output.split('\n')) {
        const auto line = QString::fromLatin1(bytes.trimmed());
        if (separator.match(line).hasMatch()) { table = true; continue; }
        if (!table || line.isEmpty() || line.startsWith(QLatin1String("* -"))) continue;
        const auto match = row.match(line);
        bool firstOk = false, lastOk = false;
        const uint first = match.captured(1).toUInt(&firstOk);
        const uint last = match.captured(2).toUInt(&lastOk);
        if (!match.hasMatch() || !firstOk || !lastOk || first == 0 || last < first || last > 65535) {
            error = QStringLiteral("InvalidPortExclusionRow");
            return false;
        }
        for (uint port = first; port <= last; ++port) parsed.insert(quint16(port));
    }
    if (!table) { error = QStringLiteral("PortExclusionTableMissing"); return false; }
    ports = std::move(parsed);
    return true;
}

struct Snapshot {
    bool valid = false;
    QSet<quint16> excluded;
    QString id;
    QString error;
};

inline Snapshot readSnapshot() {
    Snapshot snapshot;
    QJsonObject evidence{{"family", "ipv4"}, {"scope", "Read-only fixture port exclusions"}};
    QJsonArray queries;
#ifdef Q_OS_WIN
    wchar_t systemDirectory[MAX_PATH]{};
    const auto length = GetSystemDirectoryW(systemDirectory, MAX_PATH);
    const QString executable = length > 0 && length < MAX_PATH
        ? QDir(QString::fromWCharArray(systemDirectory, int(length))).filePath("netsh.exe") : QString();
    if (executable.isEmpty() || !QFileInfo(executable).isAbsolute() || !QFileInfo(executable).isFile())
        snapshot.error = QStringLiteral("PortExclusionSystemToolUnavailable");
    for (const auto &protocol : {QStringLiteral("tcp"), QStringLiteral("udp")}) {
        if (!snapshot.error.isEmpty()) break;
        const QStringList arguments{"interface", "ipv4", "show", "excludedportrange", "protocol=" + protocol};
        QProcess process;
        process.setProgram(executable);
        process.setArguments(arguments);
        QElapsedTimer timer;
        timer.start();
        process.start(QIODevice::ReadOnly);
        const bool started = process.waitForStarted(int(std::max<qint64>(0, 10000 - timer.elapsed())));
        QByteArray output, errors;
        qint64 outputBytes = 0, errorBytes = 0;
        QCryptographicHash outputHash(QCryptographicHash::Sha256), errorHash(QCryptographicHash::Sha256);
        constexpr qsizetype limit = 1048576;
        const auto drain = [&] {
            const auto out = process.readAllStandardOutput(), err = process.readAllStandardError();
            outputBytes += out.size(); errorBytes += err.size();
            outputHash.addData(out); errorHash.addData(err);
            output += out.left(std::max<qsizetype>(0, limit - output.size()));
            errors += err.left(std::max<qsizetype>(0, limit - errors.size()));
        };
        while (started && process.state() != QProcess::NotRunning && timer.elapsed() < 10000) {
            drain();
            if (outputBytes > limit || errorBytes > limit) break;
            process.waitForFinished(int(std::max<qint64>(0, std::min<qint64>(50, 10000 - timer.elapsed()))));
        }
        drain();
        const bool timedOut = process.state() != QProcess::NotRunning && timer.elapsed() >= 10000;
        bool oversized = outputBytes > limit || errorBytes > limit;
        const bool killed = process.state() != QProcess::NotRunning;
        if (killed) { process.kill(); process.waitForFinished(2000); drain(); }
        oversized = oversized || outputBytes > limit || errorBytes > limit;
        const bool exitConfirmed = process.state() == QProcess::NotRunning;
        QJsonObject query{{"executable", executable}, {"arguments", QJsonArray::fromStringList(arguments)},
            {"protocol", protocol}, {"started", started}, {"workDeadlineMs", 10000},
            {"elapsedMs", double(timer.elapsed())}, {"timedOut", timedOut}, {"killRequested", killed},
            {"exitConfirmed", exitConfirmed}, {"exitCode", exitConfirmed ? process.exitCode() : -1},
            {"normalExit", exitConfirmed && process.exitStatus() == QProcess::NormalExit},
            {"stdoutBytes", double(outputBytes)}, {"stderrBytes", double(errorBytes)},
            {"outputLimitExceeded", oversized}, {"stdoutBase64", QString::fromLatin1(output.toBase64())},
            {"stderrBase64", QString::fromLatin1(errors.toBase64())},
            {"stdoutSha256", QString::fromLatin1(outputHash.result().toHex())},
            {"stderrSha256", QString::fromLatin1(errorHash.result().toHex())}};
        QSet<quint16> ports;
        if (!started || timedOut || oversized || !exitConfirmed || process.exitStatus() != QProcess::NormalExit || process.exitCode() != 0)
            snapshot.error = QStringLiteral("PortExclusionQueryFailed");
        else if (parseExclusions(output, ports, snapshot.error)) snapshot.excluded.unite(ports);
        query["parseAccepted"] = snapshot.error.isEmpty();
        queries.append(query);
    }
#else
    evidence["source"] = QStringLiteral("No Windows exclusion table on this platform");
#endif
    snapshot.valid = snapshot.error.isEmpty();
    evidence["queries"] = queries;
    evidence["valid"] = snapshot.valid;
    evidence["error"] = snapshot.error;
    evidence["excludedCount"] = snapshot.excluded.size();
    const auto bytes = QJsonDocument(evidence).toJson(QJsonDocument::Compact);
    snapshot.id = QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
    evidence["snapshotSha256"] = snapshot.id;
    qInfo().noquote() << "FIXTURE_PORT_EXCLUSION_SNAPSHOT" << QJsonDocument(evidence).toJson(QJsonDocument::Compact);
    return snapshot;
}

inline const Snapshot &exclusions() {
    static const Snapshot snapshot = readSnapshot();
    return snapshot;
}

struct BindResult {
    bool success = false;
    QAbstractSocket::SocketError error = QAbstractSocket::UnknownSocketError;
    QString text;
};
template<class Owner> struct Candidate {
    Owner owner;
    quint16 port = 0;
    QAbstractSocket::SocketError error = QAbstractSocket::UnknownSocketError;
    QString text;
};
struct Selection {
    quint16 candidate = 0;
    int candidates = 0, filtered = 0, controlConflicts = 0, collisions = 0, heldOwners = 0;
    QString stage, text;
    QAbstractSocket::SocketError error = QAbstractSocket::UnknownSocketError;
    QJsonArray filteredSample;
    QJsonObject json(quint16 control, const QString &snapshot) const {
        return {{"stage", stage}, {"candidate", candidate}, {"controlPort", control},
                {"qtSocketError", int(error)}, {"errorText", text}, {"candidates", candidates},
                {"excludedCandidates", filtered}, {"controlConflicts", controlConflicts},
                {"collisionAttempts", collisions}, {"collisionLimit", 32}, {"heldOwners", heldOwners},
                {"filteredSample", filteredSample}, {"filteredSampleTruncated", filtered + controlConflicts > 32},
                {"exclusionSnapshotSha256", snapshot}};
    }
};

// The injectable operations exercise the same lifetime and error policy in
// negative controls. Only a returned real owner makes a candidate selectable.
template<class Owner, class ReserveUdp, class ListenTcp>
Owner selectPair(const QSet<quint16> &excluded, quint16 control, ReserveUdp reserveUdp,
                 ListenTcp listenTcp, Selection &result) {
    if (excluded.size() == 65535) {
        result.stage = QStringLiteral("exclusion-precheck");
        result.text = QStringLiteral("NoUnexcludedFixturePort");
        return {};
    }
    std::vector<Owner> held;
    QSet<quint16> heldPorts;
    for (;;) {
        result.heldOwners = int(held.size());
        auto candidate = reserveUdp();
        ++result.candidates;
        result.candidate = candidate.port;
        result.stage = QStringLiteral("udp-bind");
        result.error = candidate.error;
        result.text = candidate.text;
        if (!candidate.owner || candidate.port == 0) return {};
        if (heldPorts.contains(candidate.port)) {
            result.text = QStringLiteral("FixtureAllocatorReusedHeldPort");
            return {};
        }
        if (excluded.contains(candidate.port) || candidate.port == control) {
            if (excluded.contains(candidate.port)) ++result.filtered;
            else ++result.controlConflicts;
            if (result.filteredSample.size() < 32) result.filteredSample.append(int(candidate.port));
        } else {
            const auto bind = listenTcp(candidate.port);
            result.stage = QStringLiteral("tcp-listen");
            result.error = bind.error;
            result.text = bind.text;
            if (bind.success) return std::move(candidate.owner);
            if (bind.error != QAbstractSocket::AddressInUseError || ++result.collisions == 32) return {};
        }
        heldPorts.insert(candidate.port);
        held.push_back(std::move(candidate.owner));
    }
}
} // namespace SwirlFixturePorts

class LoopbackPortLease final {
public:
    bool reserve() {
        release();
        m_controlPort = 0;
        m_proxyPort = 0;
        m_error.clear();
        m_control.setProxy(QNetworkProxy::NoProxy);
        m_tcp.setProxy(QNetworkProxy::NoProxy);
        const auto &snapshot = SwirlFixturePorts::exclusions();
        SwirlFixturePorts::Selection result;
        const auto fail = [&] {
            m_error = QString::fromUtf8(QJsonDocument(result.json(m_control.serverPort(), snapshot.id)).toJson(QJsonDocument::Compact));
            release();
            return false;
        };
        if (!snapshot.valid) {
            result.stage = QStringLiteral("exclusion-snapshot");
            result.text = snapshot.error;
            return fail();
        }
        if (!m_control.listen(QHostAddress::LocalHost, 0)) {
            result.stage = QStringLiteral("control-tcp-listen");
            result.error = m_control.serverError();
            result.text = m_control.errorString();
            return fail();
        }
        using Owner = std::unique_ptr<QUdpSocket>;
        m_udp = SwirlFixturePorts::selectPair<Owner>(snapshot.excluded, m_control.serverPort(), [] {
            auto socket = std::make_unique<QUdpSocket>();
            socket->setProxy(QNetworkProxy::NoProxy);
            if (!socket->bind(QHostAddress::LocalHost, 0, QUdpSocket::DontShareAddress))
                return SwirlFixturePorts::Candidate<Owner>{{}, 0, socket->error(), socket->errorString()};
            const auto port = socket->localPort();
            return SwirlFixturePorts::Candidate<Owner>{std::move(socket), port, QAbstractSocket::UnknownSocketError, {}};
        }, [&](quint16 port) {
            if (m_tcp.listen(QHostAddress::LocalHost, port)) return SwirlFixturePorts::BindResult{true, QAbstractSocket::UnknownSocketError, {}};
            const auto error = m_tcp.serverError();
            const auto text = m_tcp.errorString();
            m_tcp.close();
            return SwirlFixturePorts::BindResult{false, error, text};
        }, result);
        if (!m_udp) return fail();
        m_controlPort = m_control.serverPort();
        m_proxyPort = m_udp->localPort();
        return true;
    }

    void release() {
        m_tcp.close();
        m_udp.reset();
        m_control.close();
    }

    quint16 controlPort() const { return m_controlPort; }
    quint16 proxyPort() const { return m_proxyPort; }
    QString errorString() const { return m_error; }

private:
    QTcpServer m_control;
    QTcpServer m_tcp;
    std::unique_ptr<QUdpSocket> m_udp;
    quint16 m_controlPort = 0;
    quint16 m_proxyPort = 0;
    QString m_error;
};

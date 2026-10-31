#include "network/LanFirewall.h"

#include <QCoreApplication>
#include <QJsonDocument>
#include <QSaveFile>
#include <QTimer>
#include <QtTest>

class LanFirewallTests final : public QObject {
    Q_OBJECT
private:
    void exercise(LanFirewall::FixtureCase scenario) {
        const auto result = LanFirewall::exerciseNativeFixture(scenario);
        QVERIFY2(result.ok, qUtf8Printable(result.error));
        QCOMPARE(result.record.value("native_com"), QJsonValue(true));
        QCOMPARE(result.record.value("enabled"), QJsonValue(false));
        QCOMPARE(result.record.value("local_address"), QJsonValue("127.0.0.1"));
        QCOMPARE(result.record.value("remote_addresses"), QJsonValue("127.0.0.1/32"));
        QCOMPARE(result.record.value("tcp_and_udp"), QJsonValue(true));
        QCOMPARE(result.record.value("cleanup_complete"), QJsonValue(true));
        if (scenario == LanFirewall::FixtureCase::CrashRecoveryConflict) {
            for (const char *key : {"production_journal_valid", "live_owner_rejected", "wrong_session_rejected",
                                   "dead_owner", "recovery_refused", "foreign_rules_preserved",
                                   "independent_rules_preserved", "recovery_journal_unchanged"})
                QCOMPARE(result.record.value(QLatin1String(key)), QJsonValue(true));
        }
        qInfo().noquote() << QJsonDocument(result.record).toJson(QJsonDocument::Compact);
    }
private slots:
    void disabledTcpAndUdpRoundtripAndOwnedRemoval() {
        exercise(LanFirewall::FixtureCase::RoundTrip);
    }
    void externalEditPreservesRulesAndEncryptedJournal() {
        exercise(LanFirewall::FixtureCase::ExternalEdit);
    }
    void ownedCleanupLeavesIndependentFixtureUntouched() {
        exercise(LanFirewall::FixtureCase::IndependentOwnership);
    }
    void deadOwnerRecoveryRejectsForeignRulesAndPreservesJournals() {
        exercise(LanFirewall::FixtureCase::CrashRecoveryConflict);
    }
};

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (qEnvironmentVariable("SWIRL_LAN_FIREWALL_TEST") != "1") {
        qCritical("Native Windows firewall fixture requires SWIRL_LAN_FIREWALL_TEST=1; no rules were changed.");
        return 2;
    }
    // A real, bounded owner process for the recovery fixture. This child never
    // creates a firewall rule; the parent records its PID and creation time.
    const auto arguments = app.arguments();
    if (arguments.size() == 3 && arguments.at(1) == "--fixture-owner") {
        QSaveFile ready(arguments.at(2));
        const auto identity = QByteArray::number(QCoreApplication::applicationPid());
        if (!ready.open(QIODevice::WriteOnly) || ready.write(identity) != identity.size() || !ready.commit())
            return 3;
        QTimer::singleShot(15000, &app, &QCoreApplication::quit);
        return app.exec();
    }
    LanFirewallTests tests;
    return QTest::qExec(&tests, argc, argv);
}

#include "LanFirewallTests.moc"

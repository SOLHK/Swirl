#include "network/LanFirewall.h"

#include <QCoreApplication>
#include <QJsonDocument>
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
};

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (qEnvironmentVariable("SWIRL_LAN_FIREWALL_TEST") != "1") {
        qCritical("Native Windows firewall fixture requires SWIRL_LAN_FIREWALL_TEST=1; no rules were changed.");
        return 2;
    }
    LanFirewallTests tests;
    return QTest::qExec(&tests, argc, argv);
}

#include "LanFirewallTests.moc"


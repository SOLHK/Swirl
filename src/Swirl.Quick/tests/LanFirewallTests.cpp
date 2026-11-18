#include "network/LanFirewall.h"

#include <QCoreApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSaveFile>
#include <QTimer>
#include <QtTest>

class LanFirewallTests final : public QObject {
    Q_OBJECT
private:
    void requireDiagnostic(const QJsonObject &diagnostic) {
        QVERIFY(!diagnostic.isEmpty());
        QVERIFY(diagnostic.value("operation").isString());
        QVERIFY(!diagnostic.value("operation").toString().isEmpty());
        QVERIFY(diagnostic.value("property").isString());
        QVERIFY(QRegularExpression(QStringLiteral("^0x[0-9a-f]{8}$"))
                    .match(diagnostic.value("hresult").toString()).hasMatch());
        QVERIFY(diagnostic.value("hresult_source").isString());
        QVERIFY(diagnostic.value("value_type").isString());
        QVERIFY(diagnostic.value("value_summary").isObject());
        QVERIFY(diagnostic.value("add_attempted").isBool());
        QVERIFY(diagnostic.value("add_succeeded").isBool());
        QVERIFY(diagnostic.value("persisted_rule_state").isString());
        QVERIFY(diagnostic.value("ownership_state").isString());
        QVERIFY(diagnostic.value("cleanup_required").isBool());
        QVERIFY(diagnostic.value("partial_persistence_possible").isBool());
        QVERIFY(diagnostic.value("recovery_action").isString());
        QVERIFY(diagnostic.value("verification").isObject());
    }
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
        if (scenario == LanFirewall::FixtureCase::InvalidProperty) {
            const auto diagnostic = result.diagnostic;
            requireDiagnostic(diagnostic);
            QCOMPARE(diagnostic.value("operation"), QJsonValue("INetFwRule::put_Protocol"));
            QCOMPARE(diagnostic.value("property"), QJsonValue("Protocol"));
            QCOMPARE(diagnostic.value("hresult"), QJsonValue("0x80070057"));
            QCOMPARE(diagnostic.value("hresult_source"), QJsonValue("native_hresult"));
            QCOMPARE(diagnostic.value("value_type"), QJsonValue("LONG"));
            QCOMPARE(diagnostic.value("value_summary").toObject().value("value"), QJsonValue(257));
            QCOMPARE(diagnostic.value("add_attempted"), QJsonValue(false));
            QCOMPARE(diagnostic.value("add_succeeded"), QJsonValue(false));
            QCOMPARE(diagnostic.value("persisted_rule_state"), QJsonValue("not_added"));
            QCOMPARE(diagnostic.value("cleanup_required"), QJsonValue(false));
            QCOMPARE(result.record.value("native_failure_matched"), QJsonValue(true));
            QCOMPARE(result.record.value("redaction_checked"), QJsonValue(true));
            QCOMPARE(result.record.value("invalid_rule_absent"), QJsonValue(true));
            QCOMPARE(result.record.value("recovery_journal_unchanged"), QJsonValue(true));
        }
        if (scenario == LanFirewall::FixtureCase::AddFailure) {
            const auto absent = result.diagnostic;
            const auto existing = absent.value("existing_state").toObject();
            const auto mismatched = absent.value("mismatched_state").toObject();
            for (const auto &diagnostic : {absent, existing, mismatched}) {
                requireDiagnostic(diagnostic);
                QCOMPARE(diagnostic.value("operation"), QJsonValue("INetFwRules::Add"));
                QCOMPARE(diagnostic.value("hresult"), result.record.value("native_add_hresult"));
                QCOMPARE(diagnostic.value("hresult_source"), QJsonValue("native_hresult"));
                QCOMPARE(diagnostic.value("add_attempted"), QJsonValue(true));
                QCOMPARE(diagnostic.value("add_succeeded"), QJsonValue(false));
            }
            QCOMPARE(absent.value("persisted_rule_state"), QJsonValue("absent"));
            QCOMPARE(absent.value("cleanup_required"), QJsonValue(false));
            QCOMPARE(existing.value("persisted_rule_state"), QJsonValue("present"));
            QCOMPARE(existing.value("ownership_state"), QJsonValue("owned"));
            QCOMPARE(existing.value("cleanup_required"), QJsonValue(true));
            QCOMPARE(mismatched.value("persisted_rule_state"), QJsonValue("present"));
            QCOMPARE(mismatched.value("ownership_state"), QJsonValue("mismatch"));
            QCOMPARE(mismatched.value("recovery_action"), QJsonValue("preserve_journal_admin_review"));
            QCOMPARE(result.record.value("null_rule_add_native"), QJsonValue(true));
            QCOMPARE(result.record.value("post_add_absence_confirmed"), QJsonValue(true));
            QCOMPARE(result.record.value("existing_rules_unchanged"), QJsonValue(true));
            QCOMPARE(result.record.value("recovery_journal_unchanged"), QJsonValue(true));
        }
        if (scenario == LanFirewall::FixtureCase::ReadbackMismatch) {
            const auto diagnostic = result.diagnostic;
            requireDiagnostic(diagnostic);
            QCOMPARE(diagnostic.value("operation"), QJsonValue("INetFwRules::Add"));
            QCOMPARE(diagnostic.value("hresult"), QJsonValue("0x00000000"));
            QCOMPARE(diagnostic.value("hresult_source"), QJsonValue("native_hresult"));
            QCOMPARE(diagnostic.value("add_attempted"), QJsonValue(true));
            QCOMPARE(diagnostic.value("add_succeeded"), QJsonValue(true));
            QCOMPARE(diagnostic.value("persisted_rule_state"), QJsonValue("present_mismatch"));
            QCOMPARE(diagnostic.value("ownership_state"), QJsonValue("mismatch"));
            QCOMPARE(diagnostic.value("cleanup_required"), QJsonValue(true));
            QCOMPARE(diagnostic.value("recovery_action"), QJsonValue("preserve_journal_admin_review"));
            QVERIFY(diagnostic.value("verification").toObject().value("mismatched_properties")
                        .toArray().contains(QJsonValue("direction")));
            const auto cleanup = diagnostic.value("cleanup_refusal").toObject();
            requireDiagnostic(cleanup);
            QCOMPARE(cleanup.value("ownership_state"), QJsonValue("mismatch"));
            QCOMPARE(cleanup.value("removed_count"), QJsonValue(0));
            QCOMPARE(cleanup.value("journal_retained"), QJsonValue(true));
            QCOMPARE(result.record.value("native_add_succeeded"), QJsonValue(true));
            QCOMPARE(result.record.value("prewritten_actual_journal"), QJsonValue(true));
            QCOMPARE(result.record.value("wrong_expected_cleanup_refused"), QJsonValue(true));
            QCOMPARE(result.record.value("existing_rules_unchanged"), QJsonValue(true));
            QCOMPARE(result.record.value("recovery_journal_unchanged"), QJsonValue(true));
        }
        if (scenario == LanFirewall::FixtureCase::NameCollision) {
            const auto diagnostic = result.diagnostic;
            requireDiagnostic(diagnostic);
            QCOMPARE(diagnostic.value("operation"), QJsonValue("INetFwRules::Item"));
            QCOMPARE(diagnostic.value("add_attempted"), QJsonValue(false));
            QCOMPARE(diagnostic.value("add_succeeded"), QJsonValue(false));
            QCOMPARE(diagnostic.value("persisted_rule_state"), QJsonValue("present"));
            QCOMPARE(diagnostic.value("ownership_state"), QJsonValue("mismatch"));
            QCOMPARE(diagnostic.value("recovery_action"), QJsonValue("preserve_journal_admin_review"));
            QCOMPARE(result.record.value("same_name_different_owner_refused"), QJsonValue(true));
            QCOMPARE(result.record.value("existing_rules_unchanged"), QJsonValue(true));
            QCOMPARE(result.record.value("recovery_journal_unchanged"), QJsonValue(true));
        }
        if (scenario == LanFirewall::FixtureCase::UnknownOwnership) {
            const auto diagnostic = result.diagnostic;
            requireDiagnostic(diagnostic);
            QCOMPARE(diagnostic.value("operation"), QJsonValue("fixture::snapshotReadFailure"));
            QCOMPARE(diagnostic.value("property"), QJsonValue("Interfaces"));
            QCOMPARE(diagnostic.value("hresult"), QJsonValue("0x80070005"));
            QCOMPARE(diagnostic.value("hresult_source"), QJsonValue("test_injection"));
            QCOMPARE(diagnostic.value("persisted_rule_state"), QJsonValue("unknown"));
            QCOMPARE(diagnostic.value("ownership_state"), QJsonValue("unknown"));
            QCOMPARE(diagnostic.value("cleanup_required"), QJsonValue(true));
            QCOMPARE(diagnostic.value("recovery_action"), QJsonValue("preserve_journal_retry_read"));
            QCOMPARE(result.record.value("snapshot_read_failure_injected"), QJsonValue(true));
            QCOMPARE(result.record.value("unknown_ownership_cleanup_refused"), QJsonValue(true));
            QCOMPARE(result.record.value("existing_rules_unchanged"), QJsonValue(true));
            QCOMPARE(result.record.value("recovery_journal_unchanged"), QJsonValue(true));
        }
        auto evidence = result.record;
        if (!result.diagnostic.isEmpty()) evidence.insert("diagnostic", result.diagnostic);
        qInfo().noquote() << QJsonDocument(evidence).toJson(QJsonDocument::Compact);
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
    void invalidPropertyReportsRedactedComContext() {
        exercise(LanFirewall::FixtureCase::InvalidProperty);
    }
    void failedAddReportsObservedPersistence() {
        exercise(LanFirewall::FixtureCase::AddFailure);
    }
    void postAddReadbackMismatchRefusesCleanup() {
        exercise(LanFirewall::FixtureCase::ReadbackMismatch);
    }
    void sameNameCollisionPreservesExistingRule() {
        exercise(LanFirewall::FixtureCase::NameCollision);
    }
    void unconfirmedOwnershipRefusesCleanup() {
        exercise(LanFirewall::FixtureCase::UnknownOwnership);
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


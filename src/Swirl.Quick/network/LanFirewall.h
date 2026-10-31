#pragma once

#include <QJsonObject>
#include <QString>

// Windows control plane only. No forwarding socket, DNS resolver or routing
// policy lives here. Every operation is invoked on a worker, never the GUI loop.
namespace LanFirewall {
struct Result {
    bool ok = false;
    QString error;
    QJsonObject record;
    QJsonObject config;
};

bool privateIpv4(const QString &address);
bool validateConfiguration(const QJsonObject &input, QJsonObject *canonical,
                           QString *error = nullptr);
bool validateJournal(const QJsonObject &record);
QString journalPath();
bool journalExists(const QString &path);
Result prepare(const QString &path, const QJsonObject &config);
Result verify(const QJsonObject &record);
Result recover(const QString &path, const QString &expectedSession = {},
               bool requireDeadOwner = true);
int guard(const QString &path);

#ifdef SWIRL_LAN_FIREWALL_TESTS
// Built only into the separately opted-in Windows fixture executable. The
// production library never exposes synthetic rules or bypasses validation.
enum class FixtureCase { RoundTrip, ExternalEdit, IndependentOwnership };
Result exerciseNativeFixture(FixtureCase scenario);
#endif
}

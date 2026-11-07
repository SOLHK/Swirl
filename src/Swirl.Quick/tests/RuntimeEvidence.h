#pragma once
#include <QString>
#include <QByteArray>
#include <QUrl>
#include <QVariantMap>
#include <thread>
#ifdef SWIRL_PRIVATE_UI_QUOTA
#include <memory>
class PrivateUiDnsTrust;
#endif
class QQuickWindow;
class EngineController;
class SystemDataProvider;
class DiagnosticService;
void startRuntimeEvidence(QQuickWindow *,EngineController *,SystemDataProvider *,DiagnosticService *,const QString &,const QString &);

// One generated synthetic node in a private, parent-owned QA process. Neither
// this session nor its fixture proof authorizes provider traffic or a budget.
struct ControlledNodeSession {
    QString root,storePath,sourceSha,nonce;
    int nodeOrdinal=0,proxyPort=0;
    int fixtureHttpPort=0,fixtureHttpsPort=0,fixtureSocksPort=0;
    QString fixturePassword,fixtureNodeId;
    QByteArray fixtureCa;
    // Fixed owned-loopback negative control; ordinary deadlines stay unchanged.
    bool nativeWatchdog500msControl=false;
    // A separate, fixed private-profile workflow. The original one-node
    // controlled session keeps imports shut down and does not accept this mode.
    bool uiImportPolicy=false;
    QString uiImportControl;
    bool uiDnsPolicy=false;
    QString uiDnsControl;
    QByteArray fixtureDnsCa;
#ifdef SWIRL_PRIVATE_UI_QUOTA
    std::shared_ptr<const PrivateUiDnsTrust> dnsTrust;
#endif
    QVariantMap dnsConfiguration() const;
    QString originHost() const;
    QUrl subscriptionUrl() const;
    QByteArray subscriptionBody() const;
};
bool loadControlledNodeSession(const QString &,ControlledNodeSession *);
void startControlledNodeSession(QQuickWindow *,EngineController *,const ControlledNodeSession &);
// Declare this owner before QGuiApplication so its deadline also covers Qt and
// Rust destruction. It operates independently of their event loops.
std::jthread startControlledNodeWatchdog(bool);

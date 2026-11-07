#pragma once
#include <QString>
#include <thread>
class QQuickWindow;
class EngineController;
class SystemDataProvider;
class DiagnosticService;
void startRuntimeEvidence(QQuickWindow *,EngineController *,SystemDataProvider *,DiagnosticService *,const QString &,const QString &);

// One explicit node in a private, parent-owned QA process. The legacy runtime
// command entrance stays closed; this plan admits no proxy/TUN write actions.
struct ControlledNodeSession {
    QString root,storePath,sourceSha,nonce;
    int nodeOrdinal=0,proxyPort=0;
    int fixtureHttpPort=0,fixtureHttpsPort=0;
    QString fixtureCaPath;
};
bool loadControlledNodeSession(const QString &,ControlledNodeSession *);
void startControlledNodeSession(QQuickWindow *,EngineController *,const ControlledNodeSession &);
// Declare this owner before QGuiApplication so its deadline also covers Qt and
// Rust destruction. It operates independently of their event loops.
std::jthread startControlledNodeWatchdog(bool);

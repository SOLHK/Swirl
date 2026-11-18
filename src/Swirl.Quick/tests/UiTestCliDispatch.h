#pragma once

#include <QApplication>
#include <QString>
#include <QStringList>
#include <memory>

#include "ActivityPerfTrace.h"
#include "IsolatedUserRegistry.h"
#include "RuntimeEvidence.h"
#include "engine/SystemProxySession.h"

class CaptureService;
class EngineController;
class FontManager;
class QQuickWindow;
class WindowsBackdrop;
struct QmlVmeWarningCapture;

class SwirlTestApplication final : public QApplication {
public:
    using QApplication::QApplication;
    bool notify(QObject *receiver, QEvent *event) override {
        ActivityPerfTrace::DispatchScope dispatch(int(event->type()));
        return QApplication::notify(receiver, event);
    }
};

bool parseControlledSessionRoot(int argc, char *argv[], bool privateUiQuotaRequested, QString *rootOut);
bool tryRunEarlyUiSelfTest(int &argc, char *argv[], int *exitCode);
bool initializeIsolatedRegistryForTests(int argc, char *argv[], bool controlledNodeSession, IsolatedUserRegistry &registry);
bool validateUiLifecycleEnvironment(const QStringList &arguments);
bool tryRunPostAppUiCommand(QApplication &app, int *exitCode);
void recordFontUiMemoryProperty(QApplication &app, bool enabled, const char *propertyName);
std::unique_ptr<SystemProxySession::Backend> createUiTestProxyBackend(const QStringList &arguments, bool controlledNodeSession);
bool tryRunHdrSelfTest(const QStringList &arguments, int *exitCode);

// Returns non-zero early exit code (e.g. 64 or 5) on immediate setup failure, or 0 to enter app.exec().
int attachAndScheduleUiTests(QApplication &app,
                             QQuickWindow *rootWindow,
                             EngineController &engineController,
                             FontManager &fontManager,
                             WindowsBackdrop &backdrop,
                             CaptureService &capture,
                             QmlVmeWarningCapture &qmlVmeWarnings,
                             bool controlledNodeSession,
                             const ControlledNodeSession &controlledSession);

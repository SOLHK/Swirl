#pragma once

class QQuickWindow;
class EngineController;
class QString;

// Opt-in acceptance driver for the real application. It never starts a proxy
// or contacts a remote service; Windows persistence uses the production DPAPI.
int runXrayUiChecks(QQuickWindow *window, EngineController *controller,
                    const QString &isolatedStorePath);

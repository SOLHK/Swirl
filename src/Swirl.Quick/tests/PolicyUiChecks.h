#pragma once
#include <QString>
class QQuickWindow;
class EngineController;
int runPolicyUiChecks(QQuickWindow *window,EngineController *controller,const QString &directory);

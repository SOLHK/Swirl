#pragma once
#include <QString>
class QQuickWindow;
class EngineController;
class SystemDataProvider;
class DiagnosticService;
void startRuntimeEvidence(QQuickWindow *,EngineController *,SystemDataProvider *,DiagnosticService *,const QString &,const QString &);

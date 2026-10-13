#pragma once
#include <QObject>
#include <QVariantList>
#include <QVariantMap>
class CaptureService;
class EngineController;
class DiagnosticService;
class SystemDataProvider final : public QObject {
    Q_OBJECT
    Q_PROPERTY(int revision READ revision NOTIFY dataChanged)
    Q_PROPERTY(int eventCount READ eventCount NOTIFY dataChanged)
public:
    SystemDataProvider(CaptureService *capture,EngineController *engine,DiagnosticService *diagnostics);
    int revision() const { return m_revision; }
    int eventCount() const;
    Q_INVOKABLE void clearLogs();
    Q_INVOKABLE QVariantMap currentNetwork() const;
    Q_INVOKABLE QVariantList connections() const;
    Q_INVOKABLE QVariantList requests() const;
    Q_INVOKABLE QVariantList nodes() const;
    Q_INVOKABLE QVariantList logs() const;
    Q_INVOKABLE QVariantMap diagnosticSnapshot() const;
    Q_INVOKABLE bool copyText(const QString &text) const;
signals:
    void dataChanged();
private:
    int m_revision=0;
    CaptureService *m_capture;
    EngineController *m_engine;
    DiagnosticService *m_diagnostics;
    QVariantList m_logs;
};

#pragma once
#include <QObject>
#include <QVariantList>
#include <QVariantMap>
class CaptureService;
class EngineController;
class SystemDataProvider final : public QObject {
    Q_OBJECT
    Q_PROPERTY(int revision READ revision NOTIFY dataChanged)
public:
    SystemDataProvider(CaptureService *capture,EngineController *engine);
    int revision() const { return m_revision; }
    Q_INVOKABLE void clearLogs() { m_logs.clear(); ++m_revision; emit dataChanged(); }
    Q_INVOKABLE QVariantMap currentNetwork() const;
    Q_INVOKABLE QVariantList connections() const;
    Q_INVOKABLE QVariantList requests() const;
    Q_INVOKABLE QVariantList nodes() const;
    Q_INVOKABLE QVariantList logs() const { return m_logs; }
    Q_INVOKABLE bool copyText(const QString &text) const;
signals:
    void dataChanged();
private:
    int m_revision=0;
    CaptureService *m_capture;
    EngineController *m_engine;
    QVariantList m_logs;
};

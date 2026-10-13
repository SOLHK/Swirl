#pragma once
#include <QVariantMap>
#include <QJsonObject>
#include <QDateTime>
#include <QHash>

// Bounded sampled telemetry. Traffic totals are from the engine; rankings and
// route attribution include only connections observed by the sampler.
class ActivityTelemetry {
public:
    bool ingest(const QJsonObject &object,qint64 now);
    void reset();
    void setHistoryPath(const QString &path);
    QVariantMap snapshot() const {return m_snapshot;}
private:
    qint64 m_lastTime=0,m_lastUp=0,m_lastDown=0;
    QHash<QString,qint64> m_previous;
    QVariantMap m_days;
    QString m_historyPath;
    qint64 m_lastSave=0;
    void saveHistory();
    QVariantList m_upHistory,m_downHistory;
    QVariantMap m_snapshot;
};

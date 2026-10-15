#pragma once
#include "ProxyEngine.h"
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QTimer>
#include <QSet>

// Single model shared by overview, connections, processes and analytics.
// Only authenticated adapter observations enter the accounting model.
class TelemetryService final : public QObject {
 Q_OBJECT
 Q_PROPERTY(int revision READ revision NOTIFY changed)
 Q_PROPERTY(bool sampled READ sampled NOTIFY changed)
 Q_PROPERTY(bool connectionsSampled READ connectionsSampled NOTIFY changed)
 Q_PROPERTY(double downloadRate READ downloadRate NOTIFY changed)
 Q_PROPERTY(double uploadRate READ uploadRate NOTIFY changed)
 Q_PROPERTY(int activeConnections READ activeConnections NOTIFY changed)
 Q_PROPERTY(int activeProcesses READ activeProcesses NOTIFY changed)
 Q_PROPERTY(QVariantList connections READ connections NOTIFY changed)
 Q_PROPERTY(QVariantMap latencies READ latencies NOTIFY changed)
 Q_PROPERTY(QString externalIp READ externalIp NOTIFY changed)
 Q_PROPERTY(QString measurementState READ measurementState NOTIFY changed)
 Q_PROPERTY(QVariantMap internetDiagnostic READ internetDiagnostic NOTIFY changed)
 Q_PROPERTY(QString storageError READ storageError NOTIFY changed)
public:
 explicit TelemetryService(QString path={},bool networkMeasurements=true,QObject *parent=nullptr);
 ~TelemetryService() override;
 void ingest(const ProxyEngine::Status &);
 int revision() const { return m_revision; }
 bool sampled() const;
 bool connectionsSampled() const;
 double downloadRate() const { return m_status.downloadRate; }
 double uploadRate() const { return m_status.uploadRate; }
 int activeConnections() const;
 int activeProcesses() const;
 QVariantList connections() const;
 QVariantMap latencies() const { return m_latencies; }
 QString externalIp() const { return m_externalIp; }
 QString measurementState() const { return m_measurementState; }
 QVariantMap internetDiagnostic() const { return m_internetDiagnostic; }
 QString storageError() const { return m_storageError; }
 Q_INVOKABLE QVariantMap summary(int period=0) const;
 Q_INVOKABLE QVariantList ranking(const QString &kind,int period=0,int limit=50) const;
 Q_INVOKABLE QVariantList distribution(int period=0) const;
 Q_INVOKABLE QVariantList history(const QString &series="down",int seconds=60,bool normalized=false) const;
 Q_INVOKABLE QVariantList historyPoints(const QString &series="down",int seconds=60) const;
 Q_INVOKABLE QVariantList dailyTraffic(bool proxyOnly=false) const;
 Q_INVOKABLE QString formatBytes(double bytes) const;
 Q_INVOKABLE void measureNetwork();
 Q_INVOKABLE void flush();
signals:
 void changed();
 void diagnostic(const QString &module,const QString &code,const QString &message);
private:
 friend class TelemetryTests;
 void reportMeasurement(const QString &key,bool ok,const QString &message);
 void publish();
 void load();
 QJsonObject periodData(int period) const;
 void measureHttp(const QString &key,const QUrl &url,bool throughProxy,bool ip=false);
 void recordInternetResult(int networkError,int http,bool throughProxy,qint64 elapsed);
 QString m_path,m_epoch,m_routeEpoch,m_storageError,m_externalIp,m_measurementState;
 int m_revision=0,m_measurements=0;
 bool m_networkEnabled=true,m_dirty=false;
 qint64 m_lastConnections=0,m_lastTraffic=0,m_lastUp=0,m_lastDown=0;
 ProxyEngine::Status m_status;
 QJsonObject m_days;
 QHash<QString,QVariantMap> m_seen;
 QVariantList m_history;
 QVariantMap m_latencies;
 QVariantMap m_internetDiagnostic;
 QUrl m_internetProbe{QStringLiteral("https://www.gstatic.com/generate_204")};
 QSet<QString> m_failedMeasurements;
 QTimer m_save,m_measure,m_stale;
};

#pragma once
#include "MihomoAdapter.h"
#include <QQueue>
#include <QHash>
#include <QSet>

// Each tested node owns an isolated engine and loopback ports. Tests cannot
// alter the main engine's selection, routing mode or Windows system proxy.
class NodeTestService final : public QObject {
 Q_OBJECT
 Q_PROPERTY(bool busy READ busy NOTIFY changed)
 Q_PROPERTY(int completed READ completed NOTIFY changed)
 Q_PROPERTY(int total READ total NOTIFY changed)
 Q_PROPERTY(int succeeded READ succeeded NOTIFY changed)
 Q_PROPERTY(int failed READ failed NOTIFY changed)
 Q_PROPERTY(QString message READ message NOTIFY changed)
 Q_PROPERTY(QVariantMap results READ results NOTIFY changed)
public:
 using QObject::QObject;
 ~NodeTestService() override;
 static EngineStartOptions isolatedOptions(const EngineStartOptions &);
 void start(const EngineStartOptions &,const QStringList &ids,const QUrl &url);
 Q_INVOKABLE void cancel();
 bool busy() const { return !m_queue.isEmpty()||!m_running.isEmpty()||!m_retiring.isEmpty(); }
 int completed() const { return m_completed; }
 int total() const { return m_total; }
 int succeeded() const { return m_succeeded; }
 int failed() const { return m_failed; }
 QString message() const { return m_message; }
 QVariantMap results() const { return m_results; }
 QVariantMap result(const QString &id) const { return m_results.value(id).toMap(); }
signals:
 void changed();
 void diagnostic(const QString &code,const QString &message);
private:
 void next();
 void retire(MihomoAdapter *runner);
 void finish(const QString &,MihomoAdapter *,const QVariantMap &);
 EngineStartOptions m_options;
 QUrl m_url;
 QQueue<QString> m_queue;
 QHash<QString,MihomoAdapter *> m_running;
 QSet<MihomoAdapter *> m_retiring;
 QVariantMap m_results;
 int m_completed=0,m_total=0,m_succeeded=0,m_failed=0;
 QString m_message;
};

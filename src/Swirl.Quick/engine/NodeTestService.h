#pragma once
#include "ProxyEngine.h"
#include <QElapsedTimer>
#include <QQueue>
#include <QHash>
#include <QSet>
#include <QTimer>
#include <atomic>
#include <memory>

// One bounded Rust sweep, or at most three isolated compatibility workers. FFI and
// lifecycle work run off the UI thread; no probe changes the live session.
class NodeTestService final : public QObject {
 Q_OBJECT
 Q_PROPERTY(bool busy READ busy NOTIFY changed)
 Q_PROPERTY(int completed READ completed NOTIFY changed)
 Q_PROPERTY(int total READ total NOTIFY changed)
 Q_PROPERTY(int succeeded READ succeeded NOTIFY changed)
 Q_PROPERTY(int failed READ failed NOTIFY changed)
 Q_PROPERTY(QString message READ message NOTIFY changed)
 Q_PROPERTY(QVariantMap results READ results NOTIFY changed)
 Q_PROPERTY(quint64 generation READ generation NOTIFY changed)
public:
 using QObject::QObject;
 ~NodeTestService() override;
 static EngineStartOptions isolatedOptions(const EngineStartOptions &);
 static QString nodeReference(const QString &id);
 static QString failureStatusText(const QVariantMap &result);
 void start(const EngineStartOptions &,const QStringList &ids,const QUrl &url);
 void refreshNode(const EngineStartOptions &,const QString &id,const QUrl &url);
 Q_INVOKABLE void cancel();
 // A catalog change invalidates results for the old connection parameters.
 void invalidateResults();
 bool busy() const { return m_batchPreparation||!m_queue.isEmpty()||!m_running.isEmpty()||!m_idle.isEmpty()||!m_retiring.isEmpty()||m_batchRunner!=nullptr||m_batchAwaitingStart||!m_refreshQueue.isEmpty()||(m_interactive&&m_interactive->busy()); }
 int completed() const { return m_completed; }
 int total() const { return m_total; }
 int succeeded() const { return m_succeeded; }
 int failed() const { return m_failed; }
 QString message() const { return m_message; }
 QVariantMap results() const { return m_results; }
 quint64 generation() const {return m_generation;}
 QVariantMap result(const QString &id) const { return m_results.value(id).toMap(); }
 bool hasFreshResults(const QStringList &ids,const QUrl &url) const;
 bool testing(const QString &id) const;
signals:
 void changed();
 void diagnostic(const QString &code,const QString &message);
private:
 struct RefreshRequest {EngineStartOptions options;QString id;QUrl url;};
 QQueue<RefreshRequest> m_refreshQueue;
 NodeTestService *m_interactive=nullptr;
 QString m_refreshId;
 void nextRefresh();
 void next();
 ProxyEngine *createWorker();
 void retire(ProxyEngine *runner);
 void finish(const QString &,ProxyEngine *,const QVariantMap &);
 void record(const QString &,QVariantMap,bool notify=true);
 // One concurrent sweep inside a single engine replaces the former engine per
 // node when the engine supports it. The isolated path remains the fallback.
 bool tryBatch();
 void beginBatch(const QStringList &valid);
 std::shared_ptr<std::atomic_bool> m_batchPreparation;
 void batchStatusChanged();
 void pollBatch();
 void endBatch();
 // Latch the per-node fallback and return the unrecorded batch rows to the queue.
 void batchFallback(const QString &reason,const QString &detail);
 void failBatch(const QString &code);
 EngineStartOptions m_options;
 QUrl m_url;
 QQueue<QString> m_queue;
 QHash<QString,ProxyEngine *> m_running;
 QQueue<ProxyEngine *> m_idle;
 QSet<ProxyEngine *> m_retiring;
 QVariantMap m_results;
 ProxyEngine *m_batchRunner=nullptr;
 QTimer *m_batchPoll=nullptr;
 QSet<QString> m_batchSwept;
 QSet<QString> m_batchRecorded;
 bool m_batchAwaitingStart=false;
 // A batch that cannot start or cannot be issued falls back to the isolated
 // per-node path for the rest of this sweep. Without this latch a failing
 // batch start re-queues its nodes into the same batch forever.
 bool m_batchDisabled=false;
 QElapsedTimer m_batchStartClock;
 qint64 m_batchRequestId=0;
 int m_completed=0,m_total=0,m_succeeded=0,m_failed=0;
 QString m_message;
 quint64 m_generation=0;
};

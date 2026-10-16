#pragma once
#include "ProxyEngine.h"
#include <QSslSocket>
#include <QElapsedTimer>
#include <QTimer>
#include <functional>

// One bounded request through the running mixed entry, correlated with engine
// telemetry by the actual local source port. Never changes routing rules.
class ProxyLatencyProbe : public QObject {
public:
 using Completion=std::function<void(const QVariantMap &)>;
 ProxyLatencyProbe(const ProxyEngine::Status &,const QUrl &,Completion,QObject *parent=nullptr);
 void observe(const ProxyEngine::Status &);
private:
 void read();
 void sendRequest();
 void finish(QString code,QString state);
 QSslSocket m_socket;
 QTimer m_deadline,m_observationDeadline;
 QElapsedTimer m_elapsed;
 QUrl m_url;
 QString m_node,m_phase="connect",m_policy,m_category;
 QStringList m_chain;
 QByteArray m_header;
 Completion m_completion;
 int m_sourcePort=0,m_http=0,m_networkError=0;
 qint64 m_latency=-1;
 bool m_response=false,m_observed=false,m_done=false;
};

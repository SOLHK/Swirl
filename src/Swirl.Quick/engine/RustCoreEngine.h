#pragma once
#include "ProxyEngine.h"
#include <QLibrary>
#include <QTimer>
#include <QElapsedTimer>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QPointer>

// Qt control adapter only. All forwarding sockets, routing and protocol state
// live in the Rust DLL. Called from ThreadedEngine's existing worker thread.
class RustCoreEngine final : public ProxyEngine {
public:
 explicit RustCoreEngine(QObject *parent=nullptr);
 ~RustCoreEngine() override;
 void start(const EngineStartOptions &) override;
 void stop() override;
 void refresh() override;
 void selectNode(const QString &) override;
 void setRoutingMode(const QString &) override;
 void probeNode(const QUrl &) override;
 Status status() const override {return m_status;}
 QString configurationSummary() const override;
 QVariantList routingRules() const override;
 static QString configuration(const EngineStartOptions &,QJsonObject *);
 static QString validatePolicyGroups(const QList<ProxyNode> &,const QVariantList &);
private:
 using Command=qintptr(*)(const unsigned char *,size_t,unsigned char *,size_t);
 QJsonObject call(QJsonObject);
 void fail(Error,const QString &);
 QLibrary m_library;
 Command m_command=nullptr;
 quint64 m_handle=0;
 EngineStartOptions m_options;
 Status m_status;
 QTimer m_poll;
 QElapsedTimer m_uptime,m_rateClock;
 QNetworkAccessManager m_network;
 QPointer<QNetworkReply> m_reply;
};

#pragma once
#include "ProxyEngine.h"
#include "RustCoreLibrary.h"
#include <QTimer>
#include <QElapsedTimer>
#include <QSet>

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
 void configurationCommand(const QJsonObject &) override;
 void probeNode(const QUrl &) override;
 Status status() const override {return m_status;}
 QString probeFailureStage() const override {return m_probeFailureStage;}
 qint64 probeOutboundConnectMs() const override {return m_probeOutboundConnectMs;}
 qint64 probeOriginTlsMs() const override {return m_probeOriginTlsMs;}
 QString configurationSummary() const override;
 QVariantList routingRules() const override;
 static QVariantList routingRulesForOptions(const EngineStartOptions &);
 static QString configuration(const EngineStartOptions &,QJsonObject *);
 static QString configurationV2(const EngineStartOptions &,const QJsonObject &policy,QJsonObject *);
 static QJsonObject validateConfigurationV2(const EngineStartOptions &,const QJsonObject &policy,const QString &requestId);
 static QString validateNetworkConfiguration(const QList<ProxyNode> &,const QVariantMap &,const QStringList &,const QVariantList &,bool nativePrivateRouting=false);
 static QString validatePolicyGroups(const QList<ProxyNode> &,const QVariantList &);
private:
 friend class PolicyConfigurationTests;
 using Command=qintptr(*)(const unsigned char *,size_t,unsigned char *,size_t);
 QJsonObject call(QJsonObject);
 void startV2(const EngineStartOptions &);
 void ingestConfigurationReceipt(const QJsonObject &);
 void retainPublicNodeIdentities();
 void fail(Error,const QString &);
 void resetProbeState();
 void cancelProbe();
 void failProbe(const QString &stage,const QString &code,int httpStatus=0);
 void updateProbe(const QJsonObject &);
 void recordForwardingFailures(const QJsonObject &);
 RustCoreLibrary &m_library = RustCoreLibrary::instance();
 Command m_command=nullptr;
 quint64 m_handle=0;
 EngineStartOptions m_options;
 Status m_status;
 QTimer m_poll;
 QElapsedTimer m_uptime,m_rateClock;
 qint64 m_probeRequestId=0;
 QString m_probeFailureStage;
 qint64 m_probeOutboundConnectMs=-1,m_probeOriginTlsMs=-1;
 QSet<quint64> m_reportedForwardingFailures;
 bool m_forwardingFailureLimitReported=false;
 bool m_v2=false;
 QString m_engineEpoch;
 QJsonObject m_preparedPolicy,m_previousPolicy;
 bool m_configurationRollback=false;
};

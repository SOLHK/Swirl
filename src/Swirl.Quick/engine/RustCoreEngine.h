#pragma once
#include "ProxyEngine.h"
#include "RustCoreLibrary.h"
#include "NativeTunBrokerClient.h"
#include "app/NativeTunRecovery.h"
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
 void lanCommand(const QJsonObject &) override;
 void probeNode(const QUrl &) override;
 Status status() const override {auto value=m_status;value.tunCapturePossible=m_brokerSession||m_tunBroker.running()||m_tunRecoveryRequired;value.tunRecoveryRequired=m_tunRecoveryRequired;return value;}
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
 static bool nativeTunAvailable();
private:
 friend class PolicyConfigurationTests;
 using Command=qintptr(*)(const unsigned char *,size_t,unsigned char *,size_t);
 QJsonObject call(QJsonObject);
 QJsonObject tunCommand(const QString &operation);
 void updateTunStatus(const QJsonObject &);
 bool recoverTunConnection(QString *);
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
 NativeTunBrokerClient m_tunBroker;
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
 bool m_v2=false,m_lanTracked=false,m_brokerSession=false;
 NativeTunRecoveryState m_tunRecoveryState=NativeTunRecoveryState::Unknown;
 bool m_tunRecoveryRequired=true;
 QString m_engineEpoch;
 QJsonObject m_preparedPolicy,m_previousPolicy;
 bool m_configurationRollback=false;
};

#include "engine/TelemetryService.h"
#include "engine/EngineController.h"
#include <QElapsedTimer>
#include <QScopeGuard>
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QDateTime>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QTcpServer>
#include <QTcpSocket>
#include "ControlledNetwork.h"
#include "engine/ThreadedEngine.h"
#include <QUuid>
#include <QJsonDocument>
class PulseEngine final:public ProxyEngine {
public:
 Status current;
 void start(const EngineStartOptions &) override {}
 void stop() override {}
 void refresh() override {emit statusChanged();}
 void selectNode(const QString &) override {}
 void probeNode(const QUrl &) override {}
 Status status() const override {return current;}
 QString configurationSummary() const override {return {};}
};
class TelemetryTests:public QObject {
 Q_OBJECT
 ProxyEngine::Status sample(qint64 time,int up,int down){ProxyEngine::Status s;s.processAlive=true;s.processId=1;s.apiHealthy=true;s.connectionsAt=time;s.trafficAt=time;s.uploadTotal=up;s.downloadTotal=down;s.uploadRate=up;s.downloadRate=down;s.connections={QVariantMap{{"id","connection-a"},{"host","fixture.test"},{"process","fixture.exe"},{"policy","DIRECT"},{"category","direct"},{"uploadBytes",up},{"downloadBytes",down},{"time",QDateTime::fromMSecsSinceEpoch(time).toString(Qt::ISODateWithMs)}}};return s;}
private slots:
  void controllerPublishesOneStatusChangePerEnginePulse(){
   QTemporaryDir temp;auto engine=std::make_unique<PulseEngine>();auto *pulse=engine.get();
   EngineController controller(std::move(engine),nullptr,temp.filePath("nodes.dpapi"));
   QSignalSpy controllerChanges(&controller,&EngineController::statusChanged);
   QSignalSpy telemetryChanges(controller.telemetry(),&TelemetryService::changed);
   pulse->refresh();
   QCOMPARE(telemetryChanges.size(),1);QCOMPARE(controllerChanges.size(),1);
   pulse->refresh();
   QCOMPARE(telemetryChanges.size(),2);QCOMPARE(controllerChanges.size(),2);
   controller.telemetry()->ingest({});
   QCOMPARE(telemetryChanges.size(),3);QCOMPARE(controllerChanges.size(),3);
  }
  void nodeRowsNotifyOnlyForRelevantEngineStatus(){
   QTemporaryDir temp;auto engine=std::make_unique<PulseEngine>();auto *pulse=engine.get();
   EngineController controller(std::move(engine),nullptr,temp.filePath("nodes.dpapi"));
   const auto saved=controller.saveNode({{"name","fixture"},{"protocol","http"},{"host","127.0.0.1"},{"port",9}});
#ifdef Q_OS_WIN
   QVERIFY(saved);const auto id=controller.nodes().first().toMap().value("id").toString();QVERIFY(!id.isEmpty());
#else
   // Non-Windows storage intentionally fails closed. Exercise every display
   // invalidation transition without inventing an unencrypted saved catalogue.
   QVERIFY(!saved);QVERIFY(controller.nodes().isEmpty());const QString id="fixture";
#endif
   const auto verifyRow=[&](const QString &status){
#ifdef Q_OS_WIN
    const auto row=controller.nodes().first().toMap();
    QCOMPARE(row.value("status").toString(),status);
    QCOMPARE(row.value("latency").toString(),QStringLiteral("—"));
    QCOMPARE(row.value("connectionState").toString(),status==QStringLiteral("未测试")?QStringLiteral("未连接"):status);
    QCOMPARE(controller.nodeStateText(),row.value("connectionState").toString());
    QCOMPARE(row.value("networkVerified").toBool(),status==QStringLiteral("已连接"));
    QVERIFY(!row.value("testAvailable").toBool());
    const auto diagnostic=controller.nodeDiagnosticRows().first().toMap();
    QCOMPARE(diagnostic.value("connectionState"),row.value("connectionState"));
    QCOMPARE(diagnostic.value("requestVerified"),row.value("networkVerified"));
    QVERIFY(!diagnostic.contains("host"));QVERIFY(!diagnostic.contains("id"));QVERIFY(!diagnostic.contains("name"));
#else
    Q_UNUSED(status);QVERIFY(controller.nodes().isEmpty());
#endif
   };
   QSignalSpy rows(&controller,&EngineController::nodesChanged);
   pulse->refresh();pulse->refresh();QCOMPARE(rows.size(),0);
   pulse->current.uptimeSeconds=10;pulse->current.uploadTotal=100;
   pulse->refresh();QCOMPARE(rows.size(),0);
#ifdef Q_OS_WIN
   QVERIFY(controller.prepareRealAcceptance());controller.connectNode(id);
#endif
   pulse->current.processAlive=true;pulse->current.apiHealthy=true;pulse->current.selectedNodeId=id;
   pulse->current.nodeHealth=ProxyEngine::NodeHealth::Checking;pulse->current.latencyMs=42;
   pulse->refresh();QCOMPARE(rows.size(),1);verifyRow(QStringLiteral("会话就绪 · 未验证"));
   pulse->current.nodeHealth=ProxyEngine::NodeHealth::Available;
   pulse->refresh();QCOMPARE(rows.size(),2);verifyRow(QStringLiteral("会话就绪 · 未验证"));
   pulse->current.latencyMs=50;pulse->refresh();QCOMPARE(rows.size(),2);verifyRow(QStringLiteral("会话就绪 · 未验证"));
   pulse->current.requestState=ProxyEngine::RequestState::Succeeded;pulse->refresh();
   QCOMPARE(rows.size(),3);verifyRow(QStringLiteral("已连接"));
   pulse->current.requestState=ProxyEngine::RequestState::Failed;pulse->refresh();
   QCOMPARE(rows.size(),4);verifyRow(QStringLiteral("连接失败"));
   pulse->current.requestState=ProxyEngine::RequestState::NotTested;
   pulse->current.selectedNodeId.clear();pulse->refresh();QCOMPARE(rows.size(),5);verifyRow(QStringLiteral("未测试"));
  }
  void stalePollingPublishesOnlySamplingTransitions(){
   QTemporaryDir temp;TelemetryService model(temp.filePath("stale.json"),false);model.m_stale.stop();
   QSignalSpy changes(&model,&TelemetryService::changed);
   auto poll=[&]{QVERIFY(QMetaObject::invokeMethod(&model.m_stale,"timeout",Qt::DirectConnection));};
   poll();poll();QCOMPARE(changes.size(),0);
   model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),0,0));
   QCOMPARE(changes.size(),1);QVERIFY(model.sampled());QVERIFY(model.connectionsSampled());
   poll();poll();QCOMPARE(changes.size(),1);
   model.m_status.trafficAt=QDateTime::currentMSecsSinceEpoch()-7000;
   poll();QCOMPARE(changes.size(),2);QVERIFY(!model.sampled());QVERIFY(model.connectionsSampled());
   poll();QCOMPARE(changes.size(),2);
   model.m_status.connectionsAt=QDateTime::currentMSecsSinceEpoch()-7000;
   poll();QCOMPARE(changes.size(),3);QVERIFY(!model.connectionsSampled());
   poll();poll();QCOMPARE(changes.size(),3);
  }
 void httpsMeasurementWaitsForCompleteResponse(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("https-timing.json"),false);
  QFile cert(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-cert.pem"),key(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-key.pem");
  QVERIFY(cert.open(QIODevice::ReadOnly));QVERIFY(key.open(QIODevice::ReadOnly));
  const QSslCertificate certificate(cert.readAll());auto serverTls=QSslConfiguration::defaultConfiguration();
  serverTls.setLocalCertificate(certificate);serverTls.setPrivateKey(QSslKey(key.readAll(),QSsl::Rsa));
  serverTls.setPeerVerifyMode(QSslSocket::VerifyNone);serverTls.setAllowedNextProtocols({QByteArray("http/1.1")});
  QSslServer origin;origin.setSslConfiguration(serverTls);QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  const auto original=QSslConfiguration::defaultConfiguration();auto trusted=original;trusted.addCaCertificate(certificate);
  const auto restore=qScopeGuard([&]{QSslConfiguration::setDefaultConfiguration(original);});
  QSslConfiguration::setDefaultConfiguration(trusted);
  QPointer<QTcpSocket> pending;QByteArray request;
  connect(&origin,&QTcpServer::pendingConnectionAvailable,&origin,[&]{
   auto *socket=origin.nextPendingConnection();pending=socket;connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
   connect(socket,&QTcpSocket::readyRead,&origin,[&,socket]{request+=socket->readAll();});
   request+=socket->readAll();
  });
  model.m_measurements=1;model.measureHttp("internet",QUrl(QString("https://127.0.0.1:%1/timing").arg(origin.serverPort())),false);
  QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),5000);QVERIFY(request.startsWith("GET /timing HTTP/1.1"));
  pending->write("HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\n");
  QElapsedTimer bodyDelay;bodyDelay.start();QTest::qWait(100);
  // The diagnostic measures QNetworkReply completion, not TCP/TLS handshake
  // or HTTP headers. A response whose body is withheld must remain pending.
  QCOMPARE(model.m_measurements,1);QVERIFY(model.internetDiagnostic().isEmpty());
  const auto withheldMs=bodyDelay.elapsed();pending->write("done");pending->disconnectFromHost();
  QTRY_COMPARE_WITH_TIMEOUT(model.m_measurements,0,3000);
  const auto result=model.internetDiagnostic();QVERIFY(result.value("success").toBool());
  QVERIFY(result.value("elapsedMs").toLongLong()>=withheldMs);
  QCOMPARE(model.latencies().value("internet").toString(),QString::number(result.value("elapsedMs").toLongLong())+" ms");
  QVERIFY(result.value("advice").toString().contains(QStringLiteral("连接、TLS 与目标响应")));
 }
#ifdef SWIRL_USE_RUST_CORE
 void nativeNodeProbeKeepsOutboundAndHeaderDurationsSeparate(){
  ControlledNetwork net;QVERIFY(net.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  net.a.targetPorts.append(origin.serverPort());QPointer<QTcpSocket> pending;QByteArray request;
  connect(&origin,&QTcpServer::newConnection,&origin,[&]{
   auto *socket=origin.nextPendingConnection();pending=socket;connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
   connect(socket,&QTcpSocket::readyRead,&origin,[&,socket]{request+=socket->readAll();});
   request+=socket->readAll();
  });
  EngineStartOptions options;ProxyNode node;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name="Timing fixture";node.protocol="socks5";node.host="127.0.0.1";node.port=net.a.serverPort();options.nodes={node};
  const auto validation=ProxyNode::validate(node);QVERIFY2(validation.isEmpty(),qPrintable(validation));
  NodeTestService probes;const QUrl url(QString("http://127.0.0.1:%1/timing").arg(origin.serverPort()));
  probes.start(options,{node.id},url);QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),5000);
  QVERIFY(request.startsWith("HEAD /timing HTTP/1.1"));QElapsedTimer headerDelay;headerDelay.start();QTest::qWait(100);
  QVERIFY(probes.busy());QVERIFY(probes.result(node.id).isEmpty());const auto withheldMs=headerDelay.elapsed();
  // A HEAD response completes at headers; the declared body is never sent.
  pending->write("HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n");
  QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);const auto result=probes.result(node.id);
  QVERIFY2(result.value("success").toBool(),qPrintable(result.value("error").toString()));
  QCOMPARE(result.value("metricType").toString(),QString("http_headers"));
  const auto outbound=result.value("outboundConnectMs").toLongLong(),headers=result.value("latency").toLongLong();
  QVERIFY(outbound>=0);QVERIFY(headers>outbound);QVERIFY(headers>=withheldMs);
  QCOMPARE(result.value("originTlsMs").toLongLong(),qint64(-1));QCOMPARE(net.a.forwarded,1);
  request.clear();probes.start(options,{node.id},url);QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),5000);
  pending->write("HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");pending->disconnectFromHost();
  QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);const auto failed=probes.result(node.id);
  QVERIFY(!failed.value("success").toBool());QCOMPARE(failed.value("latency").toLongLong(),qint64(-1));
  QCOMPARE(failed.value("outboundConnectMs").toLongLong(),qint64(-1));QCOMPARE(net.a.forwarded,2);
 }
#endif

 void httpsMeasurementStaysHttp1WhenOriginOffersHttp2(){
  const auto original=QSslConfiguration::defaultConfiguration();
  struct RestoreSsl {QSslConfiguration value;~RestoreSsl(){QSslConfiguration::setDefaultConfiguration(value);}} restore{original};
  QFile certificate(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-cert.pem"));
  QFile key(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-key.pem"));
  QVERIFY(certificate.open(QIODevice::ReadOnly));QVERIFY(key.open(QIODevice::ReadOnly));
  const QSslCertificate cert(certificate.readAll());const QSslKey privateKey(key.readAll(),QSsl::Rsa);
  QVERIFY(!cert.isNull());QVERIFY(!privateKey.isNull());
  auto trusted=original;trusted.addCaCertificate(cert);
  QSslConfiguration::setDefaultConfiguration(trusted);
  auto serverSsl=trusted;serverSsl.setLocalCertificate(cert);serverSsl.setPrivateKey(privateKey);
  serverSsl.setPeerVerifyMode(QSslSocket::VerifyNone); // This fixture does not require client certificates.
  serverSsl.setAllowedNextProtocols({QByteArray("h2"),QByteArray("http/1.1")});
  QList<QByteArray> protocols,requestLines;
  QSslServer origin;origin.setSslConfiguration(serverSsl);
  QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  connect(&origin,&QSslServer::pendingConnectionAvailable,&origin,[&]{
   while(origin.hasPendingConnections()){
    auto *socket=qobject_cast<QSslSocket *>(origin.nextPendingConnection());
    if(!socket)continue;
    const auto protocol=socket->sslConfiguration().nextNegotiatedProtocol();protocols.append(protocol);
    connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    // Negotiating h2 is the regression: this endpoint deliberately handles
    // only HTTP/1.1 payloads and never sends malformed HTTP/2 frames.
    if(protocol=="h2"){socket->disconnectFromHost();continue;}
    auto data=std::make_shared<QByteArray>();
    const auto respond=[&,socket,data]{
     *data+=socket->readAll();if(!data->contains("\r\n\r\n")||socket->property("responded").toBool())return;
     socket->setProperty("responded",true);requestLines.append(data->left(data->indexOf("\r\n")));
     socket->write("HTTP/1.1 200 OK\r\nContent-Length: 12\r\nConnection: close\r\n\r\n203.0.113.10");
     socket->disconnectFromHost();
    };
    connect(socket,&QTcpSocket::readyRead,socket,respond);if(socket->bytesAvailable())respond();
   }
  });
  // A verified TLS positive control proves this exact origin can select h2.
  QSslSocket control;control.setProxy(QNetworkProxy::NoProxy);
  auto controlSsl=trusted;controlSsl.setAllowedNextProtocols({QByteArray("h2"),QByteArray("http/1.1")});
  control.setSslConfiguration(controlSsl);QSignalSpy encrypted(&control,&QSslSocket::encrypted);
  control.connectToHostEncrypted("localhost",origin.serverPort());
  QTRY_VERIFY_WITH_TIMEOUT(!encrypted.isEmpty(),4000);
  QTRY_COMPARE_WITH_TIMEOUT(protocols.size(),1,4000);QCOMPARE(protocols.first(),QByteArray("h2"));
  control.abort();protocols.clear();

  QTemporaryDir temp;QVERIFY(temp.isValid());TelemetryService model(temp.filePath("https-policy.json"),false);
  const QUrl url(QString("https://localhost:%1/probe").arg(origin.serverPort()));
  model.m_measurements=1;model.measureHttp("internet",url,false);
  QTRY_COMPARE_WITH_TIMEOUT(model.m_measurements,0,5000);
  QVERIFY(model.internetDiagnostic().value("success").toBool());
  QCOMPARE(model.internetDiagnostic().value("http").toInt(),200);
  // The public-IP measurement uses the same real request path.
  model.m_measurements=1;model.measureHttp("exit",url,false,true);
  QTRY_COMPARE_WITH_TIMEOUT(model.m_measurements,0,5000);
  QCOMPARE(model.externalIp(),QString("203.0.113.10"));
  QCOMPARE(protocols.size(),2);QCOMPARE(requestLines.size(),2);
  for(const auto &protocol:protocols)QVERIFY(protocol.isEmpty()||protocol=="http/1.1");
  for(const auto &line:requestLines)QCOMPARE(line,QByteArray("GET /probe HTTP/1.1"));
 }
 void proxyLatencyComesFromRustAndRejectsUntrustedTargetTls(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;QVERIFY(directory.isValid());
  QTcpServer reservation;QVERIFY(reservation.listen(QHostAddress::LocalHost,0));
  EngineStartOptions options;options.routingMode="global";options.proxyPort=reservation.serverPort();reservation.close();
  ProxyNode node;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name="Probe node";node.protocol="socks5";node.host="127.0.0.1";node.port=net.a.serverPort();options.nodes={node};options.selectedNodeId=node.id;
  ThreadedEngine engine;TelemetryService model(directory.filePath("probe.json"),false);
  connect(&engine,&ProxyEngine::statusChanged,&model,[&]{model.ingest(engine.status());});
  connect(&model,&TelemetryService::nativeProbeRequested,&engine,&ProxyEngine::probeNodeTagged);
  connect(&engine,&ProxyEngine::probeRequestRejected,&model,&TelemetryService::rejectNativeProbe);
  engine.start(options);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);
  model.m_internetProbe=net.url();model.measureProxy();QVERIFY(model.m_nativeProbePending);
  QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,5000);
  const auto result=model.proxyDiagnostic();
  QVERIFY2(result.value("success").toBool(),qPrintable(result.value("state").toString()));
  QCOMPARE(result.value("metricType").toString(),QString("http_headers"));QVERIFY(result.value("routeVerified").toBool());
  QVERIFY(result.value("elapsedMs").toLongLong()>=0);QVERIFY(result.value("outboundConnectMs").toLongLong()>=0);
  QCOMPARE(net.a.forwarded,1);QCOMPARE(net.b.forwarded,0);QCOMPARE(net.httpRequests,1);QCOMPARE(model.m_measurements,0);
  // Queue a user URL before the worker's busy snapshot reaches the UI. The
  // periodic request must not consume that other request's response.
  engine.probeNode(net.url());model.measureProxy();
  QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,5000);
  QCOMPARE(model.proxyDiagnostic().value("code").toString(),QString("probe-busy"));
  QVERIFY(!model.proxyDiagnostic().value("success").toBool());
  QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,5000);QCOMPARE(net.httpRequests,2);
  // The self-signed target certificate is not a Rust trusted CA. Qt's UI TLS
  // state cannot accidentally make this core probe claim HTTPS success.
  model.m_internetProbe=net.url(true);model.measureProxy();
  QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,5000);
  QVERIFY(!model.proxyDiagnostic().value("success").toBool());
  QCOMPARE(model.proxyDiagnostic().value("code").toString(),QString("origin_tls"));
  QCOMPARE(model.m_measurements,0);engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
 }
 void nativeProbeIgnoresStaleSuccessAndInvalidatesOnRouteChange(){
  QTemporaryDir directory;TelemetryService model(directory.filePath("probe-generation.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);status.proxyPort=7898;status.selectedNodeId="A";model.ingest(status);
  QSignalSpy requested(&model,&TelemetryService::nativeProbeRequested);model.measureProxy();QCOMPARE(requested.size(),1);
  // A queued terminal snapshot from a previous request is not a new success.
  status.requestState=ProxyEngine::RequestState::Succeeded;status.latencyMs=5;status.responseCode=200;model.ingest(status);
  QVERIFY(model.m_nativeProbePending);QVERIFY(!model.proxyDiagnostic().value("success").toBool());
  // A manual probe on the same node has tag zero and must not be attributed to
  // the periodic URL, even if both requests were queued before UI refresh.
  status.requestState=ProxyEngine::RequestState::InProgress;status.nodeBusy=true;model.ingest(status);QVERIFY(!model.m_nativeProbeObservedRunning);
  status.probeRequestTag=requested.first().at(1).toULongLong();model.ingest(status);QVERIFY(model.m_nativeProbeObservedRunning);
  status.selectedNodeId="B";model.ingest(status);QVERIFY(!model.m_nativeProbePending);QCOMPARE(model.m_measurements,0);
  status.selectedNodeId="A";status.nodeBusy=false;status.requestState=ProxyEngine::RequestState::Succeeded;model.ingest(status);
  QVERIFY(model.proxyDiagnostic().isEmpty());QCOMPARE(model.latencies().value("proxy").toString(),QStringLiteral("尚未测量"));
  // A missing completion also has a bounded diagnostic, not an eternal spinner.
  model.m_nativeProbeDeadline.setInterval(1);model.measureProxy();QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,500);
  QCOMPARE(model.proxyDiagnostic().value("code").toString(),QString("timeout"));QCOMPARE(model.m_measurements,0);
 }
 void httpProbeRejectsObsoleteRoundTrip(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("proxy.json"),false);
  QTcpServer proxy;QVERIFY(proxy.listen(QHostAddress::LocalHost,0));
  QPointer<QTcpSocket> pending;QByteArray request;
  connect(&proxy,&QTcpServer::newConnection,this,[&]{pending=proxy.nextPendingConnection();connect(pending,&QTcpSocket::readyRead,this,[&]{request+=pending->readAll();});});
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);status.proxyPort=proxy.serverPort();status.selectedNodeId="A";model.ingest(status);

  model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/proxy"),true);
  QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),3000);
  QVERIFY(request.startsWith("GET http://fixture.invalid/proxy HTTP/1.1"));
  pending->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");pending->disconnectFromHost();
  QTRY_COMPARE(model.m_measurements,0);QVERIFY(model.internetDiagnostic().value("success").toBool());

  request.clear();model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/proxy"),true);
  QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),3000);
  // A -> B -> A must still invalidate the first A request (string IDs alone cannot).
  status.selectedNodeId="B";model.ingest(status);status.selectedNodeId="A";model.ingest(status);
  pending->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");pending->disconnectFromHost();
  QTRY_COMPARE(model.m_measurements,0);QVERIFY(model.internetDiagnostic().isEmpty());
  QCOMPARE(model.latencies().value("proxy").toString(),QStringLiteral("尚未测量"));
  QCOMPARE(model.measurementState(),QStringLiteral("尚未测量"));
  proxy.close();model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/proxy"),true);
  QTRY_COMPARE(model.m_measurements,0);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("proxy-port"));
 }
 void cachedPeriodInvalidatesWithoutErasingHistory(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("cache.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),10,20);model.ingest(status);
  QCOMPARE(model.summary().value("total").toInt(),30);model.distribution();model.ranking("apps");
  status=sample(status.connectionsAt+1000,20,40);model.ingest(status);
  QCOMPARE(model.summary().value("total").toInt(),60);
  QCOMPARE(model.ranking("apps").first().toMap().value("total").toInt(),60);
  status.processAlive=false;status.apiHealthy=false;model.ingest(status);
  QVERIFY(!model.sampled());QCOMPARE(model.summary().value("total").toInt(),60);
  QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);
 }
 void closedSnapshotsAreNotActiveAndControlFailureIsNotClosure(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("activity-state.json"),false);
  auto s=sample(QDateTime::currentMSecsSinceEpoch(),10,20);
  auto closed=s.connections.first().toMap();closed["id"]="closed";closed["process"]="retired.exe";closed["closed"]=true;
  s.connections.append(closed);model.ingest(s);
  QCOMPARE(model.activeConnections(),1);QCOMPARE(model.activeProcesses(),1);
  s.apiHealthy=false;model.ingest(s);
  auto rows=model.connections();for(const auto &r:rows)if(r.toMap().value("id")=="connection-a")QCOMPARE(r.toMap().value("status").toString(),QStringLiteral("采样中断"));
  s.processAlive=false;model.ingest(s);
  for(const auto &r:model.connections())QCOMPARE(r.toMap().value("status").toString(),QStringLiteral("已结束"));
 }
 void internetUsesExplicitProxyAndActualHttpResponse(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("diagnostic.json"),false);
  QTcpServer proxy;QVERIFY(proxy.listen(QHostAddress::LocalHost,0));QByteArray request;
  connect(&proxy,&QTcpServer::newConnection,this,[&]{auto socket=proxy.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,this,[&,socket]{request+=socket->readAll();if(request.contains("\r\n\r\n")){socket->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");socket->disconnectFromHost();}});});
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);status.proxyPort=proxy.serverPort();model.ingest(status);
  model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/probe"),true);
  QTRY_VERIFY_WITH_TIMEOUT(model.m_measurements==0,4000);
  QVERIFY(request.startsWith("GET http://fixture.invalid/probe HTTP/1.1"));
  QVERIFY(model.internetDiagnostic().value("success").toBool());QCOMPARE(model.internetDiagnostic().value("http").toInt(),204);
  // A stopped listener must never reuse the previous success.
  proxy.close();model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/probe"),true);
  QTRY_VERIFY_WITH_TIMEOUT(model.m_measurements==0,4000);
  QVERIFY(!model.internetDiagnostic().value("success").toBool());QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("proxy-port"));
 }
 void internetFailureClassificationAndRouteChanges(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("classification.json"),false);
  model.recordInternetResult(QNetworkReply::HostNotFoundError,0,false,2);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("dns"));
  model.recordInternetResult(QNetworkReply::OperationCanceledError,0,true,9000);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("timeout"));
  model.recordInternetResult(QNetworkReply::ServiceUnavailableError,503,true,80);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("service"));
  QVERIFY(!model.internetDiagnostic().value("success").toBool());
  model.recordInternetResult(QNetworkReply::NoError,204,false,20);QVERIFY(model.internetDiagnostic().value("success").toBool());
  QVERIFY(model.internetDiagnostic().value("advice").toString().contains(QStringLiteral("未验证代理节点")));
  model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),0,0));QVERIFY(model.internetDiagnostic().isEmpty());
 }
 void continuingMeasurementFailureIsOneIncident(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("measurements.json"),false);QSignalSpy incidents(&model,&TelemetryService::diagnostic);
  for(int i=0;i<510;++i)model.reportMeasurement("InternetTCP",false,"timeout");
  QCOMPARE(incidents.size(),1);
  model.reportMeasurement("DNS",false,"lookup failed");QCOMPARE(incidents.size(),2);
  model.reportMeasurement("InternetTCP",true,{});model.reportMeasurement("InternetTCP",false,"timeout");QCOMPARE(incidents.size(),3);
  model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),0,0));model.reportMeasurement("InternetTCP",false,"timeout");QCOMPARE(incidents.size(),4);
 }
 void dailyBucketsPreserveGapsAndProxyFilter(){QTemporaryDir temp;const auto path=temp.filePath("day.json");TelemetryService model(path,false);const auto now=QDateTime::currentMSecsSinceEpoch();auto s=sample(now,100,200);auto row=s.connections.first().toMap();row["category"]="proxy";s.connections={row};model.ingest(s);model.ingest(s);s=sample(now+1,150,300);row=s.connections.first().toMap();row["category"]="proxy";s.connections={row};model.ingest(s);
  const auto all=model.dailyTraffic(),proxy=model.dailyTraffic(true);QCOMPARE(all.size(),48);int observed=0;double sum=0,proxySum=0;for(int i=0;i<48;++i){observed+=all[i].toMap().value("sampled").toBool();sum+=all[i].toMap().value("value").toDouble();proxySum+=proxy[i].toMap().value("value").toDouble();}QCOMPARE(observed,1);QCOMPARE(sum,450.0);QCOMPARE(proxySum,450.0);model.flush();TelemetryService restored(path,false);QCOMPARE(restored.dailyTraffic(),all);}
 void processAndDeviceRates(){QTemporaryDir temp;TelemetryService model(temp.filePath("rates.json"),false);auto s=sample(QDateTime::currentMSecsSinceEpoch(),100,200);auto row=s.connections.first().toMap();row["sourceIp"]="192.0.2.100";s.connections={row};model.ingest(s);QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);
  s.connectionsAt+=1000;s.trafficAt=s.connectionsAt;s.uploadTotal=400;s.downloadTotal=900;row["uploadBytes"]=400;row["downloadBytes"]=900;s.connections={row};model.ingest(s);
  QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),1000.0);QCOMPARE(model.ranking("devices").first().toMap().value("total").toDouble(),1300.0);QCOMPARE(model.ranking("devices").first().toMap().value("speed").toDouble(),1000.0);
  s.connectionsAt++;s.connections.clear();model.ingest(s);QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);}
 void accounting(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);QVERIFY(!model.sampled());auto s=sample(QDateTime::currentMSecsSinceEpoch(),10,20);model.ingest(s);QVERIFY(model.sampled());QCOMPARE(model.summary().value("total").toInt(),30);model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),30);s=sample(s.connectionsAt+1,15,30);model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),45);auto rank=model.ranking("apps");QCOMPARE(rank.first().toMap().value("connections").toInt(),1);QCOMPARE(rank.first().toMap().value("total").toInt(),45);QCOMPARE(model.activeProcesses(),1);s.connectionsAt++;s.connections.clear();model.ingest(s);QCOMPARE(model.activeConnections(),0);QCOMPARE(model.connections().size(),1);QCOMPARE(model.connections().first().toMap().value("status").toString(),QStringLiteral("已结束"));model.flush();TelemetryService restored(temp.filePath("history.json"),false);QCOMPARE(restored.summary().value("total").toInt(),45);QVERIFY(!restored.sampled());QCOMPARE(restored.ranking("apps").first().toMap().value("connections").toInt(),1);}
 void resetsAndNewProcess(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);auto s=sample(QDateTime::currentMSecsSinceEpoch(),100,200);model.ingest(s);s=sample(s.connectionsAt+1,5,10);model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),315);s=sample(s.connectionsAt+1,7,14);s.processId=2;model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),336);QCOMPARE(model.ranking("apps").first().toMap().value("connections").toInt(),2);}
 void idleAndUncollected(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);auto s=sample(QDateTime::currentMSecsSinceEpoch(),0,0);model.ingest(s);QVERIFY(model.sampled());QCOMPARE(model.downloadRate(),0.0);QVERIFY(model.summary().value("sampled").toBool());s.trafficAt=0;s.connectionsAt=0;s.apiHealthy=false;model.ingest(s);QVERIFY(!model.sampled());QVERIFY(!model.connectionsSampled());}
 void timestampedHistory(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);const auto t=QDateTime::currentMSecsSinceEpoch();auto s=sample(t-20000,2,4);model.ingest(s);s=sample(t-1000,3,6);model.ingest(s);const auto points=model.historyPoints("down",60);QCOMPARE(points.size(),2);QCOMPARE(points.first().toMap().value("time").toLongLong(),t-20000);QCOMPARE(points.last().toMap().value("time").toLongLong(),t-1000);QCOMPARE(points.last().toMap().value("value").toDouble(),6.0);}
 void ranges(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);const auto yesterday=QDateTime(QDate::currentDate().addDays(-1),QTime(12,0)).toMSecsSinceEpoch();auto s=sample(yesterday,2,4);model.ingest(s);QCOMPARE(model.summary(0).value("total").toInt(),0);QCOMPARE(model.summary(1).value("total").toInt(),6);s=sample(QDateTime::currentMSecsSinceEpoch(),3,6);model.ingest(s);QCOMPARE(model.summary(0).value("total").toInt(),3);QCOMPARE(model.summary(1).value("total").toInt(),6);QCOMPARE(model.ranking("apps",0).first().toMap().value("connections").toInt(),1);}
};
QTEST_GUILESS_MAIN(TelemetryTests)
#include "TelemetryTests.moc"

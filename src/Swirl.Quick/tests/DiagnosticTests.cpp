#include "app/DiagnosticService.h"
#include "engine/MihomoLogDiagnostic.h"
#include <QTest>
#include <QTemporaryDir>
#include <QFile>
class DiagnosticTests:public QObject {
 Q_OBJECT
private slots:
 void mihomoFailureReasons_data(){
  QTest::addColumn<QString>("reason");QTest::addColumn<QString>("code");QTest::addColumn<QString>("detail");
  const auto row=[](const char *name,const char *reason,const char *code,const char *detail){QTest::newRow(name)<<QString::fromUtf8(reason)<<QString::fromUtf8(code)<<QString::fromUtf8(detail);};
  row("proxy-auth","407 Proxy Authentication Required","ProxyAuthenticationFailure","407");
  row("socks-auth","socks5 authentication failed","ProxyAuthenticationFailure","认证被拒绝");
  row("dns","dns resolve failed: no such host","DNSFailure","域名不存在");
  row("dns-timeout","all DNS requests failed: i/o timeout","DNSFailure","解析失败");
  row("tls-eof","TLS handshake EOF","TLSFailure","EOF");
  row("certificate","x509: certificate signed by unknown authority","TLSFailure","证书校验失败");
  row("reset","read: connection reset by peer","UpstreamConnectionReset","被重置");
  row("refused","connect: connection refused","UpstreamConnectionRefused","被拒绝");
  row("timeout","context deadline exceeded","UpstreamTimeout","超时");
  row("eof","unexpected EOF","UpstreamEOF","阶段未确定");
 }
 void mihomoFailureReasons(){
  QFETCH(QString,reason);QFETCH(QString,code);QFETCH(QString,detail);
  const auto payload="[TCP] dial NODE-DNS-TLS (match RuleSet/private-rule) 192.168.1.1:5678 --> auth.openai.com:443 error: "+reason+" via https://user:SECRET@private-node.invalid/path?token=PRIVATE";
  const auto fault=classifyMihomoLog(payload);QCOMPARE(fault.code,code);QVERIFY(fault.message.contains(detail));QVERIFY(fault.message.contains("auth.openai.com:443"));
  for(const auto &secret:{"SECRET","PRIVATE","private-node","private-rule","192.168","5678","NODE-DNS-TLS"})QVERIFY2(!fault.message.contains(secret),secret);
 }
 void mihomoPreambleDoesNotInventFailure(){
  const auto fault=classifyMihomoLog("[TCP] dial DNS TLS certificate rule --> private.example:443 error: opaque failure");
  QCOMPARE(fault.code,QStringLiteral("RouteHandshakeFailure"));QVERIFY(!fault.message.contains("private.example"));
  QCOMPARE(classifyMihomoLog("warning tls EOF at private-node").code,QStringLiteral("RouteHandshakeFailure"));
 }
 void activityCountIncludesNonFailureEvents(){
  QTemporaryDir temp;
  {DiagnosticService log(temp.path());log.record("INFO","Engine","Connected","connected");log.record("WARN","Import","Notice","notice");log.record("DEBUG","Qt","Trace","trace");QCOMPARE(log.eventCount(),2);}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),2);log.acknowledge();QCOMPARE(log.eventCount(),0);}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),0);log.record("INFO","Import","Updated","updated");QCOMPARE(log.eventCount(),1);}
 }
 void clearSurvivesRestart(){
  QTemporaryDir temp;
  {DiagnosticService log(temp.path());log.record("ERROR","Fixture","OldFailure","old");log.clearView();QCOMPARE(log.eventCount(),0);QVERIFY(log.records().isEmpty());}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),0);QVERIFY(log.records().isEmpty());log.record("ERROR","Fixture","NewFailure","new");}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),1);QCOMPARE(log.records().size(),1);QCOMPARE(log.records().first().toMap().value("code").toString(),QStringLiteral("NewFailure"));}
 }
 void replayCapsCountAndPreservesAcknowledgement(){
  QTemporaryDir temp;
  {DiagnosticService log(temp.path());for(int i=0;i<545;++i)log.record("ERROR","Fixture","Failure","fixture");QCOMPARE(log.eventCount(),500);}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),500);QCOMPARE(log.records().size(),500);log.acknowledge();}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),0);QVERIFY(!log.records().isEmpty());log.record("ERROR","Fixture","NewFailure","new");}
  {DiagnosticService log(temp.path());QCOMPARE(log.eventCount(),1);}
 }
 void clearAtRotationBoundary(){
  QTemporaryDir temp;
  {DiagnosticService log(temp.path());for(int i=0;i<140;++i)log.record("ERROR","Fixture","Large",QString(8192,'x'));log.clearView();log.record("INFO","Fixture","AfterClear","retained");}
  DiagnosticService restored(temp.path());QCOMPARE(restored.eventCount(),1);QCOMPARE(restored.records().size(),1);QCOMPARE(restored.records().first().toMap().value("code").toString(),QStringLiteral("AfterClear"));
 }
 void redactionAndZip(){QTemporaryDir temp;DiagnosticService log(temp.path());
  const auto secrets=QStringLiteral("token=FIXTURE-TOKEN password: FIXTURE-PASSWORD Cookie: private-cookie\nhttps://fixture.test/sub?secret=PRIVATE-URL\nuuid: 11111111-1111-4111-8111-111111111111\n-----BEGIN PRIVATE KEY-----\nPRIVATE-KEY\n-----END PRIVATE KEY-----");
  log.record("ERROR","Fixture","ExpectedFailure",secrets);QCOMPARE(log.eventCount(),1);const auto text=log.records().first().toMap().value("message").toString();for(const auto &secret:{"FIXTURE-TOKEN","FIXTURE-PASSWORD","private-cookie","PRIVATE-URL","11111111","PRIVATE-KEY"})QVERIFY2(!text.contains(secret),secret);
  const auto path=qEnvironmentVariable("SWIRL_DIAGNOSTIC_SAMPLE",temp.filePath("diagnostics.zip"));
  const auto sourceSha=QString(40,'a'),binarySha=QString(64,'b');
  QVERIFY(log.exportReport(QUrl::fromLocalFile(path),{{"sample",true},{"state","controlled failure"},{"sourceSha",sourceSha},{"executableSha256",binarySha},{"actualEngineType","rust"},{"engineProcessId","1234"}}));
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto archive=file.readAll();QVERIFY(archive.startsWith("PK"));QVERIFY(archive.contains("logs.jsonl"));QVERIFY(archive.contains("environment.json"));
  QVERIFY(archive.contains("identity.json"));QVERIFY(archive.contains(sourceSha.toLatin1()));QVERIFY(archive.contains(binarySha.toLatin1()));
  QVERIFY(!archive.contains("FIXTURE-TOKEN"));log.acknowledge();QCOMPARE(log.eventCount(),0);
 }
 void rotationAndBound(){QTemporaryDir temp;DiagnosticService log(temp.path());for(int i=0;i<750;++i)log.record("INFO","Fixture","Bound",QStringLiteral("fixture diagnostic text ").repeated(250));QCOMPARE(log.records().size(),500);QVERIFY(QFileInfo(temp.filePath("events.jsonl.1")).exists());QVERIFY(QFileInfo(temp.filePath("events.jsonl")).size()<1024*1024+9000);}
};
QTEST_GUILESS_MAIN(DiagnosticTests)
#include "DiagnosticTests.moc"

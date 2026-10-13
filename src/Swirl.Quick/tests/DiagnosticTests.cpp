#include "app/DiagnosticService.h"
#include <QTest>
#include <QTemporaryDir>
#include <QFile>
class DiagnosticTests:public QObject {
 Q_OBJECT
private slots:
 void bareBrowsingMetadataIsRemoved(){const auto safe=DiagnosticService::redact("TLS failure for private.example.net and https://private.example.net/path Cookie: session-private");QVERIFY(!safe.contains("private.example.net"));QVERIFY(!safe.contains("session-private"));}
 void redactionAndZip(){QTemporaryDir temp;DiagnosticService log(temp.path());
  const auto secrets=QStringLiteral("token=FIXTURE-TOKEN password: FIXTURE-PASSWORD Cookie: private-cookie\nhttps://fixture.test/sub?secret=PRIVATE-URL\nuuid: 11111111-1111-4111-8111-111111111111\n-----BEGIN PRIVATE KEY-----\nPRIVATE-KEY\n-----END PRIVATE KEY-----");
  log.record("ERROR","Fixture","ExpectedFailure",secrets);QCOMPARE(log.eventCount(),1);const auto text=log.records().first().toMap().value("message").toString();for(const auto &secret:{"FIXTURE-TOKEN","FIXTURE-PASSWORD","private-cookie","PRIVATE-URL","11111111","PRIVATE-KEY"})QVERIFY2(!text.contains(secret),secret);
  const auto path=qEnvironmentVariable("SWIRL_DIAGNOSTIC_SAMPLE",temp.filePath("diagnostics.zip"));QVERIFY(log.exportReport(QUrl::fromLocalFile(path),{{"sample",true},{"state","controlled failure"}}));QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto archive=file.readAll();QVERIFY(archive.startsWith("PK"));QVERIFY(archive.contains("logs.jsonl"));QVERIFY(archive.contains("environment.json"));QVERIFY(!archive.contains("FIXTURE-TOKEN"));log.acknowledge();QCOMPARE(log.eventCount(),0);
 }
 void rotationAndBound(){QTemporaryDir temp;DiagnosticService log(temp.path());for(int i=0;i<750;++i)log.record("INFO","Fixture","Bound",QStringLiteral("fixture diagnostic text ").repeated(250));QCOMPARE(log.records().size(),500);QVERIFY(QFileInfo(temp.filePath("events.jsonl.1")).exists());QVERIFY(QFileInfo(temp.filePath("events.jsonl")).size()<1024*1024+9000);}
};
QTEST_GUILESS_MAIN(DiagnosticTests)
#include "DiagnosticTests.moc"

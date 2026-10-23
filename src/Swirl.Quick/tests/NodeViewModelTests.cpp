#include "app/NodeViewModel.h"
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QSettings>
#include <QElapsedTimer>
class NodeViewModelTests : public QObject {
    Q_OBJECT
private slots:
    void stableSearchAndTelemetry(){
        QTemporaryDir config;QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,config.path());
        NodeViewModel model;QVariantList rows;
        for(int i=0;i<5000;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString("日本 Tokyo %1").arg(i)},{"host","node.example.test"},{"protocol",i%2?"vless":"ss"},{"regionCode","JP"},{"regionName","日本"},{"sourceId",i%3?"provider-a":"provider-b"},{"status","未测试"},{"latency","—"}});
        model.updateRows(rows);QCOMPARE(model.rowCount(),5000);
        QSignalSpy notifications(&model,&NodeViewModel::changed);
        for(int i=0;i<10;++i)model.updateRows(rows);
        QCOMPARE(notifications.size(),0);
        QSignalSpy resets(model.sourceModel(),&QAbstractItemModel::modelReset),changes(model.sourceModel(),&QAbstractItemModel::dataChanged);
        QElapsedTimer timer;timer.start();
        for(int i=0;i<30;++i){model.setQuery(i%2?"TOKYO":"日本");QCOMPARE(model.rowCount(),5000);}
        qInfo()<<"5000-node search, 30 edits milliseconds"<<timer.elapsed();
        model.setQuery("VLESS");QCOMPARE(model.rowCount(),2500);
        model.setFilters({{"sourceId","provider-b"}});QCOMPARE(model.rowCount(),833);
        model.setQuery("missing");QCOMPARE(model.rowCount(),0);model.setQuery("");model.setFilters({});
        auto row=rows[10].toMap();row["latency"]="50";row["status"]="可用";row["testAvailable"]=true;rows[10]=row;model.updateRows(rows);
        QCOMPARE(changes.size(),1);QCOMPARE(resets.size(),0);
        model.setFilters({{"available",true},{"maxLatency",100},{"sort","latency"}});QCOMPARE(model.rowCount(),1);QCOMPARE(model.get(0).value("id").toString(),"10");
        model.setFilters({{"group","favorites"}});QCOMPARE(model.rowCount(),0);model.toggleFavorite("10");QCOMPARE(model.rowCount(),1);
        model.toggleFavorite("10");QCOMPARE(model.rowCount(),0);
        model.setFilters({});rows.removeAt(10);model.updateRows(rows);QCOMPARE(model.rowCount(),4999);QVERIFY(model.find("10").isEmpty());QCOMPARE(resets.size(),0);
        model.updateRows({});QCOMPARE(model.rowCount(),0);
    }
};
QTEST_MAIN(NodeViewModelTests)
#include "NodeViewModelTests.moc"

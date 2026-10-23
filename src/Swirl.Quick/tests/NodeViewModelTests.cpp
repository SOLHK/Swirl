#include "app/NodeViewModel.h"
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QSettings>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonDocument>
#include <QFile>
#include "engine/ThreadedEngine.h"
class NodeViewModelTests : public QObject {
    Q_OBJECT
private slots:
    void unrelatedStatusDoesNotScheduleCatalogWork(){
        QTemporaryDir temp;QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,temp.path());
        EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,temp.filePath("nodes.dpapi"));
        NodeViewModel model;model.setController(&controller);
        auto *refresh=model.findChild<QTimer *>();QVERIFY(refresh);QSignalSpy wakeups(refresh,&QTimer::timeout);
        for(int i=0;i<40;++i)QMetaObject::invokeMethod(&controller,"statusChanged");
        QTest::qWait(100);QCOMPARE(wakeups.size(),0);
        QMetaObject::invokeMethod(&controller,"nodesChanged");QTRY_COMPARE(wakeups.size(),1);
    }
    void batchUpdatesPreserveIdentityAndSorting(){
        NodeViewModel model;QVariantList rows;
        for(int i=0;i<12;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString::number(i)},{"latency",QString::number(i)}});
        model.updateRows(rows);model.setFilters({{"sort","latency"}});
        const QPersistentModelIndex retained(model.sourceModel()->index(11,0));
        QSignalSpy changes(model.sourceModel(),&QAbstractItemModel::dataChanged),resets(model.sourceModel(),&QAbstractItemModel::modelReset),removes(model.sourceModel(),&QAbstractItemModel::rowsRemoved);
        for(int i=0;i<12;++i){auto row=rows[i].toMap();row["latency"]=QString::number(100-i);rows[i]=row;}
        model.updateRows(rows);QCOMPARE(changes.size(),1);QCOMPARE(model.get(0).value("id").toString(),QString("11"));
        QCOMPARE(retained.data(Qt::UserRole).toMap().value("latency").toString(),QString("89"));
        rows.remove(3,5);model.updateRows(rows);QCOMPARE(removes.size(),1);QCOMPARE(model.rowCount(),7);QVERIFY(retained.isValid());
        QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),QString("11"));QCOMPARE(resets.size(),0);
        changes.clear();model.updateRows(rows);QCOMPARE(changes.size(),0);
    }
    void catalogScaleMeasurements(){
        QJsonArray samples;
        for(const int count:{100,500,1000,2000}){
            NodeViewModel model;QVariantList rows;
            for(int i=0;i<count;++i)rows.append(QVariantMap{{"id",QString::number(i)},{"name",QString("日本 Tokyo %1").arg(count-i)},{"host","node.example.test"},{"protocol",i%2?"vless":"ss"},{"regionCode","JP"},{"regionName","日本"},{"status","未测试"},{"latency","—"}});
            QElapsedTimer timer;timer.start();model.updateRows(rows);QCOMPARE(model.rowCount(),count);const auto insert=timer.nsecsElapsed()/1e6;
            QSignalSpy resets(model.sourceModel(),&QAbstractItemModel::modelReset),changes(model.sourceModel(),&QAbstractItemModel::dataChanged);
            timer.restart();for(int i=0;i<20;++i){model.setQuery(i%2?"TOKYO":"VLESS");QCOMPARE(model.rowCount(),i%2?count:count/2);}const auto search=timer.nsecsElapsed()/1e6;
            model.setQuery("");model.setFilters({{"sort","latency"}});
            for(int i=0;i<count;++i){auto row=rows[i].toMap();row["latency"]=QString::number(count-i);row["status"]="可用";rows[i]=row;}
            timer.restart();model.updateRows(rows);const auto update=timer.nsecsElapsed()/1e6;
            QCOMPARE(model.get(0).value("id").toString(),QString::number(count-1));QCOMPARE(resets.size(),0);
            timer.restart();for(int i=0;i<20;++i)model.updateRows(rows);const auto unchanged=timer.nsecsElapsed()/1e6;
            samples.append(QJsonObject{{"nodes",count},{"insertMs",insert},{"search20Ms",search},{"allLatencyUpdateMs",update},{"unchanged20Ms",unchanged},{"dataChangedSignals",changes.size()},{"modelResets",resets.size()}});
        }
        const QJsonDocument report(samples);qInfo().noquote()<<report.toJson(QJsonDocument::Compact);
        const auto output=qEnvironmentVariable("SWIRL_NODE_MODEL_REPORT");if(!output.isEmpty()){QFile file(output);QVERIFY(file.open(QIODevice::WriteOnly));file.write(report.toJson());}
    }
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
QTEST_GUILESS_MAIN(NodeViewModelTests)
#include "NodeViewModelTests.moc"

#include "app/NodeSectionModel.h"

#include <QAbstractItemModelTester>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPersistentModelIndex>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>
#include <algorithm>
#include <cmath>
#include <memory>

namespace {
QVariantMap node(const QString &id,const QString &name,const QString &kind="manual",const QString &source={},int latency=-1) {
    return {{"id",id},{"name",name},{"sourceKind",kind},{"sourceId",source},
        {"sourceName",kind=="subscription"?QStringLiteral("Provider label"):QString()},
        {"protocol","vless"},{"regionCode","JP"},{"regionName","日本"},
        {"latency",latency<0?QStringLiteral("—"):QString::number(latency)}};
}
QStringList keys(const NodeSectionModel &model) {
    QStringList result;for(int row=0;row<model.rowCount();++row)result.append(model.get(row).value("displayKey").toString());return result;
}
double percentile(QList<double> values,double quantile) {
    std::sort(values.begin(),values.end());
    return values.at(std::clamp(int(std::ceil(values.size()*quantile))-1,0,int(values.size())-1));
}
}

class NodeSectionModelTests final : public QObject {
    Q_OBJECT
private slots:
    void initTestCase() {
        QVERIFY(m_settings.isValid());QCoreApplication::setOrganizationName("SwirlNodeSectionTests");
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,m_settings.path());
    }
    void init() { QSettings().clear(); }
    void sourceNamespacesAndProviderOrder() {
        NodeViewModel source;
        source.updateRows({node("s1","Alpha","subscription","a"),node("m1","Manual"),
            node("s2","Zulu","subscription","b"),node("l1","Old","legacy","a")});
        NodeSectionModel model;model.setProviders({QVariantMap{{"id","b"},{"name","Same"}},QVariantMap{{"id","a"},{"name","Same"}},QVariantMap{{"id","empty"},{"name","Empty"}}});
        model.setSource(&source);QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        QCOMPARE(model.count(),4);QCOMPARE(model.total(),4);
        QCOMPARE(keys(model),QStringList({"section:manual","node:m1","section:subscription:b","node:s2",
            "section:subscription:a","node:s1","section:subscription:empty","section:legacy","node:l1"}));
        for(int row=0;row<model.rowCount();++row) {
            const auto entry=model.get(row);
            if(entry.value("rowKind")=="section") {
                QVERIFY(entry.value("id").toString().isEmpty());
                QVERIFY(!(model.flags(model.index(row,0))&Qt::ItemIsSelectable));
            }
        }
        QCOMPARE(model.nodeIds(),QStringList({"m1","s2","s1","l1"}));
        QCOMPARE(model.indexOfNode(""),-1);QVERIFY(model.get(-1).isEmpty());
    }
    void collapsedNodesRemainInFilteredTestScopeAndSearchRestoresCollapse() {
        NodeViewModel source;source.updateRows({node("a1","Tokyo one","subscription","a"),node("a2","Tokyo two","subscription","a"),node("b1","London","subscription","b")});
        NodeSectionModel model;model.setProviders({QVariantMap{{"id","a"},{"name","A"}},QVariantMap{{"id","b"},{"name","B"}}});model.setSource(&source);
        QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        model.toggleSection("subscription:a");
        QCOMPARE(model.count(),3);QCOMPARE(model.displayCount(),3);QCOMPARE(model.indexOfNode("a1"),-1);
        QCOMPARE(model.nodeIds(),QStringList({"a1","a2","b1"}));
        source.setQuery("Tokyo");QCOMPARE(model.count(),2);QCOMPARE(model.displayCount(),3);
        QVERIFY(model.indexOfNode("a1")>=0);QVERIFY(!model.get(0).value("collapsible").toBool());
        model.toggleSection("subscription:a");QCOMPARE(model.displayCount(),3);
        source.setQuery("");QCOMPARE(model.indexOfNode("a1"),-1);
        QVERIFY(!model.get(model.rowForDisplayKey("section:subscription:a")).value("expanded").toBool());
        model.toggleSection("subscription:a");QVERIFY(model.indexOfNode("a1")>=0);
    }
    void filteringKeepsCatalogTotalsAndHidesUnrelatedEmptyProviders() {
        NodeViewModel source;source.updateRows({node("a1","Tokyo","subscription","a"),node("a2","Kyoto","subscription","a"),node("m","Manual")});
        NodeSectionModel model;model.setProviders({QVariantMap{{"id","a"},{"name","A"}},QVariantMap{{"id","empty"},{"name","Empty"}}});model.setSource(&source);
        QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        source.setQuery("Tokyo");QCOMPARE(model.count(),1);QCOMPARE(model.total(),3);QCOMPARE(model.rowCount(),2);
        QCOMPARE(model.get(0).value("matchedCount").toInt(),1);QCOMPARE(model.get(0).value("totalCount").toInt(),2);
        source.setQuery("no match");QCOMPARE(model.rowCount(),0);QCOMPARE(model.nodeIds().size(),0);
        source.setQuery("");source.setFilters({{"sourceKind","subscription"},{"sourceId","empty"}});
        QCOMPARE(model.rowCount(),1);QCOMPARE(model.get(0).value("sectionKey").toString(),QString("subscription:empty"));
        source.setFilters({{"sourceKind","manual"}});QCOMPARE(model.nodeIds(),QStringList({"m"}));
        source.setFilters({{"group","favorites"}});QCOMPARE(model.rowCount(),0);
        source.toggleFavorite("a1");QCOMPARE(model.nodeIds(),QStringList({"a1"}));QCOMPARE(model.rowCount(),2);
    }
    void renamesDoNotChangeSectionOrNodeIdentities() {
        NodeViewModel source;source.updateRows({node("a1","One","subscription","a")});
        NodeSectionModel model;model.setProviders({QVariantMap{{"id","a"},{"name","Before"}}});model.setSource(&source);
        QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        const QPersistentModelIndex header(model.index(0,0)),retained(model.index(1,0));
        QSignalSpy resets(&model,&QAbstractItemModel::modelReset),removed(&model,&QAbstractItemModel::rowsRemoved);
        model.setProviders({QVariantMap{{"id","a"},{"name","After"}}});
        source.updateRows({node("a1","Renamed","subscription","a")});
        QVERIFY(header.isValid());QVERIFY(retained.isValid());
        QCOMPARE(header.data(Qt::UserRole).toMap().value("sectionName").toString(),QString("After"));
        QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),QString("a1"));
        QCOMPARE(retained.data(Qt::UserRole).toMap().value("name").toString(),QString("Renamed"));
        QCOMPARE(resets.size(),0);QCOMPARE(removed.size(),0);
    }
    void sortIsWithinSourceAndPersistentSelectionFollowsNode() {
        NodeViewModel source;source.updateRows({node("a1","One","subscription","a",80),node("a2","Two","subscription","a",10),node("b1","B","subscription","b",1)});
        NodeSectionModel model;model.setProviders({QVariantMap{{"id","a"},{"name","A"}},QVariantMap{{"id","b"},{"name","B"}}});model.setSource(&source);
        QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        const QPersistentModelIndex retained(model.index(model.indexOfNode("a1"),0));
        QSignalSpy moved(&model,&QAbstractItemModel::rowsMoved),resets(&model,&QAbstractItemModel::modelReset);
        source.setFilters({{"sort","latency"}});
        QCOMPARE(model.nodeIds(),QStringList({"a2","a1","b1"}));
        QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),QString("a1"));
        QCOMPARE(retained.row(),model.indexOfNode("a1"));QVERIFY(moved.size()>0);QCOMPARE(resets.size(),0);
    }
    void removingOneNodeInvalidatesOnlyItsPersistentIndex() {
        NodeViewModel source;source.updateRows({node("a","A"),node("b","B"),node("c","C")});
        NodeSectionModel model;model.setSource(&source);QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        const QPersistentModelIndex removed(model.index(model.indexOfNode("b"),0)),retained(model.index(model.indexOfNode("c"),0));
        QSignalSpy resets(&model,&QAbstractItemModel::modelReset),about(&model,&NodeSectionModel::aboutToSync),synced(&model,&NodeSectionModel::synced);
        source.updateRows({node("a","A"),node("c","C")});
        QVERIFY(!removed.isValid());QVERIFY(retained.isValid());QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),QString("c"));
        QCOMPARE(model.count(),2);QCOMPARE(about.size(),1);QCOMPARE(synced.size(),1);QCOMPARE(resets.size(),0);
    }
    void noChangeAndUnrelatedProvidersProduceNoProjectionWork() {
        NodeViewModel source;const QVariantList rows{node("a","A")};source.updateRows(rows);
        NodeSectionModel model;model.setSource(&source);
        QSignalSpy about(&model,&NodeSectionModel::aboutToSync),synced(&model,&NodeSectionModel::synced),changed(&model,&NodeSectionModel::changed);
        for(int iteration=0;iteration<20;++iteration)source.updateRows(rows);
        model.setProviders({});QCOMPARE(about.size(),0);QCOMPARE(synced.size(),0);QCOMPARE(changed.size(),0);
    }
    void largeReorderingIsOnePermutationAndLatencyUpdateIsOneProjection() {
        NodeViewModel source;QVariantList rows;
        for(int row=0;row<2000;++row)rows.append(node(QString::number(row),QString("Node %1").arg(row,4,10,QLatin1Char('0')),"subscription","a",row));
        source.updateRows(rows);NodeSectionModel model;model.setProviders({QVariantMap{{"id","a"},{"name","A"}}});model.setSource(&source);
        QAbstractItemModelTester tester(&model,QAbstractItemModelTester::FailureReportingMode::QtTest);
        const QPersistentModelIndex retained(model.index(model.indexOfNode("1500"),0));
        QSignalSpy resets(&model,&QAbstractItemModel::modelReset),layouts(&model,&QAbstractItemModel::layoutChanged),moves(&model,&QAbstractItemModel::rowsMoved),batches(&model,&NodeSectionModel::synced);
        QElapsedTimer timer;timer.start();source.setFilters({{"sort","name"},{"descending",true}});
        qInfo()<<"2000-node section sort with model contract tester ms"<<timer.nsecsElapsed()/1e6;
        QCOMPARE(model.get(1).value("id").toString(),QString("1999"));QCOMPARE(model.nodeIds().size(),2000);
        QCOMPARE(layouts.size(),1);QCOMPARE(moves.size(),0);QCOMPARE(batches.size(),1);QCOMPARE(resets.size(),0);
        QVERIFY(retained.isValid());QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),QString("1500"));
        batches.clear();
        for(int row=0;row<rows.size();++row){auto value=rows.at(row).toMap();value["latency"]=QString::number(3000-row);rows[row]=value;}
        source.updateRows(rows);QCOMPARE(batches.size(),1);QCOMPARE(resets.size(),0);
    }
    void destroyingOrReplacingSourceDoesNotLeaveNodeReferences() {
        auto source=std::make_unique<NodeViewModel>();source->updateRows({node("a","A")});
        NodeSectionModel model;model.setSource(source.get());QCOMPARE(model.count(),1);
        source.reset();QVERIFY(!model.source());QCOMPARE(model.count(),0);QCOMPARE(model.total(),0);QCOMPARE(model.rowCount(),0);
        NodeViewModel replacement;replacement.updateRows({node("b","B")});model.setSource(&replacement);QCOMPARE(model.nodeIds(),QStringList({"b"}));
        model.setSource(nullptr);QCOMPARE(model.nodeIds().size(),0);QCOMPARE(model.indexOfNode("b"),-1);
    }
    void projectionScaleMeasurements() {
        // Pair the existing catalog sort with/without the presentation model.
        // QAbstractItemModelTester deliberately does full model traversals on
        // every signal, so it must not be attached to these timing samples.
        QJsonArray samples;
        for(const int count:{100,500,2000}) {
            QVariantList rows;
            for(int row=0;row<count;++row)rows.append(node(QString::number(row),QString("Node %1").arg(row,4,10,QLatin1Char('0')),"subscription","a",row));
            NodeViewModel baseline,source;baseline.updateRows(rows);source.updateRows(rows);
            NodeSectionModel model;model.setProviders({QVariantMap{{"id","a"},{"name","A"}}});model.setSource(&source);
            QSignalSpy batches(&model,&NodeSectionModel::synced),resets(&model,&QAbstractItemModel::modelReset);
            const QPersistentModelIndex retained(model.index(model.indexOfNode(QString::number(count/2)),0));
            QJsonArray baseTimes,projectedTimes;QList<double> baseSamples,projectedSamples;
            for(int iteration=0;iteration<6;++iteration) {
                const QVariantMap filters{{"sort","name"},{"descending",iteration%2==0}};
                QElapsedTimer timer;double baseMs=0,projectedMs=0;
                if(iteration%2==0) {
                    timer.start();baseline.setFilters(filters);baseMs=timer.nsecsElapsed()/1e6;
                    timer.restart();source.setFilters(filters);projectedMs=timer.nsecsElapsed()/1e6;
                } else {
                    timer.start();source.setFilters(filters);projectedMs=timer.nsecsElapsed()/1e6;
                    timer.restart();baseline.setFilters(filters);baseMs=timer.nsecsElapsed()/1e6;
                }
                const auto expected=QString::number(iteration%2==0?count-1:0);
                QCOMPARE(baseline.get(0).value("id").toString(),expected);
                QCOMPARE(model.get(1).value("id").toString(),expected);
                QCOMPARE(model.count(),count);QVERIFY(retained.isValid());
                QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),QString::number(count/2));
                baseTimes.append(baseMs);projectedTimes.append(projectedMs);baseSamples.append(baseMs);projectedSamples.append(projectedMs);
            }
            QCOMPARE(batches.size(),6);QCOMPARE(resets.size(),0);
            samples.append(QJsonObject{{"nodes",count},{"baselineSortMs",baseTimes},{"withSectionsSortMs",projectedTimes},
                {"baselineP50Ms",percentile(baseSamples,0.5)},{"baselineP95Ms",percentile(baseSamples,0.95)},
                {"withSectionsP50Ms",percentile(projectedSamples,0.5)},{"withSectionsP95Ms",percentile(projectedSamples,0.95)},
                {"projectionBatches",batches.size()},{"modelResets",resets.size()}});
        }
        qInfo().noquote()<<QJsonDocument(samples).toJson(QJsonDocument::Compact);
    }
    void twoThousandNodesAcrossThirtyTwoSameNamedSources() {
        constexpr int count=2000,sourceCount=32;
        QVariantList providers,rows;QHash<QString,QString> nodeSources;
        QHash<QString,int> totals,targetTotals;QSet<QString> targetIds,allIds;
        QStringList sourceIds;
        for(int source=0;source<sourceCount;++source) {
            const auto id=QString("10000000-0000-4000-8000-%1").arg(source,12,16,QLatin1Char('0'));
            sourceIds.append(id);providers.append(QVariantMap{{"id",id},{"name","Same provider name"}});
        }
        QString retainedId;
        for(int row=0;row<count;++row) {
            const auto id=QString("20000000-0000-4000-8000-%1").arg(row,12,16,QLatin1Char('0'));
            const auto source=sourceIds.at(row%sourceCount),key="subscription:"+source;
            const bool target=row%5==0;
            rows.append(node(id,QString("%1 Node %2").arg(target?"Target":"Other").arg(row,4,10,QLatin1Char('0')),"subscription",source,row));
            nodeSources.insert(id,key);++totals[key];allIds.insert(id);
            if(target){++targetTotals[key];targetIds.insert(id);}
            if(row==85)retainedId=id;
        }
        NodeViewModel source;source.updateRows(rows);NodeSectionModel model;model.setProviders(providers);
        QElapsedTimer timer;timer.start();model.setSource(&source);const auto initialProjectionMs=timer.nsecsElapsed()/1e6;
        QCOMPARE(model.count(),count);QCOMPARE(model.total(),count);QCOMPARE(model.displayCount(),count+sourceCount);
        const QPersistentModelIndex retained(model.index(model.indexOfNode(retainedId),0));QVERIFY(retained.isValid());
        QSet<QString> sections;QString currentSection;int nodeRows=0;
        for(int row=0;row<model.rowCount();++row) {
            const auto entry=model.get(row);
            if(entry.value("rowKind")=="section") {
                currentSection=entry.value("sectionKey").toString();sections.insert(currentSection);
                QCOMPARE(entry.value("sectionName").toString(),QString("Same provider name"));
                QCOMPARE(entry.value("matchedCount").toInt(),totals.value(currentSection));
                QCOMPARE(entry.value("totalCount").toInt(),totals.value(currentSection));
            } else {
                const auto id=entry.value("id").toString();QVERIFY(!QUuid(id).isNull());
                QCOMPARE(entry.value("sectionKey").toString(),currentSection);QCOMPARE(nodeSources.value(id),currentSection);++nodeRows;
            }
        }
        QCOMPARE(sections.size(),sourceCount);QCOMPARE(nodeRows,count);
        QSignalSpy resets(&model,&QAbstractItemModel::modelReset),batches(&model,&NodeSectionModel::synced);
        timer.restart();source.setFilters({{"sort","latency"},{"descending",true}});const auto sortMs=timer.nsecsElapsed()/1e6;
        QVERIFY(retained.isValid());QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),retainedId);
        const auto collapsed="subscription:"+sourceIds.first();model.toggleSection(collapsed);
        QCOMPARE(model.displayCount(),count+sourceCount-totals.value(collapsed));QCOMPARE(model.count(),count);
        const auto filteredBeforeQuery=model.nodeIds();QCOMPARE(QSet<QString>(filteredBeforeQuery.begin(),filteredBeforeQuery.end()),allIds);
        timer.restart();source.setQuery("Target");const auto queryMs=timer.nsecsElapsed()/1e6;
        QCOMPARE(model.count(),targetIds.size());QCOMPARE(model.displayCount(),targetIds.size()+sourceCount);
        const auto filtered=model.nodeIds();QCOMPARE(QSet<QString>(filtered.begin(),filtered.end()),targetIds);
        for(const auto &key:sections) {
            const auto header=model.get(model.rowForDisplayKey("section:"+key));
            QCOMPARE(header.value("matchedCount").toInt(),targetTotals.value(key));
            QCOMPARE(header.value("totalCount").toInt(),totals.value(key));QVERIFY(header.value("expanded").toBool());
        }
        QVERIFY(retained.isValid());QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),retainedId);
        source.setQuery("");QCOMPARE(model.displayCount(),count+sourceCount-totals.value(collapsed));
        QVERIFY(!model.get(model.rowForDisplayKey("section:"+collapsed)).value("expanded").toBool());
        QVERIFY(retained.isValid());QCOMPARE(retained.data(Qt::UserRole).toMap().value("id").toString(),retainedId);
        QCOMPARE(resets.size(),0);QCOMPARE(batches.size(),4);
        qInfo().noquote()<<"multi-source single-sample model measurements"<<QJsonDocument(QJsonObject{{"nodes",count},{"sources",sourceCount},{"sampleCount",1},
            {"initialProjectionMs",initialProjectionMs},{"warmSortMs",sortMs},{"queryMs",queryMs},{"modelResets",resets.size()},{"projectionBatches",batches.size()}}).toJson(QJsonDocument::Compact);
    }
private:
    QTemporaryDir m_settings;
};

QTEST_GUILESS_MAIN(NodeSectionModelTests)
#include "NodeSectionModelTests.moc"

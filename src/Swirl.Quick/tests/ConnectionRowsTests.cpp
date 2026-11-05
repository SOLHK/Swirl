#include "app/SwirlConnectionRows.h"

#include <QAbstractItemModelTester>
#include <QImage>
#include <QJSValue>
#include <QPersistentModelIndex>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QSignalSpy>
#include <QStringListModel>
#include <QtTest>
#include <algorithm>
#include <functional>
#include <memory>

class RowsCallback : public QObject {
    Q_OBJECT
public:
    std::function<void()> callback;
    Q_INVOKABLE void run() { if (callback) callback(); }
};

class NativeSnapshotSource : public QObject {
    Q_OBJECT
public:
    QVariantList rows;
    std::function<void()> onRead;
    int reads=0;
    Q_INVOKABLE QVariantList connectionSnapshot(){++reads;const auto result=rows;const auto callback=onRead;if(callback)callback();return result;}
};

class ConnectionRowsTests : public QObject {
    Q_OBJECT
    static std::unique_ptr<SwirlConnectionRows> model(QQmlEngine &engine) {
        QQmlComponent component(&engine);
        component.setData("import ConnectionRowsTest 1.0\nConnectionRows {}", QUrl());
        auto result = std::unique_ptr<SwirlConnectionRows>(qobject_cast<SwirlConnectionRows *>(component.create()));
        if (!result) qWarning().noquote() << component.errorString();
        return result;
    }
    static QJSValue rows(QQmlEngine &engine, const char *json) {
        return engine.evaluate(QStringLiteral("(") + QString::fromUtf8(json) + QLatin1Char(')'));
    }
    static QString json(QQmlEngine &engine, const QJSValue &value) {
        const auto object = engine.globalObject().property(QStringLiteral("JSON"));
        return object.property(QStringLiteral("stringify")).callWithInstance(object, {value}).toString();
    }
    static QStringList keys(SwirlConnectionRows &model) {
        QStringList result;
        for (int i = 0; i < model.count(); ++i) result.append(model.get(i).property(QStringLiteral("id")).toString());
        return result;
    }
private slots:
    void initTestCase() {
        // The GUILESS model tester also inspects GUI role metatypes in Qt 6.12.
        // Load/register QtGui without creating a window or a platform surface.
        qRegisterMetaType<QImage>("QImage");
        qmlRegisterType<SwirlConnectionRows>("ConnectionRowsTest", 1, 0, "ConnectionRows");
    }
    void fullImmutableEntriesAndNoOpUpdates() {
        QQmlEngine engine;
        auto target = model(engine);
        QVERIFY(target);
        QAbstractItemModelTester tester(target.get(), QAbstractItemModelTester::FailureReportingMode::QtTest);
        int changed = 0;
        connect(target.get(), &QAbstractItemModel::dataChanged, target.get(), [&] { ++changed; });
        QSignalSpy about(target.get(), &SwirlConnectionRows::aboutToSync);
        QSignalSpy done(target.get(), &SwirlConnectionRows::synced);
        const auto input = rows(engine, R"([{"id":"a","host":"长节点.example","ip":"2001:db8::1","route":{"chosen_ip":"2001:db8::1","revision":"9007199254740993","chain":["来源",null,true,7]},"missing":null,"active":false,"downloadBytes":123456789}])");
        target->setSourceRows(input);
        QCOMPARE(target->count(), 1);
        QCOMPARE(target->error(), QString());
        QCOMPARE(target->rowForDisplayKey(QStringLiteral("a")), 0);
        QCOMPARE(target->roleNames().value(SwirlConnectionRows::EntryRole), QByteArray("entry"));
        const QJSValue oldEntry = target->get(0);
        QVERIFY(oldEntry.strictlyEquals(input.property(0)));
        QVERIFY(target->data(target->index(0), SwirlConnectionRows::EntryRole).value<QJSValue>().strictlyEquals(oldEntry));
        QCOMPARE(json(engine, oldEntry), json(engine, input.property(0)));
        QCOMPARE(about.count(), 1);
        QCOMPARE(done.count(), 1);
        const auto sameValue = engine.evaluate(QLatin1Char('(') + json(engine, input) + QLatin1Char(')'));
        target->setSourceRows(sameValue);
        QVERIFY(target->get(0).strictlyEquals(oldEntry));
        QCOMPARE(changed, 0);
        QCOMPARE(about.count(), 1);
        const auto update = rows(engine, R"([{"id":"a","host":"长节点.example","ip":"2001:db8::2","route":{"chosen_ip":"2001:db8::2","revision":"9007199254740994","chain":["新来源",null,false,8]},"missing":null,"active":true,"downloadBytes":123456799}])");
        target->setSourceRows(update);
        QCOMPARE(changed, 1);
        QVERIFY(target->get(0).strictlyEquals(update.property(0)));
        QCOMPARE(json(engine, oldEntry), json(engine, input.property(0)));
        QCOMPARE(oldEntry.property("route").property("chosen_ip").toString(), QStringLiteral("2001:db8::1"));
        QCOMPARE(json(engine, target->get(0)), json(engine, update.property(0)));
        QVERIFY(target->get(-1).isUndefined());
        QVERIFY(target->get(1).isUndefined());
        QVERIFY(!target->data({}, SwirlConnectionRows::EntryRole).isValid());
        QVERIFY(!target->data(target->index(0, 1), SwirlConnectionRows::EntryRole).isValid());
        QStringListModel foreign(QStringList{QStringLiteral("foreign")});
        QVERIFY(!target->data(foreign.index(0), SwirlConnectionRows::EntryRole).isValid());
        QCOMPARE(target->rowCount(target->index(0)), 0);
    }
    void movesKeepPersistentIdentityAndRemovalInvalidates() {
        QQmlEngine engine;
        auto target = model(engine);
        QVERIFY(target);
        QAbstractItemModelTester tester(target.get(), QAbstractItemModelTester::FailureReportingMode::QtTest);
        QSignalSpy moves(target.get(), &QAbstractItemModel::rowsMoved);
        QSignalSpy layouts(target.get(), &QAbstractItemModel::layoutChanged);
        QSignalSpy resets(target.get(), &QAbstractItemModel::modelReset);
        target->setSourceRows(rows(engine, R"([{"id":"a"},{"id":"b"},{"id":"c"},{"id":"d"}])"));
        const QPersistentModelIndex retained(target->index(1));
        const QJSValue retainedEntry = target->get(1);
        const QList<QByteArray> updates = {
            R"([{"id":"d"},{"id":"b"},{"id":"a"},{"id":"c"}])",
            R"([{"id":"b"},{"id":"c"},{"id":"d"},{"id":"a"}])",
            R"([{"id":"x"},{"id":"b"},{"id":"a"},{"id":"y"}])",
            R"([{"id":"y"},{"id":"a"},{"id":"b"},{"id":"x"}])"
        };
        for (const auto &update : updates) {
            const auto desired = rows(engine, update.constData());
            target->setSourceRows(desired);
            QVERIFY(retained.isValid());
            QCOMPARE(retained.row(), target->rowForDisplayKey(QStringLiteral("b")));
            QVERIFY(retained.data(SwirlConnectionRows::EntryRole).value<QJSValue>().strictlyEquals(retainedEntry));
            for (int i = 0; i < target->count(); ++i) {
                QCOMPARE(json(engine, target->get(i)), json(engine, desired.property(i)));
                QCOMPARE(target->rowForDisplayKey(target->get(i).property("id").toString()), i);
            }
        }
        QVERIFY(moves.count() > 0);
        QCOMPARE(layouts.count(), 0);
        QCOMPARE(resets.count(), 0);
        target->setSourceRows(rows(engine, R"([{"id":"y"},{"id":"x"}])"));
        QVERIFY(!retained.isValid());
        QCOMPARE(target->rowForDisplayKey(QStringLiteral("b")), -1);
        target->setSourceRows(rows(engine, "[]"));
        QCOMPARE(target->count(), 0);
        target->setSourceRows(rows(engine, R"([{"id":"b"}])"));
        QCOMPARE(target->count(), 1);
        QVERIFY(!retained.isValid());
    }
    void twoThousandCompleteRowsAcrossUpdatesAndReorder() {
        QQmlEngine engine;
        auto target = model(engine);
        QVERIFY(target);
        const auto make = engine.evaluate(QStringLiteral(R"((function(step) {
            const result=[];
            for(let i=0;i<2000;++i)result.push({id:'id-'+i,host:'长节点-'+i+'.example',
                ip:'2001:db8::'+i,uploadBytes:i*100+step,downloadBytes:i*200+step,
                sourcePort:1000+i,active:i%2===0,missing:null,
                route:{chosen_ip:'2001:db8::'+i,revision:'9007199254740993',
                    group_chain:['来源',i,null,true],unknown:{value:step}}});
            if(step===3){result.splice(100,2);result.unshift({id:'new-a',route:{all:[null,true]}});result.push({id:'new-b',route:{all:[false,7]}});}
            if(step===4)result.reverse();
            if(step===5){const first=result[0];result[0]=result[1];result[1]=first;}
            return result;
        }))"));
        QVERIFY(make.isCallable());
        for (int step = 0; step < 6; ++step) {
            const QJSValue desired = make.call({step});
            QVERIFY(desired.isArray());
            target->setSourceRows(desired);
            QCOMPARE(target->error(), QString());
            QCOMPARE(target->count(), 2000);
            for (int i = 0; i < target->count(); ++i) {
                QCOMPARE(json(engine, target->get(i)), json(engine, desired.property(i)));
                QCOMPARE(target->rowForDisplayKey(target->get(i).property("id").toString()), i);
            }
        }
    }
    void invalidSourceIsAtomicAndCanRecover() {
        QQmlEngine engine;
        auto target = model(engine);
        QVERIFY(target);
        QAbstractItemModelTester tester(target.get(), QAbstractItemModelTester::FailureReportingMode::QtTest);
        target->setSourceRows(rows(engine, R"([{"id":"retained","route":{"revision":"9007199254740993"}}])"));
        const auto original = target->get(0);
        QSignalSpy changes(target.get(), &SwirlConnectionRows::aboutToSync);
        const QStringList invalid = {
            QStringLiteral("({bad:true})"), QStringLiteral("[null]"),
            QStringLiteral("[{}]"), QStringLiteral("[{id:''}]"),
            QStringLiteral("[{id:'same'},{id:'same'}]"),
            QStringLiteral("(function(){const row={id:'cycle'};row.self=row;return [row]})()"),
            QStringLiteral("(function(){const a=[];a.length=2147483648;return a})()")
        };
        for (const auto &expression : invalid) {
            target->setSourceRows(engine.evaluate(expression));
            QVERIFY2(!target->error().isEmpty(), qPrintable(expression));
            QCOMPARE(target->count(), 1);
            QVERIFY(target->get(0).strictlyEquals(original));
            QCOMPARE(changes.count(), 0);
        }
        target->setSourceRows(rows(engine, R"([{"id":"recovered"}])"));
        QCOMPARE(target->error(), QString());
        QCOMPARE(keys(*target), QStringList{QStringLiteral("recovered")});
    }
    void bulkNotificationsPreserveRetainedRowsAndIndices() {
        QQmlEngine engine;
        auto target = model(engine);
        QVERIFY(target);
        const auto make = engine.evaluate(QStringLiteral(R"((function(step) {
            const result=[];
            for(let i=0;i<2000;++i)result.push({id:'bulk-'+i,bytes:i+step,
                route:{chosen_ip:'2001:db8::'+i,unknown:[null,true,step]}});
            return result;
        }))"));
        QSignalSpy inserted(target.get(), &QAbstractItemModel::rowsInserted);
        QSignalSpy changed(target.get(), &QAbstractItemModel::dataChanged);
        QSignalSpy moved(target.get(), &QAbstractItemModel::rowsMoved);
        QSignalSpy resets(target.get(), &QAbstractItemModel::modelReset);
        target->setSourceRows(make.call({0}));
        QCOMPARE(target->count(), 2000);
        QCOMPARE(inserted.count(), 1);
        QCOMPARE(inserted.first().at(1).toInt(), 0);
        QCOMPARE(inserted.first().at(2).toInt(), 1999);
        const QPersistentModelIndex retained(target->index(1000));
        const auto history = target->get(1000);
        target->setSourceRows(make.call({1}));
        QCOMPARE(changed.count(), 1);
        QCOMPARE(changed.first().at(0).value<QModelIndex>().row(), 0);
        QCOMPARE(changed.first().at(1).value<QModelIndex>().row(), 1999);
        QVERIFY(retained.isValid());
        QCOMPARE(retained.row(), 1000);
        QCOMPARE(retained.data(SwirlConnectionRows::EntryRole).value<QJSValue>().property("bytes").toInt(), 1001);
        QCOMPARE(history.property("bytes").toInt(), 1000);
        const auto source = target->sourceRows();
        engine.globalObject().setProperty(QStringLiteral("bulkSource"), source);
        const auto rotate = engine.evaluate(QStringLiteral("bulkSource.slice(1000).concat(bulkSource.slice(0,1000))"));
        target->setSourceRows(rotate);
        QCOMPARE(moved.count(), 1);
        QCOMPARE(moved.first().at(1).toInt(), 1000);
        QCOMPARE(moved.first().at(2).toInt(), 1999);
        QCOMPARE(moved.first().at(4).toInt(), 0);
        QCOMPARE(changed.count(), 1);
        QVERIFY(retained.isValid());
        QCOMPARE(retained.row(), 0);
        QCOMPARE(resets.count(), 0);
        for (int i = 0; i < target->count(); ++i) {
            QCOMPARE(json(engine, target->get(i)), json(engine, rotate.property(i)));
            QCOMPARE(target->rowForDisplayKey(target->get(i).property("id").toString()), i);
        }
    }
    void reentrantChangesCoalesceAfterCurrentTransaction() {
        QQmlEngine engine;
        auto target = model(engine);
        QVERIFY(target);
        QAbstractItemModelTester tester(target.get(), QAbstractItemModelTester::FailureReportingMode::QtTest);
        const auto initial = rows(engine, R"([{"id":"initial"}])");
        const auto superseded = rows(engine, R"([{"id":"superseded"}])");
        const auto latest = rows(engine, R"([{"id":"latest"}])");
        bool once = false;
        int depth = 0, maximumDepth = 0;
        connect(target.get(), &SwirlConnectionRows::aboutToSync, target.get(), [&] {
            maximumDepth = std::max(maximumDepth, ++depth);
            if (!once) { once = true; target->setSourceRows(superseded); target->setSourceRows(latest); }
        });
        connect(target.get(), &SwirlConnectionRows::synced, target.get(), [&] { --depth; });
        target->setSourceRows(initial);
        QCOMPARE(keys(*target), QStringList{QStringLiteral("initial")});
        QVERIFY(QTest::qWaitFor([&] { return keys(*target) == QStringList{QStringLiteral("latest")}; }));
        QCOMPARE(maximumDepth, 1);
        QCOMPARE(depth, 0);
        bool replacingNotification = true;
        connect(target.get(), &SwirlConnectionRows::sourceRowsChanged, target.get(), [&] {
            if (replacingNotification) {
                replacingNotification = false;
                target->setSourceRows(latest);
            }
        });
        target->setSourceRows(superseded);
        QCOMPARE(keys(*target), QStringList{QStringLiteral("latest")});
    }
    void callbacksMayReplaceSourceOrDestroyOwner() {
        QQmlEngine engine;
        RowsCallback callback;
        QQmlEngine::setObjectOwnership(&callback, QQmlEngine::CppOwnership);
        engine.globalObject().setProperty(QStringLiteral("callback"), engine.newQObject(&callback));
        auto target = model(engine);
        QVERIFY(target);
        const auto latest = rows(engine, R"([{"id":"latest"}])");
        callback.callback = [&] { target->setSourceRows(latest); };
        target->setSourceRows(engine.evaluate(QStringLiteral("[{get id(){callback.run();return 'stale'}}]")));
        QVERIFY(QTest::qWaitFor([&] { return keys(*target) == QStringList{QStringLiteral("latest")}; }));
        for (const auto &expression : {
                 QStringLiteral("(function(){const a=[];Object.defineProperty(a,0,{get:function(){callback.run();return {id:'deleted'}}});return a})()"),
                 QStringLiteral("[{get id(){callback.run();return 'deleted'}}]"),
                 QStringLiteral("[{id:{toString:function(){callback.run();return 'deleted'}}}]"),
                 QStringLiteral("[{id:'deleted',toJSON:function(){callback.run();return {id:'deleted'}}}]")}) {
            target = model(engine);
            QVERIFY(target);
            QPointer<SwirlConnectionRows> guard(target.get());
            callback.callback = [&] { target.reset(); };
            const auto input = engine.evaluate(expression);
            guard->setSourceRows(input);
            QVERIFY(!guard);
        }
        target = model(engine);
        QVERIFY(target);
        target->setSourceRows(rows(engine, "[{}]"));
        QVERIFY(!target->error().isEmpty());
        QPointer<SwirlConnectionRows> errorGuard(target.get());
        connect(target.get(), &SwirlConnectionRows::errorChanged, target.get(), [&] {
            if (target->error().isEmpty()) target.reset();
        });
        target->setSourceRows(latest);
        QVERIFY(!errorGuard);
        target = model(engine);
        QVERIFY(target);
        QPointer<SwirlConnectionRows> signalGuard(target.get());
        connect(target.get(), &SwirlConnectionRows::aboutToSync, target.get(), [&] { target.reset(); });
        target->setSourceRows(latest);
        QVERIFY(!signalGuard);
    }
    void engineDestructionClearsRowsAndPendingWork() {
        auto engine = std::make_unique<QQmlEngine>();
        auto target = model(*engine);
        QVERIFY(target);
        target->setSourceRows(rows(*engine, R"([{"id":"retained"}])"));
        const QPersistentModelIndex retained(target->index(0));
        QSignalSpy reset(target.get(), &QAbstractItemModel::modelReset);
        engine.reset();
        QCOMPARE(target->count(), 0);
        QVERIFY(!retained.isValid());
        QVERIFY(target->get(0).isUndefined());
        QVERIFY(target->sourceRows().isUndefined());
        QCOMPARE(reset.count(), 1);
        engine = std::make_unique<QQmlEngine>();
        target = model(*engine);
        QVERIFY(target);
        const auto pending = rows(*engine, R"([{"id":"pending"}])");
        bool once = false;
        connect(target.get(), &SwirlConnectionRows::aboutToSync, target.get(), [&] {
            if (!once) { once = true; target->setSourceRows(pending); }
        });
        target->setSourceRows(rows(*engine, R"([{"id":"current"}])"));
        target.reset();
        QCoreApplication::processEvents();
    }
    void ownedProducerFreezesCompleteNativeValuesAndRetainsHistory() {
        QQmlEngine engine;auto target=model(engine);QVERIFY(target);
        QAbstractItemModelTester tester(target.get(),QAbstractItemModelTester::FailureReportingMode::QtTest);
        NativeSnapshotSource source;
        for(int i=0;i<2000;++i)source.rows.append(QVariantMap{{"id",QString("owned-%1").arg(i)},
            {"host",QString("长节点-%1.example").arg(i)},{"ip","198.51.100.1"},{"process",QVariant::fromValue(nullptr)},
            {"protocol",false},{"latency",0},{"uploadBytes",qint64(9007199254740993LL+i)},
            {"downloadBytes",qint64(9007199254740998LL+i)},{"__proto__","top-retained"},
            {"unknown",QVariantMap{{"2",i},{"10",true},{"__proto__","nested-retained"},{"null",QVariant::fromValue(nullptr)}}},
            {"route",QVariantMap{{"chosen_ip",QString("2001:db8::%1").arg(i)},
                {"revision","9007199254740993"},{"group_chain",QStringList{"来源","策略组"}}}}});
        const auto original=QJsonDocument::fromVariant(source.rows).toJson(QJsonDocument::Compact);
        auto expected=source.rows;
        for(auto &value:expected){auto row=value.toMap();row["ip"]=row.value("route").toMap().value("chosen_ip");
            row["process"]="missing";row["protocol"]="false";row["latency"]="0";value=row;}
        const auto referenceJson=engine.globalObject().property("JSON");
        const auto reference=referenceJson.property("parse").callWithInstance(referenceJson,
            {QString::fromUtf8(QJsonDocument::fromVariant(expected).toJson(QJsonDocument::Compact))});
        auto snapshot=target->readSnapshot(&source,"missing");QCOMPARE(source.reads,1);QVERIFY(snapshot.isArray());
        QCOMPARE(QJsonDocument::fromVariant(source.rows).toJson(QJsonDocument::Compact),original);
        QCOMPARE(json(engine,snapshot),json(engine,reference));
        const auto frozen=engine.evaluate(QStringLiteral(R"((function deep(value){if(value===null||typeof value!=='object')return true;
            return Object.isFrozen(value)&&Object.keys(value).every(key=>deep(value[key]));}))"));
        QVERIFY(frozen.call({snapshot}).toBool());
        const auto mutate=engine.evaluate(QStringLiteral("(function(value){'use strict';value.unknown.__proto__='changed'})"));
        QVERIFY(mutate.call({snapshot.property(0)}).isError());QCOMPARE(json(engine,snapshot),json(engine,reference));
        target->setSourceRows(snapshot);QCOMPARE(target->count(),2000);QCOMPARE(target->error(),QString());
        const QPersistentModelIndex retained(target->index(1000));const auto entry=target->get(1000);
        const auto history=json(engine,snapshot),entryHistory=json(engine,entry);
        QSignalSpy changes(target.get(),&QAbstractItemModel::dataChanged),moves(target.get(),&QAbstractItemModel::rowsMoved);
        auto same=target->readSnapshot(&source,"missing");target->setSourceRows(same);QCOMPARE(source.reads,2);
        QCOMPARE(changes.count(),0);QVERIFY(target->get(1000).strictlyEquals(entry));
        for(int i=0;i<2000;++i)QVERIFY(same.property(i).strictlyEquals(snapshot.property(i)));
        auto last=source.rows.last().toMap();last["downloadBytes"]=last.value("downloadBytes").toLongLong()+1;source.rows.last()=last;
        auto sparse=target->readSnapshot(&source,"missing");
        for(int i=0;i<1999;++i)QVERIFY(sparse.property(i).strictlyEquals(same.property(i)));
        QVERIFY(!sparse.property(1999).strictlyEquals(same.property(1999)));
        target->setSourceRows(sparse);QCOMPARE(changes.count(),1);
        QCOMPARE(changes.last().at(0).value<QModelIndex>().row(),1999);QCOMPARE(changes.last().at(1).value<QModelIndex>().row(),1999);
        QCOMPARE(json(engine,same),history);changes.clear();
        for(auto &value:source.rows){auto row=value.toMap();row["downloadBytes"]=row.value("downloadBytes").toLongLong()+7;value=row;}
        snapshot=target->readSnapshot(&source,"missing");target->setSourceRows(snapshot);QCOMPARE(changes.count(),1);
        QCOMPARE(json(engine,entry),entryHistory);QCOMPARE(json(engine,same),history);
        for(int i=0;i<target->count();++i)QVERIFY(target->get(i).strictlyEquals(snapshot.property(i)));
        engine.globalObject().setProperty("ownedSnapshot",snapshot);
        const auto rotated=engine.evaluate("ownedSnapshot.slice(1000).concat(ownedSnapshot.slice(0,1000))");
        target->setSourceRows(rotated);QCOMPARE(moves.count(),1);QVERIFY(retained.isValid());QCOMPARE(retained.row(),0);
        const auto filtered=engine.evaluate("ownedSnapshot.filter((row,index)=>index%2===0)");
        target->setSourceRows(filtered);QCOMPARE(target->count(),1000);QVERIFY(retained.isValid());
        source.rows.removeAt(1000);snapshot=target->readSnapshot(&source,"missing");target->setSourceRows(snapshot);
        QVERIFY(!retained.isValid());QCOMPARE(target->count(),1999);QCOMPARE(json(engine,entry),entryHistory);
    }
    void ownedProducerGuardsSourceCallbacksAndEngineClosure() {
        auto engine=std::make_unique<QQmlEngine>();auto target=model(*engine);QVERIFY(target);
        NativeSnapshotSource source;source.rows={QVariantMap{{"id","native"}}};
        const auto latest=rows(*engine,R"([{"id":"latest","value":7}])");
        source.onRead=[&]{target->setSourceRows(latest);};
        QVERIFY(target->readSnapshot(&source,"missing").isUndefined());QCOMPARE(keys(*target),QStringList{"latest"});
        source.onRead={};auto snapshot=target->readSnapshot(&source,"missing");target->setSourceRows(snapshot);
        QCOMPARE(keys(*target),QStringList{"native"});
        NativeSnapshotSource inner;inner.rows={QVariantMap{{"id","inner"}}};QJSValue nested;
        source.onRead=[&]{nested=target->readSnapshot(&inner,"missing");};
        QVERIFY(target->readSnapshot(&source,"missing").isUndefined());QVERIFY(nested.isArray());target->setSourceRows(nested);
        QCOMPARE(keys(*target),QStringList{"inner"});
        source.onRead=[&]{engine.reset();};
        QVERIFY(target->readSnapshot(&source,"missing").isUndefined());QCOMPARE(target->count(),0);QVERIFY(target->get(0).isUndefined());
        QCoreApplication::processEvents();QCOMPARE(target->count(),0);
        engine=std::make_unique<QQmlEngine>();target=model(*engine);QVERIFY(target);QPointer<SwirlConnectionRows> guard(target.get());
        source.onRead=[&]{target.reset();};const auto value=guard->readSnapshot(&source,"missing");QVERIFY(value.isUndefined());QVERIFY(!guard);
    }
    void ownedProducerUsesReadOnlyIntrinsicsAndRejectsInvalidSnapshots() {
        QQmlEngine engine;auto target=model(engine);QVERIFY(target);NativeSnapshotSource source;
        const auto descriptor=engine.evaluate("JSON.stringify(Object.getOwnPropertyDescriptor(Object,'freeze'))");
        const auto properties=QJsonDocument::fromJson(descriptor.toString().toUtf8()).object();
        QVERIFY(!properties.value("writable").toBool());QVERIFY(!properties.value("configurable").toBool());
        const auto latest=rows(engine,R"([{"id":"newest"}])");target->setSourceRows(latest);
        source.rows={QVariantMap{{"id","duplicate"}},QVariantMap{{"id","duplicate"}}};
        QVERIFY(target->readSnapshot(&source,"missing").isUndefined());QVERIFY(!target->error().isEmpty());QCOMPARE(keys(*target),QStringList{"newest"});
        source.rows={QVariantMap{{"id","valid"}}};auto snapshot=target->readSnapshot(&source,"missing");QVERIFY(snapshot.isArray());QCOMPARE(target->error(),QString());
        target->setSourceRows(snapshot);QCOMPARE(keys(*target),QStringList{"valid"});
    }
    void ownedProducerPreservesArraySlotsDespiteInheritedSetters() {
        QQmlEngine engine;auto target=model(engine);QVERIFY(target);
        NativeSnapshotSource source;source.rows={QVariantMap{{"id","array"},{"unknown",QVariantList{17,QStringLiteral("second")}}}};
        QVERIFY(!engine.evaluate("var swallowed=0;Object.defineProperty(Array.prototype,'0',{set:function(value){swallowed++},configurable:true});var trial=new Array(1);trial[0]=99").isError());
        QCOMPARE(engine.evaluate("swallowed").toInt(),1);
        const auto snapshot=target->readSnapshot(&source,"missing");
        const int swallowed=engine.evaluate("swallowed").toInt();
        QVERIFY(!engine.evaluate("delete Array.prototype[0]").isError());
        QCOMPARE(swallowed,1);
        QVERIFY(snapshot.isArray());QCOMPARE(snapshot.property(0).property("unknown").property(0).toInt(),17);
        QCOMPARE(snapshot.property(0).property("unknown").property(1).toString(),QStringLiteral("second"));
        target->setSourceRows(snapshot);QCOMPARE(target->get(0).property("id").toString(),QStringLiteral("array"));
    }
    void ownedComparisonKeepsUnknownJsonTypesDistinct() {
        QQmlEngine engine;auto target=model(engine);QVERIFY(target);NativeSnapshotSource source;
        const QVariantList cases={1,QStringLiteral("1"),false,0,QVariant::fromValue(nullptr),QString(),
            QVariantMap{{"nested",1}},QVariantMap{{"nested",QStringLiteral("1")}},
            QVariantList{QVariantMap{{"nested",false}}},QVariantList{QVariantMap{{"nested",0}}}};
        QSignalSpy changes(target.get(),&QAbstractItemModel::dataChanged);QJSValue historical;QString bytes;
        for(int i=0;i<cases.size();++i){
            source.rows={QVariantMap{{"id","typed"},{"unknown",cases[i]}}};
            const auto snapshot=target->readSnapshot(&source,"missing");QVERIFY(snapshot.isArray());
            const int notifications=changes.count();target->setSourceRows(snapshot);
            QCOMPARE(changes.count(),notifications+(i?1:0));
            QCOMPARE(json(engine,target->get(0)),json(engine,snapshot.property(0)));
            if(i)QCOMPARE(json(engine,historical),bytes);
            historical=target->get(0);bytes=json(engine,historical);
        }
    }
    void ownedProducerRetiresDestroyedSource() {
        QQmlEngine engine;
        auto target=model(engine);QVERIFY(target);auto source=std::make_unique<NativeSnapshotSource>();
        source->rows={QVariantMap{{"id","deleted-source"}}};bool called=false;
        source->onRead=[&]{called=true;source.reset();};
        auto *pointer=source.get();QVERIFY(target->readSnapshot(pointer,"missing").isUndefined());
        QVERIFY(called);QVERIFY(!source);QCOMPARE(target->count(),0);
    }
    void ownedProducerReusesOnlyStrictlyEqualFrozenSubtrees() {
        QQmlEngine engine;auto target=model(engine);QVERIFY(target);NativeSnapshotSource source;
        QVariantMap row{{"id","subtree"},{"uploadBytes",1},
            {"route",QVariantMap{{"chosen_ip","2001:db8::1"},{"group_chain",QStringList{"first"}}}},
            {"unknown",QVariantMap{{"__proto__","retained"},{"changing",QVariantMap{{"value",1}}},
                {"stable",QVariantMap{{"list",QVariantList{true,QVariant::fromValue(nullptr),7}}}}}}};
        source.rows={row};auto first=target->readSnapshot(&source,"missing");target->setSourceRows(first);
        const auto history=json(engine,first);
        const auto original=first.property(0);
        QSignalSpy changes(target.get(),&QAbstractItemModel::dataChanged);
        row["uploadBytes"]=2;source.rows={row};auto second=target->readSnapshot(&source,"missing");
        QVERIFY(!second.property(0).strictlyEquals(original));
        QVERIFY(second.property(0).property("route").strictlyEquals(original.property("route")));
        QVERIFY(second.property(0).property("unknown").strictlyEquals(original.property("unknown")));
        target->setSourceRows(second);QCOMPARE(changes.count(),1);QCOMPARE(json(engine,first),history);
        auto unknown=row.value("unknown").toMap();unknown["changing"]=QVariantMap{{"value",QStringLiteral("1")}};row["unknown"]=unknown;
        source.rows={row};auto third=target->readSnapshot(&source,"missing");target->setSourceRows(third);
        QCOMPARE(changes.count(),2);
        QVERIFY(!third.property(0).property("unknown").strictlyEquals(second.property(0).property("unknown")));
        QVERIFY(third.property(0).property("unknown").property("stable").strictlyEquals(second.property(0).property("unknown").property("stable")));
        QVERIFY(third.property(0).property("unknown").property("changing").property("value").isString());
        QVERIFY(second.property(0).property("unknown").property("changing").property("value").isNumber());
        auto route=row.value("route").toMap();route["group_chain"]=QStringList{"first","second"};row["route"]=route;
        source.rows={row};auto fourth=target->readSnapshot(&source,"missing");target->setSourceRows(fourth);
        QCOMPARE(changes.count(),3);
        QVERIFY(!fourth.property(0).property("route").strictlyEquals(third.property(0).property("route")));
        QVERIFY(fourth.property(0).property("unknown").strictlyEquals(third.property(0).property("unknown")));
        QCOMPARE(third.property(0).property("route").property("group_chain").property("length").toInt(),1);
        QCOMPARE(fourth.property(0).property("route").property("group_chain").property("length").toInt(),2);
        const auto latest=json(engine,fourth);row["uploadBytes"]=3;source.rows={row};QVERIFY(target->readSnapshot(&source,"missing").isArray());
        row["uploadBytes"]=2;source.rows={row};auto restored=target->readSnapshot(&source,"missing");target->setSourceRows(restored);
        QCOMPARE(changes.count(),4);QCOMPARE(json(engine,restored),latest);QCOMPARE(json(engine,first),history);
    }
};

QTEST_GUILESS_MAIN(ConnectionRowsTests)
#include "ConnectionRowsTests.moc"

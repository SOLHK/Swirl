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
};

QTEST_GUILESS_MAIN(ConnectionRowsTests)
#include "ConnectionRowsTests.moc"

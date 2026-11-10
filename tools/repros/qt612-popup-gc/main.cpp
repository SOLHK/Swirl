#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QTimer>
#include <QQuickStyle>
#include <QQmlIncubationController>
#include <QDebug>
#include <QElapsedTimer>
#include <QEvent>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaEnum>
#include <QtQml/private/qv4engine_p.h>
#include <QtQml/private/qv4mm_p.h>

class GcProbe final : public QObject {
    Q_OBJECT
public:
    QQmlEngine *engine = nullptr;
    int collections = 0;
    int completed = 0;
    bool incremental = false;
    int pendingReturns = 0;
    int engineMetaCallObservations = 0;
    int pendingEngineMetaCallObservations = 0;
    int pendingReturnCall = 0;
    qint64 pendingReturnAtUs = 0;
    QV4::GCState pendingReturnState = QV4::GCState::Invalid;
    QElapsedTimer runtime;
    Q_INVOKABLE bool collect(const QString &phase) {
        ++collections;
        if(incremental) engine->handle()->memoryManager->runGC();
        else engine->collectGarbage();
        const auto state=engine->handle()->memoryManager->gcStateMachine->state;
        if(incremental && state!=QV4::GCState::Invalid) {
            ++pendingReturns;
            pendingReturnCall=collections;
            pendingReturnAtUs=runtime.nsecsElapsed()/1000;
            pendingReturnState=state;
        }
        if(collections<=8) qInfo() << "GC_PHASE" << phase;
        return true;
    }
    Q_INVOKABLE void complete() { ++completed; }
    bool eventFilter(QObject *receiver,QEvent *event) override {
        if(incremental&&receiver==engine&&event->type()==QEvent::MetaCall&&pendingReturnCall>0) {
            ++engineMetaCallObservations;
            const auto observed=engine->handle()->memoryManager->gcStateMachine->state;
            if(observed!=QV4::GCState::Invalid)++pendingEngineMetaCallObservations;
            if(engineMetaCallObservations<=16) {
                const auto meta=QMetaEnum::fromType<QV4::GCStateMachine::GCState>();
                qInfo().noquote()<<"GC_YIELD_OBSERVATION"<<QJsonDocument(QJsonObject{
                    {"lastPendingReturnCollectionCall",pendingReturnCall},
                    {"pendingReturnAtUs",pendingReturnAtUs},
                    {"engineMetaCallEntryAtUs",runtime.nsecsElapsed()/1000},
                    {"returnedState",QString::fromLatin1(meta.valueToKey(pendingReturnState))},
                    {"engineEntryState",QString::fromLatin1(meta.valueToKey(observed))},
                    {"scope",QStringLiteral("After collect returned, current GC state at the engine's queued-event entry. This does not identify a particular GC continuation or prove the same GC cycle.")}
                }).toJson(QJsonDocument::Compact);
            }
        }
        return false;
    }
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle("Basic");
    QQmlApplicationEngine engine;
    GcProbe probe;
    probe.engine=&engine;
    probe.incremental=app.arguments().contains("--incremental");
    if(probe.incremental)engine.installEventFilter(&probe);
    // Zero runs every state through Invalid synchronously; it is not incremental.
    if(probe.incremental) engine.handle()->memoryManager->setGCTimeLimit(1);
    probe.runtime.start();
    qInfo()<<"FIXTURE_GC_MODE"<<"incremental"<<probe.incremental
           <<"actualTimeLimitUs"<<engine.handle()->memoryManager->gcStateMachine->timeLimit.count();
    int warnings=0;
    QObject::connect(&engine, &QQmlEngine::warnings, &app, [&](const QList<QQmlError> &errors) {
        warnings+=errors.size();
    });
    engine.rootContext()->setContextProperty("gcProbe", &probe);
    engine.load(QUrl::fromLocalFile(app.arguments().at(1)));
    if(engine.rootObjects().isEmpty()) return 3;
    QTimer timer;
    timer.setInterval(1);
    int frames=0;
    QObject::connect(&timer, &QTimer::timeout, &app, [&] {
        auto *controller=engine.incubationController();
        if(controller && controller->incubatingObjectCount()>0) {
            controller->incubateFor(1);
            probe.collect("between-incubation-slices");
        }
        if(++frames>3000) app.exit(4);
    });
    timer.start();
    const int result=app.exec();
    qInfo()<<"FIXTURE_RESULT"<<"exit"<<result<<"warnings"<<warnings<<"collections"<<probe.collections<<"completedHelpers"<<probe.completed;
    const bool observedYield=probe.pendingReturns>0&&probe.pendingEngineMetaCallObservations>0;
    qInfo()<<"FIXTURE_INCREMENTAL_COVERAGE"<<"requested"<<probe.incremental
           <<"pendingReturns"<<probe.pendingReturns<<"engineMetaCallObservations"<<probe.engineMetaCallObservations
           <<"pendingEngineMetaCallObservations"<<probe.pendingEngineMetaCallObservations
           <<"yieldObserved"<<observedYield
           <<"status"<<(probe.incremental?(observedYield?"observed":"inconclusive"):"not-requested");
    if(warnings)return 2;
    if(result)return result;
    return probe.incremental&&!observedYield?3:0;
}

#include "main.moc"

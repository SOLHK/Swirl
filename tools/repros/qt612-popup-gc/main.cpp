#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QTimer>
#include <QQuickStyle>
#include <QQmlIncubationController>
#include <QDebug>
#include <QtQml/private/qv4engine_p.h>
#include <QtQml/private/qv4mm_p.h>

class GcProbe final : public QObject {
    Q_OBJECT
public:
    QQmlEngine *engine = nullptr;
    int collections = 0;
    int completed = 0;
    bool incremental = false;
    Q_INVOKABLE bool collect(const QString &phase) {
        ++collections;
        if(incremental) engine->handle()->memoryManager->runGC();
        else engine->collectGarbage();
        if(collections<=8) qInfo() << "GC_PHASE" << phase;
        return true;
    }
    Q_INVOKABLE void complete() { ++completed; }
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle("Basic");
    QQmlApplicationEngine engine;
    GcProbe probe;
    probe.engine=&engine;
    probe.incremental=app.arguments().contains("--incremental");
    if(probe.incremental) engine.handle()->memoryManager->setGCTimeLimit(0);
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
    return warnings?2:result;
}

#include "main.moc"

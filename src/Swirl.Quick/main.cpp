#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QIcon>
#include <QTimer>
#include "demo/DemoDataProvider.h"
#include "app/WindowsBackdrop.h"

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Swirl"));
    app.setWindowIcon(QIcon(QStringLiteral(":/swirl/swirl-256.png")));
    DemoDataProvider demo;
    WindowsBackdrop backdrop;
    QQmlApplicationEngine engine;
    const bool smoke = app.arguments().contains("--smoke-test");
    bool qmlWarnings = false;
    QObject::connect(&engine, &QQmlEngine::warnings, &app,
                     [&qmlWarnings, smoke](const QList<QQmlError> &warnings) {
                         if (smoke && !warnings.isEmpty()) qmlWarnings = true;
                     });
    engine.rootContext()->setContextProperty("smokeTestMode", smoke);
    engine.rootContext()->setContextProperty("demoProvider", &demo);
    engine.rootContext()->setContextProperty("backdrop", &backdrop);
    engine.loadFromModule("SwirlQuick", "Main");
    if (engine.rootObjects().isEmpty())
        return 1;
    if (smoke)
        QTimer::singleShot(1900, &app, &QCoreApplication::quit);
    const int result = app.exec();
    return smoke && qmlWarnings ? 2 : result;
}

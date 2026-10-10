#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
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
    engine.rootContext()->setContextProperty("demoProvider", &demo);
    engine.rootContext()->setContextProperty("backdrop", &backdrop);
    engine.loadFromModule("SwirlQuick", "Main");
    if (engine.rootObjects().isEmpty())
        return 1;
    if (app.arguments().contains("--smoke-test"))
        QTimer::singleShot(1200, &app, &QCoreApplication::quit);
    return app.exec();
}

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QIcon>
#include <QTimer>
#include <QQuickWindow>
#include <QImage>
#include <QDebug>
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
    const QStringList arguments = app.arguments();
    const auto argumentValue = [&arguments](const QString &prefix) {
        for (const QString &argument : arguments)
            if (argument.startsWith(prefix))
                return argument.mid(prefix.size());
        return QString();
    };
    const QString previewPath = argumentValue(QStringLiteral("--capture-preview="));
    const QString previewPage = argumentValue(QStringLiteral("--preview-page="));
    const QString previewTheme = argumentValue(QStringLiteral("--preview-theme="));
    engine.rootContext()->setContextProperty("previewPage", previewPage);
    engine.rootContext()->setContextProperty("previewTheme", previewTheme);
    engine.rootContext()->setContextProperty("smokeTestMode", smoke);
    engine.rootContext()->setContextProperty("demoProvider", &demo);
    engine.rootContext()->setContextProperty("backdrop", &backdrop);
    engine.loadFromModule("SwirlQuick", "Main");
    if (engine.rootObjects().isEmpty())
        return 1;
    if (smoke)
        QTimer::singleShot(1900, &app, &QCoreApplication::quit);
    else if (!previewPath.isEmpty()) {
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
        if (window) {
            QTimer::singleShot(900, &app, [window, previewPath]() {
                const QImage screenshot = window->grabWindow();
                if (screenshot.isNull() || !screenshot.save(previewPath))
                    qWarning() << "Optional preview screenshot was unavailable:" << previewPath;
                else
                    qInfo() << "Saved synthetic UI preview:" << previewPath;
            });
            QTimer::singleShot(1450, &app, &QCoreApplication::quit);
        } else
            QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const int result = app.exec();
    return smoke && qmlWarnings ? 2 : result;
}

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QIcon>
#include <QTimer>
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QImage>
#include <QDebug>
#include <QFile>
#include <QTextStream>
#include <QCoreApplication>
#include "demo/DemoDataProvider.h"
#include "app/WindowsBackdrop.h"

// Collect Qt/QML diagnostics in a file because the Windows GUI subsystem
// does not attach stderr to GitHub Actions' PowerShell console.
static void recordQtDiagnostic(QtMsgType type, const QMessageLogContext &, const QString &message)
{
    QFile file(QCoreApplication::applicationDirPath() + QStringLiteral("/SwirlQuick-diagnostics.txt"));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        return;
    QTextStream out(&file);
    out << static_cast<int>(type) << ": " << message << '\n';
}

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
    if (smoke || !previewPath.isEmpty()) {
        QFile::remove(QCoreApplication::applicationDirPath() + QStringLiteral("/SwirlQuick-diagnostics.txt"));
        qInstallMessageHandler(recordQtDiagnostic);
    }
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
                if (!screenshot.isNull() && screenshot.save(previewPath)) {
                    qInfo() << "Saved synthetic UI preview:" << previewPath;
                    return;
                }

                // The offscreen QPA plugin may not support QQuickWindow::grabWindow().
                // Grab the rendered Quick item asynchronously as a software fallback.
                const auto fallback = window->contentItem()->grabToImage();
                if (!fallback) {
                    qWarning() << "Optional UI screenshot unavailable on this renderer:"
                               << previewPath;
                    return;
                }
                QObject::connect(fallback.data(), &QQuickItemGrabResult::ready, window,
                                 [fallback, previewPath]() {
                    if (!fallback->image().isNull() && fallback->image().save(previewPath))
                        qInfo() << "Saved Qt item snapshot:" << previewPath;
                    else
                        qWarning() << "Unable to save optional item preview:"
                                   << previewPath;
                });
            });
            QTimer::singleShot(2400, &app, &QCoreApplication::quit);
        } else
            QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const int result = app.exec();
    return smoke && qmlWarnings ? 2 : result;
}

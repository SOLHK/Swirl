#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QIcon>
#include <QTimer>
#include <QQuickWindow>
#include <QQuickStyle>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QImage>
#include <QDebug>
#include <QFile>
#include <QTextStream>
#include <QCoreApplication>
#include <QQmlExpression>
#include <QQmlIncubationController>
#include <QScreen>
#ifdef SWIRL_UI_TESTS
#include "tests/OverviewChecks.h"
#include "tests/CaptureChecks.h"
#endif
#include "demo/DemoDataProvider.h"
#include "app/WindowsBackdrop.h"
#include "network/CaptureService.h"

// Collect Qt/QML diagnostics in a file because the Windows GUI subsystem
// does not attach stderr to GitHub Actions' PowerShell console.
static void recordQtDiagnostic(QtMsgType type, const QMessageLogContext &, const QString &message)
{
    QFile file(QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-diagnostics.txt"));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        return;
    QTextStream out(&file);
    out << static_cast<int>(type) << ": " << message << '\n';
}

int main(int argc, char *argv[])
{
    QQuickWindow::setDefaultAlphaBuffer(true);
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Swirl"));
    app.setWindowIcon(QIcon(QStringLiteral(":/swirl/swirl-app.png")));
    // Native Windows Qt Quick Controls do not support custom backgrounds/content.
    // Swirl draws its own visual controls, so explicitly use the customizable style.
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    DemoDataProvider demo;
    WindowsBackdrop backdrop;
    CaptureService capture;
    QQmlApplicationEngine engine;
    const bool smoke = app.arguments().contains("--smoke-test");
    const bool interaction = app.arguments().contains("--interaction-test");
    const bool captureTest = app.arguments().contains("--capture-self-test");
    bool qmlWarnings = false;
    QObject::connect(&engine, &QQmlEngine::warnings, &app,
                     [&qmlWarnings, smoke, interaction, captureTest](const QList<QQmlError> &warnings) {
                         if ((smoke || interaction || captureTest) && !warnings.isEmpty()) qmlWarnings = true;
                     });
    const QStringList arguments = app.arguments();
    const auto argumentValue = [&arguments](const QString &prefix) {
        for (const QString &argument : arguments)
            if (argument.startsWith(prefix))
                return argument.mid(prefix.size());
        return QString();
    };
    const QString nativeFramePath = argumentValue(QStringLiteral("--capture-native-frame="));
    const QString previewPath = nativeFramePath.isEmpty()?argumentValue(QStringLiteral("--capture-preview=")):nativeFramePath;
    const QString previewPage = argumentValue(QStringLiteral("--preview-page="));
    const QString previewTheme = argumentValue(QStringLiteral("--preview-theme="));
    if (smoke || interaction || captureTest || !previewPath.isEmpty()) {
        QFile::remove(QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-diagnostics.txt"));
        qInstallMessageHandler(recordQtDiagnostic);
    }
    engine.rootContext()->setContextProperty("previewPage", previewPage);
    engine.rootContext()->setContextProperty("previewTheme", previewTheme);
    engine.rootContext()->setContextProperty("smokeTestMode", smoke);
    engine.rootContext()->setContextProperty("demoProvider", &demo);
    engine.rootContext()->setContextProperty("backdrop", &backdrop);
    engine.rootContext()->setContextProperty("captureProvider", &capture);
    engine.loadFromModule("SwirlQuick", "Main");
    if (engine.rootObjects().isEmpty())
        return 1;
    auto *rootWindow = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    const auto sizeParts = argumentValue(QStringLiteral("--preview-size=")).split('x');
    if (rootWindow && sizeParts.size() == 2 && sizeParts[0].toInt() >= 1000 && sizeParts[1].toInt() >= 650)
        rootWindow->resize(sizeParts[0].toInt(), sizeParts[1].toInt());
    if (app.arguments().contains("--preview-connected")) {
        QQmlExpression state(qmlContext(rootWindow), rootWindow,
                            QStringLiteral("AppState.setConnection(true); AppState.toast = ''"));
        state.evaluate();
    }
    if (interaction) {
#ifdef SWIRL_UI_TESTS
        QTimer::singleShot(400, &app, [&app, rootWindow]() {
            app.exit(runOverviewChecks(rootWindow));
        });
#else
        qWarning() << "Rebuild with -DSWIRL_BUILD_UI_TESTS=ON to run input checks.";
        return 4;
#endif
    }
    if(captureTest) {
#ifdef SWIRL_UI_TESTS
        QTimer::singleShot(400,&app,[&app,&capture]{app.exit(runCaptureChecks(&capture));});
#else
        return 4;
#endif
    }
    if (app.arguments().contains("--preview-scroll-bottom"))
        QTimer::singleShot(400, rootWindow, [rootWindow]() { QMetaObject::invokeMethod(rootWindow,"previewScrollBottom"); });
    if (!interaction && !captureTest && smoke)
        QTimer::singleShot(15000, &app, [&app]() {
            qCritical() << "Navigation smoke test timed out before completing all pages.";
            app.exit(3);
        });
    else if (!interaction && !captureTest && !previewPath.isEmpty()) {
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
        if (window) {
            QTimer::singleShot(900, &app, [window, previewPath, nativeFramePath]() {
                const QImage screenshot = nativeFramePath.isEmpty()?window->grabWindow():window->screen()->grabWindow(0,window->x()-8,window->y()-8,window->width()+16,window->height()+16).toImage();
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
    // Drain any lazy Qt Controls creation before the engine is destroyed.
    // This also keeps scripted page-navigation shutdown free of incubation warnings.
    if (auto *controller = engine.incubationController())
        controller->incubateFor(100);
    return (smoke || interaction || captureTest) && qmlWarnings ? 2 : result;
}

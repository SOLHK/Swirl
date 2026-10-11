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
#include <QSvgRenderer>
#include <QPainter>
#include <QDir>
#include <QStandardPaths>
#include "app/ModuleDraftStore.h"
#ifdef SWIRL_UI_TESTS
#include "tests/OverviewChecks.h"
#include "tests/CaptureChecks.h"
#include "tests/WindowChecks.h"
#endif
#include "demo/DemoDataProvider.h"
#include "app/WindowsBackdrop.h"
#include "app/SvgIconProvider.h"
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
    app.setApplicationVersion(QStringLiteral("1.0.0-preview"));
    app.setWindowIcon(QIcon(QStringLiteral(":/swirl/icons/swirl_wave_mark.svg")));
    // Native Windows Qt Quick Controls do not support custom backgrounds/content.
    // Swirl draws its own visual controls, so explicitly use the customizable style.
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    if(app.arguments().contains("--interaction-test")||app.arguments().contains("--capture-self-test")||app.arguments().contains("--smoke-test")||app.arguments().contains("--window-test"))
        QStandardPaths::setTestModeEnabled(true);
    DemoDataProvider demo;
    WindowsBackdrop backdrop;
    CaptureService capture;
    ModuleDraftStore drafts;
    QQmlApplicationEngine engine;
    engine.addImageProvider(QStringLiteral("swirl"),new SvgIconProvider);
    const bool smoke = app.arguments().contains("--smoke-test");
    const bool interaction = app.arguments().contains("--interaction-test");
    const bool captureTest = app.arguments().contains("--capture-self-test");
    const bool windowTest = app.arguments().contains("--window-test");
    bool qmlWarnings = false;
    bool previewCaptured = false;
    QObject::connect(&engine, &QQmlEngine::warnings, &app,
                     [&qmlWarnings, smoke, interaction, captureTest, windowTest](const QList<QQmlError> &warnings) {
                         if (!warnings.isEmpty()) qmlWarnings = true;
                     });
    const QStringList arguments = app.arguments();
    const auto argumentValue = [&arguments](const QString &prefix) {
        for (const QString &argument : arguments)
            if (argument.startsWith(prefix))
                return argument.mid(prefix.size());
        return QString();
    };
    const QString brandOutput=argumentValue(QStringLiteral("--render-brand-assets="));
    if(!brandOutput.isEmpty()) {
        QDir().mkpath(brandOutput);
        for(const auto &name:{QStringLiteral("swirl-app"),QStringLiteral("swirl-mark")}) {
            QImage image(1024,1024,QImage::Format_ARGB32_Premultiplied);image.fill(Qt::transparent);
            QPainter painter(&image);QSvgRenderer svg(name==QStringLiteral("swirl-app") ? QStringLiteral(":/swirl/icons/swirl_wave_light.svg") : QStringLiteral(":/swirl/icons/swirl_wave_mark.svg"));svg.render(&painter);painter.end();
            if(!image.save(brandOutput+QStringLiteral("/")+name+QStringLiteral(".png")))return 5;
        }
        return 0;
    }
    const QString nativeFramePath = argumentValue(QStringLiteral("--capture-native-frame="));
    const QString previewPath = nativeFramePath.isEmpty()?argumentValue(QStringLiteral("--capture-preview=")):nativeFramePath;
    const QString previewPage = argumentValue(QStringLiteral("--preview-page="));
    const QString previewTheme = argumentValue(QStringLiteral("--preview-theme="));
    if (smoke || interaction || captureTest || windowTest || !previewPath.isEmpty()) {
        QFile::remove(QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-diagnostics.txt"));
        qInstallMessageHandler(recordQtDiagnostic);
    }
    engine.rootContext()->setContextProperty("previewPage", previewPage);
    engine.rootContext()->setContextProperty("gpuEffectsSupported", QQuickWindow::graphicsApi()!=QSGRendererInterface::Software && qEnvironmentVariable("QT_QUICK_BACKEND")!=QStringLiteral("software"));
    engine.rootContext()->setContextProperty("previewTheme", previewTheme);
    engine.rootContext()->setContextProperty("smokeTestMode", smoke);
    engine.rootContext()->setContextProperty("demoProvider", &demo);
    engine.rootContext()->setContextProperty("backdrop", &backdrop);
    engine.rootContext()->setContextProperty("captureProvider", &capture);
    engine.rootContext()->setContextProperty("moduleDrafts", &drafts);
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
    if (windowTest) {
#ifdef SWIRL_UI_TESTS
        const auto output=argumentValue(QStringLiteral("--window-test-output="));
        QTimer::singleShot(400,&app,[&app,rootWindow,&backdrop,output]{app.exit(runWindowChecks(rootWindow,&backdrop,output));});
#else
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
        QTimer::singleShot(60000, &app, [&app]() {
            qCritical() << "Navigation smoke test timed out before completing all pages.";
            app.exit(3);
        });
    else if (!interaction && !captureTest && !previewPath.isEmpty()) {
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
        if (window) {
            if(!nativeFramePath.isEmpty())QTimer::singleShot(400,&app,[&app,&backdrop]{if(!backdrop.prepareNativeCapture()){qCritical()<<"Native capture blocked: cannot activate target window";app.exit(3);}});
            QTimer::singleShot(900, &app, [window, previewPath, nativeFramePath, &backdrop, &app, &previewCaptured]() {
                if(!nativeFramePath.isEmpty()&&!backdrop.isCaptureForeground()){qCritical()<<"Native capture blocked: target window lost foreground";backdrop.finishNativeCapture();app.exit(3);return;}
                const QImage screenshot = nativeFramePath.isEmpty()?window->grabWindow():window->screen()->grabWindow(0,window->x(),window->y(),window->width(),window->height()).toImage();
                if (!screenshot.isNull() && screenshot.save(previewPath)) {
                    previewCaptured=true;
                    qInfo() << (nativeFramePath.isEmpty()?"Saved Qt UI render:":"Saved Windows compositor screenshot:") << previewPath;
                    qInfo()<<"Capture geometry"<<window->geometry()<<"DPR"<<window->devicePixelRatio()<<backdrop.status();
                    if(!nativeFramePath.isEmpty())backdrop.finishNativeCapture();
                    return;
                }
                if(!nativeFramePath.isEmpty()){backdrop.finishNativeCapture();qCritical()<<"Native capture failed; no synthetic fallback used";app.exit(3);return;}

                // The offscreen QPA plugin may not support QQuickWindow::grabWindow().
                // Grab the rendered Quick item asynchronously as a software fallback.
                const auto fallback = window->contentItem()->grabToImage();
                if (!fallback) {
                    qWarning() << "Optional UI screenshot unavailable on this renderer:"
                               << previewPath;
                    return;
                }
                QObject::connect(fallback.data(), &QQuickItemGrabResult::ready, window,
                                 [fallback, previewPath, &previewCaptured]() {
                    if (!fallback->image().isNull() && fallback->image().save(previewPath)) {
                        previewCaptured=true;
                        qInfo() << "Saved Qt item snapshot:" << previewPath;
                    } else
                        qWarning() << "Unable to save optional item preview:"
                                   << previewPath;
                });
            });
            QTimer::singleShot(2400, &app, [&app,&previewCaptured]{app.exit(previewCaptured?0:3);});
        } else
            QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const int result = app.exec();
    // Drain any lazy Qt Controls creation before the engine is destroyed.
    // This also keeps scripted page-navigation shutdown free of incubation warnings.
    if (auto *controller = engine.incubationController())
        controller->incubateFor(100);
    return (smoke || interaction || captureTest || windowTest || !previewPath.isEmpty()) && qmlWarnings ? 2 : result;
}

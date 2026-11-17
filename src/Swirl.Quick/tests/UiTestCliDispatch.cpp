#include "UiTestCliDispatch.h"

#include "ActivityLayoutChecks.h"
#include "AppearanceChecks.h"
#include "CaptureChecks.h"
#include "EngineUiChecks.h"
#include "FontAcceptanceChecks.h"
#include "FontDpiWatch.h"
#include "FontFrameChecks.h"
#include "FontUiChecks.h"
#include "GatewayChecks.h"
#include "HdrChecks.h"
#include "HeroChecks.h"
#include "MaterialChecks.h"
#include "MotionChecks.h"
#include "NavigationChecks.h"
#include "NodeUiChecks.h"
#include "OverviewChecks.h"
#include "PolicySystemProxyBackend.h"
#include "PolicyUiChecks.h"
#include "UiQualityChecks.h"
#include "WindowChecks.h"
#include "WindowRadiusChecks.h"
#include "app/QmlDiagnosticCapture.h"
#include "app/WindowsBackdrop.h"
#include "engine/EngineController.h"
#include "network/CaptureService.h"

#include <QCoreApplication>
#include <QFile>
#include <QHostAddress>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPixmap>
#include <QQmlContext>
#include <QQmlDebuggingEnabler>
#include <QQmlExpression>
#include <QQuickWindow>
#include <QScreen>
#include <QSslSocket>
#include <QTcpServer>
#include <QTimer>
#include <cstdio>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include "NativeTunBrokerChecks.h"
#include "SystemProxyExitFixture.h"
#include "third_party/renderdoc_app.h"
#endif

namespace {

QString argumentValue(const QStringList &arguments, const QString &prefix)
{
    for (const QString &argument : arguments)
        if (argument.startsWith(prefix))
            return argument.mid(prefix.size());
    return QString();
}

} // namespace

bool parseControlledSessionRoot(int argc, char *argv[], bool privateUiQuotaRequested, QString *rootOut)
{
    for (int i = 1; i < argc; ++i) {
        const QByteArray argument(argv[i]);
        if (argument == "--controlled-node-session" || argument.startsWith("--controlled-node-session=")) {
            constexpr auto prefix = "--controlled-node-session=";
            if ((argc != 2 && !(privateUiQuotaRequested && argc == 3))
                || !argument.startsWith(prefix)
                || argument.size() == int(sizeof("--controlled-node-session=") - 1)) {
                return false;
            }
            *rootOut = QString::fromLocal8Bit(argument.mid(sizeof("--controlled-node-session=") - 1));
        }
    }
    return true;
}

bool tryRunEarlyUiSelfTest(int &argc, char *argv[], int *exitCode)
{
    for (int i = 1; i < argc; ++i) {
        if (QByteArray(argv[i]) == "--native-tun-broker-self-test") {
#ifdef Q_OS_WIN
            QCoreApplication selfTest(argc, argv);
            *exitCode = (i + 1 >= argc) ? 64 : runNativeTunBrokerChecks(QString::fromLocal8Bit(argv[i + 1]));
#else
            *exitCode = 64;
#endif
            return true;
        }
    }
    return false;
}

bool initializeIsolatedRegistryForTests(int argc, char *argv[], bool controlledNodeSession, IsolatedUserRegistry &registry)
{
    bool registryFixture = false;
    bool interactiveProfile = controlledNodeSession;
    for (int i = 1; i < argc; ++i) {
        const QByteArray argument(argv[i]);
        registryFixture = registryFixture || argument == "--policy-self-test" || argument == "--motion-test"
            || argument == "--window-test" || argument == "--node-self-test" || argument == "--engine-self-test"
            || argument == "--navigation-test" || argument == "--activity-layout-test";
        interactiveProfile = interactiveProfile || argument == "--ui-preview" || argument == "--lifecycle-test";
    }
    if (registryFixture && (interactiveProfile || !registry.initialize()))
        return false;
    return true;
}

bool validateUiLifecycleEnvironment(const QStringList &arguments)
{
#ifdef Q_OS_WIN
    const bool lifecycleTest = arguments.contains(QStringLiteral("--lifecycle-test"));
    const bool lifecycleSystemProxyTest = qEnvironmentVariable("SWIRL_LIFECYCLE_SYSTEM_PROXY") == QStringLiteral("1");
    if (lifecycleSystemProxyTest && (!lifecycleTest || !SwirlSystemProxyExit::environmentIsValid()))
        return false;
#else
    Q_UNUSED(arguments);
#endif
    return true;
}

bool tryRunPostAppUiCommand(QApplication &app, int *exitCode)
{
    const QStringList arguments = app.arguments();
    if (arguments.contains(QStringLiteral("--capture-self-test"))) {
        const auto backend = qEnvironmentVariable("SWIRL_CAPTURE_TEST_TLS_BACKEND");
        if (!backend.isEmpty() && !QSslSocket::setActiveBackend(backend)) {
            std::fprintf(stderr, "The requested capture-test TLS backend is unavailable.\n");
            *exitCode = 2;
            return true;
        }
    }
#ifdef Q_OS_WIN
    for (const auto &argument : arguments) {
        if (argument.startsWith(QStringLiteral("--capture-taskbar="))) {
            const auto taskbar = FindWindowW(L"Shell_TrayWnd", nullptr);
            if (!taskbar || !app.primaryScreen()) { *exitCode = 3; return true; }
            RECT area{};
            if (!GetWindowRect(taskbar, &area)) { *exitCode = 3; return true; }
            const auto desktop = app.primaryScreen()->grabWindow(0);
            const auto origin = app.primaryScreen()->geometry().topLeft() * app.primaryScreen()->devicePixelRatio();
            const auto shot = desktop.copy(area.left - origin.x(), area.top - origin.y(),
                                           area.right - area.left, area.bottom - area.top);
            *exitCode = (!shot.isNull() && shot.save(argument.mid(QStringLiteral("--capture-taskbar=").size()))) ? 0 : 4;
            return true;
        }
    }
#endif
    if (arguments.contains(QStringLiteral("--motion-test")) && qEnvironmentVariableIsSet("SWIRL_QML_PROFILE")) {
        QQmlDebuggingEnabler::setServices(QQmlDebuggingEnabler::profilerServices());
        QQmlDebuggingEnabler::enableDebugging(false);
    }
    return false;
}

void recordFontUiMemoryProperty(QApplication &app, bool enabled, const char *propertyName)
{
    if (enabled)
        app.setProperty(propertyName, fontUiPrivateBytes());
}

std::unique_ptr<SystemProxySession::Backend> createUiTestProxyBackend(const QStringList &arguments, bool controlledNodeSession)
{
    if (arguments.contains(QStringLiteral("--policy-self-test"))
        || arguments.contains(QStringLiteral("--node-self-test"))
        || controlledNodeSession) {
        return std::make_unique<PolicySystemProxyBackend>();
    }
    return nullptr;
}

bool tryRunHdrSelfTest(const QStringList &arguments, int *exitCode)
{
    if (arguments.contains(QStringLiteral("--hdr-self-test"))) {
        *exitCode = runHdrChecks();
        return true;
    }
    return false;
}

int attachAndScheduleUiTests(QApplication &app,
                             QQuickWindow *rootWindow,
                             EngineController &engineController,
                             FontManager &fontManager,
                             WindowsBackdrop &backdrop,
                             CaptureService &capture,
                             QmlVmeWarningCapture &qmlVmeWarnings,
                             bool controlledNodeSession,
                             const ControlledNodeSession &controlledSession)
{
    const QStringList arguments = app.arguments();
    const bool activityLayoutTest = arguments.contains(QStringLiteral("--activity-layout-test"));
    const bool lifecycleTest = arguments.contains(QStringLiteral("--lifecycle-test"));
    const bool nodeTest = arguments.contains(QStringLiteral("--node-self-test"));
    const bool policyTest = arguments.contains(QStringLiteral("--policy-self-test"));
    const bool navigationTest = arguments.contains(QStringLiteral("--navigation-test"));
    const bool appearanceTest = arguments.contains(QStringLiteral("--appearance-test"))
        || arguments.contains(QStringLiteral("--appearance-restore-test"));
    const bool heroTest = arguments.contains(QStringLiteral("--hero-test"));
    const bool motionTest = arguments.contains(QStringLiteral("--motion-test"));
    const bool engineTest = arguments.contains(QStringLiteral("--engine-self-test"));
    const bool interaction = arguments.contains(QStringLiteral("--interaction-test"));
    const bool fontDpiWatch = arguments.contains(QStringLiteral("--font-dpi-watch"));
    const bool fontAcceptanceTest = arguments.contains(QStringLiteral("--font-acceptance-test"));
    const bool fontFrameTest = arguments.contains(QStringLiteral("--font-frame-test"));
    const bool fontReview = arguments.contains(QStringLiteral("--font-review"));
    const bool fontUiTest = arguments.contains(QStringLiteral("--font-ui-test"));
    const bool uiQualityTest = arguments.contains(QStringLiteral("--ui-quality-test"));
    const bool windowTest = arguments.contains(QStringLiteral("--window-test"));
    const bool radiusTest = arguments.contains(QStringLiteral("--window-radius-test"));
    const bool gatewayTest = arguments.contains(QStringLiteral("--gateway-self-test"));
    const bool captureTest = arguments.contains(QStringLiteral("--capture-self-test"));

    if (rootWindow && lifecycleTest) {
#ifdef Q_OS_WIN
        if (qEnvironmentVariable("SWIRL_LIFECYCLE_SYSTEM_PROXY") == QStringLiteral("1")) {
            if (!SwirlSystemProxyExit::start(rootWindow, &engineController))
                return 64;
        } else
#endif
        {
            const auto fixture = qEnvironmentVariable("SWIRL_LIFECYCLE_ENGINE");
            if (!fixture.isEmpty()) {
                QTcpServer reserve;
                reserve.listen(QHostAddress::LocalHost);
                const auto port = reserve.serverPort();
                reserve.close();
                if (fixture != QStringLiteral("rust")) return 64;
                engineController.setProxyPort(port);
                engineController.setRoutingMode(QStringLiteral("direct"));
                QObject::connect(&engineController, &EngineController::statusChanged, &app, [&app, &engineController] {
                    if (engineController.processAlive())
                        app.setProperty("lifecycleEnginePid", engineController.processId());
                });
                engineController.connectNode(QString());
            }
            QObject::connect(&app, &QCoreApplication::aboutToQuit, &app, [&app] {
                const auto path = qEnvironmentVariable("SWIRL_LIFECYCLE_REPORT");
                if (!path.isEmpty()) {
                    QFile file(path);
                    if (file.open(QIODevice::WriteOnly)) {
                        file.write(QJsonDocument(QJsonObject{
                            {"pid", double(QCoreApplication::applicationPid())},
                            {"enginePid", app.property("lifecycleEnginePid").toString()},
                            {"shutdownMs", double(app.property("shutdownDurationMs").toLongLong())},
                            {"executable", QCoreApplication::applicationFilePath()}}).toJson());
                    }
                }
            });
            QTimer::singleShot(250, rootWindow, [rootWindow] { QMetaObject::invokeMethod(rootWindow, "openDashboard"); });
            const auto delay = qEnvironmentVariableIntValue("SWIRL_LIFECYCLE_EXIT_MS");
            QTimer::singleShot(delay > 0 ? delay : 2500, rootWindow, [rootWindow] { rootWindow->close(); });
        }
    }

    if (controlledNodeSession && rootWindow)
        startControlledNodeSession(rootWindow, &engineController, controlledSession);

    if (activityLayoutTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--activity-layout-output="));
        QTimer::singleShot(450, &app, [&app, rootWindow, output] { app.exit(runActivityLayoutChecks(rootWindow, output)); });
    }

#ifdef Q_OS_WIN
    const auto renderdocOutput = argumentValue(arguments, QStringLiteral("--renderdoc-output="));
    if (!renderdocOutput.isEmpty()) {
        const auto library = GetModuleHandleW(L"renderdoc.dll");
        auto getApi = library ? reinterpret_cast<pRENDERDOC_GetAPI>(GetProcAddress(library, "RENDERDOC_GetAPI")) : nullptr;
        RENDERDOC_API_1_6_0 *api = nullptr;
        if (!getApi || !getApi(eRENDERDOC_API_Version_1_6_0, reinterpret_cast<void **>(&api)))
            return 5;
        api->SetCaptureFilePathTemplate(renderdocOutput.toUtf8().constData());
        api->MaskOverlayBits(0, 0);
        QTimer::singleShot(650, rootWindow, [api, rootWindow] { api->TriggerCapture(); rootWindow->update(); });
        QTimer::singleShot(1100, rootWindow, [api, rootWindow] {
            QQmlExpression expression(qmlContext(rootWindow), rootWindow, QStringLiteral("Theme.glassBlurStrength+=0.25"));
            expression.evaluate();
            api->TriggerMultiFrameCapture(3);
            rootWindow->update();
        });
    }
#endif

    if (nodeTest) {
        QTimer::singleShot(400, &app, [&app, rootWindow, &engineController, &qmlVmeWarnings] {
            qmlVmeWarnings.phase = "node-self-test";
            const int result = runNodeUiChecks(rootWindow, &engineController);
            qmlVmeWarnings.phase = "after-node-self-test";
            app.exit(result);
        });
    }
    if (policyTest) {
        const auto directory = argumentValue(arguments, QStringLiteral("--policy-output="));
        QTimer::singleShot(400, &app, [&app, rootWindow, &engineController, directory] {
            app.exit(runPolicyUiChecks(rootWindow, &engineController, directory));
        });
    }

    const auto viewportDirectory = argumentValue(arguments, QStringLiteral("--viewport-test-output="));
    const auto materialDirectory = argumentValue(arguments, QStringLiteral("--material-test-output="));
    const auto demoDirectory = argumentValue(arguments, QStringLiteral("--motion-demo-output="));
    const auto visualDirectory = argumentValue(arguments, QStringLiteral("--motion-visual-dir="));
    if (navigationTest) {
        const auto directory = argumentValue(arguments, QStringLiteral("--navigation-output="));
        QTimer::singleShot(450, &app, [&app, rootWindow, &engineController, directory] {
            app.exit(runNavigationChecks(rootWindow, &engineController, directory));
        });
    } else if (appearanceTest) {
        const bool restore = arguments.contains(QStringLiteral("--appearance-restore-test"));
        QTimer::singleShot(450, &app, [&app, rootWindow, restore] {
            app.exit(runAppearanceChecks(rootWindow, restore));
        });
    } else if (heroTest) {
        const auto directory = argumentValue(arguments, QStringLiteral("--hero-output="));
        const auto armFile = argumentValue(arguments, QStringLiteral("--hero-arm-file="));
        if (armFile.isEmpty()) {
            QTimer::singleShot(450, &app, [&app, rootWindow, &engineController, directory] {
                app.exit(runHeroChecks(rootWindow, &engineController, directory));
            });
        } else {
            auto *armTimer = new QTimer(&app);
            armTimer->setInterval(100);
            QObject::connect(armTimer, &QTimer::timeout, &app,
                             [&app, rootWindow, &engineController, directory, armFile, armTimer] {
                                 if (!QFile::exists(armFile)) return;
                                 armTimer->stop();
                                 armTimer->deleteLater();
                                 QFile::remove(armFile);
                                 app.exit(runHeroChecks(rootWindow, &engineController, directory));
                             });
            armTimer->start();
        }
    } else if (!materialDirectory.isEmpty()) {
        QTimer::singleShot(450, &app, [&app, rootWindow, materialDirectory] {
            app.exit(runMaterialChecks(rootWindow, materialDirectory));
        });
    } else if (!viewportDirectory.isEmpty()) {
        QTimer::singleShot(450, &app, [&app, rootWindow, viewportDirectory] {
            app.exit(runViewportChecks(rootWindow, viewportDirectory));
        });
    } else if (!demoDirectory.isEmpty()) {
        QTimer::singleShot(450, &app, [&app, rootWindow, demoDirectory] {
            app.exit(runMotionDemo(rootWindow, demoDirectory));
        });
    } else if (!visualDirectory.isEmpty()) {
        QTimer::singleShot(450, &app, [&app, rootWindow, visualDirectory] {
            app.exit(runMotionVisualChecks(rootWindow, visualDirectory));
        });
    } else if (motionTest) {
        const auto report = argumentValue(arguments, QStringLiteral("--motion-output="));
        QTimer::singleShot(450, &app, [&app, rootWindow, report] {
            app.exit(runMotionChecks(rootWindow, report));
        });
    }

    if (engineTest) {
        QTimer::singleShot(400, &app, [&app, rootWindow, &engineController, &capture] {
            app.exit(runEngineUiChecks(rootWindow, &engineController, &capture));
        });
    }
    if (interaction) {
        QTimer::singleShot(400, &app, [&app, rootWindow] { app.exit(runOverviewChecks(rootWindow)); });
    }
    if (fontDpiWatch) {
        startFontDpiWatch(rootWindow, &fontManager,
                          argumentValue(arguments, QStringLiteral("--font-source-file=")),
                          argumentValue(arguments, QStringLiteral("--font-dpi-output=")));
    }
    if (fontAcceptanceTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--font-acceptance-output="));
        const auto source = argumentValue(arguments, QStringLiteral("--font-source-file="));
        const bool currentPageOnly = arguments.contains(QStringLiteral("--font-acceptance-current-page"));
        QTimer::singleShot(700, &app, [&app, rootWindow, &fontManager, output, source, currentPageOnly] {
            app.exit(runFontAcceptanceChecks(rootWindow, &fontManager, source, output, currentPageOnly));
        });
    }
    if (fontFrameTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--font-frame-output="));
        QTimer::singleShot(700, &app, [&app, rootWindow, &fontManager, output] {
            app.exit(runFontFrameChecks(rootWindow, &fontManager, output));
        });
    }
    if (fontReview && rootWindow) {
        const double points = argumentValue(arguments, QStringLiteral("--font-reading-points=")).toDouble();
        const auto label = argumentValue(arguments, QStringLiteral("--font-reading-label="));
        const auto readingOutput = argumentValue(arguments, QStringLiteral("--font-reading-output="));
        if (points >= 9 && points <= 16) {
            QTimer::singleShot(700, rootWindow, [rootWindow, points, label, readingOutput] {
                applyFontReadingReview(rootWindow, points, label, readingOutput);
            });
        }
    }
    if (fontUiTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--font-ui-output="));
        QTimer::singleShot(500, &app, [&app, rootWindow, &fontManager, output] {
            app.exit(runFontUiChecks(rootWindow, &fontManager, output));
        });
    }
    if (uiQualityTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--ui-quality-output="));
        const bool baseline = arguments.contains(QStringLiteral("--ui-quality-baseline"));
        QTimer::singleShot(500, &app, [&app, rootWindow, &backdrop, output, baseline] {
            app.exit(runUiQualityChecks(rootWindow, &backdrop, output, baseline));
        });
    }
    if (windowTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--window-test-output="));
        QTimer::singleShot(400, &app, [&app, rootWindow, &backdrop, output] {
            app.exit(runWindowChecks(rootWindow, &backdrop, output));
        });
    }
    if (radiusTest) {
        const auto output = argumentValue(arguments, QStringLiteral("--window-radius-output="));
        QTimer::singleShot(400, &app, [&app, rootWindow, &backdrop, output] {
            app.exit(runWindowRadiusChecks(rootWindow, &backdrop, output));
        });
    }
    if (gatewayTest) {
        QTimer::singleShot(400, &app, [&app] { app.exit(runGatewayChecks()); });
    }
    if (captureTest) {
        QTimer::singleShot(400, &app, [&app, &capture] { app.exit(runCaptureChecks(&capture)); });
    }
    return 0;
}

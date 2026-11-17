#ifdef _WIN32
#if !defined(_WIN32_WINNT) || _WIN32_WINNT < 0x0A00
#undef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#if !defined(NTDDI_VERSION) || NTDDI_VERSION < 0x0A000000
#undef NTDDI_VERSION
#define NTDDI_VERSION 0x0A000000
#endif
#endif

#include <QApplication>
#include <QCoreApplication>
#include <QDebug>
#include <QFile>
#include <QIcon>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMessageBox>
#include <QMouseEvent>
#include <QPainter>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QQmlExpression>
#include <QQmlIncubationController>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QScreen>
#include <QSettings>
#include <QStandardPaths>
#include <QSvgRenderer>
#include <QTemporaryDir>
#include <QTimer>
#include <cstdio>
#include <memory>

#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <shobjidl.h>
#include <propkey.h>
#include <propvarutil.h>
#include <QDir>
#endif

#include "SwirlBuildIdentity.h"
#include "app/BrandRaster.h"
#include "app/DiagnosticService.h"
#include "app/DismissalController.h"
#include "app/ExtensionService.h"
#include "app/FontManager.h"
#include "app/FontRendering.h"
#include "app/HdrOutput.h"
#include "app/ModuleDraftStore.h"
#include "app/MotionPolicy.h"
#include "app/NativeTunRecovery.h"
#include "app/QmlDiagnosticCapture.h"
#include "app/ShutdownCoordinator.h"
#include "app/SingleInstance.h"
#include "app/StoragePaths.h"
#include "app/SvgIconProvider.h"
#include "app/SystemDataProvider.h"
#include "app/TrayController.h"
#include "app/WindowsBackdrop.h"
#include "engine/EngineController.h"
#include "engine/RustCoreSelfTest.h"
#include "engine/ThreadedEngine.h"
#include "network/CaptureService.h"
#include "network/GatewayService.h"
#include "network/TlsRuntimeSelfTest.h"

#ifdef SWIRL_XRAY_UI_TESTS
#include "tests/XrayUiChecks.h"
#endif
#ifdef SWIRL_UI_TESTS
#include "tests/UiTestCliDispatch.h"
#endif
#ifdef SWIRL_PRIVATE_UI_QUOTA
#include "tests/PrivateUiQuotaSession.h"
#endif

#ifdef Q_OS_WIN
static void configureTaskbarIdentity(QQuickWindow *window)
{
    if (QGuiApplication::platformName() != QStringLiteral("windows")) return;
    IPropertyStore *store = nullptr;
    HRESULT result = SHGetPropertyStoreForWindow(reinterpret_cast<HWND>(window->winId()), IID_PPV_ARGS(&store));
    if (FAILED(result)) { qWarning() << "Taskbar property store unavailable" << quint32(result); return; }
    const auto setString = [&](const PROPERTYKEY &key, const QString &text) {
        PROPVARIANT value{};
        HRESULT status = InitPropVariantFromString(reinterpret_cast<LPCWSTR>(text.utf16()), &value);
        if (SUCCEEDED(status)) status = store->SetValue(key, value);
        PropVariantClear(&value);
        return status;
    };
    const auto exe = QDir::toNativeSeparators(QCoreApplication::applicationFilePath());
    // A process AppID alone lets Explorer reuse an older registered shortcut's
    // group icon. Publish this window's own resources before its explicit ID.
    const auto iconPath = QDir::toNativeSeparators(
        QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-brand-0217-optical.ico"));
    result = setString(PKEY_AppUserModel_RelaunchIconResource, iconPath + QStringLiteral(",0"));
    if (SUCCEEDED(result)) result = setString(PKEY_AppUserModel_RelaunchCommand, QStringLiteral("\"%1\"").arg(exe));
    if (SUCCEEDED(result)) result = setString(PKEY_AppUserModel_RelaunchDisplayNameResource, QStringLiteral("@%1,-100").arg(exe));
    if (SUCCEEDED(result)) result = setString(PKEY_AppUserModel_ID, QStringLiteral("SOLHK.Swirl.Desktop"));
    store->Release();
    if (FAILED(result)) qWarning() << "Taskbar identity publication failed" << quint32(result);
}
#endif

int main(int argc, char *argv[])
{
    QString controlledSessionRoot;
    bool privateUiQuotaRequested = false, privateUiQuotaIdentity = false;
    for (int i = 1; i < argc; ++i) {
        const QByteArray argument(argv[i]);
        if (argument == "--private-ui-quota") privateUiQuotaRequested = true;
        else if (argument == "--private-ui-quota-build-info") privateUiQuotaIdentity = true;
        else if (argument.startsWith("--private-ui-quota")) return 64;
    }
#ifndef SWIRL_PRIVATE_UI_QUOTA
    if (privateUiQuotaRequested || privateUiQuotaIdentity) return 64;
#endif
#ifdef SWIRL_UI_TESTS
    if (!parseControlledSessionRoot(argc, argv, privateUiQuotaRequested, &controlledSessionRoot))
        return 64;
#else
    for (int i = 1; i < argc; ++i) {
        const QByteArray argument(argv[i]);
        if (argument == "--controlled-node-session" || argument.startsWith("--controlled-node-session="))
            return 64;
    }
#endif
    // The legacy real-node QA harness has no authenticated billing/ledger or
    // complete wire guard. Reject even partial/empty options in BOTH builds,
    // before maintenance dispatch, Qt startup, private stores or networking.
    // Never echo an argument: its value may contain a private path or token.
    for (int i = 1; i < argc; ++i) {
        const QByteArray argument(argv[i]);
        for (const auto option : {"--runtime-store", "--runtime-commands", "--runtime-state"}) {
            if (argument == option || argument.startsWith(QByteArray(option) + '=')) {
                std::fputs("{\"errorCode\":\"AuthenticatedBillingAndWireGuardRequired\",\"networkStarted\":false}\n", stderr);
                return 64;
            }
        }
    }
#ifdef SWIRL_PRIVATE_UI_QUOTA
    if (privateUiQuotaIdentity) {
        if (argc != 2 || privateUiQuotaRequested || !controlledSessionRoot.isEmpty()) return 64;
        QCoreApplication identityApplication(argc, argv);
        return PrivateUiQuotaSession::writeBuildIdentity();
    }
    if (!privateUiQuotaRequested || controlledSessionRoot.isEmpty() || argc != 3) return 64;
#endif
#ifdef SWIRL_UI_TESTS
    auto controlledWatchdog = startControlledNodeWatchdog(!controlledSessionRoot.isEmpty());
    int earlyUiExitCode = 0;
    if (tryRunEarlyUiSelfTest(argc, argv, &earlyUiExitCode))
        return earlyUiExitCode;
#endif
    // Package verification runs the real EXE/DLL, before any UI, NodeStore,
    // system-proxy ownership, or persisted settings are opened.
    for (int i = 1; i < argc; ++i) {
        const QByteArray arg(argv[i]);
        if (arg == "--recover-tun") {
            if (argc != 2) return 64;
            QCoreApplication maintenance(argc, argv);
            return recoverNativeTunForMaintenance();
        }
        if (arg == "--native-tun-broker-self-test") return 64;
        if (arg == "--tls-runtime-self-test") {
            QCoreApplication selfTest(argc, argv);
            if (i + 1 >= argc) return 64;
            return runTlsRuntimeSelfTest(QString::fromLocal8Bit(argv[i + 1]));
        }
        if (arg == "--rust-core-self-test") {
            QCoreApplication selfTest(argc, argv);
            if (i + 1 >= argc) return 64;
            return runRustCoreSelfTest(QString::fromLocal8Bit(argv[i + 1]));
        }
    }
#ifdef Q_OS_WIN
    SetCurrentProcessExplicitAppUserModelID(L"SOLHK.Swirl.Desktop");
    if (!qEnvironmentVariableIsSet("QT_D3D_MAX_FRAME_LATENCY"))
        qputenv("QT_D3D_MAX_FRAME_LATENCY", "1");
#endif
#ifdef SWIRL_UI_TESTS
    IsolatedUserRegistry automatedRegistry;
    if (!initializeIsolatedRegistryForTests(argc, argv, !controlledSessionRoot.isEmpty(), automatedRegistry))
        return 64;
#endif
    configureSwirlFontRendering();
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
    QQuickWindow::setDefaultAlphaBuffer(true);
    QQuickWindow::setTextRenderType(QQuickWindow::NativeTextRendering);
#ifdef SWIRL_UI_TESTS
    SwirlTestApplication app(argc, argv);
#else
    QApplication app(argc, argv);
#endif
    app.setApplicationName(QStringLiteral("Swirl"));
    app.setOrganizationName(QStringLiteral("SOLHK"));
    app.setOrganizationDomain(QStringLiteral("solhk.dev"));
    app.setApplicationVersion(QStringLiteral(SWIRL_APP_VERSION));
#ifdef SWIRL_PRIVATE_UI_QUOTA
    PrivateUiQuotaSession privateUiQuota;
    if (!privateUiQuota.begin()) return 64;
#endif
#ifdef SWIRL_UI_TESTS
    int postAppExitCode = 0;
    if (tryRunPostAppUiCommand(app, &postAppExitCode))
        return postAppExitCode;
#endif
#ifdef Q_OS_WIN
    QSvgRenderer brand(QStringLiteral(":/swirl/icons/swirl_windows.svg"));
#else
    QSvgRenderer brand(QStringLiteral(":/swirl/icons/swirl_knot_mark_light.svg"));
#endif
    QIcon icon;
    const auto brandContent = swirlBrandContentBounds(brand);
    for (int size : swirlBrandIconSizes)
        icon.addPixmap(QPixmap::fromImage(swirlBrandRaster(brand, size, brandContent)));
    app.setWindowIcon(icon);
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    const QStringList arguments = app.arguments();
    const auto argumentValue = [&arguments](const QString &prefix) {
        for (const QString &argument : arguments)
            if (argument.startsWith(prefix))
                return argument.mid(prefix.size());
        return QString();
    };

    const bool motionTest = arguments.contains(QStringLiteral("--motion-test"));
    const bool activityLayoutTest = arguments.contains(QStringLiteral("--activity-layout-test"));
    const bool heroTest = arguments.contains(QStringLiteral("--hero-test"));
    const bool navigationTest = arguments.contains(QStringLiteral("--navigation-test"));
    const bool radiusTest = arguments.contains(QStringLiteral("--window-radius-test"));
    const bool appearanceTest = arguments.contains(QStringLiteral("--appearance-test"))
        || arguments.contains(QStringLiteral("--appearance-restore-test"));
    const bool uiQualityTest = arguments.contains(QStringLiteral("--ui-quality-test"));
    const bool fontUiTest = arguments.contains(QStringLiteral("--font-ui-test"));
    const bool fontReview = arguments.contains(QStringLiteral("--font-review"));
    const bool fontFrameTest = arguments.contains(QStringLiteral("--font-frame-test"));
    const bool fontAcceptanceTest = arguments.contains(QStringLiteral("--font-acceptance-test"));
    const bool fontDpiWatch = arguments.contains(QStringLiteral("--font-dpi-watch"));
    const bool interactivePreview = arguments.contains(QStringLiteral("--ui-preview"));
    const bool hdrTest = arguments.contains(QStringLiteral("--hdr-self-test"));
    const bool hdrDisplayTest = arguments.contains(QStringLiteral("--hdr-display-test"));
    const bool nodeTest = arguments.contains(QStringLiteral("--node-self-test"));
    const bool engineTest = arguments.contains(QStringLiteral("--engine-self-test"));
    const bool xrayUiTest = arguments.contains(QStringLiteral("--xray-import-ui-test"));
    const bool smoke = arguments.contains(QStringLiteral("--smoke-test"));
    const bool interaction = arguments.contains(QStringLiteral("--interaction-test"));
    const bool captureTest = arguments.contains(QStringLiteral("--capture-self-test"));
    const bool gatewayTest = arguments.contains(QStringLiteral("--gateway-self-test"));
    const bool windowTest = arguments.contains(QStringLiteral("--window-test"));
#ifdef SWIRL_UI_TESTS
    const bool policyTest = arguments.contains(QStringLiteral("--policy-self-test"));
    const bool lifecycleTest = arguments.contains(QStringLiteral("--lifecycle-test"));
#else
    constexpr bool policyTest = false;
    constexpr bool lifecycleTest = false;
    if (interaction)
        qWarning() << "Rebuild with -DSWIRL_BUILD_UI_TESTS=ON to run input checks.";
    if (activityLayoutTest || arguments.contains(QStringLiteral("--policy-self-test"))
        || nodeTest || engineTest || interaction || fontDpiWatch || fontAcceptanceTest
        || fontFrameTest || fontUiTest || uiQualityTest || windowTest || radiusTest
        || gatewayTest || captureTest) {
        return 4;
    }
#endif
#ifndef SWIRL_XRAY_UI_TESTS
    if (xrayUiTest) return 4;
#endif
    if (xrayUiTest && !qEnvironmentVariableIsSet("SWIRL_TEST_ROOT")) return 2;

    bool previewMode = interactivePreview || uiQualityTest || fontUiTest || fontReview
        || fontFrameTest || fontAcceptanceTest || fontDpiWatch;
    for (const QString &argument : arguments) {
        if (argument.startsWith(QStringLiteral("--material-test-output="))
            || argument.startsWith(QStringLiteral("--viewport-test-output="))
            || argument.startsWith(QStringLiteral("--motion-demo-output="))
            || argument.startsWith(QStringLiteral("--motion-visual-dir="))
            || argument.startsWith(QStringLiteral("--capture-preview="))
            || argument.startsWith(QStringLiteral("--capture-native-frame="))) {
            previewMode = true;
        }
    }

    QString runtimeStore;
#ifdef SWIRL_UI_TESTS
    ControlledNodeSession controlledSession;
    if (!controlledSessionRoot.isEmpty()) {
        if (!loadControlledNodeSession(controlledSessionRoot, &controlledSession)) return 64;
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if (!privateUiQuota.fixtureReady(controlledSession)) return 64;
#endif
        runtimeStore = controlledSession.storePath;
    }
    if (!validateUiLifecycleEnvironment(arguments))
        return 64;
#endif
    const bool controlledNodeSession = !controlledSessionRoot.isEmpty();
    const bool realAcceptance = controlledNodeSession;
    const bool isolatedRun = xrayUiTest || appearanceTest || lifecycleTest || realAcceptance
        || heroTest || navigationTest || radiusTest || nodeTest || policyTest || motionTest
        || activityLayoutTest || engineTest || hdrDisplayTest || hdrTest || interaction
        || captureTest || gatewayTest || smoke || windowTest || previewMode;

    SingleInstance instance;
    if (lifecycleTest || (!isolatedRun && !appearanceTest)) {
        const auto ownership = instance.acquire(
            lifecycleTest ? QStringLiteral("isolated-lifecycle-test") : QStringLiteral("production"));
        if (ownership == SingleInstance::Activated) return 0;
        if (ownership == SingleInstance::Unavailable) {
            if (!lifecycleTest) {
                QMessageBox::warning(nullptr, QStringLiteral("Swirl 暂未响应"),
                    QStringLiteral("未能确认现有 Swirl 窗口已恢复。若正在启动、退出或等待管理员授权，请完成该操作后重试。没有启动第二个代理内核。"));
            }
            return 10;
        }
    }
    if (isolatedRun || appearanceTest) {
        QStandardPaths::setTestModeEnabled(true);
        SwirlPaths::initializeTestStorage();
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope,
                           SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));
        QSettings isolatedSettings;
        if (!arguments.contains(QStringLiteral("--preview-preserve-settings")))
            isolatedSettings.clear();
        isolatedSettings.sync();
    }
#if defined(SWIRL_UI_TESTS) || defined(SWIRL_XRAY_UI_TESTS)
    const QString qmlCacheFlavor = QStringLiteral("qa");
#else
    const QString qmlCacheFlavor = QStringLiteral("release");
#endif
    SwirlPaths::initializeQmlCache(QStringLiteral(SWIRL_QML_CACHE_REVISION), qmlCacheFlavor);
#ifdef SWIRL_UI_TESTS
    recordFontUiMemoryProperty(app, fontUiTest, "fontBeforeManagerBytes");
#endif
    QTemporaryDir previewFonts;
    FontManager fontManager(nullptr, previewMode && !fontReview ? previewFonts.path() : QString());
#ifdef SWIRL_UI_TESTS
    recordFontUiMemoryProperty(app, fontUiTest, "fontAfterManagerBytes");
#endif
    if (previewMode) {
        for (const auto &argument : arguments) {
            if (argument.startsWith(QStringLiteral("--preview-font-file="))) {
                if (!fontManager.importFont(QUrl::fromLocalFile(argument.mid(20)))
                    || (!fontReview && !fontManager.applyPreview())) return 3;
            } else if (argument.startsWith(QStringLiteral("--preview-font-family="))) {
                if (!fontManager.selectFamily(argument.mid(22))) return 3;
            }
        }
    }
#ifdef SWIRL_UI_TESTS
    recordFontUiMemoryProperty(app, fontUiTest, "fontAfterImportBytes");
#endif
    WindowsBackdrop backdrop;
    WindowsBackdrop panelBackdrop;
    HdrOutput hdrOutput;
    QTemporaryDir isolatedTls;
    CaptureService capture(nullptr, isolatedRun ? isolatedTls.filePath(QStringLiteral("ca.dpapi")) : QString());
    ModuleDraftStore drafts;
    QTemporaryDir isolatedNodes(xrayUiTest
        ? SwirlPaths::testRoot() + QStringLiteral("/xray-ui-nodes-XXXXXX")
        : QDir::tempPath() + QStringLiteral("/Swirl-XXXXXX"));
    if (isolatedRun && !realAcceptance && !isolatedNodes.isValid()) return 2;
    const bool persistentPreview = interactivePreview && arguments.contains(QStringLiteral("--preview-preserve-settings"));
    const auto isolatedProfile = persistentPreview ? SwirlPaths::persistentPreviewDirectory() : isolatedNodes.path();
    const auto nodeStorePath = realAcceptance ? runtimeStore
        : isolatedRun ? isolatedProfile + QStringLiteral("/nodes.dpapi") : QString();
    auto runtimeEngine = std::make_unique<ThreadedEngine>();
#ifdef SWIRL_UI_TESTS
    EngineController engineController(std::move(runtimeEngine), nullptr, nodeStorePath, realAcceptance,
                                      createUiTestProxyBackend(arguments, controlledNodeSession),
                                      controlledNodeSession);
#else
    EngineController engineController(std::move(runtimeEngine), nullptr, nodeStorePath, realAcceptance);
#endif
#if defined(SWIRL_UI_TESTS) && defined(SWIRL_PRIVATE_UI_QUOTA)
    if (controlledNodeSession && controlledSession.uiImportPolicy) {
        if (!privateUiQuota.attachImportCapability(engineController.imports(), controlledSession)) return 64;
        if (controlledSession.uiDnsPolicy && !privateUiQuota.attachDnsCapability(&engineController, &controlledSession)) return 64;
    } else
#endif
    if (controlledNodeSession) engineController.imports()->shutdown();

    ExtensionService extensions(&engineController, isolatedRun ? isolatedProfile + QStringLiteral("/extensions.dpapi") : QString());
    GatewayService gateway(&engineController, isolatedRun ? isolatedProfile + QStringLiteral("/gateway.json") : QString());
    DiagnosticService diagnostics(isolatedRun ? isolatedProfile + QStringLiteral("/diagnostics") : QString());
    diagnostics.installQtHandler();
    SystemDataProvider systemData(&capture, &engineController, &diagnostics);
    MotionPolicy motionPolicy;
    DismissalController dismissals;
    QmlVmeWarningCapture qmlVmeWarnings;
    qmlVmeWarnings.runtime.start();
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("fontManager", &fontManager);
    engine.rootContext()->setContextProperty("motionPolicy", &motionPolicy);
    engine.rootContext()->setContextProperty("panelBackdrop", &panelBackdrop);
    engine.rootContext()->setContextProperty("dismissals", &dismissals);
    engine.addImageProvider(QStringLiteral("swirl"), new SvgIconProvider);

    bool qmlWarnings = false;
    bool previewCaptured = false;
    bool xrayUiCompleted = false;
    bool xrayUiTimedOut = false;
    QObject::connect(&engine, &QQmlEngine::warnings, &app,
                     [&qmlWarnings, smoke, &engine, &qmlVmeWarnings
#ifdef SWIRL_UI_TESTS
                      , nodeTest
#endif
                     ](const QList<QQmlError> &warnings) {
                         if (!warnings.isEmpty()) qmlWarnings = true;
                         bool captureVmeWarning = smoke;
#ifdef SWIRL_UI_TESTS
                         captureVmeWarning = captureVmeWarning || nodeTest;
#endif
                         if (captureVmeWarning)
                             recordQmlVmeWarningContext(engine, qmlVmeWarnings, warnings);
                     });

    const QString nativeFramePath = argumentValue(QStringLiteral("--capture-native-frame="));
    const QString previewPath = nativeFramePath.isEmpty() ? argumentValue(QStringLiteral("--capture-preview=")) : nativeFramePath;
    const QString previewPage = argumentValue(QStringLiteral("--preview-page="));
    const QString previewTheme = argumentValue(QStringLiteral("--preview-theme="));
    const QString previewFont = argumentValue(QStringLiteral("--preview-font="));
    if (previewMode && !previewFont.isEmpty() && !fontManager.selectFamily(previewFont)) {
        qCritical() << "Preview font unavailable:" << previewFont;
        return 2;
    }
    const QString previewState = argumentValue(QStringLiteral("--preview-state="));
    if (xrayUiTest || appearanceTest || heroTest || navigationTest || radiusTest || nodeTest
        || policyTest || motionTest || activityLayoutTest || previewMode || engineTest
        || hdrDisplayTest || hdrTest || smoke || interaction || captureTest || gatewayTest
        || windowTest || !previewPath.isEmpty()) {
        installQtDiagnosticFileHandler(selectQtDiagnosticLogFile(arguments));
        qInfo() << "Font rendering" << qgetenv("QT_QPA_PLATFORM") << fontManager.currentFamily()
                << "NativeRendering / FullHinting";
        if (smoke && fontReview) {
            qInfo().noquote() << "QML_CACHE_EVIDENCE" << QJsonDocument(QJsonObject{
                {"path", qEnvironmentVariable("QML_DISK_CACHE_PATH")},
                {"revision", QStringLiteral(SWIRL_QML_CACHE_REVISION)},
                {"flavor", qmlCacheFlavor}, {"qtVersion", QString::fromLatin1(qVersion())},
                {"diskCacheDisabledEnvironment", qEnvironmentVariable("QML_DISABLE_DISK_CACHE")}
            }).toJson(QJsonDocument::Compact);
        }
    }

    engine.rootContext()->setContextProperty("previewPage", previewPage);
    engine.rootContext()->setContextProperty("previewCaptureMode", previewMode && !interactivePreview);
    engine.rootContext()->setContextProperty("gpuEffectsSupported",
        QQuickWindow::graphicsApi() != QSGRendererInterface::Software
        && qEnvironmentVariable("QT_QUICK_BACKEND") != QStringLiteral("software"));
    engine.rootContext()->setContextProperty("previewTheme", previewTheme);
    engine.rootContext()->setContextProperty("previewState", previewState);
    engine.rootContext()->setContextProperty("smokeTestMode", smoke);
    engine.rootContext()->setContextProperty("fontSmokeReadyMode", smoke && fontReview);
    engine.rootContext()->setContextProperty("systemProvider", &systemData);
    engine.rootContext()->setContextProperty("extensionsProvider", &extensions);
    engine.rootContext()->setContextProperty("diagnostics", &diagnostics);
    engine.rootContext()->setContextProperty("backdrop", &backdrop);
    engine.rootContext()->setContextProperty("hdrOutput", &hdrOutput);
    engine.rootContext()->setContextProperty("captureProvider", &capture);
    engine.rootContext()->setContextProperty("gatewayProvider", &gateway);
    engine.rootContext()->setContextProperty("moduleDrafts", &drafts);
    engine.rootContext()->setContextProperty("engineController", &engineController);

#ifdef SWIRL_UI_TESTS
    int hdrSelfTestExitCode = 0;
    if (tryRunHdrSelfTest(arguments, &hdrSelfTestExitCode))
        return hdrSelfTestExitCode;
#endif
    qmlVmeWarnings.phase = "main-load";
    engine.loadFromModule("SwirlQuick", "Main");
    qmlVmeWarnings.phase = "after-main-load";
#ifdef SWIRL_UI_TESTS
    recordQmlCreationLifecycle(engine, "after-main-load");
#endif
    if (engine.rootObjects().isEmpty())
        return 1;

    auto *rootWindow = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (rootWindow) {
        rootWindow->setProperty("previewProfile", interactivePreview);
        rootWindow->contentItem()->setClip(true);
        rootWindow->setIcon(icon);
    }
#ifdef Q_OS_WIN
    if (rootWindow) configureTaskbarIdentity(rootWindow);
#endif
    const auto sizeParts = argumentValue(QStringLiteral("--preview-size=")).split('x');
    if (rootWindow && sizeParts.size() == 2 && sizeParts[0].toInt() >= 760 && sizeParts[1].toInt() >= 520)
        rootWindow->resize(sizeParts[0].toInt(), sizeParts[1].toInt());
    if (rootWindow && rootWindow->screen()) {
        const auto area = rootWindow->screen()->availableGeometry();
        rootWindow->setPosition(area.x() + qMax(0, (area.width() - rootWindow->width()) / 2),
                                area.y() + qMax(0, (area.height() - rootWindow->height()) / 2));
    }

    QTimer firstFrameWatchdog;
    bool firstFramePending = false;
    QMetaObject::Connection firstFrameConnection;
    if (rootWindow && backdrop.beginInitialPresentation()) {
        firstFramePending = true;
        firstFrameWatchdog.setSingleShot(true);
        firstFrameConnection = QObject::connect(rootWindow, &QQuickWindow::frameSwapped, &app, [&] {
            if (!firstFramePending) return;
            firstFramePending = false;
            firstFrameWatchdog.stop();
            if (!backdrop.presentFirstFrame()) app.exit(2);
        }, Qt::ConnectionType(Qt::QueuedConnection | Qt::SingleShotConnection));
        QObject::connect(&firstFrameWatchdog, &QTimer::timeout, &app, [&] {
            if (!firstFramePending) return;
            firstFramePending = false;
            QObject::disconnect(firstFrameConnection);
            qCritical() << "Startup aborted: Qt Quick did not present its first frame within 5000 ms"
                        << rootWindow->geometry() << rootWindow->devicePixelRatio();
            app.exit(2);
        });
        firstFrameWatchdog.start(5000);
    }
    if (rootWindow) rootWindow->show();

    std::unique_ptr<ShutdownCoordinator> shutdown;
    std::unique_ptr<TrayController> tray;
    if (rootWindow && (lifecycleTest || (!isolatedRun && !appearanceTest))) {
        app.setQuitOnLastWindowClosed(false);
        shutdown = std::make_unique<ShutdownCoordinator>(rootWindow, [&] {
            if (tray) tray->beginExit();
            QMetaObject::invokeMethod(rootWindow, "persistExitDrafts");
            engineController.shutdown(); extensions.shutdown(); capture.stop(); gateway.shutdown();
            QSettings().sync();
        }, [&] {
            return engineController.processAlive() || engineController.busy()
                || engineController.systemProxyBusy() || engineController.tests()->busy()
                || gateway.busy() || extensions.busy();
        }, [&] { return tray && tray->hideWindows(); });
        if (!lifecycleTest) tray = std::make_unique<TrayController>(rootWindow, icon, [&] { shutdown->request(); });
        instance.activate = [&] {
            if (shutdown->started()) return false;
            if (tray && tray->isAvailable()) { tray->restore(); return rootWindow->isVisible(); }
            const auto states = rootWindow->windowStates();
            if (states.testFlag(Qt::WindowMinimized))
                rootWindow->setWindowStates(states & ~Qt::WindowMinimized);
            if (!rootWindow->isVisible()) rootWindow->setVisible(true);
            rootWindow->raise();
            rootWindow->requestActivate();
            return rootWindow->isVisible();
        };
    }

    QTimer smokeFinish;
    smokeFinish.setSingleShot(true);
    smokeFinish.setInterval(0);
    if (rootWindow && smoke) {
        QObject::connect(rootWindow, SIGNAL(navigationSmokeCompleted()), &smokeFinish, SLOT(start()), Qt::QueuedConnection);
        QObject::connect(&smokeFinish, &QTimer::timeout, &app, [&app] { app.exit(0); });
    }
#ifdef SWIRL_XRAY_UI_TESTS
    if (xrayUiTest) {
        QTimer::singleShot(60000, &app, [&app, &xrayUiTimedOut] {
            xrayUiTimedOut = true;
            qCritical() << "XRAY_UI_FAIL timeout";
            app.exit(3);
        });
        const auto testStore = isolatedNodes.filePath(QStringLiteral("nodes.dpapi"));
        QTimer::singleShot(500, &app, [&app, rootWindow, &engineController, testStore, &xrayUiCompleted, &xrayUiTimedOut] {
            const int outcome = runXrayUiChecks(rootWindow, &engineController, testStore);
            xrayUiCompleted = outcome == 0 && !xrayUiTimedOut;
            app.exit(xrayUiTimedOut ? 3 : outcome);
        });
    }
#endif
    hdrOutput.attach(rootWindow);
    motionPolicy.attach(rootWindow);
#ifdef SWIRL_UI_TESTS
    if (const int uiSetupStatus = attachAndScheduleUiTests(
            app, rootWindow, engineController, fontManager, backdrop, capture,
            qmlVmeWarnings, controlledNodeSession, controlledSession);
        uiSetupStatus != 0) {
        return uiSetupStatus;
    }
#endif
    if (hdrDisplayTest) {
        auto *readbackFrames = new QTimer(&app);
        readbackFrames->setInterval(16);
        QObject::connect(readbackFrames, &QTimer::timeout, rootWindow, &QQuickWindow::update);
        readbackFrames->start();
        QTimer::singleShot(400, &app, [rootWindow, &backdrop] {
            rootWindow->showNormal(); rootWindow->raise(); rootWindow->requestActivate();
            backdrop.prepareNativeCapture();
        });
        QObject::connect(&hdrOutput, &HdrOutput::displayTestFinished, &app, [&app, &backdrop](bool success) {
            backdrop.finishNativeCapture();
            app.exit(success ? 0 : 2);
        });
        QTimer::singleShot(1600, &hdrOutput, [&hdrOutput, argumentValue] {
            hdrOutput.startDisplayTest(argumentValue(QStringLiteral("--hdr-display-output=")));
        });
        QTimer::singleShot(10000, &app, [&app] { qCritical() << "HDR display readback timeout"; app.exit(3); });
    }

    const auto previewSection = argumentValue(QStringLiteral("--preview-section="));
    if (rootWindow && !previewSection.isEmpty()) {
        QTimer::singleShot(350, rootWindow, [rootWindow, previewSection] {
            if (auto *loader = rootWindow->findChild<QObject *>(QStringLiteral("pageLoader")))
                if (auto *page = qvariant_cast<QObject *>(loader->property("item")))
                    page->setProperty("section", previewSection);
        });
    }
    const auto previewScale = argumentValue(QStringLiteral("--preview-ui-scale="));
    if (rootWindow && !previewScale.isEmpty()) {
        QQmlExpression scale(qmlContext(rootWindow), rootWindow,
                             QStringLiteral("Theme.setScalePercent(%1)").arg(qBound(75, previewScale.toInt(), 150)));
        scale.evaluate();
    }
    const auto previewPopup = argumentValue(QStringLiteral("--preview-popup="));
    if (previewMode && rootWindow && !previewPopup.isEmpty()) {
        QTimer::singleShot(600, rootWindow, [rootWindow, previewPopup]() {
            auto *loader = rootWindow->findChild<QObject *>(QStringLiteral("pageLoader"));
            auto *page = loader ? qvariant_cast<QObject *>(loader->property("item")) : nullptr;
            if (!page) return;
            QObject *popup = nullptr;
            if (previewPopup == QStringLiteral("node-dialog"))
                popup = rootWindow->findChild<QObject *>(QStringLiteral("proxyAddDialog"));
            else if (previewPopup == QStringLiteral("node-import"))
                popup = rootWindow->findChild<QObject *>(QStringLiteral("nodeImportDialog"));
            else if (previewPopup == QStringLiteral("subscription-dialog"))
                popup = rootWindow->findChild<QObject *>(QStringLiteral("subscriptionDialog"));
            else if (previewPopup == QStringLiteral("region-menu")) {
                auto *combo = rootWindow->findChild<QObject *>(QStringLiteral("proxyRegionCombo"));
                if (combo) popup = qvariant_cast<QObject *>(combo->property("popup"));
            }
            if (!popup || !QMetaObject::invokeMethod(popup, "open"))
                qWarning() << "Preview popup could not be opened" << previewPopup;
        });
    }
    if (arguments.contains(QStringLiteral("--preview-scroll-bottom")))
        QTimer::singleShot(400, rootWindow, [rootWindow]() { QMetaObject::invokeMethod(rootWindow, "previewScrollBottom"); });

    if (!interaction && !captureTest && smoke) {
        QTimer::singleShot(60000, &app, [&app]() {
            qCritical() << "Navigation smoke test timed out before completing all pages.";
            app.exit(3);
        });
    } else if (!interaction && !captureTest && !previewPath.isEmpty()) {
        if (rootWindow) {
            QTimer::singleShot(500, &app, [rootWindow, previewState] {
                QMouseEvent move(QEvent::MouseMove, QPointF(1, 1), rootWindow->mapToGlobal(QPoint(1, 1)),
                                 Qt::NoButton, Qt::NoButton, Qt::NoModifier);
                QCoreApplication::sendEvent(rootWindow, &move);
                QQmlExpression expression(qmlContext(rootWindow), rootWindow, QStringLiteral("preparePreviewState(previewState)"));
                expression.evaluate();
                if (expression.hasError()) qWarning() << expression.error();
            });
            auto *captureBackdrop = previewPage == QStringLiteral("external") ? &panelBackdrop : &backdrop;
            if (!nativeFramePath.isEmpty()) {
                QTimer::singleShot(400, &app, [&app, captureBackdrop] {
                    if (!captureBackdrop->prepareNativeCapture()) {
                        qCritical() << "Native capture blocked: cannot activate target window";
                        app.exit(3);
                    }
                });
            }
            const int nativeMargin = qBound(0, argumentValue(QStringLiteral("--capture-native-margin=")).toInt(), 80);
            const int captureDelay = (fontReview && !argumentValue(QStringLiteral("--font-reading-points=")).isEmpty()) ? 1500 : 900;
            QTimer::singleShot(captureDelay, &app, [rootWindow, previewPage, previewPath, nativeFramePath, nativeMargin, captureBackdrop, &app, &previewCaptured]() {
                QQuickWindow *captureWindow = rootWindow;
                const QString targetName = previewPage == QStringLiteral("external") ? QStringLiteral("dashboardWindow") : QString();
                if (!targetName.isEmpty()) {
                    for (auto *candidate : QGuiApplication::allWindows())
                        if (candidate->isVisible() && candidate->objectName() == targetName)
                            if (auto *quick = qobject_cast<QQuickWindow *>(candidate)) { captureWindow = quick; break; }
                }
                if (!nativeFramePath.isEmpty() && !captureBackdrop->isCaptureForeground()) {
                    qCritical() << "Native capture blocked: target window lost foreground";
                    captureBackdrop->finishNativeCapture();
                    app.exit(3);
                    return;
                }
                QImage screenshot = nativeFramePath.isEmpty()
                    ? captureWindow->grabWindow()
                    : captureWindow->screen()->grabWindow(0, captureWindow->x() - nativeMargin,
                          captureWindow->y() - nativeMargin, captureWindow->width() + 2 * nativeMargin,
                          captureWindow->height() + 2 * nativeMargin).toImage();
                if (nativeFramePath.isEmpty() && captureWindow == rootWindow) {
                    QList<QQuickWindow *> popups;
                    QRect bounds = rootWindow->geometry();
                    for (auto *candidate : QGuiApplication::allWindows()) {
                        if (candidate != rootWindow && candidate->isVisible() && candidate->flags().testFlag(Qt::Popup)) {
                            if (auto *quick = qobject_cast<QQuickWindow *>(candidate)) {
                                popups.append(quick);
                                bounds = bounds.united(candidate->geometry());
                            }
                        }
                    }
                    if (!popups.isEmpty()) {
                        qInfo() << "Capture union geometry" << bounds;
                        for (auto *popup : popups) qInfo() << "Capture popup geometry" << popup->geometry();
                        const auto ratio = rootWindow->devicePixelRatio();
                        QImage combined(qRound(bounds.width() * ratio), qRound(bounds.height() * ratio),
                                        QImage::Format_ARGB32_Premultiplied);
                        combined.setDevicePixelRatio(ratio);
                        combined.fill(Qt::transparent);
                        QPainter painter(&combined);
                        painter.drawImage(rootWindow->position() - bounds.topLeft(), screenshot);
                        for (auto *popup : popups)
                            painter.drawImage(popup->position() - bounds.topLeft(), popup->grabWindow());
                        painter.end();
                        screenshot = combined;
                    }
                }
                if (!screenshot.isNull() && screenshot.save(previewPath)) {
                    previewCaptured = true;
                    qInfo() << (nativeFramePath.isEmpty() ? "Saved Qt UI render:" : "Saved Windows compositor screenshot:") << previewPath;
                    qInfo() << "Capture geometry" << captureWindow->geometry() << "DPR" << captureWindow->devicePixelRatio() << captureBackdrop->status();
                    QQmlExpression scaleState(qmlContext(rootWindow), rootWindow, QStringLiteral("Theme.uiScale"));
                    qInfo() << "Capture UI scale" << scaleState.evaluate();
                    if (!nativeFramePath.isEmpty()) captureBackdrop->finishNativeCapture();
                    return;
                }
                if (!nativeFramePath.isEmpty()) {
                    captureBackdrop->finishNativeCapture();
                    qCritical() << "Native capture failed; no synthetic fallback used";
                    app.exit(3);
                    return;
                }
                const auto fallback = rootWindow->contentItem()->grabToImage();
                if (!fallback) {
                    qWarning() << "Optional UI screenshot unavailable on this renderer:" << previewPath;
                    return;
                }
                QObject::connect(fallback.data(), &QQuickItemGrabResult::ready, rootWindow,
                                 [fallback, previewPath, &previewCaptured]() {
                    if (!fallback->image().isNull() && fallback->image().save(previewPath)) {
                        previewCaptured = true;
                        qInfo() << "Saved Qt item snapshot:" << previewPath;
                    } else {
                        qWarning() << "Unable to save optional item preview:" << previewPath;
                    }
                });
            });
            QTimer::singleShot(2400, &app, [&app, &previewCaptured] { app.exit(previewCaptured ? 0 : 3); });
        } else {
            QTimer::singleShot(0, &app, &QCoreApplication::quit);
        }
    }

    const int result = app.exec();
    qmlVmeWarnings.phase = "after-event-loop";
#ifdef SWIRL_UI_TESTS
    recordQmlCreationLifecycle(engine, "after-event-loop");
#endif
    qmlVmeWarnings.phase = "existing-incubation-drain";
    if (auto *controller = engine.incubationController())
        controller->incubateFor(100);
    qmlVmeWarnings.phase = "after-existing-incubation-drain";
#ifdef SWIRL_UI_TESTS
    recordQmlCreationLifecycle(engine, "after-existing-incubation-drain");
#endif
    qmlVmeWarnings.phase = "main-return";
    const int finalResult = (controlledNodeSession || xrayUiTest || heroTest || radiusTest
        || nodeTest || policyTest || motionTest || activityLayoutTest || previewMode
        || engineTest || smoke || interaction || captureTest || gatewayTest || windowTest
        || !previewPath.isEmpty()) && qmlWarnings ? 2 : result;
    if (xrayUiTest) {
        if (!xrayUiCompleted || xrayUiTimedOut) return finalResult == 0 ? 3 : finalResult;
        if (finalResult == 0) qInfo() << "XRAY_UI_PASS";
    }
#ifdef SWIRL_PRIVATE_UI_QUOTA
    if (!privateUiQuota.finish()) return 64;
#endif
    return finalResult;
}

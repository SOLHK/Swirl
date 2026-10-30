#include <QGuiApplication>
#include "engine/RustCoreSelfTest.h"
#include "network/TlsRuntimeSelfTest.h"
#include "app/SingleInstance.h"
#include "app/ShutdownCoordinator.h"
#include "app/FontManager.h"
#include "app/StoragePaths.h"
#include "app/FontRendering.h"
#if defined(SWIRL_UI_TESTS) && defined(Q_OS_WIN)
#include "tests/third_party/renderdoc_app.h"
#endif
#include <QQmlApplicationEngine>
#ifdef SWIRL_UI_TESTS
#include <QQmlDebuggingEnabler>
#include <QtQml/private/qqmlengine_p.h>
#include <QtQuickTemplates2/private/qquickcontrol_p_p.h>
#include <QJsonArray>
#include <QSet>
#endif
#include <QQmlContext>
#include <QQmlError>
#include <QIcon>
#include <QSvgRenderer>
#include <QPainter>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shobjidl.h>
#include <propkey.h>
#include <propvarutil.h>
#include <QDir>
#endif
#include <QTimer>
#include <QQuickWindow>
#include <QQuickStyle>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QImage>
#include <QMouseEvent>
#include <QDebug>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTcpServer>
#include <QTextStream>
#include <QCoreApplication>
#include <QQmlExpression>
#include <QQmlIncubationController>
#include <QScreen>
#include <QStandardPaths>
#include <QSettings>
#include <QTemporaryDir>
#include "app/ModuleDraftStore.h"
#include "app/ExtensionService.h"
#include "app/MotionPolicy.h"
#include "app/DismissalController.h"
#ifdef SWIRL_XRAY_UI_TESTS
#include "tests/XrayUiChecks.h"
#endif
#ifdef SWIRL_UI_TESTS
#include "tests/OverviewChecks.h"
#include "tests/RuntimeEvidence.h"
#include "tests/CaptureChecks.h"
#include "tests/GatewayChecks.h"
#include "tests/WindowChecks.h"
#include "tests/WindowRadiusChecks.h"
#include "tests/UiQualityChecks.h"
#include "tests/FontUiChecks.h"
#include "tests/FontFrameChecks.h"
#include "tests/FontAcceptanceChecks.h"
#include "tests/FontDpiWatch.h"
#include "tests/HdrChecks.h"
#include "tests/EngineUiChecks.h"
#include "tests/NodeUiChecks.h"
#include "tests/PolicyUiChecks.h"
#include "tests/PolicySystemProxyBackend.h"
#include "tests/MotionChecks.h"
#include "tests/ActivityLayoutChecks.h"
#include "tests/MaterialChecks.h"
#include "tests/HeroChecks.h"
#include "tests/NavigationChecks.h"
#include "tests/AppearanceChecks.h"
#include <QSslSocket>
#endif
#include "app/SystemDataProvider.h"
#include "app/WindowsBackdrop.h"
#include "app/SvgIconProvider.h"
#include "app/BrandRaster.h"
#include "app/DiagnosticService.h"
#include "app/HdrOutput.h"
#include "network/CaptureService.h"
#include "network/GatewayService.h"
#include "engine/ThreadedEngine.h"
#include "engine/EngineController.h"

#ifdef SWIRL_UI_TESTS
static void recordQmlCreationLifecycle(QQmlApplicationEngine &engine, const char *phase)
{
    // The public controller counts incubators, while the engine also counts
    // synchronous and Qt Controls deferred creation. Observe both without
    // completing, cancelling or reading any deferred QML property.
    auto *engineState=QQmlEnginePrivate::get(&engine);
    const int inProgressBefore=engineState->inProgressCreations;
    auto *controller=engine.incubationController();
    QJsonArray pendingControls;
    QSet<QObject *> visited;
    QList<QObject *> pending=engine.rootObjects();
    int controlCount=0;
    int pendingControlCount=0;
    constexpr int maximumObjects=8192;
    constexpr int maximumReportedControls=128;
    const auto flags=[](const QQuickUntypedDeferredPointer &pointer){
        return QJsonObject{{"hasDeferredState",pointer.deferredState()!=nullptr},
                           {"executing",pointer.isExecuting()},
                           {"executed",pointer.wasExecuted()}};
    };
    while(!pending.isEmpty() && visited.size()<maximumObjects) {
        auto *object=pending.takeLast();
        if(!object || visited.contains(object))continue;
        visited.insert(object);
        for(auto *child:object->children())pending.append(child);
        if(auto *item=qobject_cast<QQuickItem *>(object))
            for(auto *child:item->childItems())pending.append(child);
        if(auto *control=qobject_cast<QQuickControl *>(object)) {
            ++controlCount;
            auto *state=QQuickControlPrivate::get(control);
            // These are raw deferred-pointer flags. Calling background() or
            // contentItem(), including through QObject::property(), would
            // itself create the objects this diagnostic is trying to locate.
            if(!state->background.deferredState() && !state->contentItem.deferredState())continue;
            ++pendingControlCount;
            if(pendingControls.size()>=maximumReportedControls)continue;
            auto *context=qmlContext(control);
            pendingControls.append(QJsonObject{
                {"objectName",control->objectName()},
                {"type",QString::fromLatin1(control->metaObject()->className())},
                {"parentName",control->parent()?control->parent()->objectName():QString()},
                {"contextUrl",context?context->baseUrl().toString():QString()},
                {"background",flags(state->background)},
                {"contentItem",flags(state->contentItem)}});
        }
    }
    qInfo().noquote()<<"QML_CREATION_LIFECYCLE"<<QJsonDocument(QJsonObject{
        {"phase",QString::fromLatin1(phase)},
        {"inProgressCreations",inProgressBefore},
        {"inProgressAfterObservation",engineState->inProgressCreations},
        {"controllerPresent",controller!=nullptr},
        {"publicIncubators",controller?controller->incubatingObjectCount():0},
        {"visitedObjects",static_cast<int>(visited.size())},
        {"traversalTruncated",!pending.isEmpty()},
        {"controls",controlCount},
        {"pendingControlCount",pendingControlCount},
        {"pendingControls",pendingControls},
        {"pendingControlsTruncated",pendingControlCount>maximumReportedControls},
        {"scope",QStringLiteral("Root QObject/visual trees; raw Control background/contentItem flags only. Other deferred properties and engine-owned singletons are not enumerated.")}
    }).toJson(QJsonDocument::Compact);
}
#endif

#ifdef Q_OS_WIN
static void configureTaskbarIdentity(QQuickWindow *window)
{
    if(QGuiApplication::platformName()!=QStringLiteral("windows"))return;
    IPropertyStore *store=nullptr;
    HRESULT result=SHGetPropertyStoreForWindow(reinterpret_cast<HWND>(window->winId()),IID_PPV_ARGS(&store));
    if(FAILED(result)){qWarning()<<"Taskbar property store unavailable"<<quint32(result);return;}
    const auto setString=[&](const PROPERTYKEY &key,const QString &text){
        PROPVARIANT value{};
        HRESULT status=InitPropVariantFromString(reinterpret_cast<LPCWSTR>(text.utf16()),&value);
        if(SUCCEEDED(status))status=store->SetValue(key,value);
        PropVariantClear(&value);
        return status;
    };
    const auto exe=QDir::toNativeSeparators(QCoreApplication::applicationFilePath());
    // A process AppID alone lets Explorer reuse an older registered shortcut's
    // group icon. Publish this window's own resources before its explicit ID.
    const auto iconPath=QDir::toNativeSeparators(QCoreApplication::applicationDirPath()+QStringLiteral("/Swirl-brand-0217-optical.ico"));
    result=setString(PKEY_AppUserModel_RelaunchIconResource,iconPath+QStringLiteral(",0"));
    if(SUCCEEDED(result))result=setString(PKEY_AppUserModel_RelaunchCommand,QStringLiteral("\"%1\"").arg(exe));
    if(SUCCEEDED(result))result=setString(PKEY_AppUserModel_RelaunchDisplayNameResource,QStringLiteral("@%1,-100").arg(exe));
    if(SUCCEEDED(result))result=setString(PKEY_AppUserModel_ID,QStringLiteral("SOLHK.Swirl.Desktop"));
    store->Release();
    if(FAILED(result))qWarning()<<"Taskbar identity publication failed"<<quint32(result);
}
#endif

// Collect Qt/QML diagnostics in a file because the Windows GUI subsystem
// does not attach stderr to GitHub Actions' PowerShell console.
static void recordQtDiagnostic(QtMsgType type, const QMessageLogContext &, const QString &message)
{
    const auto name=qApp->property("qtDiagnosticFile").toString();
    QFile file(QCoreApplication::applicationDirPath()+"/"+(name.isEmpty()?QStringLiteral("Swirl-diagnostics.txt"):name));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        return;
    QTextStream out(&file);
    out << static_cast<int>(type) << ": " << message << '\n';
}

int main(int argc, char *argv[])
{
    // Package verification runs the real EXE/DLL, before any UI, NodeStore,
    // system-proxy ownership, or persisted settings are opened.
    for (int i = 1; i < argc; ++i) {
        if (QByteArray(argv[i]) == "--tls-runtime-self-test") {
            QCoreApplication selfTest(argc, argv);
            if (i + 1 >= argc) return 64;
            return runTlsRuntimeSelfTest(QString::fromLocal8Bit(argv[i + 1]));
        }
        if (QByteArray(argv[i]) == "--rust-core-self-test") {
            QCoreApplication selfTest(argc, argv);
            if (i + 1 >= argc) return 64;
            return runRustCoreSelfTest(QString::fromLocal8Bit(argv[i + 1]));
        }
    }
#ifdef Q_OS_WIN
    SetCurrentProcessExplicitAppUserModelID(L"SOLHK.Swirl.Desktop");
#endif
    configureSwirlFontRendering();
    // Keep fractional Windows monitor scale factors (125%, 150%, 175%) intact;
    // Qt then exposes logical geometry and raster DPR per screen.
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
    QQuickWindow::setDefaultAlphaBuffer(true);
    QQuickWindow::setTextRenderType(QQuickWindow::NativeTextRendering);
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Swirl"));
    app.setOrganizationName(QStringLiteral("SOLHK"));
    app.setOrganizationDomain(QStringLiteral("solhk.dev"));
    app.setApplicationVersion(QStringLiteral(SWIRL_APP_VERSION));
#ifdef SWIRL_UI_TESTS
    if (app.arguments().contains(QStringLiteral("--capture-self-test"))) {
        const auto backend = qEnvironmentVariable("SWIRL_CAPTURE_TEST_TLS_BACKEND");
        if (!backend.isEmpty() && !QSslSocket::setActiveBackend(backend)) {
            std::fprintf(stderr, "The requested capture-test TLS backend is unavailable.\n");
            return 2;
        }
    }
#ifdef Q_OS_WIN
    // Read-only native QA capture, limited to the actual Windows taskbar.
    for(const auto &argument:app.arguments())if(argument.startsWith("--capture-taskbar=")) {
        const auto taskbar=FindWindowW(L"Shell_TrayWnd",nullptr);
        if(!taskbar||!app.primaryScreen())return 3;
        RECT area{};if(!GetWindowRect(taskbar,&area))return 3;
        // The taskbar itself uses DirectComposition, so its window DC is
        // black. Capture the composed desktop and retain only its taskbar ROI.
        const auto desktop=app.primaryScreen()->grabWindow(0);
        const auto origin=app.primaryScreen()->geometry().topLeft()*app.primaryScreen()->devicePixelRatio();
        const auto shot=desktop.copy(area.left-origin.x(),area.top-origin.y(),area.right-area.left,area.bottom-area.top);
        return !shot.isNull()&&shot.save(argument.mid(QStringLiteral("--capture-taskbar=").size()))?0:4;
    }
#endif
#endif
    // Rasterize the square optical master at every Windows icon size. This works even
    // when the optional SVG QIcon plugin is missing and avoids the old wind logo.
#ifdef Q_OS_WIN
    QSvgRenderer brand(QStringLiteral(":/swirl/icons/swirl_windows.svg"));
#else
    QSvgRenderer brand(QStringLiteral(":/swirl/icons/swirl_knot_mark_light.svg"));
#endif
    QIcon icon;
    const auto brandContent=swirlBrandContentBounds(brand);
    for(int size:swirlBrandIconSizes) {
        icon.addPixmap(QPixmap::fromImage(swirlBrandRaster(brand,size,brandContent)));
    }
    app.setWindowIcon(icon);
    // Native Windows Qt Quick Controls do not support custom backgrounds/content.
    // Swirl draws its own visual controls, so explicitly use the customizable style.
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    const bool motionTest=app.arguments().contains("--motion-test");
    const bool activityLayoutTest=app.arguments().contains("--activity-layout-test");
#ifndef SWIRL_UI_TESTS
    if(activityLayoutTest)return 4;
#endif
#ifdef SWIRL_UI_TESTS
    // Opt-in tracing in the isolated test executable only. No debugger in packages.
    if(motionTest && qEnvironmentVariableIsSet("SWIRL_QML_PROFILE")) {
        QQmlDebuggingEnabler::setServices(QQmlDebuggingEnabler::profilerServices());
        QQmlDebuggingEnabler::enableDebugging(false);
    }
#endif
    const bool heroTest=app.arguments().contains("--hero-test");
    const bool navigationTest=app.arguments().contains("--navigation-test");
    const bool radiusTest=app.arguments().contains("--window-radius-test");
    const bool appearanceTest=app.arguments().contains("--appearance-test")||app.arguments().contains("--appearance-restore-test");
    const bool uiQualityTest=app.arguments().contains("--ui-quality-test");
    const bool fontUiTest=app.arguments().contains("--font-ui-test");
    const bool fontReview=app.arguments().contains("--font-review");
    const bool fontFrameTest=app.arguments().contains("--font-frame-test");
    const bool fontAcceptanceTest=app.arguments().contains("--font-acceptance-test");
    const bool fontDpiWatch=app.arguments().contains("--font-dpi-watch");
    const bool interactivePreview=app.arguments().contains("--ui-preview");
    bool previewMode=interactivePreview||uiQualityTest||fontUiTest||fontReview||fontFrameTest||fontAcceptanceTest||fontDpiWatch;
    for(const QString &argument:app.arguments())
        if(argument.startsWith(QStringLiteral("--material-test-output="))||argument.startsWith(QStringLiteral("--viewport-test-output="))||argument.startsWith(QStringLiteral("--motion-demo-output="))||argument.startsWith(QStringLiteral("--motion-visual-dir="))||argument.startsWith(QStringLiteral("--capture-preview="))||argument.startsWith(QStringLiteral("--capture-native-frame=")))previewMode=true;
    const bool hdrTest=app.arguments().contains("--hdr-self-test");
    const bool hdrDisplayTest=app.arguments().contains("--hdr-display-test");
    const bool nodeTest=app.arguments().contains("--node-self-test");
#ifdef SWIRL_UI_TESTS
    const bool policyTest=app.arguments().contains("--policy-self-test");
#else
    constexpr bool policyTest=false;
    if(app.arguments().contains("--policy-self-test"))return 4;
#endif
    const bool engineTest=app.arguments().contains("--engine-self-test");
    const bool xrayUiTest=app.arguments().contains("--xray-import-ui-test");
#ifndef SWIRL_XRAY_UI_TESTS
    if(xrayUiTest)return 4;
#endif
    // This profile must never fall back to the user's normal test-mode folders.
    if(xrayUiTest&&!qEnvironmentVariableIsSet("SWIRL_TEST_ROOT"))return 2;
    QString runtimeStore,runtimeCommands,runtimeState;
#ifdef SWIRL_UI_TESTS
    for(const auto &argument:app.arguments()){
        if(argument.startsWith("--runtime-store="))runtimeStore=argument.mid(16);
        if(argument.startsWith("--runtime-commands="))runtimeCommands=argument.mid(19);
        if(argument.startsWith("--runtime-state="))runtimeState=argument.mid(16);
    }
#endif
    const bool realAcceptance=!runtimeStore.isEmpty()&&!runtimeCommands.isEmpty()&&!runtimeState.isEmpty();
    bool lifecycleTest=false;
#ifdef SWIRL_UI_TESTS
    lifecycleTest=app.arguments().contains("--lifecycle-test");
#endif
    const bool isolatedRun=xrayUiTest||appearanceTest||lifecycleTest||realAcceptance||heroTest||navigationTest||radiusTest||nodeTest||policyTest||motionTest||activityLayoutTest||engineTest||hdrDisplayTest||hdrTest||app.arguments().contains("--interaction-test")||app.arguments().contains("--capture-self-test")||app.arguments().contains("--gateway-self-test")||app.arguments().contains("--smoke-test")||app.arguments().contains("--window-test")||previewMode;
    SingleInstance instance;
    if(lifecycleTest || (!isolatedRun && !appearanceTest)) {
        const auto ownership=instance.acquire(lifecycleTest?QStringLiteral("isolated-lifecycle-test"):QStringLiteral("production"));
        if(ownership!=SingleInstance::Primary)return ownership==SingleInstance::Activated?0:10;
    }
    if(isolatedRun||appearanceTest) {
        QStandardPaths::setTestModeEnabled(true);
        SwirlPaths::initializeTestStorage();
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));
        QSettings isolatedSettings;
        if(!app.arguments().contains("--preview-preserve-settings"))isolatedSettings.clear();
        isolatedSettings.sync();
    }
#if defined(SWIRL_UI_TESTS) || defined(SWIRL_XRAY_UI_TESTS)
    const QString qmlCacheFlavor=QStringLiteral("qa");
#else
    const QString qmlCacheFlavor=QStringLiteral("release");
#endif
    SwirlPaths::initializeQmlCache(QStringLiteral(SWIRL_QML_CACHE_REVISION),qmlCacheFlavor);
#ifdef SWIRL_UI_TESTS
    if(fontUiTest)app.setProperty("fontBeforeManagerBytes",fontUiPrivateBytes());
#endif
    QTemporaryDir previewFonts;
    FontManager fontManager(nullptr,previewMode&&!fontReview?previewFonts.path():QString());
#ifdef SWIRL_UI_TESTS
    if(fontUiTest)app.setProperty("fontAfterManagerBytes",fontUiPrivateBytes());
#endif
    if(previewMode)for(const auto &argument:app.arguments()){
        if(argument.startsWith("--preview-font-file=")){
            if(!fontManager.importFont(QUrl::fromLocalFile(argument.mid(20)))||(!fontReview&&!fontManager.applyPreview()))return 3;
        }else if(argument.startsWith("--preview-font-family=")){
            if(!fontManager.selectFamily(argument.mid(22)))return 3;
        }
    }
#ifdef SWIRL_UI_TESTS
    if(fontUiTest)app.setProperty("fontAfterImportBytes",fontUiPrivateBytes());
#endif
    WindowsBackdrop backdrop;
    WindowsBackdrop panelBackdrop;
    HdrOutput hdrOutput;
    QTemporaryDir isolatedTls;
    CaptureService capture(nullptr,isolatedRun?isolatedTls.filePath("ca.dpapi"):QString());
    ModuleDraftStore drafts;
    QTemporaryDir isolatedNodes(xrayUiTest?SwirlPaths::testRoot()+QStringLiteral("/xray-ui-nodes-XXXXXX")
                                        :QDir::tempPath()+QStringLiteral("/Swirl-XXXXXX"));
    if(isolatedRun&&!realAcceptance&&!isolatedNodes.isValid())return 2;
    auto runtimeEngine=std::make_unique<ThreadedEngine>();
#ifdef SWIRL_UI_TESTS
    // Native node/policy acceptance uses the actual controller and listener,
    // with only host system-proxy I/O replaced by an owned in-memory adapter.
    std::unique_ptr<SystemProxySession::Backend> policyProxyBackend;
    if(policyTest||nodeTest)policyProxyBackend=std::make_unique<PolicySystemProxyBackend>();
    EngineController engineController(std::move(runtimeEngine),nullptr,realAcceptance?runtimeStore:isolatedRun?isolatedNodes.filePath("nodes.dpapi"):QString(),realAcceptance,std::move(policyProxyBackend));
#else
    EngineController engineController(std::move(runtimeEngine),nullptr,realAcceptance?runtimeStore:isolatedRun?isolatedNodes.filePath("nodes.dpapi"):QString(),realAcceptance);
#endif
    ExtensionService extensions(&engineController,isolatedRun?isolatedNodes.filePath("extensions.dpapi"):QString());
    GatewayService gateway(&engineController,isolatedRun?isolatedNodes.filePath("gateway.json"):QString());
    DiagnosticService diagnostics(isolatedRun?isolatedNodes.filePath("diagnostics"):QString());
    diagnostics.installQtHandler();
    SystemDataProvider systemData(&capture,&engineController,&diagnostics);
    MotionPolicy motionPolicy;
    DismissalController dismissals;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("fontManager", &fontManager);
    engine.rootContext()->setContextProperty("motionPolicy", &motionPolicy);
    engine.rootContext()->setContextProperty("panelBackdrop", &panelBackdrop);
    engine.rootContext()->setContextProperty("dismissals", &dismissals);
    engine.addImageProvider(QStringLiteral("swirl"),new SvgIconProvider);
    const bool smoke = app.arguments().contains("--smoke-test");
    const bool interaction = app.arguments().contains("--interaction-test");
    const bool captureTest = app.arguments().contains("--capture-self-test");
    const bool gatewayTest=app.arguments().contains("--gateway-self-test");
    const bool windowTest = app.arguments().contains("--window-test");
    bool qmlWarnings = false;
    bool previewCaptured = false;
    bool xrayUiCompleted = false;
    bool xrayUiTimedOut = false;
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
    const QString nativeFramePath = argumentValue(QStringLiteral("--capture-native-frame="));
    const QString previewPath = nativeFramePath.isEmpty()?argumentValue(QStringLiteral("--capture-preview=")):nativeFramePath;
    const QString previewPage = argumentValue(QStringLiteral("--preview-page="));
    const QString previewTheme = argumentValue(QStringLiteral("--preview-theme="));
    const QString previewFont = argumentValue(QStringLiteral("--preview-font="));
    if(previewMode && !previewFont.isEmpty() && !fontManager.selectFamily(previewFont)) {
        qCritical()<<"Preview font unavailable:"<<previewFont;return 2;
    }
    const QString previewState = argumentValue(QStringLiteral("--preview-state="));
    if (xrayUiTest || appearanceTest || heroTest || navigationTest || radiusTest || nodeTest || policyTest || motionTest || activityLayoutTest || previewMode || engineTest || hdrDisplayTest || hdrTest || smoke || interaction || captureTest || gatewayTest || windowTest || !previewPath.isEmpty()) {
        if(uiQualityTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-ui-quality.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-ui-quality.txt");}
        if(appearanceTest){const QString file=app.arguments().contains("--appearance-restore-test")?"Swirl-appearance-restore.txt":"Swirl-appearance.txt";app.setProperty("qtDiagnosticFile",file);QFile::remove(QCoreApplication::applicationDirPath()+"/"+file);}
        if(heroTest){const QString file=app.arguments().contains("--hero-material-only")?"Swirl-hero-material-diagnostics.txt":"Swirl-hero-diagnostics.txt";app.setProperty("qtDiagnosticFile",file);QFile::remove(QCoreApplication::applicationDirPath()+"/"+file);}
        else if(motionTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-motion-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-motion-diagnostics.txt");}
        if(nodeTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-node-ui-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-node-ui-diagnostics.txt");}
        if(policyTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-policy-ui-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-policy-ui-diagnostics.txt");}
        else if(interaction){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-input-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-input-diagnostics.txt");}
        if(engineTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-engine-ui-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-engine-ui-diagnostics.txt");}
        if(xrayUiTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-xray-ui-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-xray-ui-diagnostics.txt");}
        QFile::remove(QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-diagnostics.txt"));
        qInstallMessageHandler(recordQtDiagnostic);
        qInfo()<<"Font rendering"<<qgetenv("QT_QPA_PLATFORM")<<fontManager.currentFamily()
               <<"NativeRendering / FullHinting";
    }
    engine.rootContext()->setContextProperty("previewPage", previewPage);
    engine.rootContext()->setContextProperty("previewCaptureMode", previewMode && !interactivePreview);
    engine.rootContext()->setContextProperty("gpuEffectsSupported", QQuickWindow::graphicsApi()!=QSGRendererInterface::Software && qEnvironmentVariable("QT_QUICK_BACKEND")!=QStringLiteral("software"));
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
    if(hdrTest)return runHdrChecks();
#endif
    engine.loadFromModule("SwirlQuick", "Main");
#ifdef SWIRL_UI_TESTS
    recordQmlCreationLifecycle(engine,"after-main-load");
#endif
    if (engine.rootObjects().isEmpty())
        return 1;
    auto *rootWindow = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
#ifdef SWIRL_UI_TESTS
    if(rootWindow && activityLayoutTest && qEnvironmentVariableIsSet("SWIRL_LAYOUT_EXPECTED_DPR")) {
        // Reuse the existing render-only native viewport fixture before the
        // first explicit preview resize. High-DPR cases keep their full HWND
        // and swapchain even when the hosted desktop is smaller. The driver
        // verifies Win32 client pixels and RHI readback; physical presentation
        // remains a separate, unexecuted Windows 11 acceptance requirement.
        rootWindow->setProperty("swirlViewportTest",true);
    }
#endif
    if(rootWindow){
        // Keep animated and antialiased damage inside this HWND. The native
        // outer shadow remains in its own window.
        rootWindow->contentItem()->setClip(true);
        rootWindow->setIcon(icon);
    }
#ifdef Q_OS_WIN
    if(rootWindow)configureTaskbarIdentity(rootWindow);
#endif
    const auto sizeParts = argumentValue(QStringLiteral("--preview-size=")).split('x');
    if (rootWindow && sizeParts.size() == 2 && sizeParts[0].toInt() >= 760 && sizeParts[1].toInt() >= 520)
        rootWindow->resize(sizeParts[0].toInt(), sizeParts[1].toInt());
    if (rootWindow && rootWindow->screen()) {
        // Commit the restored QML size and screen position before first show.
        // The first exposed frame must use the final geometry and DPI.
        const auto area = rootWindow->screen()->availableGeometry();
        rootWindow->setPosition(area.x()+qMax(0,(area.width()-rootWindow->width())/2),
                                area.y()+qMax(0,(area.height()-rootWindow->height())/2));
    }
    QTimer firstFrameWatchdog;
    bool firstFramePending=false;
    QMetaObject::Connection firstFrameConnection;
    if(rootWindow && backdrop.beginInitialPresentation()){
        firstFramePending=true;
        firstFrameWatchdog.setSingleShot(true);
        firstFrameConnection=QObject::connect(rootWindow,&QQuickWindow::frameSwapped,&app,[&]{
            if(!firstFramePending)return;
            firstFramePending=false;
            firstFrameWatchdog.stop();
            if(!backdrop.presentFirstFrame())app.exit(2);
        },Qt::ConnectionType(Qt::QueuedConnection|Qt::SingleShotConnection));
        QObject::connect(&firstFrameWatchdog,&QTimer::timeout,&app,[&]{
            if(!firstFramePending)return;
            firstFramePending=false;
            QObject::disconnect(firstFrameConnection);
            qCritical()<<"Startup aborted: Qt Quick did not present its first frame within 5000 ms"
                       <<rootWindow->geometry()<<rootWindow->devicePixelRatio();
            app.exit(2);
        });
        firstFrameWatchdog.start(5000);
    }
    if(rootWindow)rootWindow->show();
    std::unique_ptr<ShutdownCoordinator> shutdown;
    if(rootWindow && (lifecycleTest || (!isolatedRun && !appearanceTest))) {
        app.setQuitOnLastWindowClosed(false);
        shutdown=std::make_unique<ShutdownCoordinator>(rootWindow,[&]{
            QMetaObject::invokeMethod(rootWindow,"persistExitDrafts");
            engineController.shutdown();extensions.shutdown();capture.stop();gateway.shutdown();
            QSettings().sync();
        },[&]{return engineController.processAlive()||engineController.busy()||engineController.tests()->busy()||gateway.busy()||extensions.busy();});
        instance.activate=[&]{
            if(shutdown->started())return;
            const auto states=rootWindow->windowStates();
            if(states.testFlag(Qt::WindowMinimized))
                rootWindow->setWindowStates(states & ~Qt::WindowMinimized);
            if(!rootWindow->isVisible())rootWindow->setVisible(true);
            rootWindow->raise();
            rootWindow->requestActivate();
        };
    }
#ifdef SWIRL_UI_TESTS
    if(rootWindow&&lifecycleTest){
        const auto fixture=qEnvironmentVariable("SWIRL_LIFECYCLE_ENGINE");
        if(!fixture.isEmpty()){
            QTcpServer reserve;reserve.listen(QHostAddress::LocalHost);const auto port=reserve.serverPort();reserve.close();
            if(fixture!="rust")return 64;
            engineController.setProxyPort(port);engineController.setRoutingMode("direct");
            QObject::connect(&engineController,&EngineController::statusChanged,&app,[&]{if(engineController.processAlive())app.setProperty("lifecycleEnginePid",engineController.processId());});
            engineController.connectNode("");
        }
        QObject::connect(&app,&QCoreApplication::aboutToQuit,&app,[&]{
            const auto path=qEnvironmentVariable("SWIRL_LIFECYCLE_REPORT");
            if(!path.isEmpty()){QFile file(path);if(file.open(QIODevice::WriteOnly))file.write(QJsonDocument(QJsonObject{{"pid",double(QCoreApplication::applicationPid())},{"enginePid",app.property("lifecycleEnginePid").toString()},{"shutdownMs",double(app.property("shutdownDurationMs").toLongLong())},{"executable",QCoreApplication::applicationFilePath()}}).toJson());}
        });
        QTimer::singleShot(250,rootWindow,[rootWindow]{QMetaObject::invokeMethod(rootWindow,"openDashboard");});
        const auto delay=qEnvironmentVariableIntValue("SWIRL_LIFECYCLE_EXIT_MS");
        QTimer::singleShot(delay>0?delay:2500,rootWindow,[rootWindow]{rootWindow->close();});
    }
#endif
    // All smoke state is isolated. Finish with exit(), as other QA drivers do,
    // rather than the user-facing window close/unsaved-change quit path.
    QTimer smokeFinish;smokeFinish.setSingleShot(true);smokeFinish.setInterval(0);
    if(rootWindow&&smoke){QObject::connect(rootWindow,SIGNAL(navigationSmokeCompleted()),&smokeFinish,SLOT(start()),Qt::QueuedConnection);QObject::connect(&smokeFinish,&QTimer::timeout,&app,[&app]{app.exit(0);});}
#ifdef SWIRL_XRAY_UI_TESTS
    if(xrayUiTest) {
        QTimer::singleShot(60000,&app,[&app,&xrayUiTimedOut]{
            xrayUiTimedOut=true;
            qCritical()<<"XRAY_UI_FAIL timeout";
            app.exit(3);
        });
        const auto testStore=isolatedNodes.filePath(QStringLiteral("nodes.dpapi"));
        QTimer::singleShot(500,&app,[&app,rootWindow,&engineController,testStore,&xrayUiCompleted,&xrayUiTimedOut]{
            const int outcome=runXrayUiChecks(rootWindow,&engineController,testStore);
            xrayUiCompleted=outcome==0&&!xrayUiTimedOut;
            app.exit(xrayUiTimedOut?3:outcome);
        });
    }
#endif
#ifdef SWIRL_UI_TESTS
    if(realAcceptance&&rootWindow)startRuntimeEvidence(rootWindow,&engineController,&systemData,&diagnostics,runtimeCommands,runtimeState);
    if(activityLayoutTest) {
        const auto output=argumentValue(QStringLiteral("--activity-layout-output="));
        QTimer::singleShot(450,&app,[&app,rootWindow,output]{app.exit(runActivityLayoutChecks(rootWindow,output));});
    }
#endif
    hdrOutput.attach(rootWindow);
#if defined(SWIRL_UI_TESTS) && defined(Q_OS_WIN)
    const auto renderdocOutput=argumentValue(QStringLiteral("--renderdoc-output="));
    if(!renderdocOutput.isEmpty()) {
        // Opt-in QA only: the external RenderDoc launcher injects its library.
        // This captures this process's graphics commands, never the desktop.
        const auto library=GetModuleHandleW(L"renderdoc.dll");
        auto getApi=library?reinterpret_cast<pRENDERDOC_GetAPI>(GetProcAddress(library,"RENDERDOC_GetAPI")):nullptr;
        RENDERDOC_API_1_6_0 *api=nullptr;
        if(!getApi||!getApi(eRENDERDOC_API_Version_1_6_0,reinterpret_cast<void **>(&api)))return 5;
        api->SetCaptureFilePathTemplate(renderdocOutput.toUtf8().constData());
        api->MaskOverlayBits(0,0);
        QTimer::singleShot(650,rootWindow,[api,rootWindow]{api->TriggerCapture();rootWindow->update();});
        QTimer::singleShot(1100,rootWindow,[api,rootWindow]{
            QQmlExpression expression(qmlContext(rootWindow),rootWindow,"Theme.glassBlurStrength+=0.25");expression.evaluate();
            api->TriggerMultiFrameCapture(3);rootWindow->update();
        });
    }
#endif
    if(nodeTest) {
#ifdef SWIRL_UI_TESTS
        QTimer::singleShot(400,&app,[&app,rootWindow,&engineController]{app.exit(runNodeUiChecks(rootWindow,&engineController));});
#else
        return 4;
#endif
    }
#ifdef SWIRL_UI_TESTS
    if(policyTest){
        const auto directory=argumentValue(QStringLiteral("--policy-output="));
        QTimer::singleShot(400,&app,[&app,rootWindow,&engineController,directory]{app.exit(runPolicyUiChecks(rootWindow,&engineController,directory));});
    }
#endif
        motionPolicy.attach(rootWindow);
#ifdef SWIRL_UI_TESTS
    const auto viewportDirectory=argumentValue(QStringLiteral("--viewport-test-output="));
    const auto materialDirectory=argumentValue(QStringLiteral("--material-test-output="));
    const auto demoDirectory=argumentValue(QStringLiteral("--motion-demo-output="));
    const auto visualDirectory=argumentValue(QStringLiteral("--motion-visual-dir="));
    if(navigationTest){
        const auto directory=argumentValue(QStringLiteral("--navigation-output="));
        QTimer::singleShot(450,&app,[&app,rootWindow,&engineController,directory]{app.exit(runNavigationChecks(rootWindow,&engineController,directory));});
    } else if(appearanceTest){
        const bool restore=app.arguments().contains("--appearance-restore-test");
        QTimer::singleShot(450,&app,[&app,rootWindow,restore]{app.exit(runAppearanceChecks(rootWindow,restore));});
    } else if(heroTest) {
        const auto directory=argumentValue(QStringLiteral("--hero-output="));
        const auto armFile=argumentValue(QStringLiteral("--hero-arm-file="));
        if(armFile.isEmpty())QTimer::singleShot(450,&app,[&app,rootWindow,&engineController,directory]{app.exit(runHeroChecks(rootWindow,&engineController,directory));});
        else {
            // Wait until the external ETW recorder has been allowed through
            // the Windows secure desktop before exercising display modes.
            auto armTimer=new QTimer(&app);armTimer->setInterval(100);
            QObject::connect(armTimer,&QTimer::timeout,&app,[&app,rootWindow,&engineController,directory,armFile,armTimer]{
                if(!QFile::exists(armFile))return;
                armTimer->stop();armTimer->deleteLater();QFile::remove(armFile);
                app.exit(runHeroChecks(rootWindow,&engineController,directory));
            });armTimer->start();
        }
    } else if(!materialDirectory.isEmpty()) {
        QTimer::singleShot(450,&app,[&app,rootWindow,materialDirectory]{app.exit(runMaterialChecks(rootWindow,materialDirectory));});
    } else if(!viewportDirectory.isEmpty()) {
        QTimer::singleShot(450,&app,[&app,rootWindow,viewportDirectory]{app.exit(runViewportChecks(rootWindow,viewportDirectory));});
    } else if(!demoDirectory.isEmpty()) {
        QTimer::singleShot(450,&app,[&app,rootWindow,demoDirectory]{app.exit(runMotionDemo(rootWindow,demoDirectory));});
    } else if(!visualDirectory.isEmpty()) {
        QTimer::singleShot(450,&app,[&app,rootWindow,visualDirectory]{app.exit(runMotionVisualChecks(rootWindow,visualDirectory));});
    } else if(motionTest) {
        const auto report=argumentValue(QStringLiteral("--motion-output="));
        QTimer::singleShot(450,&app,[&app,rootWindow,report]{app.exit(runMotionChecks(rootWindow,report));});
    }
#endif
    if (engineTest) {
#ifdef SWIRL_UI_TESTS
        QTimer::singleShot(400, &app, [&app, rootWindow, &engineController, &capture] { app.exit(runEngineUiChecks(rootWindow, &engineController, &capture)); });
#else
        return 4;
#endif
    }
    if(hdrDisplayTest) {
        // Asynchronous GPU readbacks retire on later frames. Keep this test
        // rendering even when the UI is idle; ordinary runs remain event driven.
        auto *readbackFrames = new QTimer(&app);
        readbackFrames->setInterval(16);
        QObject::connect(readbackFrames, &QTimer::timeout, rootWindow, &QQuickWindow::update);
        readbackFrames->start();
        QTimer::singleShot(400,&app,[rootWindow,&backdrop]{rootWindow->showNormal();rootWindow->raise();rootWindow->requestActivate();backdrop.prepareNativeCapture();});
        QObject::connect(&hdrOutput,&HdrOutput::displayTestFinished,&app,[&app,&backdrop](bool success){backdrop.finishNativeCapture();app.exit(success?0:2);});
        QTimer::singleShot(1600,&hdrOutput,[&hdrOutput,argumentValue]{hdrOutput.startDisplayTest(argumentValue(QStringLiteral("--hdr-display-output=")));});
        QTimer::singleShot(10000,&app,[&app]{qCritical()<<"HDR display readback timeout";app.exit(3);});
    }
    const auto previewSection=argumentValue(QStringLiteral("--preview-section="));
    if(rootWindow && !previewSection.isEmpty()) {
        QTimer::singleShot(350,rootWindow,[rootWindow,previewSection]{
            if(auto *loader=rootWindow->findChild<QObject *>(QStringLiteral("pageLoader")))
                if(auto *page=qvariant_cast<QObject *>(loader->property("item")))page->setProperty("section",previewSection);
        });
    }
    const auto previewScale=argumentValue(QStringLiteral("--preview-ui-scale="));
    if(rootWindow && !previewScale.isEmpty()) {
        QQmlExpression scale(qmlContext(rootWindow),rootWindow,QStringLiteral("Theme.setScalePercent(%1)").arg(qBound(75,previewScale.toInt(),150)));
        scale.evaluate();
    }
    // Capture-only controls for visually reviewing actual popup surfaces.
    const auto previewPopup=argumentValue(QStringLiteral("--preview-popup="));
    if(previewMode && rootWindow && !previewPopup.isEmpty()) {
        QTimer::singleShot(600, rootWindow, [rootWindow, previewPopup]() {
            auto *loader=rootWindow->findChild<QObject *>(QStringLiteral("pageLoader"));
            auto *page=loader?qvariant_cast<QObject *>(loader->property("item")):nullptr;
            if(!page)return;
            QObject *popup=nullptr;
            if(previewPopup==QStringLiteral("node-dialog"))
                popup=rootWindow->findChild<QObject *>(QStringLiteral("proxyAddDialog"));
            else if(previewPopup==QStringLiteral("node-import"))
                popup=rootWindow->findChild<QObject *>(QStringLiteral("nodeImportDialog"));
            else if(previewPopup==QStringLiteral("subscription-dialog"))
                popup=rootWindow->findChild<QObject *>(QStringLiteral("subscriptionDialog"));
            else if(previewPopup==QStringLiteral("region-menu")) {
                auto *combo=rootWindow->findChild<QObject *>(QStringLiteral("proxyRegionCombo"));
                if(combo)popup=qvariant_cast<QObject *>(combo->property("popup"));
            }
            if(!popup || !QMetaObject::invokeMethod(popup,"open"))
                qWarning()<<"Preview popup could not be opened"<<previewPopup;
        });
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
    if(fontDpiWatch) {
#ifdef SWIRL_UI_TESTS
        startFontDpiWatch(rootWindow,&fontManager,argumentValue(QStringLiteral("--font-source-file=")),argumentValue(QStringLiteral("--font-dpi-output=")));
#else
        return 4;
#endif
    }
    if(fontAcceptanceTest) {
#ifdef SWIRL_UI_TESTS
        const auto output=argumentValue(QStringLiteral("--font-acceptance-output="));
        const auto source=argumentValue(QStringLiteral("--font-source-file="));
        const bool currentPageOnly=app.arguments().contains("--font-acceptance-current-page");
        QTimer::singleShot(700,&app,[&app,rootWindow,&fontManager,output,source,currentPageOnly]{app.exit(runFontAcceptanceChecks(rootWindow,&fontManager,source,output,currentPageOnly));});
#else
        return 4;
#endif
    }
    if(fontFrameTest) {
#ifdef SWIRL_UI_TESTS
        const auto output=argumentValue(QStringLiteral("--font-frame-output="));
        QTimer::singleShot(700,&app,[&app,rootWindow,&fontManager,output]{app.exit(runFontFrameChecks(rootWindow,&fontManager,output));});
#else
        return 4;
#endif
    }
#ifdef SWIRL_UI_TESTS
    if(fontReview && rootWindow) {
        const double points=argumentValue(QStringLiteral("--font-reading-points=")).toDouble();
        const auto label=argumentValue(QStringLiteral("--font-reading-label="));
        const auto readingOutput=argumentValue(QStringLiteral("--font-reading-output="));
        if(points>=9 && points<=16)QTimer::singleShot(700,rootWindow,[rootWindow,points,label,readingOutput]{applyFontReadingReview(rootWindow,points,label,readingOutput);});
    }
#endif
    if(fontUiTest) {
#ifdef SWIRL_UI_TESTS
        const auto output=argumentValue(QStringLiteral("--font-ui-output="));
        QTimer::singleShot(500,&app,[&app,rootWindow,&fontManager,output]{app.exit(runFontUiChecks(rootWindow,&fontManager,output));});
#else
        return 4;
#endif
    }
    if (uiQualityTest) {
#ifdef SWIRL_UI_TESTS
        const auto output=argumentValue(QStringLiteral("--ui-quality-output="));
        const bool baseline=app.arguments().contains("--ui-quality-baseline");
        QTimer::singleShot(500,&app,[&app,rootWindow,&backdrop,output,baseline]{app.exit(runUiQualityChecks(rootWindow,&backdrop,output,baseline));});
#else
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
    if (radiusTest) {
#ifdef SWIRL_UI_TESTS
        const auto output=argumentValue(QStringLiteral("--window-radius-output="));
        QTimer::singleShot(400,&app,[&app,rootWindow,&backdrop,output]{app.exit(runWindowRadiusChecks(rootWindow,&backdrop,output));});
#else
        return 4;
#endif
    }
    if(gatewayTest){
#ifdef SWIRL_UI_TESTS
        QTimer::singleShot(400,&app,[&app]{app.exit(runGatewayChecks());});
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
            QTimer::singleShot(500,&app,[window,previewState]{
                QMouseEvent move(QEvent::MouseMove,QPointF(1,1),window->mapToGlobal(QPoint(1,1)),Qt::NoButton,Qt::NoButton,Qt::NoModifier);
                QCoreApplication::sendEvent(window,&move);
                QQmlExpression expression(qmlContext(window),window,QStringLiteral("preparePreviewState(previewState)"));expression.evaluate();
                if(expression.hasError())qWarning()<<expression.error();
            });
            auto *captureBackdrop=previewPage=="external"?&panelBackdrop:&backdrop;
            if(!nativeFramePath.isEmpty())QTimer::singleShot(400,&app,[&app,captureBackdrop]{if(!captureBackdrop->prepareNativeCapture()){qCritical()<<"Native capture blocked: cannot activate target window";app.exit(3);}});
            const int nativeMargin=qBound(0,argumentValue(QStringLiteral("--capture-native-margin=")).toInt(),80);
            QTimer::singleShot(fontReview && !argumentValue(QStringLiteral("--font-reading-points=")).isEmpty()?1500:900, &app, [window, previewPage, previewPath, nativeFramePath, nativeMargin, captureBackdrop, &app, &previewCaptured]() {
                QQuickWindow *captureWindow=window;
                const QString targetName=previewPage=="external"?"dashboardWindow":QString();
                if(!targetName.isEmpty())for(auto *candidate:QGuiApplication::allWindows())if(candidate->isVisible()&&candidate->objectName()==targetName)if(auto *quick=qobject_cast<QQuickWindow *>(candidate)){captureWindow=quick;break;}
                if(!nativeFramePath.isEmpty()&&!captureBackdrop->isCaptureForeground()){qCritical()<<"Native capture blocked: target window lost foreground";captureBackdrop->finishNativeCapture();app.exit(3);return;}
                QImage screenshot = nativeFramePath.isEmpty()?captureWindow->grabWindow():captureWindow->screen()->grabWindow(0,captureWindow->x()-nativeMargin,captureWindow->y()-nativeMargin,captureWindow->width()+2*nativeMargin,captureWindow->height()+2*nativeMargin).toImage();
                if(nativeFramePath.isEmpty()&&captureWindow==window){
                    QList<QQuickWindow *> popups;QRect bounds=window->geometry();
                    for(auto *candidate:QGuiApplication::allWindows())if(candidate!=window&&candidate->isVisible()&&candidate->flags().testFlag(Qt::Popup))if(auto *quick=qobject_cast<QQuickWindow *>(candidate)){popups.append(quick);bounds=bounds.united(candidate->geometry());}
                    if(!popups.isEmpty()){
                        qInfo()<<"Capture union geometry"<<bounds;
                        for(auto *popup:popups)qInfo()<<"Capture popup geometry"<<popup->geometry();
                        const auto ratio=window->devicePixelRatio();QImage combined(qRound(bounds.width()*ratio),qRound(bounds.height()*ratio),QImage::Format_ARGB32_Premultiplied);combined.setDevicePixelRatio(ratio);combined.fill(Qt::transparent);
                        QPainter painter(&combined);painter.drawImage(window->position()-bounds.topLeft(),screenshot);
                        for(auto *popup:popups)painter.drawImage(popup->position()-bounds.topLeft(),popup->grabWindow());painter.end();screenshot=combined;
                    }
                }
                if (!screenshot.isNull() && screenshot.save(previewPath)) {
                    previewCaptured=true;
                    qInfo() << (nativeFramePath.isEmpty()?"Saved Qt UI render:":"Saved Windows compositor screenshot:") << previewPath;
                    qInfo()<<"Capture geometry"<<captureWindow->geometry()<<"DPR"<<captureWindow->devicePixelRatio()<<captureBackdrop->status();
                    QQmlExpression scaleState(qmlContext(window),window,QStringLiteral("Theme.uiScale"));
                    qInfo()<<"Capture UI scale"<<scaleState.evaluate();
                    if(!nativeFramePath.isEmpty())captureBackdrop->finishNativeCapture();
                    return;
                }
                if(!nativeFramePath.isEmpty()){captureBackdrop->finishNativeCapture();qCritical()<<"Native capture failed; no synthetic fallback used";app.exit(3);return;}

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
#ifdef SWIRL_UI_TESTS
    recordQmlCreationLifecycle(engine,"after-event-loop");
#endif
    // Drain any lazy Qt Controls creation before the engine is destroyed.
    // This also keeps scripted page-navigation shutdown free of incubation warnings.
    if (auto *controller = engine.incubationController())
        controller->incubateFor(100);
#ifdef SWIRL_UI_TESTS
    recordQmlCreationLifecycle(engine,"after-existing-incubation-drain");
#endif
    const int finalResult=(xrayUiTest || heroTest || radiusTest || nodeTest || policyTest || motionTest || activityLayoutTest || previewMode || engineTest || smoke || interaction || captureTest || gatewayTest || windowTest || !previewPath.isEmpty()) && qmlWarnings ? 2 : result;
    if(xrayUiTest) {
        if(!xrayUiCompleted||xrayUiTimedOut)return finalResult==0?3:finalResult;
        if(finalResult==0)qInfo()<<"XRAY_UI_PASS";
    }
    return finalResult;
}

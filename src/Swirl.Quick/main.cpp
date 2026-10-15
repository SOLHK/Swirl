#include <QGuiApplication>
#include "app/FontManager.h"
#if defined(SWIRL_UI_TESTS) && defined(Q_OS_WIN)
#include "tests/third_party/renderdoc_app.h"
#endif
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QIcon>
#include <QSvgRenderer>
#include <QPainter>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shobjidl.h>
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
#include <QTextStream>
#include <QCoreApplication>
#include <QQmlExpression>
#include <QQmlIncubationController>
#include <QScreen>
#include <QStandardPaths>
#include <QSettings>
#include <QTemporaryDir>
#include <QFontDatabase>
#include "app/ModuleDraftStore.h"
#include "app/ExtensionService.h"
#include "app/MotionPolicy.h"
#include "app/DismissalController.h"
#ifdef SWIRL_UI_TESTS
#include "tests/OverviewChecks.h"
#include "tests/RuntimeEvidence.h"
#include "tests/CaptureChecks.h"
#include "tests/GatewayChecks.h"
#include "tests/WindowChecks.h"
#include "tests/UiQualityChecks.h"
#include "tests/HdrChecks.h"
#include "tests/EngineUiChecks.h"
#include "tests/NodeUiChecks.h"
#include "tests/MotionChecks.h"
#include "tests/MaterialChecks.h"
#include "tests/HeroChecks.h"
#include "tests/AppearanceChecks.h"
#endif
#include "app/SystemDataProvider.h"
#include "app/WindowsBackdrop.h"
#include "app/SvgIconProvider.h"
#include "app/BrandRaster.h"
#include "app/DiagnosticService.h"
#include "app/HdrOutput.h"
#include "network/CaptureService.h"
#include "network/GatewayService.h"
#include "engine/MihomoAdapter.h"
#include "engine/SwirlEngineManager.h"
#include "engine/EngineController.h"

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
#ifdef Q_OS_WIN
    SetCurrentProcessExplicitAppUserModelID(L"SOLHK.Swirl.Desktop");
#endif
    // Keep fractional Windows monitor scale factors (125%, 150%, 175%) intact;
    // Qt then exposes logical geometry and raster DPR per screen.
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
    QQuickWindow::setDefaultAlphaBuffer(true);
    QQuickWindow::setTextRenderType(QQuickWindow::NativeTextRendering);
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Swirl"));
    app.setOrganizationName(QStringLiteral("SOLHK"));
    app.setOrganizationDomain(QStringLiteral("solhk.dev"));
    app.setApplicationVersion(QStringLiteral("1.0.0-phase3-preview"));
#ifdef SWIRL_UI_TESTS
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
    // Rasterize the canonical mark at every Windows icon size. This works even
    // when the optional SVG QIcon plugin is missing and avoids the old wind logo.
    QSvgRenderer brand(QStringLiteral(":/swirl/icons/swirl_knot_mark_light.svg"));
    QIcon icon;
    for(int size:{16,20,24,32,40,48,64,128,256}) {
        icon.addPixmap(QPixmap::fromImage(swirlBrandRaster(brand,size)));
    }
    app.setWindowIcon(icon);
    // Native Windows Qt Quick Controls do not support custom backgrounds/content.
    // Swirl draws its own visual controls, so explicitly use the customizable style.
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    const bool motionTest=app.arguments().contains("--motion-test");
    const bool heroTest=app.arguments().contains("--hero-test");
    const bool appearanceTest=app.arguments().contains("--appearance-test")||app.arguments().contains("--appearance-restore-test");
    const bool uiQualityTest=app.arguments().contains("--ui-quality-test");
    bool previewMode=uiQualityTest;
    for(const QString &argument:app.arguments())
        if(argument.startsWith(QStringLiteral("--material-test-output="))||argument.startsWith(QStringLiteral("--viewport-test-output="))||argument.startsWith(QStringLiteral("--motion-demo-output="))||argument.startsWith(QStringLiteral("--motion-visual-dir="))||argument.startsWith(QStringLiteral("--capture-preview="))||argument.startsWith(QStringLiteral("--capture-native-frame=")))previewMode=true;
    const bool hdrTest=app.arguments().contains("--hdr-self-test");
    const bool hdrDisplayTest=app.arguments().contains("--hdr-display-test");
    const bool nodeTest=app.arguments().contains("--node-self-test");
    const bool engineTest=app.arguments().contains("--engine-self-test");
    QString runtimeStore,runtimeCommands,runtimeState;
#ifdef SWIRL_UI_TESTS
    for(const auto &argument:app.arguments()){
        if(argument.startsWith("--runtime-store="))runtimeStore=argument.mid(16);
        if(argument.startsWith("--runtime-commands="))runtimeCommands=argument.mid(19);
        if(argument.startsWith("--runtime-state="))runtimeState=argument.mid(16);
    }
#endif
    const bool realAcceptance=!runtimeStore.isEmpty()&&!runtimeCommands.isEmpty()&&!runtimeState.isEmpty();
    const bool isolatedRun=realAcceptance||heroTest||nodeTest||motionTest||engineTest||hdrDisplayTest||hdrTest||app.arguments().contains("--interaction-test")||app.arguments().contains("--capture-self-test")||app.arguments().contains("--gateway-self-test")||app.arguments().contains("--smoke-test")||app.arguments().contains("--window-test")||previewMode;
    if(isolatedRun||appearanceTest) {
        QStandardPaths::setTestModeEnabled(true);
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation));
        QSettings isolatedSettings;
        if(!app.arguments().contains("--preview-preserve-settings"))isolatedSettings.clear();
        isolatedSettings.sync();
    }
    FontManager fontManager;
    WindowsBackdrop backdrop;
    WindowsBackdrop settingsBackdrop;
    WindowsBackdrop panelBackdrop;
    HdrOutput hdrOutput;
    QTemporaryDir isolatedTls;
    CaptureService capture(nullptr,isolatedRun?isolatedTls.filePath("ca.dpapi"):QString());
    ModuleDraftStore drafts;
    QTemporaryDir isolatedNodes;
    std::unique_ptr<ProxyEngine> runtimeEngine;
    if(nodeTest||engineTest)runtimeEngine=std::make_unique<MihomoAdapter>(); // Pinned legacy regression fixtures.
    else runtimeEngine=std::make_unique<SwirlEngineManager>();
    EngineController engineController(std::move(runtimeEngine),nullptr,realAcceptance?runtimeStore:isolatedRun?isolatedNodes.filePath("nodes.dpapi"):QString(),realAcceptance);
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
    engine.rootContext()->setContextProperty("settingsBackdrop", &settingsBackdrop);
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
    const QString previewFontFile = argumentValue(QStringLiteral("--preview-font-file="));
    if(previewMode && !previewFontFile.isEmpty() && QFontDatabase::addApplicationFont(previewFontFile)<0) {
        qCritical()<<"Preview font file could not be loaded";return 2;
    }
    const QString previewFont = argumentValue(QStringLiteral("--preview-font="));
    if(previewMode && !previewFont.isEmpty() && !fontManager.selectFamily(previewFont)) {
        qCritical()<<"Preview font unavailable:"<<previewFont;return 2;
    }
    const QString previewState = argumentValue(QStringLiteral("--preview-state="));
    if (appearanceTest || heroTest || nodeTest || motionTest || previewMode || engineTest || hdrDisplayTest || hdrTest || smoke || interaction || captureTest || gatewayTest || windowTest || !previewPath.isEmpty()) {
        if(uiQualityTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-ui-quality.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-ui-quality.txt");}
        if(appearanceTest){const QString file=app.arguments().contains("--appearance-restore-test")?"Swirl-appearance-restore.txt":"Swirl-appearance.txt";app.setProperty("qtDiagnosticFile",file);QFile::remove(QCoreApplication::applicationDirPath()+"/"+file);}
        if(nodeTest){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-node-ui-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-node-ui-diagnostics.txt");}
        else if(interaction){app.setProperty("qtDiagnosticFile",QStringLiteral("Swirl-input-diagnostics.txt"));QFile::remove(QCoreApplication::applicationDirPath()+"/Swirl-input-diagnostics.txt");}
        QFile::remove(QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-diagnostics.txt"));
        qInstallMessageHandler(recordQtDiagnostic);
    }
    engine.rootContext()->setContextProperty("previewPage", previewPage);
    engine.rootContext()->setContextProperty("previewCaptureMode", previewMode);
    engine.rootContext()->setContextProperty("gpuEffectsSupported", QQuickWindow::graphicsApi()!=QSGRendererInterface::Software && qEnvironmentVariable("QT_QUICK_BACKEND")!=QStringLiteral("software"));
    engine.rootContext()->setContextProperty("previewTheme", previewTheme);
    engine.rootContext()->setContextProperty("previewState", previewState);
    engine.rootContext()->setContextProperty("smokeTestMode", smoke);
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
    if (engine.rootObjects().isEmpty())
        return 1;
    auto *rootWindow = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if(rootWindow)rootWindow->setIcon(icon);
    // All smoke state is isolated. Finish with exit(), as other QA drivers do,
    // rather than the user-facing window close/unsaved-change quit path.
    QTimer smokeFinish;smokeFinish.setSingleShot(true);smokeFinish.setInterval(0);
    if(rootWindow&&smoke){QObject::connect(rootWindow,SIGNAL(navigationSmokeCompleted()),&smokeFinish,SLOT(start()),Qt::QueuedConnection);QObject::connect(&smokeFinish,&QTimer::timeout,&app,[&app]{app.exit(0);});}
#ifdef SWIRL_UI_TESTS
    if(realAcceptance&&rootWindow)startRuntimeEvidence(rootWindow,&engineController,&systemData,&diagnostics,runtimeCommands,runtimeState);
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
        motionPolicy.attach(rootWindow);
#ifdef SWIRL_UI_TESTS
    const auto viewportDirectory=argumentValue(QStringLiteral("--viewport-test-output="));
    const auto materialDirectory=argumentValue(QStringLiteral("--material-test-output="));
    const auto demoDirectory=argumentValue(QStringLiteral("--motion-demo-output="));
    const auto visualDirectory=argumentValue(QStringLiteral("--motion-visual-dir="));
    if(appearanceTest){
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
    const auto sizeParts = argumentValue(QStringLiteral("--preview-size=")).split('x');
    if (rootWindow && sizeParts.size() == 2 && sizeParts[0].toInt() >= 760 && sizeParts[1].toInt() >= 520)
        rootWindow->resize(sizeParts[0].toInt(), sizeParts[1].toInt());
    if (rootWindow && rootWindow->screen()) {
        // QML chooses the initial logical size after the platform has placed
        // its small bootstrap window. Recenter once using the final size.
        const auto area = rootWindow->screen()->availableGeometry();
        rootWindow->setPosition(area.x()+qMax(0,(area.width()-rootWindow->width())/2),
                                area.y()+qMax(0,(area.height()-rootWindow->height())/2));
    }
    const auto previewSection=argumentValue(QStringLiteral("--preview-section="));
    if(rootWindow && !previewSection.isEmpty()) {
        if(auto *loader=rootWindow->findChild<QObject *>(QStringLiteral("pageLoader")))
            if(auto *page=qvariant_cast<QObject *>(loader->property("item")))page->setProperty("section",previewSection);
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
            if(!nativeFramePath.isEmpty())QTimer::singleShot(400,&app,[&app,&backdrop]{if(!backdrop.prepareNativeCapture()){qCritical()<<"Native capture blocked: cannot activate target window";app.exit(3);}});
            QTimer::singleShot(900, &app, [window, previewPage, previewPath, nativeFramePath, &backdrop, &app, &previewCaptured]() {
                QQuickWindow *captureWindow=window;
                if(previewPage=="dns"||previewPage=="external")for(auto *candidate:QGuiApplication::allWindows())if(candidate->isVisible()&&candidate!=window)if(auto *quick=qobject_cast<QQuickWindow *>(candidate)){captureWindow=quick;break;}
                if(!nativeFramePath.isEmpty()&&!backdrop.isCaptureForeground()){qCritical()<<"Native capture blocked: target window lost foreground";backdrop.finishNativeCapture();app.exit(3);return;}
                QImage screenshot = nativeFramePath.isEmpty()?captureWindow->grabWindow():window->screen()->grabWindow(0,window->x(),window->y(),window->width(),window->height()).toImage();
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
                    qInfo()<<"Capture geometry"<<window->geometry()<<"DPR"<<window->devicePixelRatio()<<backdrop.status();
                    QQmlExpression scaleState(qmlContext(window),window,QStringLiteral("Theme.uiScale"));
                    qInfo()<<"Capture UI scale"<<scaleState.evaluate();
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
    return (heroTest || nodeTest || motionTest || previewMode || engineTest || smoke || interaction || captureTest || gatewayTest || windowTest || !previewPath.isEmpty()) && qmlWarnings ? 2 : result;
}

#pragma once

#include "app/FontDisplayContext.h"
#include <QQmlProperty>
#include <QQuickImageProvider>
#include <QQuickStyle>
#include <QSignalSpy>
#include <QMetaProperty>
#include <QEvent>
#include <functional>
#include <memory>

// Only non-font services and decorative icons are isolated. Theme and every
// control under test are loaded from the actual application QML source files.
class FontQmlIconProvider final : public QQuickImageProvider {
public:
    FontQmlIconProvider() : QQuickImageProvider(QQuickImageProvider::Image) {}
    QImage requestImage(const QString &, QSize *size, const QSize &requested) override {
        const QSize dimensions = requested.isValid() ? requested : QSize(16, 16);
        if (size) *size = dimensions;
        QImage image(dimensions, QImage::Format_ARGB32_Premultiplied);
        image.fill(Qt::transparent);
        return image;
    }
};

inline void registerFontQmlTypes()
{
    static const bool registered = [] {
        QQuickStyle::setStyle(QStringLiteral("Basic")); // same style as main.cpp
        // Match qmltyperegistrar's generated path, including QQmlElement<T>,
        // so standalone compilation catches incompatible QML type declarations.
        qmlRegisterTypesAndRevisions<FontDisplayContext>("SwirlQuick", 1);
        qmlRegisterType<VariableFontPreview>("SwirlQuick", 1, 0, "VariableFontPreview");
        qmlRegisterType(QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/components/SwirlContinuousSurface.qml")),
                        "SwirlQuick", 1, 0, "SwirlContinuousSurface");
        qmlRegisterType(QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/controls/SwirlText.qml")),
                        "SwirlQuick", 1, 0, "SwirlText");
        qmlRegisterSingletonType(QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/Theme.qml")),
                                 "SwirlQuick", 1, 0, "Theme");
        qmlRegisterSingletonType(QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/SwirlMotion.qml")),
                                 "SwirlQuick", 1, 0, "SwirlMotion");
        qmlRegisterSingletonType(QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/SwirlTransitionRegistry.qml")),
                                 "SwirlQuick", 1, 0, "SwirlTransitionRegistry");
        return true;
    }();
    Q_UNUSED(registered);
}

void FontTests::qmlLiveAutomaticFonts()
{
    const auto fixtures = qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if (fixtures.isEmpty()) QSKIP("Generate the original public variable-font fixtures to run the QML integration test");
    QVERIFY(QFile::exists(fixtures + "/automation.ttf"));
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, directory.path());
    QSettings().clear();
    FontManager manager(nullptr, directory.filePath("fonts"));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures + "/automation.ttf")));
    QVERIFY(manager.applyPreview());
    QVERIFY(manager.automatic());

    registerFontQmlTypes();
    QStringList warnings;
    // Context services must outlive the engine's Theme singleton.
    QScopedPointer<QObject> serviceObject;
    QQmlEngine engine;
    // The full application build creates a SwirlQuick/qmldir beside this test
    // executable which prefers resources linked only into Swirl.exe. Keep this
    // source-based fixture independent of that unrelated application module.
    auto importPaths=engine.importPathList();
    importPaths.removeAll(QCoreApplication::applicationDirPath());
    engine.setImportPathList(importPaths);
    QObject::connect(&engine, &QQmlEngine::warnings, &engine, [&](const QList<QQmlError> &errors) {
        for (const auto &error : errors) warnings.append(error.toString());
    });
    engine.addImageProvider(QStringLiteral("swirl"), new FontQmlIconProvider);
    engine.rootContext()->setContextProperty("fontManager", &manager);
    engine.rootContext()->setContextProperty("gpuEffectsSupported", false);
    engine.rootContext()->setContextProperty("previewCaptureMode", false);
    engine.rootContext()->setContextProperty("fixtureStaticFamily", manager.defaultFamily());

    QQmlComponent services(&engine);
    services.setData(R"(
import QtQuick
QtObject {
    property bool reduced: false
    property int duration: 180
    property int hoverDuration: 120
    property int pressDuration: 80
    property int releaseDuration: 190
    property int switchDuration: 210
    property int dialogDuration: 264
    property int exitDuration: 160
    property int expandDuration: 360
    property real pressScale: 0.98
    property real speed: 1
    property real spring: 3.2
    property real damping: 0.28
    property int serial: 0
    property bool alwaysShowScrollbars: false
    property bool complexMotion: false
    property bool systemReducedMotion: false
    function zh(value) { return value }
    function noteTrigger(item) {}
    function allocate() { return ++serial }
    function setActive(token, active) {}
    function fingerprint(item) { return "" }
    function push(item, window) {}
    function pop(item) {}
    function setTransitioning(active) {}
    function popupOrigin(item) { return Item.Center }
}
)", QUrl("file:font-test-services.qml"));
    serviceObject.reset(services.create());
    QVERIFY2(serviceObject, qPrintable(services.errorString()));
    for (const char *name : {"AppState", "dismissals", "motionPolicy"})
        engine.rootContext()->setContextProperty(QString::fromLatin1(name), serviceObject.data());

    QQmlComponent component(&engine);
    component.setData(R"(
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "controls" as Controls
import "components" as Components
ApplicationWindow {
    id: window
    visible: true; width: 800; height: 900
    font.family: Theme.fontFamily; font.pixelSize: 16
    Column {
        Controls.SwirlText { id: body; objectName: "body"; text: "A"; font.pixelSize: 16
            readonly property var monitorAxes: Theme.variableAxesFor(font, 144, 1.5, "body")
        }
        Controls.SwirlText { objectName: "title"; text: "A"; textRole: "pageTitle"; font.pixelSize: 32; font.weight: Font.DemiBold }
        RowLayout { objectName: "widthHost"; width: 96
            Controls.SwirlText { objectName: "widthText"; text: "AAAAAAAA"; textRole: "button"; font.pixelSize: 20; Layout.fillWidth: true; elide: Text.ElideRight }
        }
        // The editor accepts point sizes. SwirlText deliberately keeps its
        // existing pixel-size default; Qt forbids setting both units at once.
        Controls.SwirlTextArea { objectName: "pointText"; text: "A"; font.pointSize: 18
            readonly property var monitorAxes: Theme.variableAxesFor(font, 144, 1.5, "body")
        }
        Controls.SwirlText { objectName: "staticText"; text: "A"; font.family: fixtureStaticFamily; font.pixelSize: 16 }
        Controls.SwirlTextField { objectName: "input"; text: "A"; placeholderText: "A"; font.pixelSize: 16 }
        Controls.SwirlTextArea { objectName: "area"; text: "A"; font.pixelSize: 16 }
        Controls.SwirlButton { objectName: "button"; text: "A"; font.weight: Font.Bold }
        Controls.SwirlComboBox { objectName: "combo"; model: ["A", "AA"]; font.weight: Font.DemiBold }
        Controls.SwirlToolTip { objectName: "tooltip"; parent: body; text: "A"; visible: true }
        Components.SwirlFontSettings { objectName: "fontSettings"; width: 700 }
    }
}
)", QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/font-integration-fixture.qml")));
    QScopedPointer<QObject> root(component.create());
    QVERIFY2(root, qPrintable(component.errorString()));
    auto *window = qobject_cast<QQuickWindow *>(root.data());
    QVERIFY(window);
    std::function<QQuickItem *(QQuickItem *, const QString &)> visualItem =
        [&](QQuickItem *parent, const QString &name) -> QQuickItem * {
            if (parent->objectName() == name) return parent;
            for (auto *child : parent->childItems())
                if (auto *found = visualItem(child, name)) return found;
            return nullptr;
        };
    auto item = [&](const char *name) -> QObject * {
        const auto objectName = QString::fromLatin1(name);
        if (auto *object = root->findChild<QObject *>(objectName)) return object;
        // Repeater delegates are owned by the delegate model; their visual
        // parent, rather than QObject::parent(), places them in the live UI.
        return visualItem(window->contentItem(), objectName);
    };
    auto font = [&](const char *name) { return item(name)->property("font").value<QFont>(); };
    for (const char *name : {"body", "title", "pointText", "staticText", "input", "area", "button", "combo", "tooltip", "fontSettings", "fontManualMode"})
        QVERIFY2(item(name), name);
    const auto weightTag = QFont::Tag("wght"), opticalTag = QFont::Tag("opsz"), heightTag = QFont::Tag("HGHT");
    QTRY_COMPARE(font("body").variableAxisValue(weightTag), 400.0f);
    QTRY_COMPARE(font("title").variableAxisValue(weightTag), 600.0f);
    QTRY_COMPARE(font("input").variableAxisValue(weightTag), 400.0f);
    QTRY_COMPARE(font("area").variableAxisValue(weightTag), 400.0f);
    QTRY_COMPARE(font("button").variableAxisValue(weightTag), 700.0f);
    QTRY_COMPARE(font("combo").variableAxisValue(weightTag), 600.0f);
    QTRY_VERIFY(item("fontPreviewLine_0"));
    QTRY_COMPARE(font("fontPreviewLine_0").variableAxisValue(weightTag), 600.0f);
    // Basic ToolTip retains the existing application font's Medium weight.
    QTRY_COMPARE(font("tooltip").variableAxisValue(weightTag), 500.0f);
    QCOMPARE(font("tooltip").weight(), QFont::Medium);
    QTRY_VERIFY(font("tooltip").isVariableAxisSet(heightTag));
    QVERIFY(font("staticText").variableAxisTags().isEmpty());
    QCOMPARE(font("body").pixelSize(), 16);
    QCOMPARE(font("body").pointSizeF(), -1.0);
    QCOMPARE(font("pointText").pointSizeF(), 18.0);
    QCOMPARE(font("pointText").pixelSize(), -1);
    QCOMPARE(item("body")->property("monitorAxes").toMap().value("opsz").toDouble(), 8.0);
    QCOMPARE(item("pointText")->property("monitorAxes").toMap().value("opsz").toDouble(), 18.0);
    auto *metrics = qobject_cast<FontDisplayContext *>(qmlAttachedPropertiesObject<FontDisplayContext>(window));
    QVERIFY(metrics);
    const auto expectedOpticalSize = qBound(8.0, 16.0 * 72.0 / metrics->logicalDpi(), 72.0);
    QVERIFY(qAbs(font("body").variableAxisValue(opticalTag) - expectedOpticalSize) < 0.001);
    for (const char *name : {"body", "title", "pointText", "staticText", "input", "area"}) {
        QCOMPARE(font(name).hintingPreference(), QFont::PreferFullHinting);
        // Qt Quick Text, TextInput and TextEdit all expose NativeRendering = 1.
        QCOMPARE(item(name)->property("renderType").toInt(), 1);
    }

    // The real button content must follow an explicit design weight, rather
    // than reverting to its old unconditional Medium override.
    std::function<QObject *(QObject *,const QString &)> findText = [&](QObject *object, const QString &type) -> QObject * {
        if (object->inherits(type.toLatin1())) return object;
        for (auto *child : object->children()) if (auto *found = findText(child,type)) return found;
        return nullptr;
    };
    auto *buttonText = findText(item("button"), "QQuickText");
    QVERIFY(buttonText);
    QTRY_COMPARE(buttonText->property("font").value<QFont>().variableAxisValue(weightTag), 700.0f);
    QCOMPARE(buttonText->property("font").value<QFont>().hintingPreference(), QFont::PreferFullHinting);
    QCOMPARE(buttonText->property("renderType").toInt(), 1);
    auto *tooltipText = item("tooltip")->property("contentItem").value<QObject *>();
    QVERIFY(tooltipText);
    QCOMPARE(tooltipText->property("font").value<QFont>().hintingPreference(), QFont::PreferFullHinting);
    QCOMPARE(tooltipText->property("renderType").toInt(), 1);
    auto *discardPrompt = item("discardChangesPrompt");
    QVERIFY(discardPrompt);
    auto *discardHeader = discardPrompt->property("header").value<QObject *>();
    QVERIFY(discardHeader);
    QTRY_COMPARE(discardHeader->property("font").value<QFont>().variableAxisValue(weightTag), 700.0f);
    QCOMPARE(discardHeader->property("font").value<QFont>().hintingPreference(), QFont::PreferFullHinting);
    QCOMPARE(discardHeader->property("renderType").toInt(), 1);
    QPointer<QObject> retainedBody = item("body"), retainedSettings = item("fontSettings");

    auto *manualToggle = item("fontManualMode");
    QVERIFY(!manualToggle->property("checked").toBool());
    QVERIFY(manualToggle->setProperty("checked", true));
    QVERIFY(QMetaObject::invokeMethod(manualToggle, "toggled"));
    QVERIFY(!manager.previewAutomatic());
    QVERIFY(manager.automatic()); // preview mode does not mutate the active UI
    const auto axisBinding = [](QObject *target) -> QObject * {
        for (auto *child : target->children())
            if (child->property("target").value<QObject *>() == target
                && child->property("property").toString() == QStringLiteral("font.variableAxes")
                && child->metaObject()->indexOfMethod("refreshAxes()") >= 0) return child;
        return nullptr;
    };
    auto *previewLine = qobject_cast<VariableFontPreview *>(item("fontPreviewLine_0"));
    QVERIFY(previewLine);
    QPointer<VariableFontPreview> retainedPreview = previewLine;
    auto *previewBinding = axisBinding(previewLine);
    auto *bodyBinding = axisBinding(item("body"));
    QVERIFY(previewBinding && bodyBinding);
    QTRY_VERIFY(!previewBinding->property("refreshQueued").toBool());
    const auto beforePreviewFont = previewLine->font();
    auto observedPreviewFonts = std::make_shared<QList<QFont>>();
    const auto observePreview = QObject::connect(previewLine, &VariableFontPreview::fontChanged,
        root.data(), [observedPreviewFonts, previewLine] { observedPreviewFonts->append(previewLine->font()); });
    QVERIFY(manager.setPreviewAxis("wght", 575));
    QVERIFY(manager.setPreviewAxis("HGHT", 800));
    QVERIFY(manager.setPreviewAxis("wdth", 109.75));
    QCOMPARE(previewLine->font(), beforePreviewFont); // coalesce the input turn
    // Execute the production Qt.callLater callback directly to isolate the
    // hand-off it owns: publishing the complete map must not add a second timer.
    QVERIFY(QMetaObject::invokeMethod(previewBinding, "refreshAxes"));
    QCOMPARE(previewLine->font().variableAxisValue(weightTag), 575.0f);
    QCOMPARE(previewLine->font().variableAxisValue(heightTag), 800.0f);
    QCOMPARE(previewLine->font().variableAxisValue(QFont::Tag("wdth")), 109.75f);
    QCOMPARE(observedPreviewFonts->size(), 1);
    QCOMPARE(observedPreviewFonts->first(), previewLine->font());
    QCOMPARE(retainedPreview.data(), previewLine);
    QObject::disconnect(observePreview);
    QCOMPARE(font("body").variableAxisValue(weightTag), 400.0f);
    QVERIFY(manager.applyPreview());
    // Retain the ordinary text binding's existing delayed commit behavior.
    QVERIFY(QMetaObject::invokeMethod(bodyBinding, "refreshAxes"));
    QCOMPARE(font("body").variableAxisValue(weightTag), 400.0f);
    QTRY_COMPARE(font("body").variableAxisValue(weightTag), 575.0f);
    // Manual wght is the user's exact override; automatic mode retains roles.
    QTRY_COMPARE(font("title").variableAxisValue(weightTag), 575.0f);
    QTRY_COMPARE(font("input").variableAxisValue(heightTag), 800.0f);
    QTRY_COMPARE(font("area").variableAxisValue(heightTag), 800.0f);
    QTRY_COMPARE(font("tooltip").variableAxisValue(heightTag), 800.0f);

    QTRY_VERIFY(item("fontAxisInput_wght"));
    auto *weightInput = qobject_cast<QQuickItem *>(item("fontAxisInput_wght"));
    QVERIFY(weightInput);
    // Displaying four decimals is not a request to round a stored coordinate.
    QVERIFY(manager.setPreviewAxis("wght", 623.123456));
    QTRY_COMPARE(weightInput->property("text").toString(), QStringLiteral("623.1235"));
    weightInput->forceActiveFocus();
    QTRY_VERIFY(weightInput->hasActiveFocus());
    qobject_cast<QQuickItem *>(item("input"))->forceActiveFocus();
    QTRY_VERIFY(!weightInput->hasActiveFocus());
    QCOMPARE(manager.previewValues().value("wght").toDouble(), 623.123456);
    weightInput->forceActiveFocus();
    QTRY_VERIFY(weightInput->hasActiveFocus());
    QVERIFY(weightInput->setProperty("text", "624.125"));
    // Deliver TextInput's user-edit signal, as a real key edit does; setting a
    // property alone intentionally does not mean the user changed the value.
    QVERIFY(QMetaObject::invokeMethod(weightInput, "textEdited"));
    QVERIFY(QMetaObject::invokeMethod(weightInput, "editingFinished"));
    QCOMPARE(manager.previewValues().value("wght").toDouble(), 624.125);
    QVERIFY(weightInput->setProperty("text", "625.75"));
    QVERIFY(QMetaObject::invokeMethod(weightInput, "textEdited"));
    QVERIFY(manualToggle->setProperty("checked", false));
    QVERIFY(QMetaObject::invokeMethod(manualToggle, "toggled"));
    // Finishing a hidden manual input must not turn automatic mode back off.
    QVERIFY(QMetaObject::invokeMethod(weightInput, "editingFinished"));
    QVERIFY(manager.previewAutomatic());
    QCOMPARE(manager.previewValues().value("wght").toDouble(), 624.125);
    QTRY_COMPARE(font("fontPreviewLine_0").variableAxisValue(weightTag), 600.0f);
    QCOMPARE(font("body").variableAxisValue(weightTag), 575.0f);
    QVERIFY(manager.applyPreview());
    QTRY_COMPARE(font("body").variableAxisValue(weightTag), 400.0f);
    QTRY_COMPARE(font("title").variableAxisValue(weightTag), 600.0f);
    QTRY_COMPARE(font("body").variableAxisValue(heightTag), 250.0f);
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures + "/automation-other.ttf")));
    QVERIFY(manager.applyPreview());
    QTRY_COMPARE(font("body").family(), QStringLiteral("Swirl Other Probe"));
    QTRY_COMPARE(font("body").variableAxisValue(heightTag), 500.0f);
    QTRY_COMPARE(font("body").variableAxisValue(weightTag), 500.0f);
    QCOMPARE(retainedBody.data(), item("body"));
    QCOMPARE(retainedSettings.data(), item("fontSettings"));
    QVERIFY(font("staticText").variableAxisTags().isEmpty());

    // Position/opacity/theme animation must not cause axis or font churn. Font
    // size animation is intentionally excluded: its optical size must update.
    QCoreApplication::processEvents();
    const auto fontProperty = item("body")->metaObject()->property(item("body")->metaObject()->indexOfProperty("font"));
    QSignalSpy fontChanges(item("body"), fontProperty.notifySignal());
    QVERIFY(fontChanges.isValid());
    for (int i = 0; i < 30; ++i) {
        item("body")->setProperty("x", i);
        item("body")->setProperty("opacity", 1.0 - i / 100.0);
        QCoreApplication::processEvents();
    }
    QCOMPARE(fontChanges.count(), 0);
    const auto before = font("body");
    auto *theme = engine.singletonInstance<QObject *>(qmlTypeId("SwirlQuick", 1, 0, "Theme"));
    QVERIFY(theme);
    QVERIFY(theme->setProperty("mode", "Dark"));
    QCoreApplication::processEvents();
    QCOMPARE(font("body"), before);
    QCOMPARE(fontChanges.count(), 0);
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures+"/automation-width.ttf")));
    QVERIFY(manager.applyPreview());
    QTRY_COMPARE(font("widthText").family(),QStringLiteral("Swirl Width Probe"));
    // Family selection precedes the queued axis binding. The previous Other
    // fixture's wdth=95 also satisfies <100, so it cannot prove this face ready.
    // Await the new fixture's complete two-axis profile before taking a snapshot.
    QTRY_COMPARE(font("widthText").variableAxisTags().size(),2);
    QTRY_COMPARE(font("widthText").variableAxisValue(QFont::Tag("wght")),400.f);
    QTRY_VERIFY(font("widthText").variableAxisValue(QFont::Tag("wdth"))<100.f);
    QTest::qWait(100); // let the parent layout publish the natural preferred width
    const auto fittedFont=font("widthText");
    const auto natural=manager.fittedText(fittedFont,"AAAAAAAA",96,1.5,"button",1000,100).value("naturalWidth").toDouble();
    QTRY_VERIFY(qAbs(QQmlProperty(item("widthText"),"Layout.preferredWidth",qmlContext(item("widthText"))).read().toDouble()-natural)<.001);
    const auto widthProperty=item("widthText")->metaObject()->property(item("widthText")->metaObject()->indexOfProperty("font"));
    QSignalSpy widthChanges(item("widthText"),widthProperty.notifySignal());
    QTest::qWait(100);widthChanges.clear();
    for(int i=0;i<20;++i){item("widthHost")->setProperty("width",96.+(i%2)*.2);QCoreApplication::processEvents();}
    QTest::qWait(100);
    if(font("widthText")!=fittedFont){
        const auto describe=[](const QFont &value){
            QJsonObject axes;for(const auto tag:value.variableAxisTags())axes[QString::fromLatin1(tag.toString())]=value.variableAxisValue(tag);
            return QJsonObject{{"font",value.toString()},{"axes",axes},{"resolveMask",QString::number(value.resolveMask())}};
        };
        qInfo()<<"Width jitter font mismatch"<<QJsonObject{{"before",describe(fittedFont)},{"after",describe(font("widthText"))},{"hostWidth",item("widthHost")->property("width").toDouble()},{"textWidth",item("widthText")->property("width").toDouble()},{"natural",natural},{"fontChanges",widthChanges.count()}};
    }
    QCOMPARE(font("widthText"),fittedFont);QCOMPARE(widthChanges.count(),0);
    item("widthHost")->setProperty("width",natural+10);
    QTRY_COMPARE(font("widthText").variableAxisValue(QFont::Tag("wdth")),100.f);
    const auto privateFont=qEnvironmentVariable("SWIRL_TEST_TTC");
    const auto evidence=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
    if(!privateFont.isEmpty()&&!evidence.isEmpty()){
        const QPointer<QObject> retainedWidth=item("widthText");
        QVERIFY(manager.importFont(QUrl::fromLocalFile(privateFont)));QVERIFY(manager.applyPreview());
        item("widthText")->setProperty("text",QStringLiteral("应用到整个界面 Swirl 0123456789"));
        item("widthHost")->setProperty("width",600);
        QTRY_COMPARE(font("widthText").family(),QStringLiteral("PingFang UI SC"));
        QTRY_COMPARE(font("widthText").variableAxisValue(QFont::Tag("wdth")),100.f);
        const auto privateNatural=manager.fittedText(font("widthText"),item("widthText")->property("text").toString(),96,window->devicePixelRatio(),"button",600,100).value("naturalWidth").toDouble();
        QTest::qWait(100);QVERIFY(window->grabWindow().save(evidence+"/width-layout-natural.png"));
        item("widthHost")->setProperty("width",privateNatural*.95);
        QTRY_VERIFY(font("widthText").variableAxisValue(QFont::Tag("wdth"))<100.f);
        QTest::qWait(100);QVERIFY(window->grabWindow().save(evidence+"/width-layout-fitted.png"));
        const auto actual=font("widthText");QFont uncompressed=actual;uncompressed.setVariableAxis(QFont::Tag("wdth"),100.f);
        QVERIFY(retainedWidth&&retainedWidth.data()==item("widthText"));
        const auto text=item("widthText")->property("text").toString();
        QVERIFY(QFontMetricsF(actual).horizontalAdvance(text)<QFontMetricsF(uncompressed).horizontalAdvance(text));
        QFile report(evidence+"/private-width-layout.json");QVERIFY(report.open(QIODevice::WriteOnly));
        report.write(QJsonDocument(QJsonObject{{"dpr",window->devicePixelRatio()},{"naturalAdvance",privateNatural},{"availableWidth",item("widthText")->property("width").toDouble()},{"actualWdth",actual.variableAxisValue(QFont::Tag("wdth"))},{"pixelSize",actual.pixelSize()},{"sameObject",retainedWidth.data()==item("widthText")}}).toJson());
    }
    QVERIFY2(warnings.isEmpty(), qPrintable(warnings.join('\n')));
}

void FontTests::qmlWidthControls()
{
    const auto fixtures = qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if (fixtures.isEmpty()) QSKIP("Original public width fixtures required");
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, directory.path());
    QSettings().clear();
    FontManager manager(nullptr, directory.filePath("fonts"));
    QVERIFY(manager.importFont(QUrl::fromLocalFile(fixtures + "/automation-width.ttf")));
    QVERIFY(manager.applyPreview());

    registerFontQmlTypes();
    QStringList warnings;
    QScopedPointer<QObject> serviceObject;
    QQmlEngine engine;
    auto importPaths = engine.importPathList();
    importPaths.removeAll(QCoreApplication::applicationDirPath());
    engine.setImportPathList(importPaths);
    QObject::connect(&engine, &QQmlEngine::warnings, &engine, [&](const QList<QQmlError> &errors) {
        for (const auto &error : errors) warnings.append(error.toString());
    });
    engine.addImageProvider(QStringLiteral("swirl"), new FontQmlIconProvider);
    engine.rootContext()->setContextProperty("fontManager", &manager);
    engine.rootContext()->setContextProperty("gpuEffectsSupported", false);
    engine.rootContext()->setContextProperty("previewCaptureMode", false);
    QQmlComponent services(&engine);
    services.setData(R"(
import QtQuick
QtObject {
    property string sidebarPage: "overview"
    property bool proxyOn: false
    property int measurementTick: 0
    property bool alwaysShowScrollbars: false
    property bool complexMotion: false
    property bool systemReducedMotion: false
    function zh(value) { return value }
    function fingerprint(item) { return "" }
    function push(item, window) {}
    function pop(item) {}
    function setTransitioning(active) {}
}
)", QUrl("file:width-test-services.qml"));
    serviceObject.reset(services.create());
    QVERIFY2(serviceObject, qPrintable(services.errorString()));
    for (const char *name : {"AppState", "dismissals", "motionPolicy"})
        engine.rootContext()->setContextProperty(QString::fromLatin1(name), serviceObject.data());
    QQmlComponent component(&engine);
    component.setData(R"(
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "controls" as Controls
import "components" as Components
ApplicationWindow {
    id: window
    visible: true; width: 800; height: 800; title: "AAAAAAAA"
    Column {
        Controls.SwirlComboBox { objectName: "widthCombo"; width: 300; model: ["AAAAAAAA", "AAAA"]; font.pixelSize: 20 }
        Components.SwirlNavigationItem { objectName: "widthNavigation"; width: 300; title: "AAAAAAAA" }
        Components.SwirlListRow { objectName: "widthList"; width: 300; title: "AAAAAAAA" }
        Components.SwirlMetricCard { objectName: "widthCard"; width: 300; label: "AAAAAAAA"; value: "AAAA" }
        Controls.SwirlDataTable { objectName: "widthTable"; width: 300; height: 50; columns: [{key:"name",label:"AAAAAAAA",w:100}]; rows: [] }
        Components.SwirlWindowTitleBar { objectName: "widthWindowTitle"; width: 300; targetWindow: window }
        RowLayout { objectName: "paddedHost"; width: 300
            Controls.SwirlText { objectName: "paddedLabel"; textRole: "label"; text: "AAAAAAAA"; font.pixelSize: 20
                leftPadding: 12; rightPadding: 8; Layout.fillWidth: true; elide: Text.ElideRight }
        }
        RowLayout { width: 50
            Controls.SwirlText { objectName: "bodyExcluded"; text: "AAAAAAAA"; Layout.fillWidth: true; elide: Text.ElideRight }
            Controls.SwirlText { objectName: "dataExcluded"; textRole: "data"; text: "AAAAAAAA"; Layout.fillWidth: true; elide: Text.ElideRight }
        }
        RowLayout { width: 50
            Controls.SwirlText { objectName: "richExcluded"; textRole: "label"; text: "<b>AAAAAAAA</b>"; Layout.fillWidth: true; elide: Text.ElideRight }
            Controls.SwirlText { objectName: "multilineExcluded"; textRole: "label"; text: "AAAA\nAAAA"; Layout.fillWidth: true; elide: Text.ElideRight }
            Controls.SwirlText { objectName: "designMetricsExcluded"; textRole: "label"; text: "AAAAAAAA"; renderType: Text.QtRendering; Layout.fillWidth: true; elide: Text.ElideRight }
        }
        Controls.SwirlText { objectName: "unconstrainedExcluded"; textRole: "label"; text: "AAAAAAAA"; elide: Text.ElideRight }
        Controls.SwirlTextField { objectName: "inputExcluded"; width: 40; text: "AAAAAAAA" }
    }
    Controls.SwirlDialog { objectName: "widthDialog"; title: "AAAAAAAA"; guardChanges: false
        contentItem: Controls.SwirlText { text: "A"; wrapMode: Text.Wrap }
    }
}
)", QUrl::fromLocalFile(QStringLiteral(SWIRL_QML_SOURCE_DIR "/width-controls-fixture.qml")));
    QScopedPointer<QObject> root(component.create());
    QVERIFY2(root, qPrintable(component.errorString()));
    auto *window = qobject_cast<QQuickWindow *>(root.data());
    QVERIFY(window && window->screen());
    qInfo().noquote() << "W1 width QML environment" << QJsonDocument(QJsonObject{
        {"platform", QGuiApplication::platformName()},
        {"windowDpr", window->devicePixelRatio()},
        {"logicalDpi", window->screen()->logicalDotsPerInchY()},
        {"QT_SCALE_FACTOR", qEnvironmentVariable("QT_SCALE_FACTOR")},
        {"physicalScreenVerified", false}}).toJson(QJsonDocument::Compact);
    auto object = [&](const char *name) { return root->findChild<QObject *>(QString::fromLatin1(name)); };
    std::function<QQuickItem *(QQuickItem *)> firstText = [&](QQuickItem *item) -> QQuickItem * {
        if (!item) return nullptr;
        if (item->inherits("QQuickText") && item->property("text").toString() == QStringLiteral("AAAAAAAA")) return item;
        for (auto *child : item->childItems()) if (auto *found = firstText(child)) return found;
        return nullptr;
    };
    const auto widthTag = QFont::Tag("wdth");
    const auto font = [](QObject *item) { return item->property("font").value<QFont>(); };
    const auto natural = [&](QObject *item) {
        return manager.fittedText(font(item), item->property("text").toString(), 96, 1,
            item->property("textRole").toString(), 10000, 100).value("naturalWidth").toDouble();
    };
    // Exercise the real shared content items. The owner width changes while its
    // icon/padding/layout contract stays intact; no test-only width solver exists.
    for (const char *name : {"widthCombo", "widthNavigation", "widthList", "widthCard", "widthTable", "widthWindowTitle"}) {
        auto *owner = object(name);
        QVERIFY2(owner, name);
        auto *text = firstText(qobject_cast<QQuickItem *>(owner));
        QVERIFY2(text, name);
        QTRY_VERIFY(text->property("widthFitting").toBool());
        QTRY_COMPARE(font(text).variableAxisValue(widthTag), 100.f);
        const auto defaultFont = font(text);
        const double ownerImplicitWidth = owner->property("implicitWidth").toDouble();
        const double preferred = natural(text);
        QVERIFY(preferred > 30);
        const double extra = owner->property("width").toDouble() - text->width()
            + text->property("leftPadding").toDouble() + text->property("rightPadding").toDouble();
        QVERIFY(owner->setProperty("width", preferred + extra - 8));
        QTRY_VERIFY(font(text).variableAxisValue(widthTag) < 100.f);
        QCOMPARE(font(text).pixelSize(), defaultFont.pixelSize());
        QCOMPARE(font(text).weight(), defaultFont.weight());
        QCOMPARE(font(text).hintingPreference(), defaultFont.hintingPreference());
        QTRY_VERIFY(qAbs(owner->property("implicitWidth").toDouble() - ownerImplicitWidth) < .001);
        QVERIFY(owner->setProperty("width", preferred + extra + 10));
        QTRY_COMPARE(font(text).variableAxisValue(widthTag), 100.f);
    }
    auto *padded = object("paddedLabel");
    auto *paddedHost = object("paddedHost");
    QVERIFY(padded && paddedHost);
    const double paddedNatural = natural(padded);
    // Total width fits, but the actual text area does not: ignoring padding
    // would incorrectly retain the default coordinate in this regression.
    QVERIFY(paddedHost->setProperty("width", paddedNatural + 12));
    QTRY_VERIFY(font(padded).variableAxisValue(widthTag) < 100.f);
    QTRY_VERIFY(qAbs(QQmlProperty(padded, "Layout.preferredWidth", qmlContext(padded)).read().toDouble()
        - paddedNatural - 20) < .001);
    QVERIFY(padded->setProperty("leftPadding", 0));
    QVERIFY(padded->setProperty("rightPadding", 0));
    QTRY_COMPARE(font(padded).variableAxisValue(widthTag), 100.f);
    for (const char *name : {"bodyExcluded", "dataExcluded", "richExcluded", "multilineExcluded", "designMetricsExcluded", "unconstrainedExcluded"}) {
        QVERIFY2(object(name), name);
        QVERIFY(!object(name)->property("widthFitting").toBool());
        QTRY_COMPARE(font(object(name)).variableAxisValue(widthTag), 100.f);
    }
    QTRY_COMPARE(font(object("inputExcluded")).variableAxisValue(widthTag), 100.f);

    auto *combo = object("widthCombo");
    auto *comboText = firstText(qobject_cast<QQuickItem *>(combo));
    QVERIFY(combo && comboText);
    QVERIFY(combo->setProperty("width", natural(comboText) + combo->property("leftPadding").toDouble()
        + combo->property("rightPadding").toDouble() - 8));
    QTRY_VERIFY(font(comboText).variableAxisValue(widthTag) < 100.f);
    const auto heldFont = font(comboText);
    const double heldWidth = combo->property("width").toDouble();
    const auto fontProperty = comboText->metaObject()->property(comboText->metaObject()->indexOfProperty("font"));
    QTest::qWait(100);
    QSignalSpy changes(comboText, fontProperty.notifySignal());
    for (int i = 0; i < 24; ++i) {
        QVERIFY(combo->setProperty("width", heldWidth + (i % 2) * .2));
        QCoreApplication::processEvents();
    }
    QTest::qWait(100);
    QCOMPARE(font(comboText), heldFont);
    QCOMPARE(changes.count(), 0);
    QVERIFY(manager.setPreviewAxis("wdth", 107.25));
    QVERIFY(manager.applyPreview());
    QTRY_COMPARE(font(comboText).variableAxisValue(widthTag), 107.25f);
    QVERIFY(combo->setProperty("width", 30));
    QTRY_COMPARE(font(comboText).variableAxisValue(widthTag), 107.25f);
    manager.setPreviewAutomatic(true);
    QVERIFY(manager.applyPreview());
    QTRY_VERIFY(font(comboText).variableAxisValue(widthTag) <= 100.f);

    auto *dialog = object("widthDialog");
    QVERIFY(dialog);
    auto *header = firstText(qobject_cast<QQuickItem *>(dialog->property("header").value<QObject *>()));
    QVERIFY(header);
    QTRY_VERIFY(header->property("widthFitting").toBool());
    const double dialogNatural = natural(header);
    QVERIFY(dialog->setProperty("width", dialogNatural + dialog->property("leftPadding").toDouble()
        + dialog->property("rightPadding").toDouble() - 8));
    QPointer<QQuickItem> retainedHeader(header);
    for (int i = 0; i < 6; ++i) {
        QVERIFY(QMetaObject::invokeMethod(dialog, "open"));
        QTRY_VERIFY(dialog->property("opened").toBool());
        QTRY_VERIFY(font(header).variableAxisValue(widthTag) < 100.f);
        QVERIFY(QMetaObject::invokeMethod(dialog, "close"));
        QTRY_VERIFY(!dialog->property("visible").toBool());
        QCOMPARE(retainedHeader.data(), header);
    }
    // Reuse these same live objects through static fallback and re-selection.
    const auto widthFamily = manager.currentFamily();
    for (int i = 0; i < 4; ++i) {
        QVERIFY(manager.selectFamily(manager.defaultFamily()));
        QTRY_VERIFY(!font(comboText).isVariableAxisSet(widthTag));
        QVERIFY(manager.selectFamily(widthFamily));
        QTRY_VERIFY(font(comboText).isVariableAxisSet(widthTag));
        QVERIFY(manager.automatic());
    }
    QVERIFY2(warnings.isEmpty(), qPrintable(warnings.join('\n')));
}

void FontTests::fontDisplayContextLifetime()
{
    registerFontQmlTypes();
    for (int pass = 0; pass < 12; ++pass) {
        auto window = std::make_unique<QQuickWindow>();
        auto *first = qobject_cast<FontDisplayContext *>(qmlAttachedPropertiesObject<FontDisplayContext>(window.get(), true));
        auto *second = qobject_cast<FontDisplayContext *>(qmlAttachedPropertiesObject<FontDisplayContext>(window.get(), true));
        QVERIFY(first);
        QCOMPARE(first, second);
        QCOMPARE(first->devicePixelRatio(), window->devicePixelRatio());
        QCOMPARE(first->logicalDpi(), window->screen()->logicalDotsPerInchY());
        QSignalSpy changes(first, &FontDisplayContext::metricsChanged);
        QEvent unchangedDpr(QEvent::DevicePixelRatioChange);
        QCoreApplication::sendEvent(window.get(), &unchangedDpr);
        QCOMPARE(changes.count(), 0);
        QPointer<FontDisplayContext> observer = first;
        window.reset();
        QVERIFY(observer.isNull());
    }
}

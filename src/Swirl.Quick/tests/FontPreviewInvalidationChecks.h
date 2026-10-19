#pragma once

#include "app/VariableFontPreview.h"
#include <QFontDatabase>
#include <QGuiApplication>
#include <QPointer>
#include <QScreen>
#include <QSignalSpy>
#include <QSGRendererInterface>
#include <QTextLayout>
#include <QTextOption>
#include <QtMath>

namespace FontPreviewInvalidationTest {
struct RegisteredFont {
    int id = -1;
    ~RegisteredFont() { if (id >= 0) QFontDatabase::removeApplicationFont(id); }
};

class PreviewProbe final : public VariableFontPreview {
public:
    using VariableFontPreview::VariableFontPreview;
    void simulateDprNotification()
    {
        // Exercise dispatch without changing the actual window/device ratio.
        // This is deliberately not presented as a Windows DPI acceptance test.
        itemChange(ItemDevicePixelRatioHasChanged,
                   ItemChangeData(window() ? window()->effectiveDevicePixelRatio() : 1.0));
    }
};

inline qreal layoutHeight(const QString &text, const QFont &font, qreal width,
                  const QPaintDevice *device = nullptr)
{
    QTextLayout layout(text, font, device);
    QTextOption option;
    option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);
    layout.setTextOption(option);
    layout.beginLayout();
    qreal height = 0;
    while (true) {
        auto line = layout.createLine();
        if (!line.isValid()) break;
        line.setLineWidth(width);
        height += line.height();
    }
    layout.endLayout();
    return qCeil(height);
}
} // namespace FontPreviewInvalidationTest

void FontTests::previewFontResourcesInvalidateRaster()
{
    using namespace FontPreviewInvalidationTest;
    const auto fixtures = qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if (fixtures.isEmpty()) QSKIP("Generated original multi-axis fonts not supplied");
    const QString family = QStringLiteral("Swirl Automation Probe");
    QVERIFY2(!QFontDatabase::families().contains(family), "A prior test leaked the probe registration");
    RegisteredFont registration;
    QQuickWindow window;
    window.resize(400, 180);
    window.setColor(Qt::white);
    auto *preview = new PreviewProbe(window.contentItem());
    preview->setPosition(QPointF(20, 20));
    preview->setSize(QSizeF(350, 120));
    preview->setText(QStringLiteral("AAA"));
    QFont request;
    request.setFamilies({family, QFontDatabase::systemFont(QFontDatabase::GeneralFont).family()});
    request.setPixelSize(64);
    request.setWeight(QFont::Normal);
    request.setHintingPreference(QFont::PreferFullHinting);
    preview->setFont(request);
    preview->setMeasureRaster(true);
    QSignalSpy rasters(preview, &VariableFontPreview::rasterMeasured);
    QSignalSpy fontChanges(preview, &VariableFontPreview::fontChanged);
    window.show();
    QVERIFY(QTest::qWaitForWindowExposed(&window));
    QTRY_VERIFY(rasters.count() > 0);
    QTest::qWait(60);
    const QImage before = window.grabWindow();
    QVERIFY(!before.isNull());
    rasters.clear();
    for (int i = 0; i < 5; ++i) { window.update(); QTest::qWait(20); }
    QCOMPARE(rasters.count(), 0);

    // The QFont values remain identical. Only the real database registration
    // changes from a fallback face to the new original test face.
    registration.id = QFontDatabase::addApplicationFont(fixtures + "/automation.ttf");
    QVERIFY(registration.id >= 0);
    QTRY_VERIFY(rasters.count() > 0);
    QCOMPARE(preview->font(), request);
    QCOMPARE(fontChanges.count(), 0);
    const QImage registered = window.grabWindow();
    QVERIFY(!registered.isNull());
    QVERIFY(before != registered);

    rasters.clear();
    QVERIFY(QFontDatabase::removeApplicationFont(registration.id));
    registration.id = -1;
    QVERIFY(!QFontDatabase::families().contains(family));
    QTRY_VERIFY(rasters.count() > 0);
    QCOMPARE(preview->font(), request);
    QCOMPARE(fontChanges.count(), 0);
    QVERIFY(QRawFont::fromFont(preview->font()).familyName()!=family);
    QImage removed;
    // rasterMeasured is emitted on the GUI thread before the updated texture
    // has necessarily reached the render thread. Await the actual new render,
    // retaining the exact image inequality and the existing test timeout.
    QTRY_VERIFY(!(removed=window.grabWindow()).isNull()&&removed!=registered);

    QTest::qWait(60);
    rasters.clear();
    // Several real resource notifications in one event-loop turn coalesce into
    // one raster. No update is dropped from an interactive frame sequence.
    registration.id = QFontDatabase::addApplicationFont(fixtures + "/automation-other.ttf");
    QVERIFY(registration.id >= 0);
    QVERIFY(QFontDatabase::removeApplicationFont(registration.id));
    registration.id = -1;
    QTRY_COMPARE(rasters.count(), 1);
    QTest::qWait(100);
    QCOMPARE(rasters.count(), 1);
    QCOMPARE(fontChanges.count(), 0);

    QPointer<PreviewProbe> destroyed = preview;
    delete preview;
    QVERIFY(destroyed.isNull());
    // Signal connections have a QObject context and do not retain dead items.
    registration.id = QFontDatabase::addApplicationFont(fixtures + "/automation.ttf");
    QVERIFY(registration.id >= 0);
}

void FontTests::previewWindowMetricsAndIdleStability()
{
    using namespace FontPreviewInvalidationTest;
    const auto fixtures = qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if (fixtures.isEmpty()) QSKIP("Generated original multi-axis fonts not supplied");
    RegisteredFont registration;
    registration.id = QFontDatabase::addApplicationFont(fixtures + "/automation.ttf");
    QVERIFY(registration.id >= 0);
    QQuickWindow window;
    window.resize(400, 180);
    window.setColor(Qt::white);
    auto *preview = new PreviewProbe(window.contentItem());
    preview->setPosition(QPointF(20, 20));
    preview->setSize(QSizeF(350, 120));
    preview->setText(QStringLiteral("AAA AAA AAA"));
    preview->setMeasureRaster(true);
    QSignalSpy rasters(preview, &VariableFontPreview::rasterMeasured);
    window.show();
    QVERIFY(QTest::qWaitForWindowExposed(&window));
    QVERIFY(window.screen());
    QImage device(1, 1, QImage::Format_ARGB32_Premultiplied);
    device.setDotsPerMeterX(qRound(window.screen()->logicalDotsPerInchX() / 0.0254));
    device.setDotsPerMeterY(qRound(window.screen()->logicalDotsPerInchY() / 0.0254));
    for (const bool pointSize : {false, true}) {
        QFont request(QStringLiteral("Swirl Automation Probe"));
        request.setWeight(QFont::Normal);
        request.setHintingPreference(QFont::PreferFullHinting);
        if (pointSize) request.setPointSizeF(18);
        else request.setPixelSize(24);
        rasters.clear();
        preview->setFont(request);
        QTRY_VERIFY(rasters.count() > 0);
        QCOMPARE(preview->font(), request);
        QCOMPARE(preview->implicitHeight(), layoutHeight(preview->text(), request, preview->width(), &device));
        // On the original single-screen metrics, specifying the matching paint
        // device must preserve the old QTextLayout line-height calculation.
        if (window.screen() == QGuiApplication::primaryScreen())
            QCOMPARE(preview->implicitHeight(), layoutHeight(preview->text(), request, preview->width()));
        const QImage before = window.grabWindow();
        QVERIFY(!before.isNull());
        QTest::qWait(60);
        rasters.clear();
        preview->setFont(request); // idempotent source assignment
        window.screenChanged(window.screen());
        window.screen()->logicalDotsPerInchChanged(window.screen()->logicalDotsPerInch());
        for (int i = 0; i < 5; ++i) { window.update(); QTest::qWait(20); }
        QCOMPARE(rasters.count(), 0);

        preview->simulateDprNotification();
        QTRY_COMPARE(rasters.count(), 1);
        const QImage after = window.grabWindow();
        QCOMPARE(after, before); // same actual DPR: origin and raster stay exact
        QCOMPARE(preview->font(), request);
        QTest::qWait(60);
        QCOMPARE(rasters.count(), 1);
    }
    qInfo("Preview checks used real font registration and same-screen metrics; "
          "the DPR notification was simulated, not a physical display/DPI switch.");
}

void FontTests::previewRepeatedAxesReuseResources()
{
    using namespace FontPreviewInvalidationTest;
    const auto fixtures = qEnvironmentVariable("SWIRL_FONT_METADATA_FIXTURES");
    if (fixtures.isEmpty()) QSKIP("Generated original multi-axis fonts not supplied");
    RegisteredFont registration;
    registration.id = QFontDatabase::addApplicationFont(fixtures + "/automation.ttf");
    QVERIFY(registration.id >= 0);
    const auto request = [](float weight) {
        QFont font(QStringLiteral("Swirl Automation Probe"));
        font.setPixelSize(64);
        font.setWeight(QFont::Normal);
        font.setHintingPreference(QFont::PreferFullHinting);
        font.setVariableAxis(QFont::Tag("wght"), weight);
        return font;
    };

    // Isolate CPU storage from the scene graph's legitimate in-flight image
    // references. This original fixture changes real outlines, with fixed metrics.
    {
        PreviewProbe cpu;
        cpu.setWidth(350);
        cpu.setText(QStringLiteral("AAA"));
        cpu.setFont(request(200));
        cpu.ensurePolished();
        QVERIFY(!cpu.rasterPixelSize().isEmpty());
        const auto size = cpu.rasterPixelSize();
        const auto allocations = cpu.rasterAllocationCount();
        QVERIFY(allocations > 0);
        for (const float weight : {900.f, 100.f, 650.f, 250.f, 900.f, 200.f}) {
            cpu.setFont(request(weight));
            cpu.ensurePolished();
            QCOMPARE(cpu.rasterPixelSize(), size);
            QCOMPARE(cpu.rasterAllocationCount(), allocations);
        }
    }

    QQuickWindow window;
    window.resize(400, 180);
    window.setColor(Qt::white);
    window.show();
    QVERIFY(QTest::qWaitForWindowExposed(&window));
    const QImage empty = window.grabWindow();
    QVERIFY(!empty.isNull());
    auto *preview = new PreviewProbe(window.contentItem());
    preview->setPosition(QPointF(20, 20));
    preview->setSize(QSizeF(350, 120));
    preview->setText(QStringLiteral("AAA"));
    preview->setFont(request(200));
    preview->setMeasureRaster(true);
    QSignalSpy rasters(preview, &VariableFontPreview::rasterMeasured);
    QTRY_VERIFY(rasters.count() > 0);
    QImage initial;
    QTRY_VERIFY(!(initial = window.grabWindow()).isNull() && initial != empty);
    const auto size = preview->rasterPixelSize();
    const auto textureAllocations = preview->textureAllocationCount();
    QVERIFY(textureAllocations > 0);
    const bool rhiBackend = QSGRendererInterface::isApiRhiBased(window.rendererInterface()->graphicsApi());
    QImage previous = initial;
    for (const float weight : {900.f, 100.f, 650.f, 250.f, 900.f, 200.f}) {
        preview->setFont(request(weight));
        QImage next;
        QTRY_VERIFY(!(next = window.grabWindow()).isNull() && next != previous);
        QCOMPARE(preview->rasterPixelSize(), size);
        if (rhiBackend) QCOMPARE(preview->textureAllocationCount(), textureAllocations);
        previous = next;
    }
    QCOMPARE(previous, initial); // A -> B -> A must restore the exact original pixels.

    QTest::qWait(60);
    rasters.clear();
    for (const float weight : {900.f, 100.f, 650.f}) preview->setFont(request(weight));
    QCOMPARE(preview->font(), request(650)); // the final model value is immediate
    QTRY_COMPARE(rasters.count(), 1);
    QTest::qWait(60);
    QCOMPARE(rasters.count(), 1);
    preview->setFont(request(200));
    QTRY_COMPARE(window.grabWindow(), initial);
    QTest::qWait(60);
    rasters.clear();
    const auto idleTextures = preview->textureAllocationCount();
    for (int i = 0; i < 5; ++i) { window.update(); QTest::qWait(20); }
    QCOMPARE(rasters.count(), 0);
    QCOMPARE(preview->textureAllocationCount(), idleTextures);

    // Clear/collapse must remove the old visible texture, and restoring the same
    // source must recover the exact pixels without retaining a dead scene node.
    preview->setText(QString());
    QTRY_VERIFY(preview->rasterPixelSize().isEmpty());
    QTRY_COMPARE(window.grabWindow(), empty);
    preview->setText(QStringLiteral("AAA"));
    QTRY_COMPARE(window.grabWindow(), initial);
    preview->setWidth(0);
    QTRY_VERIFY(preview->rasterPixelSize().isEmpty());
    QTRY_COMPARE(window.grabWindow(), empty);
    preview->setWidth(350);
    QTRY_COMPARE(window.grabWindow(), initial);
    QPointer<PreviewProbe> removed = preview;
    delete preview;
    QVERIFY(removed.isNull());
    QTRY_COMPARE(window.grabWindow(), empty);
    qInfo() << "Preview resource regression backend" << window.rendererInterface()->graphicsApi()
            << "RHI texture-reuse assertion executed" << rhiBackend
            << "; CPU and image checks do not establish Windows private-byte or physical-refresh acceptance.";
}

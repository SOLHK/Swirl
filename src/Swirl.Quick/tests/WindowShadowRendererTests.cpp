#include "app/WindowShadowRenderer.h"

#include <QElapsedTimer>
#include <QTest>
#include <QtMath>
#include <array>
#include <cmath>
#include <limits>

namespace {
constexpr std::array<qreal, 5> dprs{1, 1.25, 1.5, 1.75, 2};

// Independent full-image reference for the accepted UI_0232 contour. Normalize
// its 2.5-power implicit function by the analytic gradient so corner coverage
// and shadow falloff use the same edge metric as the visible surfaces. Keep
// this reference independent of SwirlContour and of the cached slice renderer.
qreal referenceContourDistance(qreal x, qreal y, qreal width, qreal height, qreal radius) {
    radius = qBound<qreal>(0, radius, qMin(width, height) / 2);
    const qreal dx = std::abs(x - width / 2) - (width / 2 - radius);
    const qreal dy = std::abs(y - height / 2) - (height / 2 - radius);
    const qreal positiveX = qMax<qreal>(dx, 0), positiveY = qMax<qreal>(dy, 0);
    const qreal cornerNorm = std::pow(std::pow(positiveX, 2.5) + std::pow(positiveY, 2.5), 0.4);
    const qreal implicit = cornerNorm + qMin(qMax(dx, dy), qreal(0)) - radius;
    const qreal gradientLength = cornerNorm > 0.0001
        ? std::hypot(std::pow(positiveX / cornerNorm, 1.5), std::pow(positiveY / cornerNorm, 1.5)) : 1;
    return implicit / qMax(gradientLength, qreal(0.001));
}

QImage referenceShadowImage(QSize body, qreal radius, qreal dpr, bool active) {
    const int padding = qCeil(20 * dpr);
    const qreal sigma = 6.0 * dpr, offset = 2.5 * dpr;
    const qreal strength = active ? 0.22 : 0.14;
    QImage image(body + QSize(padding * 2, padding * 2), QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);
    for (int y = 0; y < image.height(); ++y) {
        auto *row = reinterpret_cast<QRgb *>(image.scanLine(y));
        const qreal localY = y + 0.5 - padding;
        int clearLeft = image.width(), clearRight = image.width();
        if (localY >= 0 && localY < body.height()) {
            const qreal dy = qMax<qreal>(0, qMax(radius - localY, localY - (body.height() - radius)));
            const qreal inset = radius - std::pow(qMax<qreal>(0,
                std::pow(radius, 2.5) - std::pow(dy, 2.5)), 0.4);
            clearLeft = padding + qMax(0, qCeil(inset + 0.5));
            clearRight = padding + body.width() - qMax(0, qCeil(inset + 0.5));
        }
        for (int x = 0; x < image.width(); ++x) {
            // A reversed clear run made the old loop jump backwards for tiny
            // bodies. Positive runs, and every normal-window reference, are unchanged.
            if (x == clearLeft && clearRight > clearLeft) { x = clearRight; if (x >= image.width()) break; }
            const qreal localX = x + 0.5 - padding;
            if (localX >= radius && localX < body.width() - radius
                && localY >= 0 && localY < body.height()) continue;
            if (localY >= radius && localY < body.height() - radius
                && localX >= 0 && localX < body.width()) continue;
            const qreal edge = referenceContourDistance(localX, localY, body.width(), body.height(), radius);
            if (edge <= -0.5) continue;
            const qreal t = qBound<qreal>(0, edge + 0.5, 1);
            const qreal coverage = t * t * (3 - 2 * t);
            const qreal distance = qMax<qreal>(0, referenceContourDistance(localX, localY - offset, body.width(), body.height(), radius));
            const int alpha = qRound(255 * strength * coverage * std::exp(-distance * distance / (2 * sigma * sigma)));
            row[x] = qRgba(0, 0, 0, alpha);
        }
    }
    return image;
}

QString pixelDifference(const QImage &expected, const QImage &actual) {
    if (expected.isNull() || actual.isNull()) return QStringLiteral("A valid shadow image is null");
    if (actual.size() != expected.size())
        return QStringLiteral("Image size differs: expected %1x%2, actual %3x%4")
            .arg(expected.width()).arg(expected.height()).arg(actual.width()).arg(actual.height());
    if (actual.format() != QImage::Format_ARGB32_Premultiplied)
        return QStringLiteral("Unexpected image format %1").arg(int(actual.format()));
    for (int y = 0; y < expected.height(); ++y) {
        const auto *before = reinterpret_cast<const QRgb *>(expected.constScanLine(y));
        const auto *after = reinterpret_cast<const QRgb *>(actual.constScanLine(y));
        for (int x = 0; x < expected.width(); ++x) {
            if (before[x] != after[x])
                return QStringLiteral("ARGB differs at (%1,%2): expected 0x%3, actual 0x%4")
                    .arg(x).arg(y).arg(before[x], 8, 16, QChar('0')).arg(after[x], 8, 16, QChar('0'));
        }
    }
    return {};
}

QSize physical(QSize logical, qreal dpr) {
    return {qRound(logical.width() * dpr), qRound(logical.height() * dpr)};
}

void addPixelColumns() {
    QTest::addColumn<QSize>("body");
    QTest::addColumn<qreal>("radius");
    QTest::addColumn<qreal>("dpr");
    QTest::addColumn<bool>("active");
}

void addPixelRow(const QString &name, QSize body, qreal radius, qreal dpr, bool active) {
    const QByteArray label = QStringLiteral("%1-dpr%2-%3")
        .arg(name).arg(dpr).arg(active ? QStringLiteral("active") : QStringLiteral("inactive")).toLatin1();
    QTest::newRow(label.constData()) << body << radius << dpr << active;
}
}

class WindowShadowRendererTests final : public QObject {
    Q_OBJECT
private slots:
    void windowSizesMatchContour_data() {
        addPixelColumns();
        const std::array<QSize, 10> logicalSizes{
            QSize(914, 672), QSize(1100, 860), QSize(1100, 760), QSize(760, 672),
            QSize(900, 672), QSize(914, 672), QSize(928, 672),
            QSize(942, 672), QSize(956, 678), QSize(970, 685)};
        for (qreal dpr : dprs) {
            for (bool active : {false, true}) {
                for (std::size_t index = 0; index < logicalSizes.size(); ++index)
                    addPixelRow(QStringLiteral("window-%1").arg(index), physical(logicalSizes[index], dpr), 14 * dpr, dpr, active);
                const QSize odd(qRound(1001 * dpr) | 1, qRound(733 * dpr) | 1);
                addPixelRow(QStringLiteral("odd-physical"), odd, 14 * dpr, dpr, active);
            }
        }
    }

    void windowSizesMatchContour() {
        QFETCH(QSize, body); QFETCH(qreal, radius); QFETCH(qreal, dpr); QFETCH(bool, active);
        const QString difference = compareContour(body, radius, dpr, active);
        QVERIFY2(difference.isEmpty(), qPrintable(difference));
    }

    void smallAndSliceBoundarySizesMatchContour_data() {
        addPixelColumns();
        for (qreal dpr : dprs) {
            const qreal radius = 14 * dpr;
            const int spanX = 2 * qCeil(radius) + 1;
            const int spanY = 2 * qCeil(radius + 2.5 * dpr) + 1;
            const std::array<QSize, 10> bodies{
                QSize(1, 1), QSize(2, 3), QSize(3, 2), QSize(5, 97), QSize(103, 5),
                QSize(spanX - 1, spanY), QSize(spanX, spanY - 1), QSize(spanX, spanY),
                QSize(spanX + 1, spanY + 1), QSize(spanX + 2, spanY + 2)};
            for (bool active : {false, true}) {
                for (std::size_t index = 0; index < bodies.size(); ++index)
                    addPixelRow(QStringLiteral("small-or-seam-%1").arg(index), bodies[index], radius, dpr, active);
                addPixelRow(QStringLiteral("zero-radius"), QSize(127, 93), 0, dpr, active);
            }
        }
    }

    void smallAndSliceBoundarySizesMatchContour() {
        QFETCH(QSize, body); QFETCH(qreal, radius); QFETCH(qreal, dpr); QFETCH(bool, active);
        const QString difference = compareContour(body, radius, dpr, active);
        QVERIFY2(difference.isEmpty(), qPrintable(difference));
    }

    void transparentCenterAndDownwardOffset() {
        WindowShadowRenderer renderer;
        const QSize body(401, 301);
        const qreal dpr = 1.5, radius = 14 * dpr;
        const int padding = qCeil(20 * dpr);
        for (bool active : {false, true}) {
            const auto expected = referenceShadowImage(body, radius, dpr, active);
            const auto actual = renderer.render(body, radius, dpr, active);
            const QString difference = pixelDifference(expected, actual);
            QVERIFY2(difference.isEmpty(), qPrintable(difference));
            QCOMPARE(actual.pixel(padding + body.width() / 2, padding + body.height() / 2), QRgb(0));
            const int middleX = padding + body.width() / 2;
            const int top = qAlpha(actual.pixel(middleX, padding - 1));
            const int bottom = qAlpha(actual.pixel(middleX, padding + body.height()));
            QVERIFY2(bottom > top, "The downward shadow offset must not be mirrored from the top edge");
        }
    }

    void resizeReusesBothActivityKernels() {
        WindowShadowRenderer renderer;
        const qreal dpr = 1.5, radius = 14 * dpr;
        const std::array<QSize, 8> bodies{
            QSize(1100, 860), QSize(760, 672), QSize(900, 672), QSize(914, 672),
            QSize(928, 672), QSize(942, 672), QSize(956, 678), QSize(970, 685)};
        for (bool active : {true, false}) {
            const quint64 expectedBuilds = renderer.kernelBuildCount() + 1;
            for (QSize body : bodies) {
                QVERIFY(!renderer.render(physical(body, dpr), radius, dpr, active).isNull());
                QCOMPARE(renderer.kernelBuildCount(), expectedBuilds);
            }
        }
        QVERIFY(!renderer.render(QSize(1501, 1103), radius, dpr, true).isNull());
        QCOMPARE(renderer.kernelBuildCount(), quint64(2));
    }

    void radiusAndDprInvalidateBothKernels() {
        WindowShadowRenderer renderer;
        const QSize body(401, 301);
        quint64 expectedBuilds = 0;
        const std::array<std::array<qreal, 2>, 4> keys{{{14, 1}, {16, 1}, {16, 1.25}, {14, 1}}};
        for (const auto &key : keys) {
            for (bool active : {true, false}) {
                QVERIFY(!renderer.render(body, key[0], key[1], active).isNull());
                QCOMPARE(renderer.kernelBuildCount(), ++expectedBuilds);
                QVERIFY(!renderer.render(body + QSize(17, 23), key[0], key[1], active).isNull());
                QCOMPARE(renderer.kernelBuildCount(), expectedBuilds);
            }
        }
    }

    void tinyFallbackDoesNotBuildAKernel() {
        WindowShadowRenderer renderer;
        for (bool active : {true, false}) {
            QVERIFY(!renderer.render(QSize(1, 1), 14, 1, active).isNull());
            QCOMPARE(renderer.kernelBuildCount(), quint64(0));
        }
        QVERIFY(!renderer.render(QSize(401, 301), 14, 1, true).isNull());
        QVERIFY(!renderer.render(QSize(1, 100), 14, 1, true).isNull());
        QCOMPARE(renderer.kernelBuildCount(), quint64(1));
    }

    void invalidInputsReturnEmpty_data() {
        addPixelColumns();
        const qreal nan = std::numeric_limits<qreal>::quiet_NaN();
        const qreal inf = std::numeric_limits<qreal>::infinity();
        const auto add = [](const char *name, QSize body, qreal radius, qreal dpr) {
            QTest::newRow(name) << body << radius << dpr << true;
        };
        add("empty", QSize(), 14, 1);
        add("zero-width", QSize(0, 100), 14, 1);
        add("zero-height", QSize(100, 0), 14, 1);
        add("negative-width", QSize(-1, 100), 14, 1);
        add("negative-height", QSize(100, -1), 14, 1);
        add("negative-radius", QSize(100, 100), -1, 1);
        add("nan-radius", QSize(100, 100), nan, 1);
        add("positive-infinite-radius", QSize(100, 100), inf, 1);
        add("negative-infinite-radius", QSize(100, 100), -inf, 1);
        add("nan-dpr", QSize(100, 100), 14, nan);
        add("positive-infinite-dpr", QSize(100, 100), 14, inf);
        add("negative-infinite-dpr", QSize(100, 100), 14, -inf);
        add("zero-dpr", QSize(100, 100), 14, 0);
        add("negative-dpr", QSize(100, 100), 14, -1);
        add("size-padding-overflow", QSize((std::numeric_limits<int>::max)(), 100), 14, 1);
        add("finite-radius-overflow", QSize(100, 100), (std::numeric_limits<qreal>::max)(), 1);
        add("finite-dpr-overflow", QSize(100, 100), 14, (std::numeric_limits<qreal>::max)());
    }

    void invalidInputsReturnEmpty() {
        QFETCH(QSize, body); QFETCH(qreal, radius); QFETCH(qreal, dpr); QFETCH(bool, active);
        WindowShadowRenderer renderer;
        QVERIFY(!renderer.render(QSize(401, 301), 14, 1, true).isNull());
        QCOMPARE(renderer.kernelBuildCount(), quint64(1));
        QVERIFY(renderer.render(body, radius, dpr, active).isNull());
        QCOMPARE(renderer.kernelBuildCount(), quint64(1));
        QVERIFY(!renderer.render(QSize(403, 303), 14, 1, true).isNull());
        QCOMPARE(renderer.kernelBuildCount(), quint64(1));
    }

    void cleanupTestCase() {
        qInfo().nospace() << "Pixel-exact shadow comparisons: " << m_samples << " samples, " << m_pixels
            << " pixels; reference elapsed=" << double(m_referenceNs) / 1e6
            << " ms, optimized elapsed=" << double(m_optimizedNs) / 1e6
            << " ms (one render per data row; optimized includes required kernel construction and reuse; no FPS or speed threshold).";
    }

private:
    QString compareContour(QSize body, qreal radius, qreal dpr, bool active) {
        QElapsedTimer timer;
        timer.start();
        const auto expected = referenceShadowImage(body, radius, dpr, active);
        m_referenceNs += timer.nsecsElapsed();
        timer.restart();
        const auto actual = m_renderer.render(body, radius, dpr, active);
        m_optimizedNs += timer.nsecsElapsed();
        ++m_samples;
        m_pixels += quint64(expected.width()) * quint64(expected.height());
        return pixelDifference(expected, actual);
    }
    WindowShadowRenderer m_renderer;
    qint64 m_referenceNs = 0, m_optimizedNs = 0;
    quint64 m_samples = 0, m_pixels = 0;
};

QTEST_GUILESS_MAIN(WindowShadowRendererTests)
#include "WindowShadowRendererTests.moc"

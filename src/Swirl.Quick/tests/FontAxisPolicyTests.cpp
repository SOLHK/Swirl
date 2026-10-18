#include "app/FontAxisPolicy.h"

#include <QFont>
#include <QtTest>
#include <algorithm>
#include <limits>

namespace {
QVariantMap axis(const QString &tag, double minimum, double defaultValue, double maximum)
{
    return {{"tag", tag}, {"minimum", minimum}, {"defaultValue", defaultValue},
            {"maximum", maximum}};
}

QVariantList variableMetadata()
{
    return {axis("wght", 100, 500, 900), axis("wdth", 75, 100, 125),
            axis("HGHT", 100, 250, 1000), axis("opsz", 8, 12, 72),
            axis("GRAD", -200, 0, 150)};
}
} // namespace

class FontAxisPolicyTests : public QObject {
    Q_OBJECT
private slots:
    void ordinaryFontsReceiveNoAxes()
    {
        FontAxisPolicy::Request request;
        QVERIFY(FontAxisPolicy::resolve({}, request).isEmpty());
        request.manual = true;
        QVERIFY(FontAxisPolicy::resolve({}, request, {{"wght", 650}}).isEmpty());
    }

    void designerDefaultsArePreserved()
    {
        const auto result = FontAxisPolicy::normalized(variableMetadata());
        QCOMPARE(result.value("wght").toDouble(), 500.0);
        QCOMPARE(result.value("wdth").toDouble(), 100.0);
        QCOMPARE(result.value("HGHT").toDouble(), 250.0);
        QCOMPARE(result.value("opsz").toDouble(), 12.0);
        QCOMPARE(result.value("GRAD").toDouble(), 0.0);
    }

    void qtWeightUsesOpenTypeScale_data()
    {
        QTest::addColumn<int>("weight");
        QTest::newRow("minimum") << 1;
        QTest::newRow("thin") << int(QFont::Thin);
        QTest::newRow("intermediate") << 350;
        QTest::newRow("body") << int(QFont::Normal);
        QTest::newRow("medium") << int(QFont::Medium);
        QTest::newRow("demibold") << int(QFont::DemiBold);
        QTest::newRow("bold") << int(QFont::Bold);
        QTest::newRow("maximum") << 1000;
    }

    void qtWeightUsesOpenTypeScale()
    {
        QFETCH(int, weight);
        FontAxisPolicy::Request request;
        request.weight = weight;
        const QVariantList metadata{axis("wght", 1, 500, 1000)};
        QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(),
                 double(weight));
    }

    void designWeightsClampToActualFontRange()
    {
        const QVariantList metadata{axis("wght", 350, 500, 650)};
        FontAxisPolicy::Request request;
        request.weight = QFont::Light;
        QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(), 350.0);
        request.weight = QFont::Normal;
        QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(), 400.0);
        request.weight = QFont::DemiBold;
        QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(), 600.0);
        request.weight = QFont::Bold;
        QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(), 650.0);
        for (const int invalid : {-1, 0, 1001}) {
            request.weight = invalid;
            QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(), 500.0);
        }
    }

    void opticalSizeUsesPoints_data()
    {
        QTest::addColumn<double>("points");
        QTest::addColumn<double>("pixels");
        QTest::addColumn<double>("dpi");
        QTest::addColumn<double>("dpr");
        QTest::addColumn<double>("expected");
        QTest::newRow("points") << 14.5 << -1.0 << 96.0 << 1.0 << 14.5;
        QTest::newRow("points-priority") << 14.5 << 16.0 << 96.0 << 1.0 << 14.5;
        QTest::newRow("points-high-dpi") << 14.5 << -1.0 << 144.0 << 2.0 << 14.5;
        QTest::newRow("logical-pixels") << -1.0 << 16.0 << 96.0 << 1.0 << 12.0;
        QTest::newRow("fractional-dpr") << -1.0 << 16.0 << 96.0 << 1.25 << 12.0;
        QTest::newRow("retina-dpr") << -1.0 << 16.0 << 96.0 << 2.0 << 12.0;
        QTest::newRow("logical-dpi-change") << -1.0 << 24.0 << 144.0 << 2.0 << 12.0;
        QTest::newRow("72-logical-dpi") << -1.0 << 16.0 << 72.0 << 2.0 << 16.0;
        QTest::newRow("below-minimum") << 2.0 << -1.0 << 96.0 << 1.0 << 8.0;
        QTest::newRow("above-maximum") << -1.0 << 200.0 << 96.0 << 1.0 << 72.0;
        QTest::newRow("unknown-size") << -1.0 << -1.0 << 96.0 << 1.0 << 12.0;
    }

    void opticalSizeUsesPoints()
    {
        QFETCH(double, points);
        QFETCH(double, pixels);
        QFETCH(double, dpi);
        QFETCH(double, dpr);
        QFETCH(double, expected);
        FontAxisPolicy::Request request;
        request.pointSize = points;
        request.pixelSize = pixels;
        request.logicalDpi = dpi;
        request.devicePixelRatio = dpr;
        QCOMPARE(FontAxisPolicy::resolve(variableMetadata(), request).value("opsz").toDouble(), expected);
    }

    void invalidOpticalInputsKeepDefault()
    {
        FontAxisPolicy::Request request;
        request.pixelSize = 16;
        const double nan = std::numeric_limits<double>::quiet_NaN();
        const double inf = std::numeric_limits<double>::infinity();
        for (const double dpi : {0.0, -96.0, nan, inf}) {
            request.logicalDpi = dpi;
            QCOMPARE(FontAxisPolicy::resolve(variableMetadata(), request).value("opsz").toDouble(), 12.0);
        }
        request.logicalDpi = 96;
        for (const double size : {0.0, -1.0, nan, inf}) {
            request.pixelSize = size;
            request.pointSize = size;
            QCOMPARE(FontAxisPolicy::resolve(variableMetadata(), request).value("opsz").toDouble(), 12.0);
        }
    }

    void heightAndWidthNeverEmulateOpticalSize()
    {
        const QVariantList metadata{axis("wght", 100, 500, 900),
                                    axis("HGHT", 100, 250, 1000),
                                    axis("wdth", 75, 100, 125)};
        for (const double size : {9.0, 13.0, 24.0, 64.0}) {
            FontAxisPolicy::Request request;
            request.pixelSize = size;
            const auto result = FontAxisPolicy::resolve(metadata, request);
            QVERIFY(!result.contains("opsz"));
            QCOMPARE(result.value("HGHT").toDouble(), 250.0);
            QCOMPARE(result.value("wdth").toDouble(), 100.0);
        }
    }

    void manualCoordinatesAreExactAndClamped()
    {
        FontAxisPolicy::Request request;
        request.manual = true;
        request.weight = 400;
        request.pixelSize = 16;
        const auto result = FontAxisPolicy::resolve(variableMetadata(), request,
            {{"wght", 623.5}, {"wdth", 113.25}, {"HGHT", 2000.0}, {"opsz", -1.0},
             {"GRAD", -25.25}, {"FAKE", 50.0}});
        QCOMPARE(result.value("wght").toDouble(), 623.5);
        QCOMPARE(result.value("wdth").toDouble(), 113.25);
        QCOMPARE(result.value("HGHT").toDouble(), 1000.0);
        QCOMPARE(result.value("opsz").toDouble(), 8.0);
        QCOMPARE(result.value("GRAD").toDouble(), -25.25);
        QVERIFY(!result.contains("FAKE"));
    }

    void invalidManualValuesKeepDesignerDefaults()
    {
        FontAxisPolicy::Request request;
        request.manual = true;
        const auto result = FontAxisPolicy::resolve(variableMetadata(), request,
            {{"wght", std::numeric_limits<double>::quiet_NaN()},
             {"wdth", std::numeric_limits<double>::infinity()}, {"HGHT", "not a number"}});
        QCOMPARE(result, FontAxisPolicy::normalized(variableMetadata()));
    }

    void automaticIgnoresPersistedManualOverrides()
    {
        FontAxisPolicy::Request request;
        request.weight = QFont::DemiBold;
        request.pixelSize = 24;
        const auto result = FontAxisPolicy::resolve(variableMetadata(), request,
            {{"wght", 321.5}, {"opsz", 60.0}, {"HGHT", 1000.0}});
        QCOMPARE(result.value("wght").toDouble(), 600.0);
        QCOMPARE(result.value("opsz").toDouble(), 18.0);
        QCOMPARE(result.value("HGHT").toDouble(), 250.0);
    }

    void axesNeverLeakToAnotherFont()
    {
        FontAxisPolicy::Request request;
        request.manual = true;
        const QVariantMap otherFontValues{{"wght", 623.5}, {"HGHT", 1000.0}, {"opsz", 60.0}};
        const QVariantList metadata{axis("GRAD", -100, 20, 100)};
        const auto result = FontAxisPolicy::resolve(metadata, request, otherFontValues);
        QCOMPARE(result, QVariantMap({{"GRAD", 20.0}}));
        // Per-family storage must additionally prevent shared tags (e.g. wght)
        // crossing resources; that is verified in FontManager's state tests.
    }

    void automaticDoesNotMaskQtItalicSelection()
    {
        const QVariantList metadata{axis("ital", 0, 0, 1), axis("slnt", -15, 0, 0),
                                    axis("wght", 100, 400, 900)};
        FontAxisPolicy::Request request;
        request.italic = true;
        const auto automatic = FontAxisPolicy::resolve(metadata, request);
        QVERIFY(!automatic.contains("ital"));
        QVERIFY(!automatic.contains("slnt"));
        QCOMPARE(automatic.value("wght").toDouble(), 400.0);
        request.manual = true;
        const auto manual = FontAxisPolicy::resolve(metadata, request, {{"ital", 1.0}, {"slnt", -9.5}});
        QCOMPARE(manual.value("ital").toDouble(), 1.0);
        QCOMPARE(manual.value("slnt").toDouble(), -9.5);
    }

    void invalidMetadataIsExcluded()
    {
        const double nan = std::numeric_limits<double>::quiet_NaN();
        const double inf = std::numeric_limits<double>::infinity();
        const double huge = std::numeric_limits<double>::max();
        QVariantList metadata{
            axis("short", 0, 1, 2), axis(QString::fromUtf8("轴wgt"), 0, 1, 2),
            axis(QString("wg\nt"), 0, 1, 2), axis("MINN", nan, 1, 2),
            axis("MAXI", 0, 1, inf), axis("DEFN", 0, nan, 2),
            axis("ORDR", 2, 1, 0), axis("DEFL", 0, -1, 2),
            axis("DEFH", 0, 3, 2), axis("HUGE", 0, 1, huge),
            QVariantMap{{"tag", "MISS"}, {"minimum", 0}, {"maximum", 2}},
            QVariantMap{{"tag", "TEXT"}, {"minimum", "none"}, {"defaultValue", 1}, {"maximum", 2}},
            QString("not a record"), axis("GRAD", -100, 20, 100)};
        QCOMPARE(FontAxisPolicy::normalized(metadata), QVariantMap({{"GRAD", 20.0}}));
    }

    void duplicateAxesAreRejectedIndependentlyOfOrder()
    {
        QVariantList metadata{axis("wght", 100, 400, 900), axis("wght", 350, 500, 650),
                              axis("GRAD", -100, 20, 100)};
        const auto forward = FontAxisPolicy::normalized(metadata);
        std::reverse(metadata.begin(), metadata.end());
        const auto reversed = FontAxisPolicy::normalized(metadata);
        QCOMPARE(forward, reversed);
        QCOMPARE(forward, QVariantMap({{"GRAD", 20.0}}));
    }

    void fixedAxisRangeIsValid()
    {
        const QVariantList metadata{axis("wght", 500, 500, 500)};
        FontAxisPolicy::Request request;
        request.weight = QFont::Bold;
        QCOMPARE(FontAxisPolicy::resolve(metadata, request).value("wght").toDouble(), 500.0);
    }

    void rolesAndNamesNeverInventFontProfiles()
    {
        FontAxisPolicy::Request request;
        request.pixelSize = 16;
        request.weight = QFont::Medium;
        const auto reference = FontAxisPolicy::resolve(variableMetadata(), request);
        const QStringList roles{"auxiliary", "label", "body", "button", "navigation", "list",
                                "input", "data", "pageTitle", "largeTitle"};
        for (const QString &family : {QStringLiteral("PingFang UI SC"), QStringLiteral("Other VF")}) {
            request.family = family;
            for (const QString &role : roles) {
                request.role = role;
                QCOMPARE(FontAxisPolicy::resolve(variableMetadata(), request), reference);
            }
        }
    }
};

QTEST_APPLESS_MAIN(FontAxisPolicyTests)
#include "FontAxisPolicyTests.moc"

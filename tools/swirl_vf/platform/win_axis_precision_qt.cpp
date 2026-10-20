// Original Swirl D1 synthetic-font experiment. No Apple outlines or font data.
// Build with Qt 6.9+ Core/Gui; run on Windows with the windows QPA plugin.
// Usage: win_axis_precision_qt FONT OUTPUT_DIR [--installed] [--reverse-order]
#include "../../../src/Swirl.Quick/app/FontAxisPolicy.h"
#include <QByteArray>
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QFontDatabase>
#include <QFontInfo>
#include <QFontMetricsF>
#include <QFontVariableAxis>
#include <QGlyphRun>
#include <QGuiApplication>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMap>
#include <QPainter>
#include <QPainterPath>
#include <QProcess>
#include <QRawFont>
#include <QSysInfo>
#include <QTextLayout>
#include <QTextOption>
#include <QtMath>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace {
void require(bool ok, const QString &message)
{
    if (!ok) throw std::runtime_error(message.toStdString());
}
QString hash(const QByteArray &bytes)
{
    return QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}
QString floatBits(float value)
{
    static_assert(sizeof(float) == sizeof(quint32));
    quint32 bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return QStringLiteral("0x%1").arg(bits, 8, 16, QLatin1Char('0'));
}
quint16 be16(const QByteArray &bytes, qsizetype at)
{
    require(at >= 0 && at + 2 <= bytes.size(), "Truncated uint16");
    return (quint16(quint8(bytes[at])) << 8) | quint8(bytes[at + 1]);
}
quint32 be32(const QByteArray &bytes, qsizetype at)
{
    return (quint32(be16(bytes, at)) << 16) | be16(bytes, at + 2);
}
double fixed(const QByteArray &bytes, qsizetype at)
{
    const quint32 value = be32(bytes, at);
    const qint64 signedValue = value >= 0x80000000u ? qint64(value) - 0x100000000LL : value;
    return double(signedValue) / 65536.0;
}
struct Axis { QString tag; double minimum = 0, defaultValue = 0, maximum = 0; };
struct Source {
    QByteArray bytes;
    QMap<QByteArray, QByteArray> tables;
    QMap<QString, Axis> axes;
    QString family, sha256;
    int upem = 0;
};
Source sourceFont(const QString &fileName)
{
    QFile file(fileName);
    require(file.open(QIODevice::ReadOnly), "Cannot read synthetic font");
    Source s; s.bytes = file.readAll(); s.sha256 = hash(s.bytes);
    require(be32(s.bytes, 0) == 0x00010000, "D1 Qt probe requires its original single-face TrueType fixture");
    const auto count = be16(s.bytes, 4);
    require(count > 0 && count < 128 && 12 + qsizetype(count) * 16 <= s.bytes.size(), "Invalid SFNT directory");
    for (int i = 0; i < count; ++i) {
        const qsizetype at = 12 + 16 * i;
        const auto tag = s.bytes.mid(at, 4);
        const auto offset = be32(s.bytes, at + 8), size = be32(s.bytes, at + 12);
        require(!s.tables.contains(tag) && quint64(offset) + size <= quint64(s.bytes.size()), "Invalid SFNT table");
        s.tables.insert(tag, s.bytes.mid(offset, size));
    }
    for (const auto *tag : {"head", "name", "cmap", "glyf", "loca", "fvar", "gvar", "hmtx"})
        require(s.tables.contains(tag) && !s.tables.value(tag).isEmpty(), QString("Missing source table %1").arg(tag));
    s.upem = be16(s.tables["head"], 18);
    require(s.upem >= 16 && s.upem <= 16384, "Invalid unitsPerEm");
    const auto &name = s.tables["name"];
    const auto records = be16(name, 2), stringOffset = be16(name, 4);
    int bestScore = -1;
    for (int i = 0; i < records; ++i) {
        const qsizetype at = 6 + 12 * i;
        const auto platform = be16(name, at), language = be16(name, at + 4), nameId = be16(name, at + 6);
        if ((nameId != 1 && nameId != 16) || (platform != 0 && platform != 3)) continue;
        const auto size = be16(name, at + 8), offset = be16(name, at + 10);
        const qsizetype begin = qsizetype(stringOffset) + offset;
        require(!(size & 1) && begin + size <= name.size(), "Invalid UTF-16 font name");
        const int score = (nameId == 16 ? 100 : 0) + (language == 0x0409 ? 10 : 0) + (platform == 3 ? 1 : 0);
        if (score <= bestScore) continue;
        QString decoded;
        for (qsizetype j = begin; j < begin + size; j += 2) decoded.append(QChar(be16(name, j)));
        if (!decoded.isEmpty()) { s.family = decoded; bestScore = score; }
    }
    require(!s.family.isEmpty(), "No source family name");
    const auto &fvar = s.tables["fvar"];
    require(be16(fvar, 0) == 1, "Unsupported fvar version");
    const auto offset = be16(fvar, 4), axisCount = be16(fvar, 8), stride = be16(fvar, 10);
    require(axisCount == 3 && stride >= 20, "Expected three physical synthetic axes");
    for (int i = 0; i < axisCount; ++i) {
        const qsizetype at = offset + i * stride;
        const QString tag = QString::fromLatin1(fvar.mid(at, 4));
        Axis a{tag, fixed(fvar, at + 4), fixed(fvar, at + 8), fixed(fvar, at + 12)};
        require(!s.axes.contains(tag) && a.minimum <= a.defaultValue && a.defaultValue <= a.maximum,
                "Invalid physical axis");
        s.axes.insert(tag, a);
    }
    for (const auto *tag : {"wght", "WDTH", "HGHT"}) require(s.axes.contains(tag), "Missing case-sensitive physical axis");
    require(s.axes["wght"].minimum <= 499.006199 && s.axes["wght"].maximum >= 499.006201,
            "Synthetic fixture does not contain the declared precision pair");
    return s;
}
void writeRecord(QFile &file, const QJsonObject &record)
{
    const auto bytes = QJsonDocument(record).toJson(QJsonDocument::Compact) + '\n';
    require(file.write(bytes) == bytes.size() && file.flush(), "Cannot persist JSON evidence");
}
QJsonArray point(const QPointF &p) { return {p.x(), p.y()}; }
QJsonArray pathElements(const QPainterPath &path)
{
    QJsonArray result;
    for (int i = 0; i < path.elementCount(); ++i) {
        const auto p = path.elementAt(i);
        require(std::isfinite(p.x) && std::isfinite(p.y), "Non-finite path coordinate");
        result.append(QJsonArray{int(p.type), p.x, p.y});
    }
    return result;
}
void verifyIdentity(const QRawFont &raw, const Source &source)
{
    require(raw.isValid(), "Actual QRawFont is invalid");
    require(raw.familyName() == source.family, "Actual raw family differs from original synthetic family");
    // Exact table bytes, not family strings alone, reject fallback or a stale
    // same-name font. Optional tables are compared whenever the source has them.
    for (const auto *tag : {"name", "cmap", "glyf", "loca", "fvar", "gvar", "avar", "hmtx", "HVAR"}) {
        if (source.tables.contains(tag))
            require(raw.fontTable(tag) == source.tables.value(tag), QString("Actual font table differs: %1").arg(tag));
    }
}
struct Position {
    QString id;
    double wght, wdth, hght;
};
QVariantList policyMetadata(const Source &source)
{
    QVariantList metadata;
    for (const auto &a : source.axes)
        metadata.append(QVariantMap{{"tag", a.tag}, {"minimum", a.minimum},
                                    {"defaultValue", a.defaultValue}, {"maximum", a.maximum}});
    return metadata;
}
Position resolvedPosition(const QString &id, const QVariantMap &axes)
{
    for (const auto *tag : {"wght", "WDTH", "HGHT"})
        require(axes.contains(tag) && std::isfinite(axes.value(tag).toDouble()), "Production policy omitted a physical coordinate");
    return {id, axes.value("wght").toDouble(), axes.value("WDTH").toDouble(), axes.value("HGHT").toDouble()};
}
Position automaticPosition(const Source &source, int weight, const QString &id)
{
    FontAxisPolicy::Request request;
    request.family = source.family; request.weight = weight; request.pixelSize = 24;
    request.role = "body";
    return resolvedPosition(id, FontAxisPolicy::resolve(policyMetadata(source), request));
}
Position manualPosition(const Source &source)
{
    FontAxisPolicy::Request request;
    request.family = source.family; request.manual = true; request.pixelSize = 24;
    const QVariantMap values{{"wght", 623.25}, {"WDTH", 137.5}, {"HGHT", 172.5}};
    return resolvedPosition("mixed", FontAxisPolicy::resolve(policyMetadata(source), request, values));
}
int checkProductionPolicy(const Source &source, QFile &log)
{
    const auto metadata = policyMetadata(source);
    int count = 0;
    for (const int dpi : {96, 144, 192})
        for (const double dpr : {1.0, 1.25, 1.5, 2.0}) {
            for (const int weight : {400, 600}) {
                FontAxisPolicy::Request request;
                request.family = source.family; request.role = "body"; request.weight = weight;
                request.pixelSize = 24; request.logicalDpi = dpi; request.devicePixelRatio = dpr;
                const auto result = FontAxisPolicy::resolve(metadata, request);
                require(result.size() == 3 && result.value("wght").toDouble() == weight
                        && result.value("WDTH").toDouble() == source.axes["WDTH"].defaultValue
                        && result.value("HGHT").toDouble() == source.axes["HGHT"].defaultValue,
                        "Automatic production policy changed weight or unprofiled custom-axis defaults");
                writeRecord(log, {{"record", "policy_observation"}, {"mode", "automatic"}, {"weight", weight},
                                  {"logical_dpi", dpi}, {"dpr", dpr}, {"resolved_axes", QJsonObject::fromVariantMap(result)},
                                  {"implementation", "existing_FontAxisPolicy_resolve"}});
                ++count;
            }
            FontAxisPolicy::Request request;
            request.family = source.family; request.manual = true; request.pixelSize = 24;
            request.logicalDpi = dpi; request.devicePixelRatio = dpr;
            const QVariantMap manual{{"wght", 623.25}, {"WDTH", 137.5}, {"HGHT", 172.5}, {"wdth", 88.0}};
            const auto result = FontAxisPolicy::resolve(metadata, request, manual);
            require(result.size() == 3 && !result.contains("wdth") && result.value("wght").toDouble() == 623.25
                    && result.value("WDTH").toDouble() == 137.5 && result.value("HGHT").toDouble() == 172.5,
                    "Manual production policy changed custom units or accepted wrong-case axis");
            writeRecord(log, {{"record", "policy_observation"}, {"mode", "manual"}, {"logical_dpi", dpi}, {"dpr", dpr},
                              {"resolved_axes", QJsonObject::fromVariantMap(result)}, {"wrong_case_wdth_rejected", true},
                              {"implementation", "existing_FontAxisPolicy_resolve"}});
            ++count;
        }
    return count;
}
QList<Position> positions(const Source &source)
{
    const auto w = source.axes["wght"], d = source.axes["WDTH"], h = source.axes["HGHT"];
    const float center = float(499.006199);
    return {
        automaticPosition(source, 400, "default"),
        automaticPosition(source, 600, "automatic_600"),
        {"pair_lo", 499.006199, d.defaultValue, h.defaultValue},
        {"pair_hi", 499.006201, d.defaultValue, h.defaultValue},
        {"float_prev", double(std::nextafter(center, -std::numeric_limits<float>::infinity())), d.defaultValue, h.defaultValue},
        {"float_next", double(std::nextafter(center, std::numeric_limits<float>::infinity())), d.defaultValue, h.defaultValue},
        {"wght_min", w.minimum, d.defaultValue, h.defaultValue},
        {"wght_max", w.maximum, d.defaultValue, h.defaultValue},
        {"WDTH_min", w.defaultValue, d.minimum, h.defaultValue},
        {"WDTH_max", w.defaultValue, d.maximum, h.defaultValue},
        {"HGHT_min", w.defaultValue, d.defaultValue, h.minimum},
        {"HGHT_max", w.defaultValue, d.defaultValue, h.maximum},
        manualPosition(source)
    };
}
QJsonObject requested(const Position &p)
{
    return {{"wght", p.wght}, {"WDTH", p.wdth}, {"HGHT", p.hght}};
}
QJsonObject floatRequested(const Position &p)
{
    QJsonObject r;
    for (const auto &entry : {std::pair<const char *, double>{"wght", p.wght}, {"WDTH", p.wdth}, {"HGHT", p.hght}})
        r.insert(entry.first, QJsonObject{{"value", double(float(entry.second))}, {"bits", floatBits(float(entry.second))}});
    return r;
}
struct Observation { QJsonObject payload; QString rasterSha; QString png; double elapsedMs = 0; };
Observation observe(const Source &source, const Position &position, double points, int logicalDpi,
                    double dpr, const QString &png, QJsonArray *diagnostic = nullptr)
{
    QElapsedTimer timer; timer.start();
    QImage device(8, 8, QImage::Format_ARGB32_Premultiplied);
    device.setDotsPerMeterX(qRound(logicalDpi / 0.0254));
    device.setDotsPerMeterY(qRound(logicalDpi / 0.0254));
    device.setDevicePixelRatio(dpr);
    QFont query(source.family);
    query.setStyleName(QString());
    query.setWeight(QFont::Normal);
    query.setPointSizeF(points);
    query.setHintingPreference(QFont::PreferNoHinting);
    query.setStyleStrategy(QFont::StyleStrategy(QFont::NoFontMerging | QFont::PreferAntialias | QFont::NoSubpixelAntialias));
    query.setVariableAxis(QFont::Tag("wght"), float(position.wght));
    query.setVariableAxis(QFont::Tag("WDTH"), float(position.wdth));
    query.setVariableAxis(QFont::Tag("HGHT"), float(position.hght));
    QFont font(query, &device);
    const QRawFont raw = QRawFont::fromFont(font);
    verifyIdentity(raw, source);
    require(raw.pixelSize() > 0, "Invalid actual pixel size");
    const QFontInfo info(font);
    require(info.family() == source.family, "Font matcher substituted family");
    QJsonArray metadata;
    QMap<QString, Axis> observedAxes;
    for (const auto &axis : info.variableAxes()) {
        const QString tag = QString::fromLatin1(axis.tag().toString());
        metadata.append(QJsonObject{{"tag", tag}, {"minimum", axis.minimumValue()},
                                  {"default", axis.defaultValue()}, {"maximum", axis.maximumValue()}});
        observedAxes.insert(tag, Axis{tag, axis.minimumValue(), axis.defaultValue(), axis.maximumValue()});
    }
    for (auto it = source.axes.cbegin(); it != source.axes.cend(); ++it) {
        require(observedAxes.contains(it.key()), "Actual engine omitted physical axis metadata");
        const auto &a = observedAxes[it.key()];
        require(a.minimum == it->minimum && a.maximum == it->maximum && a.defaultValue == it->defaultValue,
                "Actual engine changed physical axis range");
    }
    const QString glyphText = QStringLiteral("A B\u4e2d\u6587");
    const auto glyphs = raw.glyphIndexesForString(glyphText);
    // Extra calls are restricted to a fresh, explicitly diagnostic process.
    // Main acceptance keeps its original observation order and no warm-up.
    const auto checkpoint = [&](const char *stage) {
        if (!diagnostic) return;
        QJsonArray paths;
        for (const auto gid : glyphs) paths.append(QJsonObject{{"gid", int(gid)}, {"path_px", pathElements(raw.pathForGlyph(gid))}});
        diagnostic->append(QJsonObject{{"stage", stage}, {"raw_pixel_size", raw.pixelSize()}, {"paths", paths}});
    };
    checkpoint("before_raw_advances");
    const auto advances = raw.advancesForGlyphIndexes(glyphs);
    checkpoint("after_raw_advances");
    require(glyphs.size() == glyphText.size() && advances.size() == glyphs.size(), "Incomplete original glyph sample");
    QJsonArray glyphPayload;
    int nonEmpty = 0;
    for (qsizetype i = 0; i < glyphs.size(); ++i) {
        require(glyphs[i] != 0, "Original synthetic sample has a missing glyph");
        const auto path = raw.pathForGlyph(glyphs[i]);
        nonEmpty += !path.isEmpty();
        require(std::isfinite(advances[i].x()) && std::isfinite(advances[i].y()), "Non-finite advance");
        glyphPayload.append(QJsonObject{{"codepoint", int(glyphText[i].unicode())}, {"gid", int(glyphs[i])},
                                       {"advance_px", point(advances[i])}, {"path_px", pathElements(path)}});
    }
    require(nonEmpty == 4, "Unexpected empty original synthetic outlines");
    checkpoint("after_raw_paths");
    const QString text = QStringLiteral("AB \u4e2d\u6587 AB");
    QFontMetricsF metrics(font, &device);
    const double width = metrics.horizontalAdvance(text), lineHeight = metrics.height();
    checkpoint("after_qfontmetrics");
    require(std::isfinite(width) && width > 0 && width < 10000 && std::isfinite(lineHeight) && lineHeight > 0 && lineHeight < 1000,
            "Invalid or excessive synthetic text metrics");
    QTextLayout layout(text, font, &device);
    QTextOption option; option.setWrapMode(QTextOption::NoWrap); option.setTextDirection(Qt::LeftToRight);
    layout.setTextOption(option);
    layout.beginLayout();
    auto line = layout.createLine();
    require(line.isValid(), "Text layout produced no line");
    line.setLineWidth(100000);
    layout.endLayout();
    checkpoint("after_textlayout_creation");
    require(line.textLength() == text.size() && layout.lineCount() == 1, "Incomplete mixed text layout");
    QJsonArray runPayload;
    QRectF actualInk;
    qsizetype glyphCount = 0;
    for (const QGlyphRun &run : layout.glyphRuns()) {
        verifyIdentity(run.rawFont(), source);
        QJsonArray runGlyphs, runPoints, runPaths, runAdvances;
        const auto ids = run.glyphIndexes(); const auto positions = run.positions();
        const auto actualAdvances = run.rawFont().advancesForGlyphIndexes(ids);
        require(ids.size() == positions.size(), "Invalid glyph run length");
        require(ids.size() == actualAdvances.size(), "Incomplete actual glyph-run advances");
        for (qsizetype i = 0; i < ids.size(); ++i) {
            require(ids[i] != 0, "Fallback or missing mixed-text glyph");
            runGlyphs.append(int(ids[i])); runPoints.append(point(positions[i]));
            const auto actualPath = run.rawFont().pathForGlyph(ids[i]);
            runPaths.append(pathElements(actualPath)); runAdvances.append(point(actualAdvances[i]));
            if (!actualPath.isEmpty()) actualInk = actualInk.united(actualPath.boundingRect().translated(positions[i]));
        }
        glyphCount += ids.size();
        runPayload.append(QJsonObject{{"family", run.rawFont().familyName()}, {"glyphs", runGlyphs}, {"positions_px", runPoints},
                                      {"paths_px", runPaths}, {"advances_px", runAdvances}});
    }
    require(glyphCount == text.size(), "Mixed text did not yield every expected authored glyph");
    checkpoint("after_actual_run_paths");
    const QPointF origin(24 - std::min(0.0, actualInk.left()), 24 - std::min(0.0, actualInk.top()));
    const int imageWidth = qCeil((std::max({width, line.naturalTextWidth(), actualInk.right()}) + origin.x() + 24) * dpr);
    const int imageHeight = qCeil((std::max({lineHeight, line.height(), actualInk.bottom()}) + origin.y() + 24) * dpr);
    QImage image(std::max(imageWidth, 96), std::max(imageHeight, 96), QImage::Format_ARGB32_Premultiplied);
    require(!image.isNull(), "Cannot allocate raster evidence");
    image.setDotsPerMeterX(device.dotsPerMeterX()); image.setDotsPerMeterY(device.dotsPerMeterY()); image.setDevicePixelRatio(dpr);
    image.fill(Qt::white);
    {
        QPainter painter(&image);
        require(painter.isActive(), "Cannot start Qt image painter");
        painter.setPen(Qt::black);
        painter.setRenderHint(QPainter::TextAntialiasing, true);
        layout.draw(&painter, origin);
    }
    checkpoint("after_raster");
    if (diagnostic) {
        const auto reacquired = QRawFont::fromFont(font);
        verifyIdentity(reacquired, source);
        QJsonArray paths;
        for (const auto gid : glyphs) paths.append(QJsonObject{{"gid", int(gid)}, {"path_px", pathElements(reacquired.pathForGlyph(gid))}});
        diagnostic->append(QJsonObject{{"stage", "after_rawfont_reacquisition"}, {"raw_pixel_size", reacquired.pixelSize()}, {"paths", paths}});
    }
    qsizetype inkPixels = 0;
    for (int y = 0; y < image.height(); ++y) {
        const auto *row = reinterpret_cast<const QRgb *>(image.constScanLine(y));
        for (int x = 0; x < image.width(); ++x) inkPixels += row[x] != qRgb(255, 255, 255);
    }
    require(inkPixels > 0, "Qt raster is empty");
    const auto pixels = QByteArray(reinterpret_cast<const char *>(image.constBits()), image.sizeInBytes());
    if (!png.isEmpty()) require(image.save(png, "PNG"), "Cannot save raster evidence");
    QJsonObject readback;
    for (const auto tag : {QFont::Tag("wght"), QFont::Tag("WDTH"), QFont::Tag("HGHT")}) {
        const float value = font.variableAxisValue(tag);
        readback.insert(QString::fromLatin1(tag.toString()), QJsonObject{{"value", double(value)}, {"bits", floatBits(value)}});
    }
    QJsonObject payload{
        {"family", info.family()}, {"table_identity_exact", true}, {"engine_axis_metadata", metadata},
        {"qfont_requested_axis_storage", readback}, {"raw_pixel_size", raw.pixelSize()}, {"glyphs", glyphPayload},
        {"metrics", QJsonObject{{"horizontal_advance_px", width}, {"ascent_px", metrics.ascent()}, {"descent_px", metrics.descent()},
                                {"height_px", lineHeight}, {"line_spacing_px", metrics.lineSpacing()}}},
        {"layout", QJsonObject{{"text", text}, {"advance_px", line.horizontalAdvance()}, {"width_px", line.naturalTextWidth()},
                               {"height_px", line.height()}, {"ascent_px", line.ascent()}, {"runs", runPayload}}},
        {"raster", QJsonObject{{"width", image.width()}, {"height", image.height()}, {"ink_pixels", double(inkPixels)}, {"pixel_sha256", hash(pixels)}}}
    };
    return {payload, hash(pixels), png, timer.nsecsElapsed() / 1e6};
}
QJsonArray outlineOnly(const QJsonObject &payload)
{
    QJsonArray result;
    for (const auto &v : payload["glyphs"].toArray()) result.append(v.toObject()["path_px"]);
    return result;
}
QJsonArray advancesOnly(const QJsonObject &payload)
{
    QJsonArray result;
    for (const auto &v : payload["glyphs"].toArray()) result.append(v.toObject()["advance_px"]);
    return result;
}
} // namespace

int main(int argc, char **argv)
{
#ifndef Q_OS_WIN
    std::puts("{\"record\":\"summary\",\"status\":\"NOT_RUN\",\"reason\":\"Requires native Windows Qt\"}");
    return 77;
#endif
    QGuiApplication app(argc, argv);
    const auto arguments = app.arguments();
    if (arguments.size() < 3) {
        std::fputs("Usage: win_axis_precision_qt FONT OUTPUT_DIR [--installed] [--reverse-order]\n", stderr); return 2;
    }
    bool installed = false, reverse = false, diagnosePathState = false;
    for (int i = 3; i < arguments.size(); ++i) {
        if (arguments[i] == "--installed") installed = true;
        else if (arguments[i] == "--reverse-order") reverse = true;
        else if (arguments[i] == "--diagnose-path-state") diagnosePathState = true;
        else { std::fputs("Unknown argument\n", stderr); return 2; }
    }
    const QString output = QDir(arguments[2]).absolutePath();
    QFile log(QDir(output).filePath(diagnosePathState ? "qt-path-state-diagnostic.jsonl" : "qt-axis-precision.jsonl"));
    int fontId = -1, observations = 0, pairs = 0, repeated = 0;
    QList<double> durations;
    try {
        require(QGuiApplication::platformName() == "windows", "This run must use the native windows QPA plugin");
        require(QDir().mkpath(output), "Cannot create evidence directory");
        require(!QFileInfo::exists(log.fileName()) && log.open(QIODevice::WriteOnly | QIODevice::NewOnly), "Use a new evidence directory");
        const Source source = sourceFont(arguments[1]);
        if (diagnosePathState) {
            writeRecord(log, {{"record", "diagnostic_header"}, {"schema", 1}, {"input_sha256", source.sha256},
                              {"qt_version", QString::fromLatin1(qVersion())}, {"requested_qpa", qEnvironmentVariable("QT_QPA_PLATFORM")},
                              {"load_mode", installed ? "system_installed" : "application_private"},
                              {"experiment", "fresh_process_path_state_with_extra_measurement_calls"},
                              {"acceptance", "DIAGNOSTIC_ONLY_PRIMARY_FAILURE_RETAINED"}});
            if (installed) {
                require(QFontDatabase::families().contains(source.family), "Diagnostic fixture is not installed");
            } else {
                require(!QFontDatabase::families().contains(source.family), "Diagnostic private font was already installed");
                fontId = QFontDatabase::addApplicationFont(arguments[1]);
                require(fontId >= 0 && QFontDatabase::applicationFontFamilies(fontId).contains(source.family), "Diagnostic registration failed");
            }
            QList<Position> probes{{"same_input_first", 499.006199, source.axes["WDTH"].defaultValue, source.axes["HGHT"].defaultValue},
                                   {"same_input_repeated", 499.006199, source.axes["WDTH"].defaultValue, source.axes["HGHT"].defaultValue},
                                   {"other_decimal_same_float", 499.006201, source.axes["WDTH"].defaultValue, source.axes["HGHT"].defaultValue}};
            for (const auto &probe : probes) {
                QJsonArray checkpoints;
                const auto result = observe(source, probe, 9, 96, 1, QDir(output).filePath(probe.id + ".png"), &checkpoints);
                writeRecord(log, {{"record", "path_state_diagnostic"}, {"case_id", probe.id}, {"requested_decimal", requested(probe)},
                                  {"api_float32", floatRequested(probe)}, {"checkpoints", checkpoints}, {"payload", result.payload}});
            }
            if (fontId >= 0) { require(QFontDatabase::removeApplicationFont(fontId), "Diagnostic removal failed"); fontId = -1; }
            writeRecord(log, {{"record", "diagnostic_summary"}, {"status", "DIAGNOSTIC_COMPLETED_NOT_ACCEPTANCE"}, {"observations", 3}});
            return 0;
        }
        const auto cases = positions(source);
        const int passes = installed ? 2 : 3;
        QJsonArray caseIds;
        for (const auto &p : cases) caseIds.append(p.id);
        QJsonArray axes;
        for (const auto &a : source.axes) axes.append(QJsonObject{{"tag", a.tag}, {"minimum", a.minimum}, {"default", a.defaultValue}, {"maximum", a.maximum}});
        QJsonObject tableHashes;
        for (auto it = source.tables.cbegin(); it != source.tables.cend(); ++it) tableHashes.insert(QString::fromLatin1(it.key()), hash(it.value()));
        writeRecord(log, {{"record", "header"}, {"schema", 1}, {"input_sha256", source.sha256}, {"input_bytes", double(source.bytes.size())},
                          {"family", source.family}, {"source_axes", axes}, {"source_table_sha256", tableHashes}, {"units_per_em", source.upem},
                          {"qt_version", QString::fromLatin1(qVersion())}, {"qt_build_version", QStringLiteral(QT_VERSION_STR)},
                          {"qpa_platform", QGuiApplication::platformName()}, {"requested_qpa", qEnvironmentVariable("QT_QPA_PLATFORM")},
                          {"backend_identity", "requested_platform_and_public_axis_behavior; private_engine_class_not_queried"},
                          {"os_product", QSysInfo::prettyProductName()}, {"kernel_version", QSysInfo::kernelVersion()},
                          {"load_mode", installed ? "system_installed" : "application_private"}, {"reverse", reverse},
                          {"float_bytes", int(sizeof(float))}, {"qreal_bytes", int(sizeof(qreal))},
                          {"case_ids", caseIds}, {"point_sizes", QJsonArray{9, 12, 18}}, {"logical_dpis", QJsonArray{96, 144}},
                          {"dprs", QJsonArray{1, 1.25, 1.5, 2}}, {"pass_count", passes},
                          {"expected_observations", int(cases.size()) * 24 * passes}, {"expected_pair_comparisons", 24 * passes},
                          {"expected_exact_replays", int(cases.size()) * 24 * (passes - 1)}, {"expected_policy_checks", 36},
                          {"original_font_acceptance", "NOT_RUN"}});
        const int policyChecks = checkProductionPolicy(source, log);
        if (installed) {
            require(QFontDatabase::families().contains(source.family), "Fixture family is not system-installed before any app font registration");
        } else {
            require(!QFontDatabase::families().contains(source.family), "Private-mode fixture is already installed; isolate the run");
            const auto before = QFontDatabase::families();
            const QString defaultBefore = QFontInfo(QGuiApplication::font()).family();
            const int missingId = QFontDatabase::addApplicationFont(QDir(output).filePath("intentionally-missing-original-font.ttf"));
            require(missingId == -1 && QFontDatabase::families() == before && QFontInfo(QGuiApplication::font()).family() == defaultBefore,
                    "Missing font load changed the active font database/default");
            writeRecord(log, {{"record", "load_failure_control"}, {"missing_file_rejected", true}, {"default_family_unchanged", true}});
            fontId = QFontDatabase::addApplicationFont(arguments[1]);
            require(fontId >= 0 && QFontDatabase::applicationFontFamilies(fontId).contains(source.family), "Cannot privately register authored fixture family");
        }
        require(floatBits(float(499.006199)) == floatBits(float(499.006201)), "Unexpected binary32 pair conversion");
        QMap<QString, QJsonObject> first;
        for (int pass = 0; pass < passes; ++pass) {
            if (pass == 2) {
                require(QFontDatabase::removeApplicationFont(fontId), "Application font removal failed"); fontId = -1;
                QCoreApplication::processEvents();
                fontId = QFontDatabase::addApplicationFont(arguments[1]);
                require(fontId >= 0 && QFontDatabase::applicationFontFamilies(fontId).contains(source.family), "Application font reload failed");
                writeRecord(log, {{"record", "reload"}, {"status", "REGISTERED_AGAIN"}});
            }
            QList<Position> ordered = cases;
            if (reverse != (pass == 1)) std::reverse(ordered.begin(), ordered.end());
            for (const double size : {9.0, 12.0, 18.0})
                for (const int dpi : {96, 144})
                    for (const double dpr : {1.0, 1.25, 1.5, 2.0}) {
                        const QString scenario = QString("pt%1-dpi%2-dpr%3").arg(size).arg(dpi).arg(dpr);
                        QMap<QString, QJsonObject> measured;
                        for (const auto &position : ordered) {
                            const QString key = scenario + '-' + position.id;
                            const QString png = pass == 0 ? QDir(output).filePath(key + ".png") : QString();
                            const auto result = observe(source, position, size, dpi, dpr, png);
                            durations.append(result.elapsedMs);
                            measured.insert(position.id, result.payload);
                            if (pass == 0) first.insert(key, result.payload);
                            else { require(first.value(key) == result.payload, "Actual output changed on reverse/reload replay: " + key); ++repeated; }
                            writeRecord(log, {{"record", "observation"}, {"pass", pass}, {"scenario", scenario}, {"case_id", position.id},
                                              {"requested_decimal", requested(position)}, {"api_float32", floatRequested(position)},
                                              {"point_size", size}, {"logical_dpi", dpi}, {"dpr", dpr}, {"payload", result.payload},
                                              {"png", QFileInfo(result.png).fileName()}, {"elapsed_ms_including_evidence", result.elapsedMs}});
                            ++observations;
                        }
                        const auto lo = measured["pair_lo"], hi = measured["pair_hi"];
                        const bool outlinesEqual = outlineOnly(lo) == outlineOnly(hi);
                        const bool advancesEqual = advancesOnly(lo) == advancesOnly(hi);
                        const bool metricsEqual = lo["metrics"] == hi["metrics"];
                        const bool layoutEqual = lo["layout"] == hi["layout"];
                        const bool pixelsEqual = lo["raster"] == hi["raster"];
                        writeRecord(log, {{"record", "pair_comparison"}, {"pass", pass}, {"scenario", scenario},
                                          {"api_float32_equal", true}, {"raw_outline_equal", outlinesEqual}, {"raw_advance_equal", advancesEqual},
                                          {"qfontmetrics_equal", metricsEqual}, {"textlayout_equal", layoutEqual}, {"raster_equal", pixelsEqual}});
                        require(outlinesEqual && advancesEqual && metricsEqual && layoutEqual && pixelsEqual,
                                "Identical API inputs produced different actual pair outputs");
                        ++pairs;
                        for (const auto *tag : {"wght", "WDTH", "HGHT"}) {
                            require(outlineOnly(measured[QString(tag) + "_min"]) != outlineOnly(measured[QString(tag) + "_max"]),
                                    QString("Axis has no actual outline effect: %1").arg(tag));
                            require(measured[QString(tag) + "_min"]["raster"] != measured[QString(tag) + "_max"]["raster"],
                                    QString("Axis has no actual raster effect: %1").arg(tag));
                        }
                    }
        }
        if (fontId >= 0) { require(QFontDatabase::removeApplicationFont(fontId), "Final private font removal failed"); fontId = -1; }
        QFile input(arguments[1]); require(input.open(QIODevice::ReadOnly) && hash(input.readAll()) == source.sha256, "Input font changed during the run");
        std::sort(durations.begin(), durations.end());
        const QJsonObject summary{{"record", "summary"}, {"status", "PASS_QT_SYNTHETIC"}, {"observations", observations},
                                  {"pair_comparisons", pairs}, {"exact_replays", repeated}, {"production_policy_checks", policyChecks},
                                  {"physical_axis_effects_verified", 3},
                                  {"application_reload", installed ? "NOT_APPLICABLE" : "PASS"},
                                  {"elapsed_median_ms_including_evidence", durations[durations.size() / 2]},
                                  {"elapsed_p95_ms_including_evidence", durations[(durations.size() - 1) * 95 / 100]},
                                  {"original_font_acceptance", "NOT_RUN"}, {"real_swirl_ui_acceptance", "NOT_RUN"},
                                  {"regional_glyph_acceptance", "NOT_RUN"}, {"font_cache_memory_benchmark", "NOT_RUN"},
                                  {"interpretation", "Observed binary32 pair collapse in this exact synthetic Qt run; API storage is not a native-face readback"}};
        writeRecord(log, summary);
        std::puts(QJsonDocument(summary).toJson(QJsonDocument::Compact).constData());
        return 0;
    } catch (const std::exception &e) {
        if (fontId >= 0) QFontDatabase::removeApplicationFont(fontId);
        const QJsonObject failure{{"record", "summary"}, {"status", "FAILED"}, {"error", QString::fromUtf8(e.what())},
                                  {"observations", observations}, {"pair_comparisons", pairs}, {"exact_replays", repeated},
                                  {"original_font_acceptance", "NOT_RUN"}};
        if (log.isOpen()) { try { writeRecord(log, failure); } catch (...) {} }
        const QString error = QString::fromUtf8(e.what());
        if (!diagnosePathState && (error.contains("actual pair outputs") || error.contains("reverse/reload replay"))) {
            // Isolate additional observations in a fresh process; never warm or
            // retry the primary observation to turn its failure into a pass.
            QProcess child;
            QStringList childArguments{arguments[1], QDir(output).filePath("path-state-diagnostic"), "--diagnose-path-state"};
            if (installed) childArguments.append("--installed");
            child.setStandardOutputFile(QDir(output).filePath("path-state-child.stdout.log"));
            child.setStandardErrorFile(QDir(output).filePath("path-state-child.stderr.log"));
            child.start(QCoreApplication::applicationFilePath(), childArguments);
            if (!child.waitForStarted(5000) || !child.waitForFinished(15000)) { child.kill(); child.waitForFinished(1000); }
        }
        std::fputs(QJsonDocument(failure).toJson(QJsonDocument::Compact).constData(), stderr);
        std::fputc('\n', stderr);
        return 1;
    }
}

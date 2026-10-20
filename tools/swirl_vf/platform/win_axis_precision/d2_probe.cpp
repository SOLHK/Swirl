// D2-1 diagnostic only. Reuse D1's unchanged fixture identity, JSON and path helpers.
// This target never replaces the primary D1 executable or any production code.
#include <QGuiApplication>
#define main d1_unmodified_entry_for_shared_probe_helpers
#include "../win_axis_precision_qt.cpp"
#undef main
#include <QtGui/private/qrawfont_p.h>
#include <QtGui/private/qfontengine_ft_p.h>
#include <QLibraryInfo>
#include <QScopeGuard>
#include "d2_ft_access.h"

namespace {
struct D2State {
    FT_Matrix matrix;
    FT_Vector delta;
    FT_Matrix cached;
    QJsonObject json() const {
        return {{"matrix_16_16", QJsonArray{double(matrix.xx), double(matrix.xy), double(matrix.yx), double(matrix.yy)}},
                {"delta_26_6", QJsonArray{double(delta.x), double(delta.y)}},
                {"qt_cached_matrix_16_16", QJsonArray{double(cached.xx), double(cached.xy), double(cached.yx), double(cached.yy)}}};
    }
};
D2State d2State(QFreetypeFace *shared)
{
    shared->lock();
    const auto unlock = qScopeGuard([&] { shared->unlock(); });
    D2State state{};
    d2_FT_Get_Transform(shared->face, &state.matrix, &state.delta);
    state.cached = shared->matrix;
    return state;
}
QPainterPath d2IsolatedPath(const QRawFont &raw, quint32 gid, QFontEngineFT *engine)
{
    // Match addGlyphsToPath's existing lock/normalization before saving state.
    // The face uses a recursive mutex, so the public query can lock it again.
    FT_Face face = engine->lockFace(QFontEngineFT::Unscaled);
    const auto unlock = qScopeGuard([&] { engine->unlockFace(); });
    FT_Matrix matrix;
    FT_Vector delta;
    d2_FT_Get_Transform(face, &matrix, &delta);
    const auto restore = qScopeGuard([&] { d2_FT_Set_Transform(face, &matrix, &delta); });
    d2_FT_Set_Transform(face, &matrix, nullptr);
    return raw.pathForGlyph(gid);
}
QJsonArray d2Cache(QFontEngineFT *engine, quint32 gid, double dpr)
{
    // This lookup can create an empty set; it does not load a glyph or change FT state.
    // All quarter-pixel keys are inspected, without guessing the chosen quantizer key.
    QTransform transform;
    transform.scale(dpr, dpr);
    auto *set = engine->loadGlyphSet(transform);
    QJsonArray entries;
    if (!set) return entries;
    for (int x : {0, 16, 32, 48}) for (int y : {0, 16, 32, 48}) {
        QFixedPoint p; p.x = QFixed::fromFixed(x); p.y = QFixed::fromFixed(y);
        auto *g = set->getGlyph(gid, p);
        if (g) entries.append(QJsonObject{{"x26_6", x}, {"y26_6", y}, {"format", int(g->format)},
                                        {"width", int(g->width)}, {"height", int(g->height)},
                                        {"data_present", g->data != nullptr}});
    }
    return entries;
}
QString d2FileHash(const QString &name)
{
    QFile f(name); require(f.open(QIODevice::ReadOnly), "Cannot hash runtime component: " + name);
    return hash(f.readAll());
}
}

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    QFile log;
    int id = -1;
    try {
        const auto args = app.arguments();
        require(args.size() == 7, "Usage: d2_probe FONT OUT DPI DPR no|full control|guard");
        require(QGuiApplication::platformName() == "windows", "Native Windows QPA required");
        require(QString::fromLatin1(qVersion()) == "6.10.3", "D2 private ABI is pinned to Qt 6.10.3");
        bool okDpi = false, okDpr = false;
        const int dpi = args[3].toInt(&okDpi);
        const double dpr = args[4].toDouble(&okDpr);
        require(okDpi && (dpi == 96 || dpi == 144 || dpi == 192), "Invalid DPI");
        require(okDpr && (dpr == 1 || dpr == 1.25 || dpr == 1.5 || dpr == 2), "Invalid DPR");
        require(args[5] == "no" || args[5] == "full", "Invalid hint mode");
        require(args[6] == "control" || args[6] == "guard", "Invalid isolation mode");
        const bool guard = args[6] == "guard";
        require(QDir().mkpath(args[2]), "Cannot create D2 directory");
        log.setFileName(QDir(args[2]).filePath("d2.jsonl"));
        require(log.open(QIODevice::WriteOnly | QIODevice::NewOnly), "D2 evidence must not be overwritten");
        const Source source = sourceFont(args[1]);
        id = QFontDatabase::addApplicationFont(args[1]);
        require(id >= 0, "Cannot load unchanged D1 fixture");
        QImage device(8, 8, QImage::Format_ARGB32_Premultiplied);
        device.setDotsPerMeterX(qRound(dpi / 0.0254)); device.setDotsPerMeterY(qRound(dpi / 0.0254));
        device.setDevicePixelRatio(dpr);
        QFont query(source.family);
        query.setStyleName(QString()); query.setWeight(QFont::Normal); query.setPointSizeF(9);
        query.setHintingPreference(args[5] == "no" ? QFont::PreferNoHinting : QFont::PreferFullHinting);
        query.setStyleStrategy(QFont::StyleStrategy(QFont::NoFontMerging | QFont::PreferAntialias | QFont::NoSubpixelAntialias));
        query.setVariableAxis(QFont::Tag("wght"), float(499.006199));
        query.setVariableAxis(QFont::Tag("WDTH"), float(source.axes["WDTH"].defaultValue));
        query.setVariableAxis(QFont::Tag("HGHT"), float(source.axes["HGHT"].defaultValue));
        const QFont font(query, &device);
        const QRawFont raw = QRawFont::fromFont(font);
        verifyIdentity(raw, source);
        auto *base = QRawFontPrivate::get(raw)->fontEngine;
        require(base && base->type() == QFontEngine::Freetype, "Actual backend is not QFontEngineFT");
        auto *engine = static_cast<QFontEngineFT *>(base);
        const auto faceId = engine->faceId();
        auto *shared = QFreetypeFace::getFace(faceId);
        require(shared != nullptr, "Cannot retain existing shared face");
        const auto release = qScopeGuard([&] { shared->release(faceId); });
        require(shared->face == engine->non_locked_face(), "Inspection did not retain the same FT_Face");
        int major = 0, minor = 0, patch = 0;
        d2_FT_Library_Version(qt_getFreetype(), &major, &minor, &patch);
        require(major == FREETYPE_MAJOR && minor == FREETYPE_MINOR && patch == FREETYPE_PATCH,
                "Runtime FreeType does not match pinned headers; refuse intervention");
        const auto ids = raw.glyphIndexesForString("A");
        require(ids.size() == 1 && ids[0] != 0, "Expected one authored A glyph");
        const auto advances = raw.advancesForGlyphIndexes(ids);
        require(advances.size() == 1, "Missing baseline advance");
        const auto baseline = pathElements(raw.pathForGlyph(ids[0]));
        require(!baseline.isEmpty(), "Empty baseline path");
        QGlyphRun run; run.setRawFont(raw); run.setGlyphIndexes(ids); run.setPositions({QPointF(0, 0)});
        const auto runtime = QLibraryInfo::path(QLibraryInfo::BinariesPath);
        writeRecord(log, {{"record", "header"}, {"schema", 1}, {"source_commit", qEnvironmentVariable("GITHUB_SHA")},
                          {"input_sha256", source.sha256}, {"qt_version", qVersion()},
                          {"qt_gui_sha256", d2FileHash(QDir(runtime).filePath("Qt6Gui.dll"))},
                          {"freetype_version", QString("%1.%2.%3").arg(major).arg(minor).arg(patch)},
                          {"actual_backend", "QFontEngineFT"}, {"logical_dpi", dpi}, {"dpr", dpr},
                          {"hint", args[5]}, {"mode", args[6]}, {"cache_disabled", qEnvironmentVariableIntValue("QT_NO_FT_CACHE") != 0},
                          {"raw_pixel_size", raw.pixelSize()}, {"gid", int(ids[0])},
                          {"fixed_axes", QJsonObject{{"wght", double(float(499.006199))}, {"WDTH", 100}, {"HGHT", 100}}},
                          {"baseline_path", baseline}, {"baseline_advance", point(advances[0])},
                          {"baseline_state", d2State(shared).json()}, {"table_identity_exact", true},
                          {"scope", "PRIVATE_ABI_DIAGNOSTIC_NOT_PRODUCTION_FIX"}});
        const QList<QPointF> offsets{{0,0}, {.25,0}, {.5,0}, {.75,0}, {0,0}, {.75,0}, {.5,0}, {.25,0}, {0,0}, {0,.25}, {.25,.25}, {0,.25}};
        int changed = 0, isolatedMismatch = 0;
        QMap<QString, QByteArray> firstPixels;
        for (qsizetype i = 0; i < offsets.size(); ++i) {
            const auto cacheBefore = d2Cache(engine, ids[0], dpr);
            const auto stateBefore = d2State(shared).json();
            QImage image(qRound(128*dpr), qRound(128*dpr), QImage::Format_ARGB32_Premultiplied);
            require(!image.isNull(), "Cannot allocate D2 raster");
            image.setDotsPerMeterX(device.dotsPerMeterX()); image.setDotsPerMeterY(device.dotsPerMeterY());
            image.setDevicePixelRatio(dpr); image.fill(Qt::white);
            { QPainter painter(&image); require(painter.isActive(), "D2 painter failed");
              painter.setPen(Qt::black); painter.setRenderHint(QPainter::TextAntialiasing);
              painter.drawGlyphRun(QPointF(24, 40) + offsets[i], run); }
            const auto afterDraw = d2State(shared).json();
            const auto cacheAfter = d2Cache(engine, ids[0], dpr);
            const auto original = pathElements(raw.pathForGlyph(ids[0]));
            const auto beforeGuard = d2State(shared).json();
            const auto isolated = pathElements(guard ? d2IsolatedPath(raw, ids[0], engine) : raw.pathForGlyph(ids[0]));
            const auto afterGuard = d2State(shared).json();
            const auto originalReplay = pathElements(raw.pathForGlyph(ids[0]));
            const auto cacheAfterGuard = d2Cache(engine, ids[0], dpr);
            const auto currentAdvance = raw.advancesForGlyphIndexes(ids);
            require(currentAdvance == advances, "Advance changed");
            require(beforeGuard == afterGuard, "Isolation changed actual or cached transform state");
            require(originalReplay == original, "Original failure was not restored after isolation");
            require(cacheAfterGuard == cacheAfter, "Outline isolation changed cached glyph entries");
            changed += original != baseline;
            isolatedMismatch += isolated != baseline;
            const QByteArray pixels(reinterpret_cast<const char *>(image.constBits()), image.sizeInBytes());
            const QString key = QString("%1,%2").arg(offsets[i].x()).arg(offsets[i].y());
            if (firstPixels.contains(key)) require(firstPixels[key] == pixels, "Raster replay differs byte-for-byte");
            else firstPixels.insert(key, pixels);
            const QString png = QString("draw-%1.png").arg(i, 2, 10, QLatin1Char('0'));
            require(image.save(QDir(args[2]).filePath(png)), "Cannot save D2 PNG");
            QFile binary(QDir(args[2]).filePath(png + ".bin"));
            require(binary.open(QIODevice::WriteOnly | QIODevice::NewOnly)
                    && binary.write(pixels) == pixels.size(), "Cannot save D2 BGRA bytes");
            binary.close();
            writeRecord(log, {{"record", "observation"}, {"index", int(i)}, {"offset", point(offsets[i])},
                              {"before_draw", stateBefore}, {"after_draw", afterDraw},
                              {"before_guard", beforeGuard}, {"after_guard", afterGuard},
                              {"cache_before", cacheBefore}, {"cache_after", cacheAfter}, {"cache_after_guard", cacheAfterGuard},
                              {"original_path", original}, {"isolated_path", isolated}, {"original_replay", originalReplay},
                              {"advance", point(currentAdvance[0])}, {"pixel_sha256", hash(pixels)},
                              {"png", png}, {"width", image.width()}, {"height", image.height()}});
        }
        verifyIdentity(raw, source);
        require(!guard || isolatedMismatch == 0, "Scoped isolation did not restore exact cold path");
        writeRecord(log, {{"record", "summary"}, {"status", "DIAGNOSTIC_PASS_NOT_D1_ACCEPTANCE"},
                          {"observations", int(offsets.size())}, {"original_path_mismatches", changed},
                          {"isolated_path_mismatches", isolatedMismatch}, {"production_fix", false}});
        require(QFontDatabase::removeApplicationFont(id), "D2 fixture removal failed"); id = -1;
        return 0;
    } catch (const std::exception &e) {
        if (log.isOpen()) writeRecord(log, {{"record", "error"}, {"error", e.what()}});
        if (id >= 0) QFontDatabase::removeApplicationFont(id);
        std::fprintf(stderr, "%s\n", e.what()); return 1;
    }
}

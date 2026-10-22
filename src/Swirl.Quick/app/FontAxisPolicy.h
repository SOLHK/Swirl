#pragma once

#include <QString>
#include <QVariantList>
#include <QVariantMap>

// Pure policy: metadata discovery, persistence and bounded caching belong to
// FontManager. No font files, QFontDatabase calls or display state are read here.
namespace FontAxisPolicy {

struct Request {
    int weight = 400; // Qt 6 and OpenType both use the 1..1000 scale.
    double pixelSize = -1; // Qt logical pixels, never physical raster pixels.
    double pointSize = -1;
    double logicalDpi = 96;
    double devicePixelRatio = 1;
    QString family;
    QString role;
    bool manual = false;
    bool italic = false;
};

// Metadata has the same schema as FontManager::axesFor(): tag, minimum,
// maximum, defaultValue. Invalid or duplicate tags are excluded, rather than
// guessed. Unspecified/invalid coordinates retain the designer's defaults.
QVariantMap normalized(const QVariantList &metadata,
                       const QVariantMap &values = {});

// Automatic: preserves the requested design weight, derives opsz from points,
// and leaves other supported axes at their actual defaults. ital/slnt are not
// explicitly set in automatic mode, so QFont's style matching remains in charge.
// Manual: applies only coordinates belonging to this metadata, clamped to its
// ranges. Callers must scope manualValues to the selected family/resource.
QVariantMap resolve(const QVariantList &metadata, const Request &request,
                    const QVariantMap &manualValues = {});

} // namespace FontAxisPolicy

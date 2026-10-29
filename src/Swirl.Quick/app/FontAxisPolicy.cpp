#include "FontAxisPolicy.h"

#include <QMap>
#include <QSet>
#include <algorithm>
#include <cmath>
#include <limits>

namespace {
struct Axis {
    double minimum;
    double maximum;
    double defaultValue;
};

bool finiteNumber(const QVariant &input, double &value)
{
    bool ok = false;
    value = input.toDouble(&ok);
    // QFont's public axis coordinate is a float. Reject an unrepresentable
    // coordinate instead of converting it to infinity at the rendering boundary.
    return ok && std::isfinite(value)
        && std::abs(value) <= std::numeric_limits<float>::max();
}

bool validTag(const QString &tag)
{
    if (tag.size() != 4)
        return false;
    // OpenType tags contain four printable ASCII bytes. Checking the original
    // string prevents Unicode replacement during a later toLatin1() conversion.
    for (const QChar ch : tag) {
        if (ch.unicode() < 0x20 || ch.unicode() > 0x7e)
            return false;
    }
    return true;
}

QMap<QString, Axis> validatedAxes(const QVariantList &metadata)
{
    QMap<QString, Axis> result;
    QSet<QString> duplicateTags;
    for (const QVariant &entry : metadata) {
        const QVariantMap record = entry.toMap();
        const QString tag = record.value(QStringLiteral("tag")).toString();
        if (!validTag(tag) || duplicateTags.contains(tag))
            continue;
        Axis axis;
        if (!finiteNumber(record.value(QStringLiteral("minimum")), axis.minimum)
            || !finiteNumber(record.value(QStringLiteral("maximum")), axis.maximum)
            || !finiteNumber(record.value(QStringLiteral("defaultValue")), axis.defaultValue)
            || axis.minimum > axis.defaultValue || axis.defaultValue > axis.maximum) {
            continue;
        }
        if (result.contains(tag)) {
            // A real fvar axis is unique. Excluding ambiguous duplicates makes
            // the result independent of which conflicting record comes first.
            result.remove(tag);
            duplicateTags.insert(tag);
            continue;
        }
        result.insert(tag, axis);
    }
    return result;
}

QVariantMap coordinates(const QMap<QString, Axis> &axes, const QVariantMap &values)
{
    QVariantMap result;
    for (auto it = axes.cbegin(); it != axes.cend(); ++it) {
        double value = it->defaultValue;
        double supplied = 0;
        if (finiteNumber(values.value(it.key()), supplied))
            value = supplied;
        result.insert(it.key(), std::clamp(value, it->minimum, it->maximum));
    }
    return result;
}

double opticalPointSize(const FontAxisPolicy::Request &request)
{
    if (std::isfinite(request.pointSize) && request.pointSize > 0)
        return request.pointSize;
    if (std::isfinite(request.pixelSize) && request.pixelSize > 0
        && std::isfinite(request.logicalDpi) && request.logicalDpi > 0) {
        const double points = request.pixelSize * (72.0 / request.logicalDpi);
        if (std::isfinite(points) && points > 0)
            return points;
    }
    return -1;
}
} // namespace

QVariantMap FontAxisPolicy::normalized(const QVariantList &metadata,
                                       const QVariantMap &values)
{
    return coordinates(validatedAxes(metadata), values);
}

QVariantMap FontAxisPolicy::resolve(const QVariantList &metadata,
                                    const Request &request,
                                    const QVariantMap &manualValues)
{
    const auto axes = validatedAxes(metadata);
    if (request.manual)
        return coordinates(axes, manualValues);

    QVariantMap result = coordinates(axes, {});
    const QString weightTag = QStringLiteral("wght");
    if (const auto it = axes.constFind(weightTag);
        it != axes.cend() && request.weight >= 1 && request.weight <= 1000) {
        // Qt 6.10.3 QFont::Weight uses OpenType values directly. Remapping a
        // 400/500/600 design hierarchy around one global slider flattens it.
        result[weightTag] = std::clamp(double(request.weight), it->minimum, it->maximum);
    }

    const QString opticalTag = QStringLiteral("opsz");
    const double points = opticalPointSize(request);
    if (const auto it = axes.constFind(opticalTag); it != axes.cend() && points > 0) {
        // OpenType opsz is measured in typographic points. Qt Quick already
        // scales logical pixels by DPR; multiplying by DPR here applies that
        // scaling a second time and changes the intended optical size on moves.
        result[opticalTag] = std::clamp(points, it->minimum, it->maximum);
    }

    // Explicit defaults for style axes can force an italic/oblique QFont back
    // to upright. The existing font style and its matching fallback stay in Qt.
    result.remove(QStringLiteral("ital"));
    result.remove(QStringLiteral("slnt"));

    // family/role/italic/DPR are context, not a license to invent undocumented
    // HGHT, width or grade rules. There are currently no validated per-font
    // profiles. All other axes keep the values supplied by their font designer.
    return result;
}

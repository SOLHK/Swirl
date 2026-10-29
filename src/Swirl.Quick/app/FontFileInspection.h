#pragma once

#include <QFile>
#include <QHash>
#include <QRawFont>
#include <QSet>
#include <QVariantList>
#include <QtEndian>

// A bounded container/variation guard, not a complete OpenType sanitizer.
// All offsets in a TTC table directory are relative to the collection file.
namespace SwirlFontFile {
inline constexpr qint64 maximumBytes = 128LL * 1024 * 1024;
struct Table { quint32 offset = 0, size = 0; };
struct Face {
    QHash<QByteArray, Table> tables;
    QVariantList axes;
};
struct Inspection {
    QList<Face> faces;
    QString error;
    bool hvfOnly = false;
    bool valid() const { return error.isEmpty() && !faces.isEmpty(); }
};

inline QByteArray read(QFile &file, quint64 offset, quint64 size)
{
    const quint64 length = file.size();
    if (offset > length || size > length - offset || !file.seek(qint64(offset)))
        return {};
    return file.read(qint64(size));
}

inline Inspection inspect(QFile &file)
{
    Inspection result;
    auto invalid = [&](const QString &reason) {
        result.error = reason;
        file.seek(0);
        return result;
    };
    if (!file.isOpen() || file.size() < 12 || file.size() > maximumBytes)
        return invalid(QStringLiteral("Font container size is invalid."));
    auto u16 = [](const QByteArray &data, qsizetype at) { return qFromBigEndian<quint16>(data.constData() + at); };
    auto u32 = [](const QByteArray &data, qsizetype at) { return qFromBigEndian<quint32>(data.constData() + at); };
    auto s16 = [](const QByteArray &data, qsizetype at) { return qFromBigEndian<qint16>(data.constData() + at); };
    auto fixed = [](const QByteArray &data, qsizetype at) { return qFromBigEndian<qint32>(data.constData() + at) / 65536.0; };
    const auto header = read(file, 0, 12);
    if (header.size() != 12)
        return invalid(QStringLiteral("Font header is truncated."));
    QList<quint32> offsets;
    if (header.first(4) == "ttcf") {
        const auto version = u32(header, 4), count = u32(header, 8);
        if ((version != 0x10000 && version != 0x20000) || !count
            || count > 4096 || quint64(count) > quint64(file.size() - 12) / 4)
            return invalid(QStringLiteral("TTC face directory is invalid or exceeds the 4096-face resource bound."));
        const auto directory = read(file, 12, quint64(count) * 4);
        if (directory.size() != qsizetype(count) * 4)
            return invalid(QStringLiteral("TTC face offsets are truncated."));
        for (quint32 index = 0; index < count; ++index)
            offsets.append(u32(directory, index * 4));
    } else {
        offsets.append(0);
    }
    for (const auto offset : offsets) {
        const auto sfnt = read(file, offset, 12);
        if (sfnt.size() != 12)
            return invalid(QStringLiteral("SFNT header is truncated."));
        const auto signature = u32(sfnt, 0);
        if (signature != 0x10000 && signature != 0x4f54544f
            && signature != 0x74727565 && signature != 0x74797031)
            return invalid(QStringLiteral("SFNT signature is invalid."));
        const auto count = u16(sfnt, 4);
        const auto directory = read(file, quint64(offset) + 12, quint64(count) * 16);
        if (!count || directory.size() != qsizetype(count) * 16)
            return invalid(QStringLiteral("SFNT table directory is truncated."));
        Face face;
        for (int index = 0; index < count; ++index) {
            const auto tag = directory.mid(index * 16, 4);
            const Table table{u32(directory, index * 16 + 8), u32(directory, index * 16 + 12)};
            if (face.tables.contains(tag) || quint64(table.offset) > quint64(file.size())
                || quint64(table.size) > quint64(file.size()) - table.offset)
                return invalid(QStringLiteral("SFNT table is duplicated or outside the file."));
            face.tables.insert(tag, table);
        }
        const bool hvf = face.tables.contains("hvgl") || face.tables.contains("HVGL");
        if (hvf && !face.tables.contains("glyf") && !face.tables.contains("CFF ") && !face.tables.contains("CFF2"))
            result.hvfOnly = true;
        result.faces.append(face);
    }
    // Recognize the actual Apple-only format before asking a Windows/FreeType
    // engine to load it. Renaming the source to Swirl-VF.ttc is not conversion.
    if (result.hvfOnly)
        return invalid(QStringLiteral("Apple HVGL outlines require a verified standard OpenType conversion."));

    for (auto &face : result.faces) {
        if (face.tables.contains("fvar")) {
            const auto table = face.tables.value("fvar");
            const auto variable = read(file, table.offset, table.size);
            if (variable.size() != table.size || variable.size() < 16 || u32(variable, 0) != 0x10000)
                return invalid(QStringLiteral("fvar header is invalid."));
            const quint64 start = u16(variable, 4), count = u16(variable, 8), stride = u16(variable, 10);
            const quint64 instances = u16(variable, 12), instanceSize = u16(variable, 14);
            if (start < 16 || !count || stride < 20 || start > table.size || count * stride > table.size - start
                || (instances && (instanceSize < 4 + count * 4 || instances * instanceSize > table.size - start - count * stride)))
                return invalid(QStringLiteral("fvar records are truncated."));
            QSet<QByteArray> tags;
            for (quint64 index = 0; index < count; ++index) {
                const auto at = start + index * stride;
                const auto tag = variable.mid(at, 4);
                for (const auto ch : tag)
                    if (ch < 0x20 || ch > 0x7e)
                        return invalid(QStringLiteral("fvar axis tag is invalid."));
                const auto minimum = fixed(variable, at + 4), value = fixed(variable, at + 8), maximum = fixed(variable, at + 12);
                if (tags.contains(tag) || minimum > value || value > maximum)
                    return invalid(QStringLiteral("fvar axes have duplicate tags or invalid ranges."));
                tags.insert(tag);
                face.axes.append(QVariantMap{{"tag", QString::fromLatin1(tag)}, {"minimum", minimum},
                    {"defaultValue", value}, {"maximum", maximum}, {"hidden", bool(u16(variable, at + 16) & 1)}});
            }
        }
        if (face.tables.contains("avar")) {
            const auto table = face.tables.value("avar");
            const auto data = read(file, table.offset, table.size);
            if (data.size() != table.size || data.size() < 8 || (u32(data, 0) != 0x10000 && u32(data, 0) != 0x20000)
                || face.axes.isEmpty() || u16(data, 6) != face.axes.size())
                return invalid(QStringLiteral("avar header or axis count is invalid."));
            qsizetype at = 8;
            for (qsizetype axis = 0; axis < face.axes.size(); ++axis) {
                if (at > data.size() - 2)
                    return invalid(QStringLiteral("avar segment map is truncated."));
                const auto count = u16(data, at);
                at += 2;
                // An empty segment map requests default normalization. The
                // three mandatory anchors apply only to nonempty maps.
                if (!count)
                    continue;
                if (count < 3 || qsizetype(count) > (data.size() - at) / 4)
                    return invalid(QStringLiteral("avar axis map is incomplete."));
                int previousFrom = -16385, previousTo = -16385;
                bool negative = false, zero = false, positive = false;
                for (int index = 0; index < count; ++index, at += 4) {
                    const int from = s16(data, at), to = s16(data, at + 2);
                    if (from <= previousFrom || from < -16384 || from > 16384
                        || to < previousTo || to < -16384 || to > 16384)
                        return invalid(QStringLiteral("avar contains duplicate, unordered or nonmonotonic coordinates."));
                    negative |= from == -16384 && to == -16384;
                    zero |= from == 0 && to == 0;
                    positive |= from == 16384 && to == 16384;
                    previousFrom = from;
                    previousTo = to;
                }
                if (!negative || !zero || !positive)
                    return invalid(QStringLiteral("avar must preserve the -1, 0 and +1 anchors."));
            }
            if (u32(data, 0) == 0x20000 && data.size() - at < 8)
                return invalid(QStringLiteral("avar version 2 offsets are truncated."));
        }
    }
    file.seek(0);
    return result;
}

// Inspect the selected physical face, not QFont's requested family string.
// Compare both presence and bytes; a static fallback missing fvar/gvar cannot
// pass by matching only a subset. Large outline reads happen only on demand.
inline int matchingFace(const QRawFont &font, QFile &file, const Inspection &inspection)
{
    if (!font.isValid() || !inspection.valid())
        return -1;
    const QList<QByteArray> tags{"name", "cmap", "fvar", "avar", "maxp", "head", "hhea", "vhea",
        "OS/2", "post", "STAT", "hmtx", "vmtx", "glyf", "loca", "gvar", "CFF ", "CFF2",
        "HVAR", "MVAR", "GSUB", "GPOS"};
    QHash<QByteArray, QByteArray> actual;
    for (const auto &tag : tags)
        actual.insert(tag, font.fontTable(tag.constData()));
    for (qsizetype index = 0; index < inspection.faces.size(); ++index) {
        const auto &face = inspection.faces[index];
        if (!face.tables.contains("name") || !face.tables.contains("cmap"))
            continue;
        bool same = true;
        for (const auto &tag : tags) {
            const auto table = face.tables.value(tag);
            const auto &bytes = actual[tag];
            if (bytes.size() != table.size || (!face.tables.contains(tag) && !bytes.isEmpty())
                || (table.size && read(file, table.offset, table.size) != bytes)) {
                same = false;
                break;
            }
        }
        if (same)
            return int(index);
    }
    return -1;
}
} // namespace SwirlFontFile

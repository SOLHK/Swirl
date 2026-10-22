#pragma once
#include "ProxyNode.h"
#include <QByteArray>

// Import is a business operation. QML receives only redacted node summaries.
class NodeImporter {
public:
    struct Result { QList<ProxyNode> nodes; QString error,format,configurationFormat; QJsonObject configuration,executionConfiguration; int incompleteNodes=0; explicit operator bool() const { return error.isEmpty() && !nodes.isEmpty(); } };
    static constexpr qsizetype MaximumBytes = 4 * 1024 * 1024;
    static Result parse(const QByteArray &document);
    static QJsonObject strictJsonObject(const QByteArray &document);
};

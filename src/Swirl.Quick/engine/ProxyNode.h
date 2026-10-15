#pragma once
#include <QString>
#include <QVariantMap>
#include <QJsonObject>

// Engine-neutral node data. Protocol-specific serialization stays in the adapter.
struct ProxyNode {
    QString id, name, protocol, host, username, password, cipher, serverName, sourceId;
    // Private extension payload. Never returned by publicInfo() or to QML.
    QJsonObject parameters;
    // Encrypted provenance only. Neither raw source nor credentials enter QML.
    QJsonObject originalConfiguration;
    QString sourceFormat;
    QStringList conversionIssues;
    quint16 port = 0;
    static QString validate(const ProxyNode &node);
    static QStringList protocols();
    QVariantMap publicInfo() const;
};

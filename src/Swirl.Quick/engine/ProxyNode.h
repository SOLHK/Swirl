#pragma once
#include <QString>
#include <QVariantMap>

// Engine-neutral node data. Protocol-specific serialization stays in the adapter.
struct ProxyNode {
    QString id, name, protocol, host, username, password, cipher, serverName;
    quint16 port = 0;
    static QString validate(const ProxyNode &node);
    QVariantMap publicInfo() const;
};

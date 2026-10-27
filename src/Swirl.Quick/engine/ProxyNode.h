#pragma once
#include <QString>
#include <QVariantMap>
#include <QJsonObject>
#include <QByteArray>

// Engine-neutral node data. Protocol-specific serialization stays in the adapter.
struct ProxyNode {
    QString id, name, protocol, host, username, password, cipher, serverName, sourceId;
    // Private extension payload. Never returned by publicInfo() or to QML.
    QJsonObject parameters;
    // Encrypted provenance only. Neither raw source nor credentials enter QML.
    QJsonObject originalConfiguration;
    QString sourceFormat;
    // Provider's imported alias, independent of user-edited display names.
    // Persisted only inside the protected catalog; never returned to QML.
    QString providerAlias;
    QStringList conversionIssues;
    // Import policy notice only; never grants execution or certificate trust.
    // A source's insecure Trojan flag is retained in originalConfiguration,
    // while executable parameters explicitly keep certificate verification on.
    bool certificateVerificationEnforced = false;
    // Xray source is authoritative. Copies share the bounded document in memory;
    // the encrypted store deduplicates it. Never expose it or nativeOutbound to QML.
    QByteArray sourceDocument;
    int sourceNodeIndex = -1;
    QString importSource, parameterState, transportType, securityType, sourceFingerprint;
    QJsonObject nativeOutbound;
    QStringList runtimeIssues;
    bool nativeExecutable = false;
    bool isXray() const { return sourceFormat == QStringLiteral("xray-v2ray-json"); }
    quint16 port = 0;
    static QString validate(const ProxyNode &node);
    static QStringList protocols();
    QVariantMap publicInfo() const;
};

#pragma once
#include <QByteArray>
#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>

// Source adapters produce engine-neutral canonical nodes; they never execute
// subscription-wide DNS, routing, scripts, listeners or remote converters.
class SubscriptionNormalizer {
public:
    struct Result {
        bool handled=false;
        QJsonArray nodes;
        QList<QJsonObject> originals;
        QList<QStringList> issues;
        QString format,error,configurationFormat;
        QJsonObject configuration; // Unapplied source semantics; never silently discard them.
        QByteArray decodedDocument;
    };
    static Result normalize(const QByteArray &document,int depth=0);
};

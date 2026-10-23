#pragma once
#include "NodeImporter.h"

// One Rust parser/converter, called with the original bytes. Qt only projects
// its validated result for display and retains the source for future replay.
class XrayJsonBridge final {
public:
    static NodeImporter::Result parse(const QByteArray &bytes);
    static bool refreshNode(ProxyNode *node, QString *error = nullptr);
    static QString executableOutbound(const ProxyNode &node, QJsonObject *output);
};

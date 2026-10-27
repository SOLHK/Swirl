#pragma once
#include "ProxyNode.h"

// One offline projection into the Rust inspector. No protocol execution or
// option translation is implemented in this Qt boundary.
class NativeNodeBridge final {
public:
    static QString executableOutbound(const ProxyNode &node, QJsonObject *output);
};

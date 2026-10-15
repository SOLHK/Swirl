#pragma once
#include "ProxyEngine.h"
class SwirlProtocolRegistry {
public:
    static QString nativeNodeReason(const ProxyNode &node);
    static QString nativeSessionReason(const EngineStartOptions &options);
    static QVariantMap describe(const ProxyNode &node);
};

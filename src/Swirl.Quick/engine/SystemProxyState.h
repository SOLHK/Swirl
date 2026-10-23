#pragma once

#include <QJsonObject>
#include <QVariantMap>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

// Read-only observations, separate from SystemProxySession's ownership and
// recovery decisions. Neither an unknown value nor PAC means manual proxy off.
namespace SystemProxyState {
struct ManualProxy {
    QVariant winInet;
    QVariant registry;
    QVariant registryValuePresent;
    bool enabled() const { return winInet.toBool() || registry.toBool(); }
    bool differs() const {
        return winInet.isValid() && registry.isValid() && winInet.toBool() != registry.toBool();
    }
    QVariantMap diagnostics() const;
};

ManualProxy inspect(const QJsonObject &snapshot);

#ifdef Q_OS_WIN
// Uses the same bounded native reader for the real Internet Settings key and
// isolated registry fixtures. It never creates a key or writes a value.
QJsonObject readRegistry(HKEY root, const wchar_t *subKey, QString *error = nullptr);
#endif
}

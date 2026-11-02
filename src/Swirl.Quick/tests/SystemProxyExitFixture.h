#pragma once
#include <QCryptographicHash>
#include <QDir>
#include <QFileInfo>
#include <QString>

class EngineController;
class QQuickWindow;

// Shared, non-secret IPC/file names for the disposable native Windows test.
// The implementation is linked only into the SWIRL_UI_TESTS executable.
namespace SwirlSystemProxyExit {
inline QString readyPath(const QString &root) { return QDir(root).filePath("system-proxy-exit-ready.json"); }
inline QString finalPath(const QString &root) { return QDir(root).filePath("system-proxy-exit-final.json"); }
inline QString controlName(const QString &root) {
    const auto canonical=QFileInfo(root).canonicalFilePath();
    return QStringLiteral("Swirl.ProxyExit.")+QString::fromLatin1(
        QCryptographicHash::hash(canonical.toUtf8(),QCryptographicHash::Sha256).toHex());
}
bool environmentIsValid();
bool start(QQuickWindow *window,EngineController *controller);
}

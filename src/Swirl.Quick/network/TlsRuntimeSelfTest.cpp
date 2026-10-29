#include "TlsRuntimeSelfTest.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QSslSocket>
#include <iterator>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

int runTlsRuntimeSelfTest(const QString &reportPath)
{
    const bool available = QSslSocket::supportsSsl();
    const auto backend = QSslSocket::activeBackend();
    const auto version = QSslSocket::sslLibraryVersionString();
    const bool alpn = QSslSocket::isFeatureSupported(QSsl::SupportedFeature::ClientSideAlpn);
    QJsonObject report{{"schema",1},{"expected_version",QStringLiteral(SWIRL_OPENSSL_VERSION)},
                       {"backend",backend},{"runtime_version",version},{"client_alpn_supported",alpn},
                       {"qt_runtime_version",QString::fromLatin1(qVersion())},{"qt_build_version",QStringLiteral(QT_VERSION_STR)}};
    bool ownLibraries = true;
    QJsonObject libraries;
#ifdef Q_OS_WIN
    for (const auto &relative : {QStringLiteral("libssl-3-x64.dll"),QStringLiteral("libcrypto-3-x64.dll"),
                                QStringLiteral("Qt6Network.dll"),QStringLiteral("tls/qopensslbackend.dll")}) {
        const auto name = QFileInfo(relative).fileName();
        const auto module = GetModuleHandleW(reinterpret_cast<LPCWSTR>(name.utf16()));
        wchar_t path[32768]{};
        const DWORD length = module ? GetModuleFileNameW(module,path,DWORD(std::size(path))) : 0;
        const QFileInfo loaded(length && length < std::size(path) ? QString::fromWCharArray(path,int(length)) : QString());
        const auto expected = QFileInfo(QCoreApplication::applicationDirPath()+QLatin1Char('/')+relative);
        const bool inside = !loaded.canonicalFilePath().isEmpty()
            && loaded.canonicalFilePath().compare(expected.canonicalFilePath(),Qt::CaseInsensitive)==0;
        QFile file(loaded.absoluteFilePath());
        QCryptographicHash hash(QCryptographicHash::Sha256);
        const bool hashed = inside && file.open(QIODevice::ReadOnly) && hash.addData(&file);
        ownLibraries = ownLibraries && hashed;
        libraries[relative] = QJsonObject{{"inside_application",inside},
            {"sha256",hashed?QString::fromLatin1(hash.result().toHex()):QString()}};
    }
#else
    ownLibraries = false;
#endif
    const bool success = available && backend==QStringLiteral("openssl") && alpn && ownLibraries
        && QString::fromLatin1(qVersion())==QStringLiteral(QT_VERSION_STR)
        && version.startsWith(QStringLiteral("OpenSSL " SWIRL_OPENSSL_VERSION " "));
    report["libraries"] = libraries;
    report["success"] = success;
    report["network_requests"] = 0;
    QSaveFile file(reportPath);
    const auto bytes = QJsonDocument(report).toJson();
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes)!=bytes.size() || !file.commit()) return 2;
    return success ? 0 : 1;
}

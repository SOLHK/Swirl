#pragma once

#include <QByteArrayView>
#include <QJsonObject>
#include <QLibrary>
#include <QString>
#include <cstddef>

// The single boundary between Qt and the native core library. It accepts no
// node/configuration data: diagnostic output is limited to local build metadata.
class RustCoreLibrary final {
public:
    using Command = qintptr (*)(const unsigned char *, size_t, unsigned char *, size_t);

    struct PortableExecutable {
        bool valid = false;
        quint16 machine = 0;
        QString architecture;
        QString error;
    };

    static constexpr quint32 AbiVersion = 1;
    static constexpr qsizetype BuildInfoCapacity = 4096;
    static constexpr qsizetype MaximumPeHeaderBytes = 1024 * 1024;

    bool load(const QString &absolutePath = defaultLibraryPath());
    Command command() const { return m_command; }
    bool isReady() const { return m_command != nullptr; }
    QJsonObject diagnostics() const { return m_diagnostics; }
    QString errorString() const;

    static QString defaultLibraryPath();
    static QString expectedBuildId();
    static QString expectedSourceSha();
    static PortableExecutable inspectPortableExecutable(QByteArrayView header);

private:
    bool fail(const char *stage, const char *code, const QString &message);
    void nativeLoadDiagnostic(const QString &path);

    QLibrary m_library;
    Command m_command = nullptr;
    QJsonObject m_diagnostics;
    QString m_message;
};

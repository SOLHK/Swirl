#pragma once

#include <QByteArray>
#include <QByteArrayView>
#include <limits>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <wincrypt.h>
#endif

namespace SwirlDpapi {

inline QByteArray protect(QByteArrayView input, const wchar_t *description, QByteArrayView entropy = {})
{
#ifdef Q_OS_WIN
    if (input.size() < 0 || static_cast<quint64>(input.size()) > std::numeric_limits<DWORD>::max()
        || entropy.size() < 0 || static_cast<quint64>(entropy.size()) > std::numeric_limits<DWORD>::max()) {
        return {};
    }
    BYTE emptyByte = 0;
    DATA_BLOB src{static_cast<DWORD>(input.size()),
                  input.isEmpty() ? &emptyByte : reinterpret_cast<BYTE *>(const_cast<char *>(input.data()))};
    DATA_BLOB ent{static_cast<DWORD>(entropy.size()),
                  entropy.isEmpty() ? nullptr : reinterpret_cast<BYTE *>(const_cast<char *>(entropy.data()))};
    DATA_BLOB out{};
    if (!CryptProtectData(&src, description, entropy.isEmpty() ? nullptr : &ent,
                          nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &out)) {
        return {};
    }
    QByteArray bytes(reinterpret_cast<const char *>(out.pbData), out.cbData);
    if (out.pbData && out.cbData > 0)
        SecureZeroMemory(out.pbData, out.cbData);
    LocalFree(out.pbData);
    return bytes;
#else
    Q_UNUSED(input);
    Q_UNUSED(description);
    Q_UNUSED(entropy);
    return {}; // Fail closed: never fall back to plaintext outside Windows.
#endif
}

inline QByteArray unprotect(QByteArrayView input, QByteArrayView entropy = {})
{
#ifdef Q_OS_WIN
    if (input.isEmpty() || static_cast<quint64>(input.size()) > std::numeric_limits<DWORD>::max()
        || entropy.size() < 0 || static_cast<quint64>(entropy.size()) > std::numeric_limits<DWORD>::max()) {
        return {};
    }
    DATA_BLOB src{static_cast<DWORD>(input.size()),
                  reinterpret_cast<BYTE *>(const_cast<char *>(input.data()))};
    DATA_BLOB ent{static_cast<DWORD>(entropy.size()),
                  entropy.isEmpty() ? nullptr : reinterpret_cast<BYTE *>(const_cast<char *>(entropy.data()))};
    DATA_BLOB out{};
    if (!CryptUnprotectData(&src, nullptr, entropy.isEmpty() ? nullptr : &ent,
                            nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &out)) {
        return {};
    }
    QByteArray bytes(reinterpret_cast<const char *>(out.pbData), out.cbData);
    if (out.pbData && out.cbData > 0)
        SecureZeroMemory(out.pbData, out.cbData);
    LocalFree(out.pbData);
    return bytes;
#else
    Q_UNUSED(input);
    Q_UNUSED(entropy);
    return {};
#endif
}

} // namespace SwirlDpapi

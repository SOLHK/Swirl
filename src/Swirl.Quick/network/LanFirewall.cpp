#include "LanFirewall.h"
#include "../app/StoragePaths.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLockFile>
#include <QProcess>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSet>
#include <QStandardPaths>
#include <QThread>
#include <QUuid>
#include <algorithm>
#include <limits>
#include <iterator>

#ifdef SWIRL_LAN_FIREWALL_TESTS
#include <QNetworkInterface>
#include <QTemporaryDir>
#endif

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <objbase.h>
#include <oleauto.h>
#include <iphlpapi.h>
#include <netioapi.h>
#include <aclapi.h>
#include <netfw.h>
#include <netlistmgr.h>
#include <sddl.h>
#include <wincrypt.h>
#endif

namespace {
bool reject(QString *error, const QString &message) {
    if (error) *error = message;
    return false;
}
bool integer(const QJsonObject &object, const char *key, int minimum, int maximum) {
    const auto value = object.value(QLatin1String(key));
    return value.isDouble() && value.toDouble() >= minimum
        && value.toDouble() <= maximum && value.toDouble() == value.toInt();
}
QString cidr(const QString &text) {
    if (!text.contains('/')) return {};
    const auto subnet = QHostAddress::parseSubnet(text);
    if (subnet.first.protocol() != QAbstractSocket::IPv4Protocol || subnet.second < 0)
        return {};
    return subnet.first.toString() + '/' + QString::number(subnet.second);
}
QString normalizedAddresses(const QString &text) {
    QStringList list;
    for (const auto &entry : text.split(',')) {
        const auto part = entry.trimmed();
        const auto address = QHostAddress(part);
        const auto value = part.contains('/') ? cidr(part) : address.isNull() ? QString() : address.toString() + "/32";
        if (value.isEmpty()) return {};
        list.append(value);
    }
    std::sort(list.begin(), list.end());
    list.removeDuplicates();
    return list.join(',');
}
QString normalizedPorts(const QString &text) {
    QStringList values = text.split(',', Qt::SkipEmptyParts);
    for (auto &value : values) value = value.trimmed();
    std::sort(values.begin(), values.end());
    values.removeDuplicates();
    return values.join(',');
}
#ifdef Q_OS_WIN
QString readyPath(const QString &path, const QString &session) {
    return path + '.' + session + ".ready";
}
template<class T> struct Com {
    T *value = nullptr;
    ~Com() { if (value) value->Release(); }
    T *operator->() const { return value; }
    T **out() { return &value; }
};
struct Apartment {
    HRESULT result = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    ~Apartment() { if (SUCCEEDED(result)) CoUninitialize(); }
};
struct String {
    BSTR value;
    explicit String(const QString &text)
        : value(SysAllocStringLen(reinterpret_cast<const OLECHAR *>(text.utf16()), UINT(text.size()))) {}
    ~String() { SysFreeString(value); }
    operator BSTR() const { return value; }
};
QString processStamp(HANDLE process) {
    FILETIME created{}, ended{}, kernel{}, user{};
    if (!GetProcessTimes(process, &created, &ended, &kernel, &user)) return {};
    return QString::number((quint64(created.dwHighDateTime) << 32) | created.dwLowDateTime);
}
QString processPath(HANDLE process) {
    wchar_t path[32768]{};
    DWORD length = DWORD(std::size(path));
    if (!QueryFullProcessImageNameW(process, 0, path, &length)) return {};
    return QDir::fromNativeSeparators(QString::fromWCharArray(path, int(length)));
}
bool ownerAlive(const QJsonObject &record) {
    HANDLE process = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                                 FALSE, DWORD(record.value("owner_pid").toDouble()));
    if (!process) return GetLastError() != ERROR_INVALID_PARAMETER;
    const auto stamp = processStamp(process);
    const auto wait = WaitForSingleObject(process, 0);
    const bool alive = stamp.isEmpty() || wait == WAIT_FAILED
        || (stamp == record.value("owner_creation").toString() && wait == WAIT_TIMEOUT);
    CloseHandle(process);
    return alive;
}
QByteArray crypt(const QByteArray &input, bool decrypt) {
    DATA_BLOB source{DWORD(input.size()), reinterpret_cast<BYTE *>(const_cast<char *>(input.constData()))}, output{};
    QByteArray purpose("Swirl.LanFirewall.v1");
    DATA_BLOB entropy{DWORD(purpose.size()), reinterpret_cast<BYTE *>(purpose.data())};
    const bool ok = decrypt
        ? CryptUnprotectData(&source, nullptr, &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &output)
        : CryptProtectData(&source, L"Swirl LAN firewall recovery", &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &output);
    if (!ok) return {};
    QByteArray result(reinterpret_cast<char *>(output.pbData), output.cbData);
    SecureZeroMemory(output.pbData, output.cbData);
    LocalFree(output.pbData);
    return result;
}
bool secureDirectory(const QString &path) {
    // This dedicated directory has no unrelated user files. Refuse junctions
    // and symlinks before creating or tightening its current-user ACL.
    QString existing = QFileInfo(path).absoluteFilePath();
    while (!existing.isEmpty()) {
        const auto native = QDir::toNativeSeparators(existing);
        const auto attributes = GetFileAttributesW(reinterpret_cast<LPCWSTR>(native.utf16()));
        if (attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return false;
        const auto parent = QFileInfo(existing).absolutePath();
        if (parent == existing) break;
        existing = parent;
    }
    if (!QDir().mkpath(path)) return false;
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    DWORD size = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &size);
    QByteArray bytes(int(size), Qt::Uninitialized);
    const bool read = size && GetTokenInformation(token, TokenUser, bytes.data(), size, &size);
    CloseHandle(token);
    if (!read) return false;
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER *>(bytes.data())->User.Sid, &sid)) return false;
    const QString sddl = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;"
        + QString::fromWCharArray(sid) + ')';
    LocalFree(sid);
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(reinterpret_cast<LPCWSTR>(sddl.utf16()), SDDL_REVISION_1, &descriptor, nullptr)) return false;
    const auto native = QDir::toNativeSeparators(path);
    // Apply the ACL through a non-following directory handle, so a replacement
    // reparse point cannot redirect a privileged ACL write to another object.
    HANDLE directory=CreateFileW(reinterpret_cast<LPCWSTR>(native.utf16()),READ_CONTROL|WRITE_DAC,
        FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    BY_HANDLE_FILE_INFORMATION information{};PACL acl=nullptr;BOOL present=FALSE,defaulted=FALSE;
    const bool safe=directory!=INVALID_HANDLE_VALUE&&GetFileInformationByHandle(directory,&information)
        &&!(information.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)
        &&GetSecurityDescriptorDacl(descriptor,&present,&acl,&defaulted)&&present;
    const bool result=safe&&SetSecurityInfo(directory,SE_FILE_OBJECT,DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,nullptr,nullptr,acl,nullptr)==ERROR_SUCCESS;
    if(directory!=INVALID_HANDLE_VALUE)CloseHandle(directory);
    LocalFree(descriptor);
    return result;
}
QJsonObject readRecord(const QString &path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() <= 0 || file.size() > 65536) return {};
    auto plain = crypt(file.readAll(), true);
    const auto result = QJsonDocument::fromJson(plain).object();
    plain.fill(0);
    return result;
}
bool writeRecord(const QString &path, const QJsonObject &record) {
    auto plain = QJsonDocument(record).toJson(QJsonDocument::Compact);
    const auto encrypted = crypt(plain, false);
    plain.fill(0);
    QSaveFile file(path);
    return !encrypted.isEmpty() && file.open(QIODevice::WriteOnly)
        && file.write(encrypted) == encrypted.size() && file.commit();
}
QString hresultText(HRESULT hr) {
    return QStringLiteral("0x%1").arg(quint32(hr), 8, 16, QLatin1Char('0'));
}
QString hrError(const char *stage, HRESULT hr) {
    return QStringLiteral("Windows LAN %1 失败（%2）；未放宽安全配置。")
        .arg(QString::fromUtf8(stage), hresultText(hr));
}
QString guidString(const GUID &guid) {
    wchar_t text[40]{};
    return StringFromGUID2(guid, text, int(std::size(text)))
        ? QString::fromWCharArray(text).toLower() : QString();
}
QJsonObject adapterSnapshot(const QString &ip, QString *error) {
    ULONG size = 15000;
    QByteArray bytes(int(size), Qt::Uninitialized);
    ULONG code = GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER,
        nullptr, reinterpret_cast<IP_ADAPTER_ADDRESSES *>(bytes.data()), &size);
    if (code == ERROR_BUFFER_OVERFLOW && size <= 1024 * 1024) {
        bytes.resize(int(size));
        code = GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER,
            nullptr, reinterpret_cast<IP_ADAPTER_ADDRESSES *>(bytes.data()), &size);
    }
    if (code != NO_ERROR) { reject(error, QStringLiteral("无法读取 Windows 接口地址。")); return {}; }
    QJsonObject selected;
    QJsonArray hosts;
    for (auto *adapter = reinterpret_cast<IP_ADAPTER_ADDRESSES *>(bytes.data()); adapter; adapter = adapter->Next) {
        for (auto *entry = adapter->FirstUnicastAddress; entry; entry = entry->Next) {
            if (!entry->Address.lpSockaddr) continue;
            QString text;
            const auto family = entry->Address.lpSockaddr->sa_family;
            if (family == AF_INET) {
                const auto *address = reinterpret_cast<sockaddr_in *>(entry->Address.lpSockaddr);
                text = QHostAddress(ntohl(address->sin_addr.s_addr)).toString();
            } else if (family == AF_INET6) {
                const auto *address = reinterpret_cast<sockaddr_in6 *>(entry->Address.lpSockaddr);
                // Scope is irrelevant for protecting the host address itself;
                // Rust denies link-local and scoped targets before dispatch.
                Q_IPV6ADDR bytes{};
                std::copy_n(address->sin6_addr.u.Byte, 16, bytes.c);
                text = QHostAddress(bytes).toString();
            } else continue;
            if (!hosts.contains(text)) hosts.append(text);
            if (family != AF_INET || text != ip) continue;
            if (!selected.isEmpty() || adapter->OperStatus != IfOperStatusUp
                || adapter->IfType == IF_TYPE_SOFTWARE_LOOPBACK || adapter->IfType == IF_TYPE_TUNNEL
                || entry->DadState != IpDadStatePreferred || entry->OnLinkPrefixLength < 1 || entry->OnLinkPrefixLength > 32) {
                reject(error, QStringLiteral("监听地址重复、接口未就绪或属于隧道接口。")); return {};
            }
            GUID guid{};
            const auto rawGuid = QString::fromLatin1(adapter->AdapterName);
            if (FAILED(CLSIDFromString(reinterpret_cast<LPCOLESTR>(rawGuid.utf16()), &guid))) {
                reject(error, QStringLiteral("无法确认 LAN 接口身份。")); return {};
            }
            selected = {{"interface_guid", guidString(guid)}, {"interface_index", int(adapter->IfIndex)},
                {"interface_name", QString::fromWCharArray(adapter->FriendlyName)}, {"listen_ip", ip},
                {"prefix", int(entry->OnLinkPrefixLength)}};
        }
    }
    if (selected.isEmpty()) { reject(error, QStringLiteral("指定的局域网 IPv4 地址已不在本机接口上。")); return {}; }
    if (hosts.size()>128) { reject(error, QStringLiteral("本机地址清单超过 LAN 安全上限，未截断宿主机访问保护。")); return {}; }
    Com<INetworkListManager> manager;
    auto hr = CoCreateInstance(CLSID_NetworkListManager, nullptr, CLSCTX_ALL, IID_INetworkListManager,
                              reinterpret_cast<void **>(manager.out()));
    if (FAILED(hr)) { reject(error, hrError("网络类别读取", hr)); return {}; }
    Com<IEnumNetworkConnections> connections;
    hr = manager->GetNetworkConnections(connections.out());
    if (FAILED(hr)) { reject(error, hrError("接口类别读取", hr)); return {}; }
    int profile = 0;
    for (;;) {
        Com<INetworkConnection> connection;
        ULONG fetched = 0;
        hr = connections->Next(1, connection.out(), &fetched);
        if (hr == S_FALSE) break;
        if (FAILED(hr) || fetched != 1) { reject(error, hrError("接口类别枚举", hr)); return {}; }
        GUID guid{};
        if (FAILED(connection->GetAdapterId(&guid))) { reject(error, QStringLiteral("网络接口身份读取失败。")); return {}; }
        if (guidString(guid) != selected.value("interface_guid").toString()) continue;
        Com<INetwork> network;
        NLM_NETWORK_CATEGORY category{};
        VARIANT_BOOL connected = VARIANT_FALSE;
        if (FAILED(connection->get_IsConnected(&connected)) || connected != VARIANT_TRUE
            || FAILED(connection->GetNetwork(network.out())) || FAILED(network->GetCategory(&category))) {
            reject(error, QStringLiteral("无法确认所选接口的网络类别，拒绝开放监听。")); return {};
        }
        const int next = category == NLM_NETWORK_CATEGORY_PRIVATE ? NET_FW_PROFILE2_PRIVATE
            : category == NLM_NETWORK_CATEGORY_DOMAIN_AUTHENTICATED ? NET_FW_PROFILE2_DOMAIN : 0;
        if (!next || (profile && profile != next)) { reject(error, QStringLiteral("局域网代理仅允许专用或已认证域网络，公共网络不能启用。")); return {}; }
        profile = next;
    }
    if (!profile) { reject(error, QStringLiteral("未找到可信网络类别，拒绝开放监听。")); return {}; }
    selected.insert("profile", profile);
    QStringList orderedHosts;for(const auto &host:hosts)orderedHosts.append(host.toString());std::sort(orderedHosts.begin(),orderedHosts.end());
    selected.insert("host_addresses", QJsonArray::fromStringList(orderedHosts));
    return selected;
}
// Only fixed labels, numeric enums, lengths and booleans enter diagnostics.
// Never serialize a journal, BSTR, interface alias or application path here.
struct ComCall {
    QString operation, property, valueType, source = QStringLiteral("native_hresult"), reason;
    QJsonObject summary;
    QJsonArray secondaryFailures;
    HRESULT hr = S_OK;
    void set(const char *op, const char *prop, HRESULT result, const char *type,
             const QJsonObject &safeSummary = {}, const char *origin = "native_hresult",
             const char *why = "") {
        operation = QString::fromLatin1(op); property = QString::fromLatin1(prop);
        hr = result; valueType = QString::fromLatin1(type); summary = safeSummary;
        source = QString::fromLatin1(origin); reason = QString::fromLatin1(why);
    }
    QJsonObject json() const {
        return {{"operation", operation}, {"property", property}, {"hresult", hresultText(hr)},
                {"hresult_source", source}, {"value_type", valueType},
                {"value_summary", summary}, {"reason", reason}, {"secondary_failures", secondaryFailures}};
    }
    void releaseFailure(const char *prop, HRESULT result) {
        secondaryFailures.append(QJsonObject{{"operation", "VariantClear"}, {"property", QLatin1String(prop)},
            {"hresult", hresultText(result)}, {"hresult_source", "native_hresult"}});
    }
};
QJsonObject textSummary(const QString &text) {
    return {{"utf16_length", double(text.size())}, {"empty", text.isEmpty()},
            {"contains_nul", text.contains(QChar(u'\0'))}, {"redacted", true}};
}
QJsonObject ruleSummary(const QJsonObject &record) {
    const auto application = QDir::toNativeSeparators(record.value("application").toString());
    return {{"protocol", record.value("protocol").toInt()}, {"profiles", record.value("profiles").toInt()},
            {"enabled", record.value("enabled").toBool()}, {"edge_traversal", record.value("edge_traversal").toBool()},
            {"application_length", double(application.size())},
            {"application_absolute", QDir::isAbsolutePath(application)},
            {"application_native_separators", !application.contains('/')},
            {"interface_count", record.value("interfaces").toArray().size()}, {"redacted", true}};
}
bool firewall(Com<INetFwPolicy2> &policy, Com<INetFwRules> &rules, QString *error,
              ComCall *diagnostic = nullptr) {
    ComCall call;
    auto hr = CoCreateInstance(CLSID_NetFwPolicy2, nullptr, CLSCTX_INPROC_SERVER, IID_INetFwPolicy2,
                              reinterpret_cast<void **>(policy.out()));
    call.set("CoCreateInstance", "FirewallPolicy", hr, "INetFwPolicy2*");
    if (SUCCEEDED(hr)) {
        hr = policy->get_Rules(rules.out());
        call.set("INetFwPolicy2::get_Rules", "Rules", hr, "INetFwRules*");
    }
    if (diagnostic) *diagnostic = call;
    return SUCCEEDED(hr) || reject(error, hrError(qPrintable(call.operation), hr));
}
bool profileEnabled(INetFwPolicy2 *policy, int profile, QString *error) {
    VARIANT_BOOL enabled = VARIANT_FALSE, blocked = VARIANT_FALSE;
    const auto type = NET_FW_PROFILE_TYPE2(profile);
    auto hr = policy->get_FirewallEnabled(type, &enabled);
    if (SUCCEEDED(hr)) hr = policy->get_BlockAllInboundTraffic(type, &blocked);
    NET_FW_ACTION inbound = NET_FW_ACTION_ALLOW;
    if (SUCCEEDED(hr)) hr = policy->get_DefaultInboundAction(type, &inbound);
    NET_FW_MODIFY_STATE modify{};
    if (SUCCEEDED(hr)) hr = policy->get_LocalPolicyModifyState(&modify);
    if (FAILED(hr)) return reject(error, hrError("防火墙策略读取", hr));
    if (enabled != VARIANT_TRUE || blocked == VARIANT_TRUE || inbound != NET_FW_ACTION_BLOCK
        || modify != NET_FW_MODIFY_STATE_OK)
        return reject(error, QStringLiteral("所选网络必须启用防火墙、默认阻止入站且允许精确规则；未更改系统防火墙设置。"));
    return true;
}
QJsonObject ruleSnapshot(INetFwRule *rule, ComCall *failure = nullptr) {
    ComCall local;
    auto &call = failure ? *failure : local;
    if (!rule) {
        call.set("ruleSnapshot", "Rule", E_POINTER, "INetFwRule*", {}, "local_validation", "null_interface");
        return {};
    }
    QJsonObject result;
    const auto read = [&](const char *op, const char *prop, HRESULT hr, const char *type) {
        call.set(op, prop, hr, type);
        return SUCCEEDED(hr);
    };
    const auto string = [&](const char *key, const char *prop, const char *op, auto getter) {
        BSTR text = nullptr;
        const auto hr = (rule->*getter)(&text);
        if (SUCCEEDED(hr))
            result.insert(QLatin1String(key), QString::fromWCharArray(text ? text : L"", int(SysStringLen(text))));
        SysFreeString(text);
        return read(op, prop, hr, "BSTR");
    };
    if (!string("name", "Name", "INetFwRule::get_Name", &INetFwRule::get_Name)
        || !string("description", "Description", "INetFwRule::get_Description", &INetFwRule::get_Description)
        || !string("group", "Grouping", "INetFwRule::get_Grouping", &INetFwRule::get_Grouping)
        || !string("application", "ApplicationName", "INetFwRule::get_ApplicationName", &INetFwRule::get_ApplicationName)
        || !string("local_addresses", "LocalAddresses", "INetFwRule::get_LocalAddresses", &INetFwRule::get_LocalAddresses)
        || !string("remote_addresses", "RemoteAddresses", "INetFwRule::get_RemoteAddresses", &INetFwRule::get_RemoteAddresses)
        || !string("local_ports", "LocalPorts", "INetFwRule::get_LocalPorts", &INetFwRule::get_LocalPorts)
        || !string("remote_ports", "RemotePorts", "INetFwRule::get_RemotePorts", &INetFwRule::get_RemotePorts)
        || !string("interface_types", "InterfaceTypes", "INetFwRule::get_InterfaceTypes", &INetFwRule::get_InterfaceTypes)
        || !string("service", "ServiceName", "INetFwRule::get_ServiceName", &INetFwRule::get_ServiceName)) return {};
    long protocol = 0, profiles = 0;
    NET_FW_RULE_DIRECTION direction{};
    NET_FW_ACTION action{};
    VARIANT_BOOL enabled{}, edge{};
    if (!read("INetFwRule::get_Protocol", "Protocol", rule->get_Protocol(&protocol), "LONG")
        || !read("INetFwRule::get_Profiles", "Profiles", rule->get_Profiles(&profiles), "LONG")
        || !read("INetFwRule::get_Direction", "Direction", rule->get_Direction(&direction), "NET_FW_RULE_DIRECTION")
        || !read("INetFwRule::get_Action", "Action", rule->get_Action(&action), "NET_FW_ACTION")
        || !read("INetFwRule::get_Enabled", "Enabled", rule->get_Enabled(&enabled), "VARIANT_BOOL")
        || !read("INetFwRule::get_EdgeTraversal", "EdgeTraversal", rule->get_EdgeTraversal(&edge), "VARIANT_BOOL")) return {};
    if ((enabled != VARIANT_TRUE && enabled != VARIANT_FALSE) || (edge != VARIANT_TRUE && edge != VARIANT_FALSE)) {
        call.set("ruleSnapshot::validateBoolean", enabled != VARIANT_TRUE && enabled != VARIANT_FALSE
                 ? "Enabled" : "EdgeTraversal", E_INVALIDARG, "VARIANT_BOOL",
                 {}, "local_validation", "noncanonical_boolean");
        return {};
    }
    result.insert("protocol", int(protocol)); result.insert("profiles", int(profiles));
    result.insert("direction", int(direction)); result.insert("action", int(action));
    result.insert("enabled", enabled == VARIANT_TRUE); result.insert("edge_traversal", edge == VARIANT_TRUE);
    VARIANT interfaces; VariantInit(&interfaces);
    bool complete = read("INetFwRule::get_Interfaces", "Interfaces", rule->get_Interfaces(&interfaces), "VARIANT");
    QJsonArray aliases;
    if (complete && (interfaces.vt != (VT_ARRAY | VT_VARIANT) || !interfaces.parray
                     || SafeArrayGetDim(interfaces.parray) != 1)) {
        call.set("ruleSnapshot::validateInterfaces", "Interfaces", E_INVALIDARG, "VARIANT",
                 {{"variant_type", int(interfaces.vt)}, {"array_present", interfaces.parray != nullptr}},
                 "local_validation", "invalid_array_shape");
        complete = false;
    }
    LONG low = 0, high = -1;
    VARTYPE elementType = VT_EMPTY;
    if (complete) complete = read("SafeArrayGetVartype", "Interfaces",
                                  SafeArrayGetVartype(interfaces.parray, &elementType), "VARTYPE");
    if (complete && elementType != VT_VARIANT) {
        call.set("ruleSnapshot::validateInterfaces", "Interfaces", E_INVALIDARG, "VARTYPE",
                 {{"element_type", int(elementType)}}, "local_validation", "invalid_element_type");
        complete = false;
    }
    if (complete) complete = read("SafeArrayGetLBound", "Interfaces", SafeArrayGetLBound(interfaces.parray, 1, &low), "LONG");
    if (complete) complete = read("SafeArrayGetUBound", "Interfaces", SafeArrayGetUBound(interfaces.parray, 1, &high), "LONG");
    const qint64 count = qint64(high) - qint64(low) + 1;
    if (complete && (count < 1 || count > 64)) {
        call.set("ruleSnapshot::validateInterfaces", "Interfaces", E_INVALIDARG, "SAFEARRAY(VARIANT)",
                 {{"count", double(count)}}, "local_validation", "invalid_array_bounds");
        complete = false;
    }
    for (qint64 offset = 0; complete && offset < count; ++offset) {
        LONG index = LONG(qint64(low) + offset);
        VARIANT item; VariantInit(&item);
        complete = read("SafeArrayGetElement", "Interfaces", SafeArrayGetElement(interfaces.parray, &index, &item), "VARIANT");
        if (complete && item.vt != VT_BSTR) {
            call.set("ruleSnapshot::validateInterfaceElement", "Interfaces", E_INVALIDARG, "VARIANT",
                     {{"variant_type", int(item.vt)}, {"index", double(offset)}},
                     "local_validation", "non_string_element");
            complete = false;
        }
        if (complete) aliases.append(QString::fromWCharArray(item.bstrVal ? item.bstrVal : L"", int(SysStringLen(item.bstrVal))));
        const auto clear = VariantClear(&item);
        if (FAILED(clear)) {
            if (complete) call.set("VariantClear", "Interfaces.Element", clear, "VARIANT");
            else call.releaseFailure("Interfaces.Element", clear);
            complete = false;
        }
    }
    const auto clear = VariantClear(&interfaces);
    if (FAILED(clear)) {
        if (complete) call.set("VariantClear", "Interfaces", clear, "VARIANT");
        else call.releaseFailure("Interfaces", clear);
        complete = false;
    }
    if (!complete) return {};
    result.insert("interfaces", aliases);
    // Preserve the pre-existing Windows-equivalent comparisons: path separators
    // and case; numeric IPv4 /32 spelling; unordered address and local-port lists.
    result["application"] = QDir::fromNativeSeparators(result.value("application").toString()).toLower();
    const auto localAddresses = normalizedAddresses(result.value("local_addresses").toString());
    const auto localSubnet = QHostAddress::parseSubnet(localAddresses);
    result["local_addresses"] = !localAddresses.contains(',') && localSubnet.second == 32
        ? localSubnet.first.toString() : QString();
    result["remote_addresses"] = normalizedAddresses(result.value("remote_addresses").toString());
    result["local_ports"] = normalizedPorts(result.value("local_ports").toString());
    return result;
}
struct RuleObservation {
    enum class Presence { Absent, Present, Unknown };
    Presence presence = Presence::Unknown;
    QJsonObject snapshot;
    ComCall call;
    bool owned = false;
    QJsonArray mismatches;
};
RuleObservation observeRule(INetFwRules *rules, const QJsonObject &expected) {
    RuleObservation result;
    const auto text = expected.value("name").toString();
    const String name(text);
    if (!name.value) {
        result.call.set("SysAllocStringLen", "Name", E_OUTOFMEMORY, "BSTR", textSummary(text), "derived_from_null");
        return result;
    }
    Com<INetFwRule> current;
    const auto hr = rules->Item(name, current.out());
    result.call.set("INetFwRules::Item", "Name", hr, "BSTR", textSummary(text));
    // The API documents exactly this result as absence; all other failures
    // remain unknown, even if the preceding Add or Remove returned success.
    if (hr == HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)) {
        result.presence = RuleObservation::Presence::Absent;
        return result;
    }
    if (FAILED(hr) || !current.value) {
        if (SUCCEEDED(hr)) result.call.reason = QStringLiteral("null_interface");
        return result;
    }
    result.presence = RuleObservation::Presence::Present;
    ComCall snapshotCall;
    result.snapshot = ruleSnapshot(current.value, &snapshotCall);
    if (result.snapshot.isEmpty()) { result.call = snapshotCall; return result; }
    result.owned = result.snapshot == expected;
    // Only constant field names, never values, describe an ownership mismatch.
    const char *keys[] = {"name", "description", "group", "application", "protocol", "local_ports",
        "remote_ports", "local_addresses", "remote_addresses", "profiles", "interface_types", "interfaces",
        "direction", "action", "enabled", "edge_traversal", "service"};
    for (const auto *key : keys)
        if (result.snapshot.value(QLatin1String(key)) != expected.value(QLatin1String(key)))
            result.mismatches.append(QLatin1String(key));
    if (!result.owned && result.mismatches.isEmpty()) result.mismatches.append("record_shape");
    return result;
}
struct RuleDiagnostic {
    ComCall call;
    bool addAttempted = false, addSucceeded = false;
    QString persisted = QStringLiteral("not_added"), ownership = QStringLiteral("not_applicable");
    QString recovery = QStringLiteral("none");
    QJsonValue present = QJsonValue::Null;
    bool cleanupRequired = false, partialPossible = false;
    QJsonObject verification;
    QJsonObject addResult;
    void observe(const RuleObservation &observed) {
        verification = observed.call.json();
        verification.insert("snapshot_complete", !observed.snapshot.isEmpty());
        verification.insert("mismatched_properties", observed.mismatches);
        if (observed.presence == RuleObservation::Presence::Absent) {
            persisted = "absent"; ownership = "not_applicable"; present = false;
            cleanupRequired = false; partialPossible = false; recovery = "none";
        } else {
            present = observed.presence == RuleObservation::Presence::Present ? QJsonValue(true) : QJsonValue(QJsonValue::Null);
            cleanupRequired = true; partialPossible = true;
            if (observed.snapshot.isEmpty()) {
                persisted = "unknown"; ownership = "unknown"; recovery = "preserve_journal_retry_read";
            } else {
                ownership = observed.owned ? "owned" : "mismatch";
                persisted = addSucceeded ? (observed.owned ? "present_owned" : "present_mismatch") : "present";
                recovery = observed.owned ? "owned_cleanup_after_revalidation" : "preserve_journal_admin_review";
            }
        }
    }
    QJsonObject json() const {
        auto result = call.json();
        result.insert("add_attempted", addAttempted); result.insert("add_succeeded", addSucceeded);
        result.insert("persisted_rule_state", persisted); result.insert("rule_present", present);
        result.insert("ownership_state", ownership); result.insert("cleanup_required", cleanupRequired);
        result.insert("partial_persistence_possible", partialPossible); result.insert("recovery_action", recovery);
        result.insert("verification", verification);
        if (addAttempted) result.insert("add_result", addResult);
        return result;
    }
};
QString diagnosticError(const QString &message, const QJsonObject &evidence) {
    return message + ' ' + QString::fromUtf8(QJsonDocument(evidence).toJson(QJsonDocument::Compact));
}
bool ruleFailure(const RuleDiagnostic &context, QString *error, QJsonObject *diagnostic,
                 const QString &message = {}) {
    const auto evidence = context.json();
    if (diagnostic) *diagnostic = evidence;
    return reject(error, diagnosticError(message.isEmpty()
        ? hrError(qPrintable(context.call.operation), context.call.hr) : message, evidence));
}
bool addAndObserve(INetFwRules *rules, INetFwRule *rule, const QJsonObject &record,
                   RuleDiagnostic &context, QString *error, QJsonObject *diagnostic) {
    context.addAttempted = true;
    const auto hr = rules->Add(rule);
    context.addSucceeded = SUCCEEDED(hr);
    auto summary = ruleSummary(record);
    summary.insert("interface_pointer_present", rule != nullptr);
    context.call.set("INetFwRules::Add", "Rule", hr, "INetFwRule*", summary);
    context.addResult = context.call.json();
    const auto observed = observeRule(rules, record);
    context.observe(observed);
    if (FAILED(hr)) return ruleFailure(context, error, diagnostic);
    if (!observed.owned) {
        // Keep the successful Add HRESULT separate from the actual read failure.
        // A property mismatch is not an invented COM failure.
        if (FAILED(observed.call.hr)) context.call = observed.call;
        else context.call.reason = observed.snapshot.isEmpty()
            ? QStringLiteral("persisted_state_unconfirmed") : QStringLiteral("snapshot_mismatch");
        return ruleFailure(context, error, diagnostic,
                           QStringLiteral("防火墙规则回读与请求不同或无法确认，恢复记录已保留。"));
    }
    if (diagnostic) *diagnostic = context.json();
    return true;
}
bool applyRule(INetFwRules *rules, const QJsonObject &record, QString *error,
               QJsonObject *diagnostic = nullptr) {
    RuleDiagnostic context;
    const auto before = observeRule(rules, record);
    if (before.presence != RuleObservation::Presence::Absent) {
        context.call = before.call;
        context.observe(before);
        context.call.reason = before.presence == RuleObservation::Presence::Present
            ? QStringLiteral("name_conflict") : QStringLiteral("existence_unconfirmed");
        return ruleFailure(context, error, diagnostic, QStringLiteral("LAN 防火墙规则名称已存在或无法确认，未覆盖原规则。"));
    }
    // Absence was observed at preflight. A property failure cannot persist this
    // new, disconnected COM object; it must not claim Add was attempted.
    context.present = false;
    context.verification = before.call.json();
    context.verification.insert("snapshot_complete", false);
    Com<INetFwRule> rule;
    auto hr = CoCreateInstance(CLSID_NetFwRule, nullptr, CLSCTX_INPROC_SERVER, IID_INetFwRule,
                              reinterpret_cast<void **>(rule.out()));
    context.call.set("CoCreateInstance", "Rule", hr, "INetFwRule*");
    if (FAILED(hr)) return ruleFailure(context, error, diagnostic);
    const auto property = [&](const char *op, const char *prop, const char *type,
                              const QJsonObject &summary, auto setter) {
        if (FAILED(hr)) return;
        hr = setter();
        context.call.set(op, prop, hr, type, summary);
    };
    const auto string = [&](const char *key, const char *prop, const char *op, auto setter, bool nativePath = false) {
        if (FAILED(hr)) return;
        auto value = record.value(QLatin1String(key)).toString();
        if (nativePath) value = QDir::toNativeSeparators(value);
        const String text(value);
        auto summary = textSummary(value);
        if (nativePath) {
            summary.insert("native_separators", !value.contains('/'));
            summary.insert("absolute", QDir::isAbsolutePath(value));
        }
        if (!text.value) {
            hr = E_OUTOFMEMORY;
            context.call.set("SysAllocStringLen", prop, hr, "BSTR", summary, "derived_from_null");
            return;
        }
        property(op, prop, "BSTR", summary, [&]() { return (rule.value->*setter)(text); });
    };
    string("name", "Name", "INetFwRule::put_Name", &INetFwRule::put_Name);
    string("description", "Description", "INetFwRule::put_Description", &INetFwRule::put_Description);
    string("group", "Grouping", "INetFwRule::put_Grouping", &INetFwRule::put_Grouping);
    // Keep the previously Windows-CI-verified native-path boundary unchanged.
    string("application", "ApplicationName", "INetFwRule::put_ApplicationName", &INetFwRule::put_ApplicationName, true);
    property("INetFwRule::put_Protocol", "Protocol", "LONG", {{"value", record.value("protocol").toInt()}},
             [&]() { return rule->put_Protocol(record.value("protocol").toInt()); });
    string("local_ports", "LocalPorts", "INetFwRule::put_LocalPorts", &INetFwRule::put_LocalPorts);
    string("remote_ports", "RemotePorts", "INetFwRule::put_RemotePorts", &INetFwRule::put_RemotePorts);
    string("local_addresses", "LocalAddresses", "INetFwRule::put_LocalAddresses", &INetFwRule::put_LocalAddresses);
    string("remote_addresses", "RemoteAddresses", "INetFwRule::put_RemoteAddresses", &INetFwRule::put_RemoteAddresses);
    string("interface_types", "InterfaceTypes", "INetFwRule::put_InterfaceTypes", &INetFwRule::put_InterfaceTypes);
    property("INetFwRule::put_Direction", "Direction", "NET_FW_RULE_DIRECTION", {{"value", int(NET_FW_RULE_DIR_IN)}},
             [&]() { return rule->put_Direction(NET_FW_RULE_DIR_IN); });
    property("INetFwRule::put_Action", "Action", "NET_FW_ACTION", {{"value", int(NET_FW_ACTION_ALLOW)}},
             [&]() { return rule->put_Action(NET_FW_ACTION_ALLOW); });
    property("INetFwRule::put_Profiles", "Profiles", "LONG", {{"value", record.value("profiles").toInt()}},
             [&]() { return rule->put_Profiles(record.value("profiles").toInt()); });
    property("INetFwRule::put_EdgeTraversal", "EdgeTraversal", "VARIANT_BOOL", {{"value", false}},
             [&]() { return rule->put_EdgeTraversal(VARIANT_FALSE); });
    VARIANT interfaces; VariantInit(&interfaces);
    if (SUCCEEDED(hr)) {
        interfaces.vt = VT_ARRAY | VT_VARIANT;
        interfaces.parray = SafeArrayCreateVector(VT_VARIANT, 0, 1);
        if (!interfaces.parray) {
            hr = E_OUTOFMEMORY;
            context.call.set("SafeArrayCreateVector", "Interfaces", hr, "SAFEARRAY(VARIANT)",
                             {{"count", 1}}, "derived_from_null");
        }
    }
    if (SUCCEEDED(hr)) {
        VARIANT alias; VariantInit(&alias); alias.vt = VT_BSTR;
        const auto text = record.value("interfaces").toArray().first().toString();
        alias.bstrVal = SysAllocStringLen(reinterpret_cast<const OLECHAR *>(text.utf16()), UINT(text.size()));
        LONG index = 0;
        if (!alias.bstrVal) {
            hr = E_OUTOFMEMORY;
            context.call.set("SysAllocStringLen", "Interfaces.Element", hr, "BSTR", textSummary(text), "derived_from_null");
        } else {
            property("SafeArrayPutElement", "Interfaces", "VARIANT(BSTR)", {{"index", 0}, {"utf16_length", double(text.size())}},
                     [&]() { return SafeArrayPutElement(interfaces.parray, &index, &alias); });
        }
        const auto clear = VariantClear(&alias);
        if (FAILED(clear)) {
            if (SUCCEEDED(hr)) {
                hr = clear; context.call.set("VariantClear", "Interfaces.Element", hr, "VARIANT");
            } else context.call.releaseFailure("Interfaces.Element", clear);
        }
    }
    property("INetFwRule::put_Interfaces", "Interfaces", "VARIANT(ARRAY|VARIANT)", {{"count", 1}},
             [&]() { return rule->put_Interfaces(interfaces); });
    const auto clear = VariantClear(&interfaces);
    if (FAILED(clear)) {
        if (SUCCEEDED(hr)) {
            hr = clear; context.call.set("VariantClear", "Interfaces", hr, "VARIANT");
        } else context.call.releaseFailure("Interfaces", clear);
    }
    // The production validator requires true. Only the separately compiled
    // fixture supplies false; no diagnostic changes any rule's Enabled value.
    property("INetFwRule::put_Enabled", "Enabled", "VARIANT_BOOL", {{"value", record.value("enabled").toBool()}},
             [&]() { return rule->put_Enabled(record.value("enabled").toBool() ? VARIANT_TRUE : VARIANT_FALSE); });
    if (FAILED(hr)) return ruleFailure(context, error, diagnostic);
    // Add may replace a matching identifier. Recheck after property setup too;
    // this narrows, but cannot make atomic, the Windows name-based API race.
    const auto beforeCommit = observeRule(rules, record);
    if (beforeCommit.presence != RuleObservation::Presence::Absent) {
        context.call = beforeCommit.call; context.observe(beforeCommit);
        context.call.reason = QStringLiteral("pre_add_name_or_read_conflict");
        return ruleFailure(context, error, diagnostic,
                           QStringLiteral("LAN 防火墙提交前发现同名规则或无法确认，未调用 Add。"));
    }
    return addAndObserve(rules, rule.value, record, context, error, diagnostic);
}
LanFirewall::Result cleanupLocked(const QString &path, const QJsonObject &record
#ifdef SWIRL_LAN_FIREWALL_TESTS
                                 , bool fixtureReadFailure = false
#endif
                                 ) {
    LanFirewall::Result result; result.record = record;
    Com<INetFwPolicy2> policy; Com<INetFwRules> rules;
    ComCall access;
    if (!firewall(policy, rules, &result.error, &access)) {
        RuleDiagnostic context;
        context.call = access; context.persisted = "unknown"; context.ownership = "unknown";
        context.cleanupRequired = true; context.partialPossible = true; context.recovery = "preserve_journal_retry_read";
        ruleFailure(context, &result.error, &result.diagnostic);
        result.diagnostic.insert("journal_retained", QFileInfo::exists(path));
        result.diagnostic.insert("removed_count", 0);
        result.diagnostic.insert("confirmed_absent_count", 0);
        result.diagnostic.insert("rules_not_confirmed_absent", record.value("rules").toArray().size());
        result.error = diagnosticError(hrError(qPrintable(access.operation), access.hr), result.diagnostic);
        return result;
    }
    const auto rows = record.value("rules").toArray();
    int removedCount = 0, absentCount = 0;
    const auto evidence = [&](const RuleDiagnostic &context) {
        result.diagnostic = context.json();
        result.diagnostic.insert("removed_count", removedCount);
        result.diagnostic.insert("confirmed_absent_count", absentCount);
        result.diagnostic.insert("journal_retained", QFileInfo::exists(path));
        result.diagnostic.insert("partial_cleanup", removedCount > 0 && absentCount < rows.size());
        result.diagnostic.insert("rules_not_confirmed_absent", rows.size() - absentCount);
        // Rule-level absence never means the whole transaction has finished.
        if (!result.ok) {
            result.diagnostic.insert("cleanup_required", true);
            result.diagnostic.insert("partial_persistence_possible", context.partialPossible || absentCount < rows.size());
            if (context.recovery == "none")
                result.diagnostic.insert("recovery_action", absentCount < rows.size()
                    ? "preserve_journal_retry_read" : "retry_journal_removal");
        }
    };
    // The Windows API has no atomic compare-and-delete. Immediately before
    // each name-based removal require the complete, unchanged owned snapshot.
    for (int index = rows.size() - 1; index >= 0; --index) {
        const auto expected = rows[index].toObject();
        auto current = observeRule(rules.value, expected);
#ifdef SWIRL_LAN_FIREWALL_TESTS
        if (fixtureReadFailure && current.presence == RuleObservation::Presence::Present) {
            current.snapshot = {}; current.owned = false;
            current.call.set("fixture::snapshotReadFailure", "Interfaces", E_ACCESSDENIED, "VARIANT",
                             {}, "test_injection", "simulated_unavailable_snapshot_after_real_item");
        }
#endif
        RuleDiagnostic context;
        context.call = current.call; context.observe(current);
        if (current.presence == RuleObservation::Presence::Absent) { ++absentCount; continue; }
        if (!current.owned) {
            evidence(context);
            result.error = diagnosticError(
                QStringLiteral("LAN 防火墙规则被外部修改或无法读取，未覆盖它；恢复记录已保留。"), result.diagnostic);
            return result;
        }
        const String name(expected.value("name").toString());
        if (!name.value) {
            context.call.set("SysAllocStringLen", "Name", E_OUTOFMEMORY, "BSTR",
                             textSummary(expected.value("name").toString()), "derived_from_null");
            evidence(context);
            result.error = diagnosticError(hrError(qPrintable(context.call.operation), context.call.hr), result.diagnostic);
            return result;
        }
        const auto removed = rules->Remove(name);
        context.call.set("INetFwRules::Remove", "Name", removed, "BSTR", textSummary(expected.value("name").toString()));
        const auto after = observeRule(rules.value, expected);
        context.observe(after);
        if (after.presence == RuleObservation::Presence::Absent) {
            ++absentCount;
            if (SUCCEEDED(removed)) ++removedCount;
        }
        if (FAILED(removed) || after.presence != RuleObservation::Presence::Absent) {
            evidence(context);
            result.error = diagnosticError(QStringLiteral("未确认 LAN 防火墙规则已安全移除，恢复记录已保留。"), result.diagnostic);
            return result;
        }
    }
    result.ok = QFile::remove(path);
    RuleDiagnostic context;
    context.persisted = "absent"; context.present = false;
    context.call.set("QFile::remove", "RecoveryJournal", result.ok ? S_OK : E_FAIL, "DPAPI file",
                     {{"removed", result.ok}}, "local_validation");
    if (result.ok) QFile::remove(readyPath(path, record.value("session").toString()));
    else {
        context.cleanupRequired = true; context.recovery = "retry_journal_removal";
        result.error = QStringLiteral("LAN 规则已恢复，但恢复记录无法移除。");
    }
    evidence(context);
    if (!result.ok) result.error = diagnosticError(result.error, result.diagnostic);
    return result;
}
#endif
}

bool LanFirewall::privateIpv4(const QString &text) {
    const QHostAddress ip(text);
    return ip.protocol() == QAbstractSocket::IPv4Protocol
        && (ip.isInSubnet(QHostAddress("10.0.0.0"), 8)
            || ip.isInSubnet(QHostAddress("172.16.0.0"), 12)
            || ip.isInSubnet(QHostAddress("192.168.0.0"), 16));
}

bool LanFirewall::validateConfiguration(const QJsonObject &input, QJsonObject *canonical, QString *error) {
    const QSet<QString> keys{"listen_ip", "http_port", "socks_port", "udp_port_start", "udp_port_end", "allowed_cidrs",
        "auth", "max_connections", "max_connections_per_client", "auth_failures_per_minute", "idle_timeout_secs", "host_addresses"};
    for (auto it = input.begin(); it != input.end(); ++it)
        if (!keys.contains(it.key())) return reject(error, QStringLiteral("LAN 配置含未知选项，未忽略该选项。"));
    if (!privateIpv4(input.value("listen_ip").toString()))
        return reject(error, QStringLiteral("请选择单个 RFC1918 局域网 IPv4 地址；不能使用全部接口、公共地址或 IPv6。"));
    for (const char *key : {"http_port", "socks_port", "udp_port_start", "udp_port_end"})
        if (!integer(input, key, 1, 65535)) return reject(error, QStringLiteral("LAN 端口必须为 1 至 65535。"));
    if (input.value("udp_port_end").toInt() < input.value("udp_port_start").toInt()
        || input.value("udp_port_end").toInt() - input.value("udp_port_start").toInt() >= 64)
        return reject(error, QStringLiteral("UDP 端口池必须为连续的 1 至 64 个端口。"));
    if (!integer(input, "max_connections", 1, 256) || !integer(input, "max_connections_per_client", 1, 64)
        || input.value("max_connections_per_client").toInt() > input.value("max_connections").toInt()
        || !integer(input, "auth_failures_per_minute", 1, 20) || !integer(input, "idle_timeout_secs", 60, 86400))
        return reject(error, QStringLiteral("LAN 连接、认证速率或空闲超时限制无效。"));
    const auto auth = input.value("auth").toObject();
    const auto username = auth.value("username").toString(), password = auth.value("password").toString();
    if (auth.size() != 2 || !QRegularExpression("^[A-Za-z0-9_.-]{1,64}$").match(username).hasMatch()
        || password.toUtf8().size() < 12 || password.toUtf8().size() > 255
        || std::any_of(password.begin(),password.end(),[](QChar ch){return ch.category()==QChar::Other_Control;}))
        return reject(error, QStringLiteral("用户名仅支持字母、数字、点和横线；密码需 12 至 255 UTF-8 字节且不能包含控制字符。"));
    const auto allowed = input.value("allowed_cidrs").toArray();
    if (!input.value("allowed_cidrs").isArray() || allowed.isEmpty() || allowed.size() > 64)
        return reject(error, QStringLiteral("请填写 1 至 64 个允许访问的局域网 CIDR。"));
    QSet<QString> seen; QJsonArray normalized;
    for (const auto &value : allowed) {
        const auto text = cidr(value.toString());
        const auto subnet = QHostAddress::parseSubnet(text);
        if (text.isEmpty() || !privateIpv4(subnet.first.toString()))
            return reject(error, QStringLiteral("访问控制仅允许 RFC1918 IPv4 CIDR。"));
        const quint32 mask = subnet.second ? std::numeric_limits<quint32>::max() << (32 - subnet.second) : 0;
        const QHostAddress last(subnet.first.toIPv4Address() | ~mask);
        if (!privateIpv4(last.toString())) return reject(error, QStringLiteral("CIDR 不能跨出局域网地址范围。"));
        if (!seen.contains(text)) { normalized.append(text); seen.insert(text); }
    }
    if (canonical) { *canonical = input; canonical->insert("listen_ip", QHostAddress(input.value("listen_ip").toString()).toString()); canonical->insert("allowed_cidrs", normalized); }
    return true;
}

bool LanFirewall::validateJournal(const QJsonObject &record) {
    const QSet<QString> keys{"schema","session","owner_pid","owner_creation","listen_ip","prefix","interface_index","interface_guid","interface_name","profile","application","phase","rules","host_addresses"};
    for(auto it=record.begin();it!=record.end();++it)if(!keys.contains(it.key()))return false;
    if(record.size()!=keys.size())return false;
    if (!integer(record,"schema",1,1) || !QRegularExpression("^[0-9a-f]{32}$").match(record.value("session").toString()).hasMatch()
        || !integer(record, "owner_pid", 1, std::numeric_limits<int>::max())
        || !QRegularExpression("^[1-9][0-9]{0,19}$").match(record.value("owner_creation").toString()).hasMatch()
        || !privateIpv4(record.value("listen_ip").toString()) || !integer(record, "prefix", 1, 32)
        || !integer(record, "interface_index", 1, std::numeric_limits<int>::max())
        || QUuid(record.value("interface_guid").toString()).isNull() || record.value("interface_name").toString().isEmpty()
        || record.value("interface_name").toString().size()>256
        || !integer(record,"profile",1,2)
        || !QStringList{"prepared","applying_tcp","applying_udp","active"}.contains(record.value("phase").toString())
        || !QDir::isAbsolutePath(record.value("application").toString())
        || record.value("application").toString().contains(QChar::Null)
        || record.value("rules").toArray().size() != 2) return false;
    const auto hosts=record.value("host_addresses").toArray();
    if(hosts.isEmpty()||hosts.size()>128||!hosts.contains(record.value("listen_ip")))return false;
    QSet<QString> uniqueHosts;
    for(const auto &host:hosts){const auto address=QHostAddress(host.toString());if((address.protocol()!=QAbstractSocket::IPv4Protocol&&address.protocol()!=QAbstractSocket::IPv6Protocol)||!address.scopeId().isEmpty()||uniqueHosts.contains(host.toString()))return false;uniqueHosts.insert(host.toString());}
    const auto session = record.value("session").toString();
    const auto rows = record.value("rules").toArray();
    const QSet<QString> ruleKeys{"name","description","group","application","local_addresses","remote_addresses","local_ports","remote_ports","interface_types","service","interfaces","profiles","protocol","direction","action","enabled","edge_traversal"};
    for (int i = 0; i < rows.size(); ++i) {
        const auto rule = rows[i].toObject();
        if(rule.size()!=ruleKeys.size())return false;
        for(auto it=rule.begin();it!=rule.end();++it)if(!ruleKeys.contains(it.key()))return false;
        if (rule.value("name").toString() != "SwirlLan-" + session + (i ? "-udp" : "-tcp")
            || rule.value("description").toString() != "Swirl native LAN session " + session
            || rule.value("group").toString() != "Swirl LAN " + session
            || rule.value("application").toString() != record.value("application").toString().toLower()
            || rule.value("local_addresses").toString() != record.value("listen_ip").toString()
            || rule.value("remote_addresses").toString().isEmpty()
            || normalizedAddresses(rule.value("remote_addresses").toString()) != rule.value("remote_addresses").toString()
            || !QRegularExpression(i ? "^[1-9][0-9]{0,4}(?:-[1-9][0-9]{0,4})?$" : "^[1-9][0-9]{0,4}(?:,[1-9][0-9]{0,4})?$").match(rule.value("local_ports").toString()).hasMatch()
            || rule.value("remote_ports").toString() != "*" || rule.value("interface_types").toString() != "All"
            || !rule.value("service").toString().isEmpty() || rule.value("interfaces").toArray() != QJsonArray{record.value("interface_name")}
            || rule.value("profiles") != record.value("profile") || !integer(rule,"protocol",i?17:6,i?17:6)
            || !integer(rule,"direction",1,1) || !integer(rule,"action",1,1)
            || rule.value("enabled") != QJsonValue(true) || rule.value("edge_traversal") != QJsonValue(false)) return false;
        if(!i&&normalizedPorts(rule.value("local_ports").toString())!=rule.value("local_ports").toString())return false;
        const auto ports=rule.value("local_ports").toString().split(i?'-':',');
        for(const auto &port:ports){bool ok=false;const auto value=port.toUInt(&ok);if(!ok||value<1||value>65535)return false;}
        if(i&&ports.size()==2&&(ports[1].toInt()<ports[0].toInt()||ports[1].toInt()-ports[0].toInt()>=64))return false;
        const auto selected = QHostAddress::parseSubnet(record.value("listen_ip").toString() + '/' + QString::number(record.value("prefix").toInt()));
        const auto remotes=rule.value("remote_addresses").toString().split(',');if(remotes.size()>64)return false;
        for (const auto &text : remotes) {
            const auto remote = QHostAddress::parseSubnet(text);
            if (remote.second < selected.second || !remote.first.isInSubnet(selected) || !privateIpv4(remote.first.toString())) return false;
            const quint32 mask=remote.second?std::numeric_limits<quint32>::max()<<(32-remote.second):0;
            if(!privateIpv4(QHostAddress(remote.first.toIPv4Address()|~mask).toString()))return false;
        }
    }
    return true;
}

QString LanFirewall::journalPath() {
    return SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/lan-firewall/session.dpapi";
}
bool LanFirewall::journalExists(const QString &path) { return QFileInfo::exists(path); }

LanFirewall::Result LanFirewall::prepare(const QString &path, const QJsonObject &input) {
    Result result;
    if (!validateConfiguration(input, &result.config, &result.error)) return result;
#ifdef Q_OS_WIN
    Apartment apartment;
    if (FAILED(apartment.result)) { result.error = hrError("COM 初始化", apartment.result); return result; }
    if (!secureDirectory(QFileInfo(path).absolutePath())) { result.error = QStringLiteral("LAN 恢复目录无法建立安全权限，未修改防火墙。"); return result; }
    QLockFile lock(path + ".lock");
    if (!lock.tryLock(1000)) { result.error = QStringLiteral("另一进程正在处理 LAN 防火墙恢复。"); return result; }
    if (QFileInfo::exists(path)) { result.error = QStringLiteral("上次 LAN 防火墙恢复记录尚未清理，请先执行恢复。"); return result; }
    auto adapter = adapterSnapshot(input.value("listen_ip").toString(), &result.error);
    if (adapter.isEmpty()) return result;
    const auto subnet = QHostAddress::parseSubnet(adapter.value("listen_ip").toString() + '/' + QString::number(adapter.value("prefix").toInt()));
    QStringList remotes;
    for (const auto &value : result.config.value("allowed_cidrs").toArray()) {
        const auto allowed = QHostAddress::parseSubnet(value.toString());
        if (allowed.second < subnet.second || !allowed.first.isInSubnet(subnet)) { result.error = QStringLiteral("允许的客户端 CIDR 必须完整位于所选 LAN 接口的本地子网。"); return result; }
        remotes.append(value.toString());
    }
    Com<INetFwPolicy2> policy; Com<INetFwRules> rules;
    if (!firewall(policy, rules, &result.error) || !profileEnabled(policy.value, adapter.value("profile").toInt(), &result.error)) return result;
    const auto application = QDir::fromNativeSeparators(QFileInfo(QCoreApplication::applicationFilePath()).canonicalFilePath());
    const auto helper = QCoreApplication::applicationDirPath() + "/SwirlProxyGuard.exe";
    if (application.isEmpty() || !QFileInfo::exists(helper)) { result.error = QStringLiteral("LAN 恢复守护程序或应用身份不可用。"); return result; }
    auto record = adapter;
    const auto session = QUuid::createUuid().toString(QUuid::Id128);
    record.insert("schema", 1); record.insert("session", session); record.insert("application", application);
    record.insert("owner_pid", double(QCoreApplication::applicationPid())); record.insert("owner_creation", processStamp(GetCurrentProcess()));
    record.insert("phase", "prepared");
    QStringList tcp{QString::number(input.value("http_port").toInt()), QString::number(input.value("socks_port").toInt())};
    auto udp = QString::number(input.value("udp_port_start").toInt());
    if (input.value("udp_port_start") != input.value("udp_port_end")) udp += '-' + QString::number(input.value("udp_port_end").toInt());
    QJsonArray desired;
    for (int i = 0; i < 2; ++i) desired.append(QJsonObject{
        {"name", "SwirlLan-" + session + (i ? "-udp" : "-tcp")}, {"description", "Swirl native LAN session " + session},
        {"group", "Swirl LAN " + session}, {"application", application.toLower()}, {"local_addresses", adapter.value("listen_ip")},
        {"remote_addresses", normalizedAddresses(remotes.join(','))}, {"local_ports", i ? udp : normalizedPorts(tcp.join(','))},
        {"remote_ports", "*"}, {"interface_types", "All"}, {"service", ""}, {"interfaces", QJsonArray{adapter.value("interface_name")}},
        {"profiles", adapter.value("profile")}, {"protocol", i ? 17 : 6}, {"direction", 1}, {"action", 1}, {"enabled", true}, {"edge_traversal", false}});
    record.insert("rules", desired);
    if (!validateJournal(record) || !writeRecord(path, record)) { result.error = QStringLiteral("无法保存有效的 DPAPI LAN 恢复记录，未修改防火墙。"); return result; }
    result.record = record;
    QProcess guardProcess;
    guardProcess.setProgram(helper); guardProcess.setArguments({"--lan-firewall", path});
    guardProcess.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *arguments) { arguments->flags |= CREATE_NO_WINDOW; });
    const bool started = guardProcess.startDetached();
    bool acknowledged = false;
    for (int i = 0; started && i < 100; ++i) {
        const auto ready = readRecord(readyPath(path, session));
        acknowledged = ready.value("session").toString() == session && ready.value("ready").toBool();
        if (acknowledged) break;
        QThread::msleep(25);
    }
    if (!acknowledged) { QFile::remove(path); result.error = QStringLiteral("LAN 安全恢复守护未就绪，未修改防火墙。"); return result; }
    const auto again = adapterSnapshot(input.value("listen_ip").toString(), &result.error);
    if (again != adapter) { QFile::remove(path); if (result.error.isEmpty()) result.error = QStringLiteral("LAN 接口状态在启动期间改变，未修改防火墙。"); return result; }
    for (int i = 0; i < desired.size(); ++i) {
        record.insert("phase", i ? "applying_udp" : "applying_tcp");
        if (!writeRecord(path, record) || !applyRule(rules.value, desired[i].toObject(), &result.error, &result.diagnostic)) {
            if (result.error.isEmpty()) result.error = QStringLiteral("无法更新 LAN 防火墙事务记录。");
            const auto cleaned = cleanupLocked(path, record);
            result.diagnostic.insert("rollback", cleaned.diagnostic);
            result.diagnostic.insert("rollback_complete", cleaned.ok);
            result.diagnostic.insert("journal_retained", QFileInfo::exists(path));
            result.error = diagnosticError(result.error, QJsonObject{{"rollback", cleaned.diagnostic},
                {"rollback_complete", cleaned.ok}, {"journal_retained", QFileInfo::exists(path)}});
            if (!cleaned.ok) result.error += ' ' + cleaned.error;
            return result;
        }
    }
    record.insert("phase", "active");
    if (!writeRecord(path, record)) {
        result.error = QStringLiteral("LAN 防火墙状态确认无法保存，已请求回滚。");
        const auto cleaned = cleanupLocked(path, record);
        result.diagnostic.insert("rollback", cleaned.diagnostic);
        result.diagnostic.insert("rollback_complete", cleaned.ok);
        result.diagnostic.insert("journal_retained", QFileInfo::exists(path));
        result.error = diagnosticError(result.error, QJsonObject{{"rollback", cleaned.diagnostic},
            {"rollback_complete", cleaned.ok}, {"journal_retained", QFileInfo::exists(path)}});
        if (!cleaned.ok) result.error += ' ' + cleaned.error;
        return result;
    }
    result.config.insert("host_addresses", adapter.value("host_addresses"));
    result.record = record; result.ok = true;
#else
    Q_UNUSED(path);
    result.error = QStringLiteral("当前平台未实现 LAN 接口与防火墙安全集成，未开启监听。");
#endif
    return result;
}

LanFirewall::Result LanFirewall::verify(const QJsonObject &record) {
    Result result; result.record = record;
    if (!validateJournal(record)) { result.error = QStringLiteral("LAN 恢复记录无效。"); return result; }
#ifdef Q_OS_WIN
    Apartment apartment;
    if (FAILED(apartment.result)) { result.error = hrError("COM 初始化", apartment.result); return result; }
    const auto adapter = adapterSnapshot(record.value("listen_ip").toString(), &result.error);
    if (adapter.isEmpty()) return result;
    for (const char *key : {"interface_guid", "interface_index", "interface_name", "listen_ip", "prefix", "profile", "host_addresses"})
        if (adapter.value(QLatin1String(key)) != record.value(QLatin1String(key))) { result.error = QStringLiteral("LAN 接口身份、地址或网络类别改变，已停止接受新连接。"); return result; }
    Com<INetFwPolicy2> policy; Com<INetFwRules> rules;
    if (!firewall(policy, rules, &result.error) || !profileEnabled(policy.value, record.value("profile").toInt(), &result.error)) return result;
    for (const auto &value : record.value("rules").toArray()) {
        const auto observed = observeRule(rules.value, value.toObject());
        RuleDiagnostic context;
        context.call = observed.call; context.observe(observed);
        result.diagnostic = context.json();
        if (!observed.owned) {
            ruleFailure(context, &result.error, nullptr,
                QStringLiteral("LAN 防火墙规则已改变，已请求停止监听并保留恢复证据。"));
            return result;
        }
    }
    result.ok = true;
#else
    result.error = QStringLiteral("当前平台不支持 Windows LAN 防火墙。");
#endif
    return result;
}

LanFirewall::Result LanFirewall::recover(const QString &path, const QString &expectedSession, bool requireDeadOwner) {
    Result result;
#ifdef Q_OS_WIN
    Apartment apartment;
    if (FAILED(apartment.result)) { result.error = hrError("COM 初始化", apartment.result); return result; }
    QLockFile lock(path + ".lock");
    if (!lock.tryLock(1000)) { result.error = QStringLiteral("LAN 恢复正在由另一进程处理，记录已保留。"); return result; }
    if (!QFileInfo::exists(path)) { result.ok = true; return result; }
    const auto record = readRecord(path); result.record = record;
    if (!validateJournal(record)) { result.error = QStringLiteral("LAN 恢复记录损坏或无法解密，未修改任何防火墙规则。"); return result; }
    if ((!expectedSession.isEmpty() && record.value("session").toString() != expectedSession)
        || (requireDeadOwner && ownerAlive(record))) { result.error = QStringLiteral("LAN 恢复记录属于另一个活动会话，未清理它的规则。"); return result; }
    if (!requireDeadOwner && expectedSession.isEmpty()) { result.error = QStringLiteral("缺少 LAN 会话所有权，未清理规则。"); return result; }
    return cleanupLocked(path, record);
#else
    Q_UNUSED(path); Q_UNUSED(expectedSession); Q_UNUSED(requireDeadOwner);
    result.error = QStringLiteral("当前平台不支持 Windows LAN 防火墙恢复。");
#endif
    return result;
}

int LanFirewall::guard(const QString &path) {
#ifdef Q_OS_WIN
    const auto record = readRecord(path);
    if (!validateJournal(record)) return 2;
    HANDLE owner = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, DWORD(record.value("owner_pid").toDouble()));
    if (!owner) return 3;
    if (processStamp(owner) != record.value("owner_creation").toString()
        || processPath(owner).compare(record.value("application").toString(), Qt::CaseInsensitive)) { CloseHandle(owner); return 3; }
    const auto session = record.value("session").toString();
    const auto ready = readyPath(path, session);
    if (!writeRecord(ready, {{"session", session}, {"ready", true}})) { CloseHandle(owner); return 4; }
    for (;;) {
        if (!QFileInfo::exists(path)) { CloseHandle(owner); QFile::remove(ready); return 0; }
        const auto current = readRecord(path);
        if (!current.isEmpty() && current.value("session") != record.value("session")) { CloseHandle(owner); QFile::remove(ready); return 0; }
        const auto wait = WaitForSingleObject(owner, 250);
        if (wait == WAIT_OBJECT_0) break;
        if (wait == WAIT_FAILED) { CloseHandle(owner); return 5; }
    }
    CloseHandle(owner);
    return recover(path, session, true).ok ? 0 : 6;
#else
    Q_UNUSED(path); return 2;
#endif
}

#ifdef SWIRL_LAN_FIREWALL_TESTS
LanFirewall::Result LanFirewall::exerciseNativeFixture(FixtureCase scenario) {
    Result result;
#ifdef Q_OS_WIN
    // This entry point is not linked into SwirlEngine or the product. Requiring
    // both the dedicated executable and explicit opt-in keeps a normal CTest
    // invocation from changing even disabled Windows firewall rules.
    if (qEnvironmentVariable("SWIRL_LAN_FIREWALL_TEST") != "1"
        || QFileInfo(QCoreApplication::applicationFilePath()).fileName()
               .compare("SwirlLanFirewallTests.exe", Qt::CaseInsensitive) != 0) {
        result.error = "The dedicated native firewall fixture requires explicit opt-in.";
        return result;
    }
    Apartment apartment;
    if (FAILED(apartment.result)) { result.error = hrError("fixture COM", apartment.result); return result; }
    Com<INetFwPolicy2> policy; Com<INetFwRules> rules;
    if (!firewall(policy, rules, &result.error)) return result;
    QString alias;
    for (const auto &iface : QNetworkInterface::allInterfaces()) {
        if (iface.flags().testFlag(QNetworkInterface::IsUp)
            && !iface.flags().testFlag(QNetworkInterface::IsLoopBack)
            && !iface.humanReadableName().isEmpty()) {
            alias = iface.humanReadableName();
            break;
        }
    }
    if (alias.isEmpty()) { result.error = "No existing interface alias is available for the disabled fixture."; return result; }
    const auto application = QDir::fromNativeSeparators(
        QFileInfo(QCoreApplication::applicationFilePath()).canonicalFilePath());
    if (application.isEmpty()) { result.error = "The fixture executable identity is unavailable."; return result; }
    QTemporaryDir directory(QDir::tempPath() + "/swirl-lan-firewall-test-XXXXXX");
    if (!directory.isValid()) { result.error = "Cannot create the isolated fixture journal directory."; return result; }
    // Preserve the encrypted journal if a real external edit prevents cleanup.
    // Disabled rules cannot admit traffic, including after an interrupted test.
    directory.setAutoRemove(false);
    if (!secureDirectory(directory.path())) { result.error = "Cannot secure the isolated fixture directory."; return result; }
    struct Fixture { QString path; QJsonObject record; };
    QList<Fixture> fixtures;
    QSet<QString> scriptedEdits;
    QJsonObject recoveryEvidence;
    bool preserveRecoveryEvidence = false;
    const auto check = [&](bool ok, const QString &message) {
        if (!ok && result.error.isEmpty()) result.error = message;
        return ok;
    };
    const auto observed = [&](const QJsonObject &expected, QJsonObject *snapshot) {
        const String name(expected.value("name").toString());
        Com<INetFwRule> rule;
        const auto hr = name.value ? rules->Item(name, rule.out()) : E_OUTOFMEMORY;
        if (FAILED(hr)) return check(false, hrError("fixture rule read", hr));
        *snapshot = ruleSnapshot(rule.value);
        return check(!snapshot->isEmpty(), "Cannot read every native firewall rule property.");
    };
    const auto exact = [&](const Fixture &fixture) {
        for (const auto &value : fixture.record.value("rules").toArray()) {
            QJsonObject actual;
            if (!observed(value.toObject(), &actual)
                || !check(actual == value.toObject(), "Native rule readback differs from the exact fixture scope.")) return false;
        }
        return true;
    };
    const auto bytes = [](const QString &path) {
        QFile file(path);
        return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
    };
    const auto add = [&](bool productionNames = false) {
        const auto session = QUuid::createUuid().toString(QUuid::Id128);
        QJsonArray desired;
        for (int index = 0; index < 2; ++index) desired.append(QJsonObject{
            {"name", (productionNames ? "SwirlLan-" : "SwirlLanTest-") + session + (index ? "-udp" : "-tcp")},
            {"description", (productionNames ? "Swirl native LAN session " : "Swirl disabled native firewall fixture ") + session},
            {"group", (productionNames ? "Swirl LAN " : "Swirl disabled test ") + session}, {"application", application.toLower()},
            {"local_addresses", "127.0.0.1"}, {"remote_addresses", "127.0.0.1/32"},
            {"local_ports", index ? "49174-49175" : "49173"}, {"remote_ports", "*"},
            {"interface_types", "All"}, {"service", ""}, {"interfaces", QJsonArray{alias}},
            {"profiles", 2}, {"protocol", index ? 17 : 6}, {"direction", 1}, {"action", 1},
            {"enabled", false}, {"edge_traversal", false}});
        Fixture fixture{directory.filePath(session + ".dpapi"),
            {{"fixture_schema", 1}, {"session", session}, {"application", application},
             {"owner_pid", double(QCoreApplication::applicationPid())},
             {"owner_creation", processStamp(GetCurrentProcess())}, {"rules", desired}}};
        if (!check(!validateJournal(fixture.record), "A test fixture must never validate as a production journal.")
            || !check(writeRecord(fixture.path, fixture.record), "Cannot write the fixture DPAPI recovery record.")) return false;
        fixtures.append(fixture);
        if (!check(readRecord(fixture.path) == fixture.record, "The DPAPI fixture journal did not roundtrip.")) return false;
        const auto encrypted = bytes(fixture.path);
        if (!check(!encrypted.isEmpty() && !encrypted.contains(session.toUtf8())
                   && !encrypted.contains(productionNames ? "SwirlLan-" : "SwirlLanTest-"),
                   "The recovery fixture journal was not encrypted.")) return false;
        for (const auto &value : desired) {
            QJsonObject diagnostic;
            if (!applyRule(rules.value, value.toObject(), &result.error, &diagnostic)) return false;
            if (!check(diagnostic.value("add_attempted") == QJsonValue(true)
                       && diagnostic.value("add_succeeded") == QJsonValue(true)
                       && diagnostic.value("persisted_rule_state") == QJsonValue("present_owned")
                       && diagnostic.value("ownership_state") == QJsonValue("owned")
                       && diagnostic.value("verification").toObject().value("snapshot_complete") == QJsonValue(true),
                       "Successful native Add was not followed by a complete, owned readback diagnostic.")) return false;
            result.diagnostic = diagnostic;
        }
        recoveryEvidence.insert("successful_add_readback_diagnostic", true);
        return exact(fixture);
    };
    const auto absent = [&](const Fixture &fixture) {
        for (const auto &value : fixture.record.value("rules").toArray()) {
            const String name(value.toObject().value("name").toString());
            Com<INetFwRule> rule;
            if (!check(name.value && rules->Item(name, rule.out()) == HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND),
                       "The native fixture rule still exists after owned cleanup.")) return false;
        }
        return check(!QFileInfo::exists(fixture.path), "The recovered fixture journal still exists.");
    };
    const auto exercise = [&]() {
        if (!add()) return false;
        const auto first = fixtures.first();
        if (scenario == FixtureCase::ReadbackMismatch) {
            const auto session = QUuid::createUuid().toString(QUuid::Id128);
            auto actual = first.record.value("rules").toArray().first().toObject();
            actual.insert("name", "SwirlLanTest-" + session + "-readback");
            Fixture candidate{directory.filePath(session + ".dpapi"), first.record};
            candidate.record.insert("session", session);
            candidate.record.insert("rules", QJsonArray{actual});
            // Save the exact disabled/loopback IN rule before any Add. The
            // teardown can use only this independently recorded actual scope.
            if (!check(actual.value("direction") == QJsonValue(1)
                       && actual.value("enabled") == QJsonValue(false)
                       && actual.value("local_addresses") == QJsonValue("127.0.0.1")
                       && actual.value("remote_addresses") == QJsonValue("127.0.0.1/32")
                       && writeRecord(candidate.path, candidate.record),
                       "Cannot preserve the exact safe readback fixture before native Add.")) return false;
            fixtures.append(candidate);
            const auto originalJournal = bytes(candidate.path);
            if (!check(!originalJournal.isEmpty() && readRecord(candidate.path) == candidate.record,
                       "The prewritten readback fixture journal did not roundtrip.")) return false;

            // Intentionally inconsistent expected direction, not a simulated
            // administrator race. The existing setter always writes IN; the
            // production journal validator rejects OUT, so production inputs
            // cannot take this deliberately malformed test-only expectation.
            auto expected = actual;
            expected.insert("direction", 2);
            QString failure;
            QJsonObject diagnostic;
            const bool applied = applyRule(rules.value, expected, &failure, &diagnostic);
            result.diagnostic = diagnostic;
            if (!check(!applied && !failure.isEmpty()
                       && diagnostic.value("operation") == QJsonValue("INetFwRules::Add")
                       && diagnostic.value("hresult") == QJsonValue("0x00000000")
                       && diagnostic.value("add_attempted") == QJsonValue(true)
                       && diagnostic.value("add_succeeded") == QJsonValue(true)
                       && diagnostic.value("persisted_rule_state") == QJsonValue("present_mismatch")
                       && diagnostic.value("ownership_state") == QJsonValue("mismatch")
                       && diagnostic.value("verification").toObject().value("mismatched_properties")
                              .toArray().contains(QJsonValue("direction")),
                       "A successful native Add with inconsistent expected direction did not report a persisted mismatch.")) return false;
            QJsonObject snapshot;
            if (!observed(actual, &snapshot)
                || !check(snapshot == actual,
                          "The persisted native readback rule differs from its prewritten exact safe scope.")) return false;

            auto wrongRecord = candidate.record;
            wrongRecord.insert("rules", QJsonArray{expected});
            const auto refused = cleanupLocked(candidate.path, wrongRecord);
            result.diagnostic.insert("cleanup_refusal", refused.diagnostic);
            if (!check(!refused.ok && !refused.error.isEmpty()
                       && refused.diagnostic.value("ownership_state") == QJsonValue("mismatch")
                       && refused.diagnostic.value("removed_count") == QJsonValue(0)
                       && refused.diagnostic.value("journal_retained") == QJsonValue(true),
                       "Cleanup removed a native rule using an inconsistent expected snapshot.")) return false;
            if (!observed(actual, &snapshot)
                || !check(snapshot == actual && bytes(candidate.path) == originalJournal
                          && readRecord(candidate.path) == candidate.record,
                          "Mismatch cleanup changed the actual rule or its prewritten encrypted ownership record.")
                || !exact(first)) return false;
            recoveryEvidence.insert("native_add_succeeded", true);
            recoveryEvidence.insert("prewritten_actual_journal", true);
            recoveryEvidence.insert("wrong_expected_cleanup_refused", true);
            recoveryEvidence.insert("existing_rules_unchanged", true);
            recoveryEvidence.insert("recovery_journal_unchanged", true);
            return true;
        }
        if (scenario == FixtureCase::InvalidProperty) {
            const auto privateValue = QStringLiteral("SwirlDiagnosticPrivateSentinel");
            // Establish the original HRESULT independently on a transient real
            // INetFwRule. This control object is never passed to Add.
            Com<INetFwRule> control;
            const auto created = CoCreateInstance(CLSID_NetFwRule, nullptr, CLSCTX_INPROC_SERVER,
                IID_INetFwRule, reinterpret_cast<void **>(control.out()));
            if (!check(SUCCEEDED(created) && control.value,
                       "Cannot create the native invalid-property positive control.")) return false;
            // Description text validation may be deferred until Add by the
            // Windows implementation. A protocol beyond ANY (256) exercises
            // the numeric setter's actual argument validation instead.
            constexpr LONG invalidProtocol = 257;
            const auto nativeFailure = control->put_Protocol(invalidProtocol);
            if (!check(nativeFailure == E_INVALIDARG,
                       "The native Protocol positive control returned " + hresultText(nativeFailure)
                           + "; expected E_INVALIDARG for protocol 257.")) return false;

            const auto session = QUuid::createUuid().toString(QUuid::Id128);
            auto invalid = first.record.value("rules").toArray().first().toObject();
            invalid.insert("name", "SwirlLanTest-" + session + "-invalid");
            invalid.insert("description", privateValue);
            invalid.insert("protocol", int(invalidProtocol));
            Fixture candidate{directory.filePath(session + ".dpapi"), first.record};
            candidate.record.insert("session", session);
            candidate.record.insert("rules", QJsonArray{invalid});
            if (!check(writeRecord(candidate.path, candidate.record),
                       "Cannot preserve the invalid-property candidate's encrypted recovery record.")) return false;
            fixtures.append(candidate);
            const auto originalJournal = bytes(candidate.path);
            QString failure;
            QJsonObject diagnostic;
            const bool applied = applyRule(rules.value, invalid, &failure, &diagnostic);
            result.diagnostic = diagnostic;
            if (!check(!applied && !failure.isEmpty()
                       && diagnostic.value("operation") == QJsonValue("INetFwRule::put_Protocol")
                       && diagnostic.value("property") == QJsonValue("Protocol")
                       && diagnostic.value("hresult") == QJsonValue("0x80070057")
                       && diagnostic.value("hresult_source") == QJsonValue("native_hresult")
                       && diagnostic.value("add_attempted") == QJsonValue(false),
                       "The invalid-property diagnostic did not preserve the real COM method and HRESULT.")) return false;
            const auto output = QJsonDocument(diagnostic).toJson(QJsonDocument::Compact) + failure.toUtf8();
            if (!check(!output.contains(privateValue.toUtf8())
                       && !output.contains("SwirlDiagnosticPrivateSentinel")
                       && !output.contains(application.toUtf8())
                       && !output.contains(application.toLower().toUtf8())
                       && !output.contains(QDir::toNativeSeparators(application).toUtf8())
                       && !output.contains(invalid.value("name").toString().toUtf8()),
                       "A native COM diagnostic exposed an unredacted parameter.")) return false;
            auto privateContext = invalid;
            privateContext.insert("application", "C:/Users/PrivatePathSentinel/Swirl.exe");
            privateContext.insert("interfaces", QJsonArray{"PrivateInterfaceSentinel"});
            const auto safeContext = QJsonDocument(ruleSummary(privateContext)).toJson(QJsonDocument::Compact);
            if (!check(!safeContext.contains("PrivatePathSentinel")
                       && !safeContext.contains("PrivateInterfaceSentinel"),
                       "The shared Add context summary exposed a private path or interface alias.")) return false;
            const String name(invalid.value("name").toString());
            Com<INetFwRule> unexpected;
            if (!check(name.value && rules->Item(name, unexpected.out()) == HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND),
                       "An invalid-property rule unexpectedly exists in the native collection.")) return false;
            if (!check(!originalJournal.isEmpty() && bytes(candidate.path) == originalJournal
                       && readRecord(candidate.path) == candidate.record,
                       "Invalid-property diagnostics changed the encrypted recovery transaction.")) return false;
            recoveryEvidence.insert("native_failure_matched", true);
            recoveryEvidence.insert("redaction_checked", true);
            recoveryEvidence.insert("invalid_rule_absent", true);
            recoveryEvidence.insert("recovery_journal_unchanged", true);
            return exact(first);
        }
        if (scenario == FixtureCase::AddFailure) {
            // A null INetFwRule is a deterministic invalid native COM argument;
            // it can never overwrite any existing disabled fixture rule. The
            // production Add/observation helper still executes the real Add.
            const auto nativeFailure = rules->Add(nullptr);
            if (!check(FAILED(nativeFailure), "The native null-rule Add positive control unexpectedly succeeded.")) return false;
            const auto originalHresult = QStringLiteral("0x%1").arg(quint32(nativeFailure), 8, 16, QLatin1Char('0'));
            const auto originalJournal = bytes(first.path);
            const auto expected = first.record.value("rules").toArray().first().toObject();
            auto missing = expected;
            missing.insert("name", "SwirlLanTest-" + QUuid::createUuid().toString(QUuid::Id128) + "-absent");
            const String missingName(missing.value("name").toString());
            Com<INetFwRule> before;
            if (!check(missingName.value && rules->Item(missingName, before.out()) == HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND),
                       "The intended absent-rule test name has a real native collision; it was preserved.")) return false;
            RuleDiagnostic absentContext;
            QJsonObject absentDiagnostic;
            QString absentError;
            if (!check(!addAndObserve(rules.value, nullptr, missing, absentContext, &absentError, &absentDiagnostic)
                       && !absentError.isEmpty()
                       && absentDiagnostic.value("hresult") == QJsonValue(originalHresult)
                       && absentDiagnostic.value("persisted_rule_state") == QJsonValue("absent"),
                       "Failed native Add did not preserve its original HRESULT and confirm absence.")) return false;
            Com<INetFwRule> after;
            if (!check(rules->Item(missingName, after.out()) == HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND),
                       "The null-rule Add changed the supposedly absent native rule.")) return false;

            RuleDiagnostic existingContext;
            QJsonObject existingDiagnostic;
            QString existingError;
            if (!check(!addAndObserve(rules.value, nullptr, expected, existingContext, &existingError, &existingDiagnostic)
                       && !existingError.isEmpty()
                       && existingDiagnostic.value("hresult") == QJsonValue(originalHresult)
                       && existingDiagnostic.value("persisted_rule_state") == QJsonValue("present")
                       && existingDiagnostic.value("ownership_state") == QJsonValue("owned"),
                       "Failed native Add incorrectly assumed an already-existing rule was absent.")) return false;

            auto mismatched = expected;
            mismatched.insert("description", "A distinct expected owner that must not replace the existing rule");
            RuleDiagnostic mismatchedContext;
            QJsonObject mismatchedDiagnostic;
            QString mismatchedError;
            if (!check(!addAndObserve(rules.value, nullptr, mismatched, mismatchedContext, &mismatchedError, &mismatchedDiagnostic)
                       && !mismatchedError.isEmpty()
                       && mismatchedDiagnostic.value("hresult") == QJsonValue(originalHresult)
                       && mismatchedDiagnostic.value("persisted_rule_state") == QJsonValue("present")
                       && mismatchedDiagnostic.value("ownership_state") == QJsonValue("mismatch"),
                       "Failed Add confused a matching name with exact rule ownership.")) return false;
            if (!exact(first)
                || !check(!originalJournal.isEmpty() && bytes(first.path) == originalJournal
                          && readRecord(first.path) == first.record,
                          "Failed Add observation changed existing native rules or the encrypted journal.")) return false;
            absentDiagnostic.insert("existing_state", existingDiagnostic);
            absentDiagnostic.insert("mismatched_state", mismatchedDiagnostic);
            result.diagnostic = absentDiagnostic;
            recoveryEvidence.insert("native_add_hresult", originalHresult);
            recoveryEvidence.insert("null_rule_add_native", true);
            recoveryEvidence.insert("post_add_absence_confirmed", true);
            recoveryEvidence.insert("existing_rules_unchanged", true);
            recoveryEvidence.insert("recovery_journal_unchanged", true);
            return true;
        }
        if (scenario == FixtureCase::NameCollision) {
            const auto originalJournal = bytes(first.path);
            auto conflicting = first.record.value("rules").toArray().first().toObject();
            conflicting.insert("description", "A different owner must never replace this disabled fixture");
            QString failure;
            QJsonObject diagnostic;
            const bool applied = applyRule(rules.value, conflicting, &failure, &diagnostic);
            result.diagnostic = diagnostic;
            if (!check(!applied && !failure.isEmpty()
                       && diagnostic.value("operation") == QJsonValue("INetFwRules::Item")
                       && diagnostic.value("add_attempted") == QJsonValue(false)
                       && diagnostic.value("persisted_rule_state") == QJsonValue("present")
                       && diagnostic.value("ownership_state") == QJsonValue("mismatch"),
                       "A same-name rule with a different expected owner was not refused before Add.")) return false;
            if (!exact(first)
                || !check(!originalJournal.isEmpty() && bytes(first.path) == originalJournal
                          && readRecord(first.path) == first.record,
                          "Collision refusal changed the original rule or encrypted recovery record.")) return false;
            recoveryEvidence.insert("same_name_different_owner_refused", true);
            recoveryEvidence.insert("existing_rules_unchanged", true);
            recoveryEvidence.insert("recovery_journal_unchanged", true);
            return true;
        }
        if (scenario == FixtureCase::UnknownOwnership) {
            const auto originalJournal = bytes(first.path);
            // Only the read failure is injected after a real Item call. This
            // is not evidence of an actual firewall-service outage; the rules,
            // DPAPI journal, refusal path and later normal cleanup are real.
            const auto refused = cleanupLocked(first.path, first.record, true);
            result.diagnostic = refused.diagnostic;
            if (!check(!refused.ok && !refused.error.isEmpty()
                       && refused.diagnostic.value("operation") == QJsonValue("fixture::snapshotReadFailure")
                       && refused.diagnostic.value("hresult") == QJsonValue("0x80070005")
                       && refused.diagnostic.value("hresult_source") == QJsonValue("test_injection")
                       && refused.diagnostic.value("ownership_state") == QJsonValue("unknown")
                       && refused.diagnostic.value("persisted_rule_state") == QJsonValue("unknown"),
                       "An explicitly injected snapshot-read failure did not refuse cleanup with unknown ownership.")) return false;
            if (!exact(first)
                || !check(!originalJournal.isEmpty() && bytes(first.path) == originalJournal
                          && readRecord(first.path) == first.record,
                          "Unconfirmed ownership removed a real rule or changed the encrypted journal.")) return false;
            recoveryEvidence.insert("snapshot_read_failure_injected", true);
            recoveryEvidence.insert("unknown_ownership_cleanup_refused", true);
            recoveryEvidence.insert("existing_rules_unchanged", true);
            recoveryEvidence.insert("recovery_journal_unchanged", true);
            return true;
        }
        if (scenario == FixtureCase::RoundTrip) {
            QString duplicateError;
            if (!check(!applyRule(rules.value, first.record.value("rules").toArray().first().toObject(), &duplicateError)
                       && !duplicateError.isEmpty(), "Duplicate native rule creation was not refused.") || !exact(first)) return false;
            const auto restored = cleanupLocked(first.path, first.record);
            return check(restored.ok, restored.error) && absent(first);
        }
        if (scenario == FixtureCase::ExternalEdit) {
            const auto originalBytes = bytes(first.path);
            const auto expected = first.record.value("rules").toArray().last().toObject();
            auto edited = expected;
            edited.insert("description", expected.value("description").toString() + " [fixture external edit]");
            const String name(expected.value("name").toString()), description(edited.value("description").toString());
            Com<INetFwRule> rule;
            auto hr = name.value ? rules->Item(name, rule.out()) : E_OUTOFMEMORY;
            if (SUCCEEDED(hr)) hr = description.value ? rule->put_Description(description) : E_OUTOFMEMORY;
            if (!check(SUCCEEDED(hr), hrError("fixture external edit", hr))) return false;
            scriptedEdits.insert(expected.value("name").toString());
            QJsonObject actual;
            if (!observed(expected, &actual) || !check(actual == edited, "The deliberate external edit was not observed.")) return false;
            const auto refused = cleanupLocked(first.path, first.record);
            result.diagnostic = refused.diagnostic;
            if (!check(!refused.ok && !refused.error.isEmpty(), "Owned cleanup did not reject an external rule edit.")
                || !check(refused.diagnostic.value("ownership_state") == QJsonValue("mismatch")
                          && refused.diagnostic.value("cleanup_required") == QJsonValue(true)
                          && refused.diagnostic.value("journal_retained") == QJsonValue(true)
                          && refused.diagnostic.value("removed_count") == QJsonValue(0),
                          "External modification did not retain explicit conflict and recovery diagnostics.")
                || !check(bytes(first.path) == originalBytes && readRecord(first.path) == first.record,
                          "A recovery conflict changed or removed its encrypted journal.")) return false;
            if (!observed(expected, &actual) || !check(actual == edited, "Conflict recovery modified the external edit.")) return false;
            const auto tcp = first.record.value("rules").toArray().first().toObject();
            return observed(tcp, &actual) && check(actual == tcp, "Reverse recovery did not stop at the edited UDP rule.");
        }
        if (scenario == FixtureCase::IndependentOwnership) {
            if (!add()) return false;
            const auto second = fixtures.last();
            const auto retainedBytes = bytes(second.path);
            const auto restored = cleanupLocked(first.path, first.record);
            return check(restored.ok, restored.error) && absent(first) && exact(second)
                && check(bytes(second.path) == retainedBytes && readRecord(second.path) == second.record,
                         "Cleaning one owned session changed another fixture or journal.");
        }
        if (scenario == FixtureCase::CrashRecoveryConflict) {
            // Keep an exited process handle alive until the assertions finish,
            // preventing PID reuse from turning this into a synthetic dead PID.
            struct OwnerProcess {
                QProcess process;
                HANDLE handle = nullptr;
                ~OwnerProcess() {
                    if (process.state() != QProcess::NotRunning) {
                        process.kill();
                        process.waitForFinished(5000);
                    }
                    if (handle) CloseHandle(handle);
                }
            } owner;
            const auto ownerReady = directory.filePath("fixture-owner.ready");
            owner.process.start(application, {"--fixture-owner", ownerReady});
            if (!check(owner.process.waitForStarted(5000), "The real fixture owner process did not start.")) return false;
            const auto ownerPid = owner.process.processId();
            bool ready = false;
            for (int attempt = 0; attempt < 50; ++attempt) {
                ready = bytes(ownerReady) == QByteArray::number(ownerPid);
                if (ready || owner.process.waitForFinished(100)) break;
            }
            if (!check(ready && owner.process.state() == QProcess::Running,
                       "The real fixture owner did not acknowledge its identity while alive.")) return false;
            owner.handle = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, DWORD(ownerPid));
            if (!check(owner.handle && WaitForSingleObject(owner.handle, 0) == WAIT_TIMEOUT
                       && processPath(owner.handle).compare(application, Qt::CaseInsensitive) == 0,
                       "The fixture child process identity could not be verified.")) return false;
            const auto stamp = processStamp(owner.handle);
            if (!check(!stamp.isEmpty(), "The fixture child creation timestamp is unavailable.")) return false;

            // The actual rules keep production names/identity but remain
            // disabled and loopback-only. Only the encrypted expected journal
            // describes an enabled RFC1918 session; it is NEVER applied.
            if (!add(true)) return false;
            const auto foreign = fixtures.last();
            const auto session = foreign.record.value("session").toString();
            QJsonArray expectedRules;
            for (const auto &value : foreign.record.value("rules").toArray()) {
                auto expected = value.toObject();
                expected.insert("enabled", true);
                expected.insert("local_addresses", "192.168.254.1");
                expected.insert("remote_addresses", "192.168.254.0/24");
                expectedRules.append(expected);
            }
            const QJsonObject journal{
                {"schema", 1}, {"session", session}, {"owner_pid", double(ownerPid)}, {"owner_creation", stamp},
                {"listen_ip", "192.168.254.1"}, {"prefix", 24}, {"interface_index", 1},
                {"interface_guid", QUuid::createUuid().toString()}, {"interface_name", alias}, {"profile", 2},
                {"application", application}, {"phase", "active"}, {"rules", expectedRules},
                {"host_addresses", QJsonArray{"192.168.254.1"}}};
            if (!check(validateJournal(journal), "The recovery safety test must pass the unmodified production journal validator."))
                return false;
            recoveryEvidence.insert("production_journal_valid", true);
            const auto recoveryPath = directory.filePath("dead-owner-recovery.dpapi");
            if (!check(writeRecord(recoveryPath, journal), "Cannot write the real recovery-path DPAPI journal.")) return false;
            preserveRecoveryEvidence = true;
            const auto originalJournal = bytes(recoveryPath);
            const auto independentJournal = bytes(first.path);
            const auto foreignJournal = bytes(foreign.path);
            const auto unchanged = [&]() {
                return check(!originalJournal.isEmpty() && bytes(recoveryPath) == originalJournal
                             && readRecord(recoveryPath) == journal,
                             "Refused recovery changed the production-format DPAPI journal.")
                    && exact(foreign) && exact(first)
                    && check(bytes(first.path) == independentJournal && readRecord(first.path) == first.record
                             && bytes(foreign.path) == foreignJournal && readRecord(foreign.path) == foreign.record,
                             "Refused recovery changed another fixture's encrypted ownership record.");
            };
            if (!check(ownerAlive(journal), "The production owner check did not recognize the live fixture child.")) return false;
            const auto active = recover(recoveryPath, session, true);
            const auto ownershipError = QStringLiteral("LAN 恢复记录属于另一个活动会话，未清理它的规则。");
            if (!check(!active.ok && active.error == ownershipError && active.record == journal,
                       "Production recovery did not reject the still-live owner at the ownership gate.") || !unchanged()) return false;
            recoveryEvidence.insert("live_owner_rejected", true);
            const auto wrongSession = recover(recoveryPath, QUuid::createUuid().toString(QUuid::Id128), false);
            if (!check(!wrongSession.ok && wrongSession.error == ownershipError && wrongSession.record == journal,
                       "Production recovery did not reject the wrong session at the ownership gate.") || !unchanged()) return false;
            recoveryEvidence.insert("wrong_session_rejected", true);

            owner.process.kill();
            if (!check(owner.process.waitForFinished(5000) && WaitForSingleObject(owner.handle, 0) == WAIT_OBJECT_0
                       && processStamp(owner.handle) == stamp && !ownerAlive(journal),
                       "The fixture owner exit was not proved by both Windows and the production owner check.")) return false;
            recoveryEvidence.insert("dead_owner", true);
            const auto refused = recover(recoveryPath, session, true);
            if (!check(!refused.ok && refused.record == journal
                       && refused.error == diagnosticError(
                           QStringLiteral("LAN 防火墙规则被外部修改或无法读取，未覆盖它；恢复记录已保留。"), refused.diagnostic)
                       && refused.diagnostic.value("ownership_state") == QJsonValue("mismatch")
                       && refused.diagnostic.value("cleanup_required") == QJsonValue(true)
                       && refused.diagnostic.value("journal_retained") == QJsonValue(true),
                       "Dead-owner recovery did not reach and reject the non-owned rule snapshot.") || !unchanged()) return false;
            recoveryEvidence.insert("recovery_refused", true);
            recoveryEvidence.insert("foreign_rules_preserved", true);
            recoveryEvidence.insert("independent_rules_preserved", true);
            recoveryEvidence.insert("recovery_journal_unchanged", true);
            // Only remove this synthetic expected journal after every real
            // recovery assertion succeeded. Actual rules are cleaned below
            // using their separately recorded exact disabled snapshots.
            if (!check(QFile::remove(recoveryPath), "Cannot remove the verified test-only recovery journal.")) return false;
            preserveRecoveryEvidence = false;
            return true;
        }
        return check(false, "Unknown native fixture scenario.");
    };
    result.ok = exercise();
    bool cleanupComplete = true;
    for (auto it = fixtures.crbegin(); it != fixtures.crend(); ++it) {
        if (!QFileInfo::exists(it->path)) continue;
        if (readRecord(it->path) != it->record) {
            cleanupComplete = false;
            check(false, "The fixture journal changed unexpectedly; encrypted recovery evidence is retained (path redacted).");
            continue;
        }
        // Undo only the exact edit this fixture just made. If any other property
        // changed, production cleanupLocked preserves the rule and the journal.
        for (const auto &value : it->record.value("rules").toArray()) {
            const auto expected = value.toObject();
            if (!scriptedEdits.contains(expected.value("name").toString())) continue;
            auto edited = expected;
            edited.insert("description", expected.value("description").toString() + " [fixture external edit]");
            const String name(expected.value("name").toString());
            Com<INetFwRule> rule;
            if (name.value && SUCCEEDED(rules->Item(name, rule.out())) && ruleSnapshot(rule.value) == edited) {
                const String description(expected.value("description").toString());
                if (!description.value || FAILED(rule->put_Description(description)) || ruleSnapshot(rule.value) != expected) {
                    cleanupComplete = false;
                    check(false, "Cannot restore the fixture's exact deliberate edit; the journal is retained.");
                }
            }
        }
        const auto restored = cleanupLocked(it->path, it->record);
        if (!restored.ok) { cleanupComplete = false; check(false, restored.error + " Encrypted recovery journal retained (path redacted)."); }
        else if (!absent(*it)) cleanupComplete = false;
    }
    if (preserveRecoveryEvidence) cleanupComplete = false;
    if (cleanupComplete) cleanupComplete = directory.remove();
    result.ok = result.ok && cleanupComplete;
    if (!cleanupComplete && result.error.isEmpty()) result.error = "The isolated native fixture directory could not be removed.";
    if (!cleanupComplete) result.error += " Isolated encrypted recovery evidence retained (directory path redacted).";
    result.record = {{"native_com", true}, {"enabled", false}, {"local_address", "127.0.0.1"},
                     {"remote_addresses", "127.0.0.1/32"}, {"tcp_and_udp", true},
                     {"cleanup_complete", cleanupComplete}};
    for (auto it = recoveryEvidence.begin(); it != recoveryEvidence.end(); ++it)
        result.record.insert(it.key(), it.value());
#else
    Q_UNUSED(scenario);
    result.error = "The native COM firewall fixture requires Windows.";
#endif
    return result;
}
#endif


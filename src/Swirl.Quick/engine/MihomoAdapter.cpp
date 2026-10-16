#include "MihomoAdapter.h"
#include "MihomoLogDiagnostic.h"
#include <cmath>
#include <QDateTime>
#include <QCryptographicHash>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QUrlQuery>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QProcessEnvironment>
#include <QRandomGenerator>
#include <QSaveFile>
#include <QSet>
#include <algorithm>
#include <QStandardPaths>
#ifdef Q_OS_WIN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <sddl.h>
#endif

MihomoAdapter::MihomoAdapter(QObject *parent) : ProxyEngine(parent) {
    m_network.setProxy(QNetworkProxy::NoProxy);
    m_deadline.setSingleShot(true);
    m_killTimer.setSingleShot(true);
    connect(&m_process, &QProcess::started, this, [this] { publish(); });
    connect(&m_process, &QProcess::finished, this, &MihomoAdapter::processFinished);
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            fail(Error::ProcessStartFailed, QStringLiteral("Mihomo 进程启动失败：") + m_process.errorString());
            unlockExecutable();
            m_directory.reset();
        }
    });
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        const auto data = m_process.readAllStandardOutput();
        if (m_stage == Stage::Version) m_output = (m_output + data).left(16384);
        // Do not forward engine output: it may contain configuration secrets.
    });
    connect(&m_poll, &QTimer::timeout, this, &MihomoAdapter::refresh);
    connect(&m_deadline, &QTimer::timeout, this, [this] {
        fail(Error::StartupTimeout, QStringLiteral("Mihomo 启动超时：未在期限内完成版本、配置和认证 API 检查。") + m_status.message);
    });
    connect(&m_killTimer, &QTimer::timeout, this, [this] {
        if (m_process.state() != QProcess::NotRunning) m_process.kill();
    });
}

MihomoAdapter::~MihomoAdapter() {
    m_poll.stop(); m_deadline.stop(); m_killTimer.stop();
    cancelRequest();
    cancelNodeRequests();
    if (m_process.state() != QProcess::NotRunning) { m_process.kill(); m_process.waitForFinished(3000); }
    unlockExecutable();
}

ProxyEngine::Status MihomoAdapter::status() const {
    auto result = m_status;
    result.processAlive = m_process.state() == QProcess::Running;
    result.processId = result.processAlive ? m_process.processId() : 0;
    result.uptimeSeconds = m_uptime.isValid() && m_stage == Stage::Engine && result.processAlive
        ? m_uptime.elapsed() / 1000 : 0;
    return result;
}
void MihomoAdapter::publish() {
    if(!m_status.telemetryError.isEmpty()&&property("lastTelemetryError").toString()!=m_status.telemetryError){setProperty("lastTelemetryError",m_status.telemetryError);emit diagnostic("Telemetry","CollectionFailed",m_status.telemetryError);}
    emit statusChanged();
}

QString MihomoAdapter::configurationSummary() const {
    // A redacted copy is inspectable; the authenticated file is kept private.
    auto result = m_generatedConfig;
    if (!m_options.selectedNodeId.isEmpty() || m_options.directSession) {
        result = result.left(result.indexOf(QStringLiteral("proxies:"))) + QStringLiteral("节点配置已生成，全部节点凭据已隐藏。\n");
    }
    result.replace(QRegularExpression("authentication: [^\\n]*"),QStringLiteral("authentication: [<已隐藏>]"));
    if (!m_secret.isEmpty()) result.replace(QString::fromLatin1(m_secret), QStringLiteral("<每次启动随机生成，已隐藏>"));
    return result;
}

void MihomoAdapter::unlockExecutable() {
    m_executable.reset();
#ifdef Q_OS_WIN
    if (m_executableHandle) CloseHandle(static_cast<HANDLE>(m_executableHandle));
#endif
    m_executableHandle = nullptr;
}

bool MihomoAdapter::lockAndVerifyExecutable() {
    const QFileInfo info(m_options.executablePath);
    if (!info.exists() || !info.isFile()) {
        fail(Error::MissingExecutable, QStringLiteral("找不到 Mihomo 程序：") + m_options.executablePath);
        return false;
    }
#ifdef Q_OS_WIN
    // Prevent replacement between verification and every CreateProcess call.
    auto handle = CreateFileW(reinterpret_cast<LPCWSTR>(m_options.executablePath.utf16()),
        GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        fail(Error::IntegrityMismatch, QStringLiteral("无法锁定 Mihomo 程序以安全校验。"));
        return false;
    }
    m_executableHandle = handle;
#endif
    m_executable = std::make_unique<QFile>(m_options.executablePath);
    if (!m_executable->open(QIODevice::ReadOnly) || m_executable->size() > 128 * 1024 * 1024) {
        fail(Error::IntegrityMismatch, QStringLiteral("无法读取 Mihomo 程序，或程序大小超过校验上限。"));
        unlockExecutable(); return false;
    }
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if (!hash.addData(m_executable.get()) || hash.result().toHex() != m_options.expectedSha256.toLower()) {
        fail(Error::IntegrityMismatch, QStringLiteral("Mihomo SHA-256 不匹配；已拒绝执行。"));
        unlockExecutable(); return false;
    }
    return true;
}

bool MihomoAdapter::prepareConfiguration() {
    const auto root = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + QStringLiteral("/engine");
    if (!QDir().mkpath(root)) return false;
    m_directory = std::make_unique<QTemporaryDir>(root + QStringLiteral("/session-XXXXXX"));
    if (!m_directory->isValid()) return false;
#ifdef Q_OS_WIN
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;OW)",
            SDDL_REVISION_1, &descriptor, nullptr)) return false;
    const bool secured = SetFileSecurityW(reinterpret_cast<LPCWSTR>(m_directory->path().utf16()),
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, descriptor);
    LocalFree(descriptor);
    if (!secured) return false;
#else
    if (!QFile::setPermissions(m_directory->path(), QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner)) return false;
#endif
    QByteArray random(32, Qt::Uninitialized);
    for (int i = 0; i < 32; i += 4) {
        const quint32 value = QRandomGenerator::system()->generate();
        memcpy(random.data() + i, &value, 4);
    }
    m_secret = random.toHex();
    m_status.configPath = m_directory->filePath(QStringLiteral("config.yaml"));
    m_generatedConfig = QStringLiteral(
        "external-controller: '127.0.0.1:%1'\nsecret: '%2'\n"
        "allow-lan: false\nbind-address: '127.0.0.1'\nmode: direct\n"
        "port: 0\nsocks-port: 0\nmixed-port: 0\nredir-port: 0\ntproxy-port: 0\n"
        "ipv6: false\nlog-level: warning\nfind-process-mode: always\ngeodata-mode: false\n"
        "disable-keep-alive: false\nkeep-alive-idle: 30\nkeep-alive-interval: 15\ntcp-concurrent: true\n"
        "geo-auto-update: false\nprofile:\n  store-selected: false\n  store-fake-ip: false\n"
        "tun:\n  enable: false\n  auto-route: false\n  auto-detect-interface: false\n"
        "dns:\n  enable: false\nproxies: []\nproxy-groups: []\nrules: []\n")
        .arg(m_options.controlPort).arg(QString::fromLatin1(m_secret));
    if (!m_options.selectedNodeId.isEmpty() || m_options.directSession) {
        QJsonArray proxies, names;
        names.append(m_options.selectedNodeId.isEmpty()?QStringLiteral("DIRECT"):m_options.selectedNodeId);
        for (const auto &n : m_options.nodes) {
            auto proxy=n.parameters;
            proxy.insert("name",n.id);proxy.insert("type",n.protocol);
            if(!n.host.isEmpty())proxy.insert("server",n.host);
            if(n.port)proxy.insert("port",n.port);
            if(!proxy.contains("udp"))proxy.insert("udp",false);
            proxy.insert("skip-cert-verify",false);
            if(n.protocol=="easytier")proxy.insert("no-listener",true);
            if (!n.password.isEmpty()) proxy.insert("password",n.password);
            if (!n.username.isEmpty()) proxy.insert("username",n.username);
            if (!n.cipher.isEmpty()) proxy.insert("cipher",n.cipher);
            if(!n.serverName.isEmpty())proxy.insert(n.protocol=="vmess"||n.protocol=="vless"?"servername":"sni",n.serverName);
            if(proxy.contains("dialer-proxy")) {
                const auto target=proxy.value("dialer-proxy").toString();
                for(const auto &candidate:m_options.nodes)if(candidate.sourceId==n.sourceId && candidate.name==target){proxy.insert("dialer-proxy",candidate.id);break;}
            }
            if (n.protocol=="trojan") { proxy.insert("sni",n.serverName.isEmpty()?n.host:n.serverName); proxy.insert("skip-cert-verify",false); }
            proxies.append(proxy); if (n.id!=m_options.selectedNodeId) names.append(n.id);
        }
        QJsonArray groups{QJsonObject{{"name","SWIRL"},{"type","select"},{"proxies",names}},
            QJsonObject{{"name","GLOBAL"},{"type","select"},{"proxies",QJsonArray{"SWIRL"}}}};
        for(const auto &group:m_options.customGroups)groups.append(QJsonObject::fromVariantMap(group.toMap()));
        m_generatedConfig.replace("mode: direct\n",QStringLiteral("mode: %1\n").arg(m_options.routingMode));
        m_generatedConfig.replace("mixed-port: 0\n",QStringLiteral("mixed-port: %1\n").arg(m_options.proxyPort));
        m_generatedConfig.replace("proxies: []\n",QStringLiteral("proxies: ")+QString::fromUtf8(QJsonDocument(proxies).toJson(QJsonDocument::Compact))+"\n");
        m_generatedConfig.replace("proxy-groups: []\n",QStringLiteral("proxy-groups: ")+QString::fromUtf8(QJsonDocument(groups).toJson(QJsonDocument::Compact))+"\n");
        if(m_options.smartRouting) {
            QFile manifest(m_options.rulesDirectory+"/manifest.json");
            if(!manifest.open(QIODevice::ReadOnly))return false;
            const auto files=QJsonDocument::fromJson(manifest.readAll()).object().value("files").toArray();
            if(files.size()!=2)return false;
            QSet<QString> copied;
            for(const auto &entry:files) {
                const auto obj=entry.toObject();const auto name=obj.value("name").toString();
                if(name!="cn-domain.mrs"&&name!="cn-ip.mrs")return false;
                QFile data(m_options.rulesDirectory+"/"+name);
                if(!data.open(QIODevice::ReadOnly)||data.size()>16*1024*1024)return false;
                QCryptographicHash hash(QCryptographicHash::Sha256);
                if(!hash.addData(&data)||hash.result().toHex()!=obj.value("sha256").toString().toLatin1())return false;
                data.close();if(!QFile::copy(data.fileName(),m_directory->filePath(name)))return false;copied.insert(name);
            }
            if(copied.size()!=2)return false;
            m_generatedConfig += QStringLiteral(
                "rule-providers:\n  cn-domain:\n    type: file\n    behavior: domain\n    format: mrs\n    path: ./cn-domain.mrs\n"
                "  cn-ip:\n    type: file\n    behavior: ipcidr\n    format: mrs\n    path: ./cn-ip.mrs\n");
            // Keep Codex HTTPS and WebSocket hosts on the active SWIRL selector
            // before a CN ruleset or CDN IP can route one endpoint directly.
            m_generatedConfig.replace("rules: []\n",QStringLiteral(
                "rules:\n  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve\n  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve\n"
                "  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve\n  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve\n"
                "  - IP-CIDR,169.254.0.0/16,DIRECT,no-resolve\n  - IP-CIDR6,::1/128,DIRECT,no-resolve\n"
                "  - IP-CIDR6,fc00::/7,DIRECT,no-resolve\n  - IP-CIDR6,fe80::/10,DIRECT,no-resolve\n"
                "  - DOMAIN,localhost,DIRECT\n  - DOMAIN-SUFFIX,local,DIRECT\n"
                "  - DOMAIN-SUFFIX,google.com,SWIRL\n  - DOMAIN-SUFFIX,google.com.hk,SWIRL\n"
                "  - DOMAIN-SUFFIX,gstatic.com,SWIRL\n  - DOMAIN-SUFFIX,googleapis.com,SWIRL\n"
                "  - DOMAIN-SUFFIX,googleusercontent.com,SWIRL\n  - DOMAIN-SUFFIX,youtube.com,SWIRL\n"
                "  - DOMAIN-SUFFIX,youtu.be,SWIRL\n  - DOMAIN-SUFFIX,ytimg.com,SWIRL\n"
                "  - DOMAIN-SUFFIX,googlevideo.com,SWIRL\n  - DOMAIN-SUFFIX,ggpht.com,SWIRL\n"
                "  - DOMAIN-SUFFIX,chatgpt.com,SWIRL\n  - DOMAIN-SUFFIX,openai.com,SWIRL\n"
                "  - DOMAIN-SUFFIX,oaistatic.com,SWIRL\n  - DOMAIN-SUFFIX,oaiusercontent.com,SWIRL\n"
                "  - DOMAIN-SUFFIX,auth0.com,SWIRL\n  - DOMAIN-SUFFIX,statsigapi.net,SWIRL\n"
                "  - RULE-SET,cn-domain,DIRECT\n  - RULE-SET,cn-ip,DIRECT\n  - MATCH,SWIRL\n"));
            // Internal DNS serves Mihomo only: no system DNS or listener changes.
            // Foreign domain resolution uses DoH through SWIRL; proxy bootstrap
            // and domestic direct traffic use the existing system resolver.
            m_generatedConfig.replace("dns:\n  enable: false\n",QStringLiteral(
                "dns:\n  enable: true\n  ipv6: false\n  enhanced-mode: redir-host\n"
                "  default-nameserver: [system]\n  proxy-server-nameserver: [system]\n"
                "  direct-nameserver: [system]\n  direct-nameserver-follow-policy: false\n"
                "  nameserver: ['https://1.1.1.1/dns-query#SWIRL']\n"
                "  nameserver-policy:\n"
                "    '+.chatgpt.com': ['https://1.1.1.1/dns-query#SWIRL']\n"
                "    '+.openai.com': ['https://1.1.1.1/dns-query#SWIRL']\n"
                "    '+.oaistatic.com': ['https://1.1.1.1/dns-query#SWIRL']\n"
                "    '+.oaiusercontent.com': ['https://1.1.1.1/dns-query#SWIRL']\n"
                "    'rule-set:cn-domain': [system]\n"));
        } else m_generatedConfig.replace("rules: []\n","rules: ['MATCH,SWIRL']\n");
    }
    if(!m_options.selectedNodeId.isEmpty() || m_options.directSession) {
        if(!m_options.customRules.isEmpty()) {
            QString prefix="rules:\n";
            for(const auto &rule:m_options.customRules)prefix+="  - "+QString::fromUtf8(QJsonDocument(QJsonArray{rule}).toJson(QJsonDocument::Compact)).mid(1).chopped(1)+"\n";
            if(m_generatedConfig.contains("rules:\n"))m_generatedConfig.replace("rules:\n",prefix);
            else m_generatedConfig.replace("rules: ['MATCH,SWIRL']\n",prefix+"  - MATCH,SWIRL\n");
        }
        if(!m_options.dnsConfig.isEmpty()) {
            const auto config=m_options.dnsConfig;
            QStringList nameservers;
            const auto mode=config.value("mode").toInt();
            if(mode!=2)nameservers.append("system");
            if(mode!=0)for(const auto &part:config.value("servers").toString().split(',',Qt::SkipEmptyParts))nameservers.append(part.trimmed());
            const auto encrypted=config.value("encrypted").toString();if(!encrypted.isEmpty())nameservers={encrypted};
            QJsonObject dns{{"enable",true},{"ipv6",false},{"enhanced-mode","redir-host"},{"default-nameserver",QJsonArray{"system"}},
                {"proxy-server-nameserver",QJsonArray{"system"}},{"nameserver",QJsonArray::fromStringList(nameservers)},
                {"use-hosts",true},{"use-system-hosts",config.value("useHosts",true).toBool()},{"respect-rules",config.value("respectRules",false).toBool()}};
            const auto begin=m_generatedConfig.indexOf("dns:\n"),end=m_generatedConfig.indexOf("proxies:",begin);
            if(begin>=0&&end>begin)m_generatedConfig.replace(begin,end-begin,"dns: "+QString::fromUtf8(QJsonDocument(dns).toJson(QJsonDocument::Compact))+"\n");
            QJsonObject hosts;for(const auto &entry:config.value("hosts").toList()){const auto row=entry.toMap();hosts[row.value("name").toString()]=row.value("value").toString();}
            if(!hosts.isEmpty())m_generatedConfig+="hosts: "+QString::fromUtf8(QJsonDocument(hosts).toJson(QJsonDocument::Compact))+"\n";
        }
    }
    if(m_options.meteredNetwork) {
        if(m_options.routingMode!="rule"){fail(Error::ConfigurationFailed,QStringLiteral("计费网络模式必须使用规则判定。"));return false;}
        QString guard="MATCH,REJECT";
        if(!m_options.meteredAllowlist.isEmpty()) {
            QStringList conditions;
            for(const auto &process:m_options.meteredAllowlist){
                if(!QRegularExpression("^[A-Za-z0-9_. -]{1,128}\\.exe$").match(process).hasMatch()){fail(Error::InvalidOptions,QStringLiteral("计费网络允许名单无效。"));return false;}
                conditions.append("(NOT,((PROCESS-NAME,"+process+")))");
            }
            guard="AND,("+conditions.join(',')+"),REJECT";
        }
        const auto encoded=QString::fromUtf8(QJsonDocument(QJsonArray{guard}).toJson(QJsonDocument::Compact)).mid(1).chopped(1);
        if(m_generatedConfig.contains("rules:\n"))m_generatedConfig.replace("rules:\n","rules:\n  - "+encoded+"\n");
        else m_generatedConfig.replace("rules: ['MATCH,SWIRL']\n","rules:\n  - "+encoded+"\n  - MATCH,SWIRL\n");
    }
    if(m_options.allowLan&&(!m_options.selectedNodeId.isEmpty()||m_options.directSession)) {
        if(m_options.lanUsername.isEmpty()||m_options.lanPassword.isEmpty()){fail(Error::ConfigurationFailed,QStringLiteral("局域网代理缺少认证凭据。"));return false;}
        m_generatedConfig.replace("allow-lan: false\n","allow-lan: true\n");m_generatedConfig.replace("bind-address: '127.0.0.1'\n",QStringLiteral("bind-address: %1\n").arg(QString::fromUtf8(QJsonDocument(QJsonArray{m_options.lanBindAddress}).toJson(QJsonDocument::Compact)).mid(1).chopped(1)));
        m_generatedConfig+="authentication: "+QString::fromUtf8(QJsonDocument(QJsonArray{m_options.lanUsername+":"+m_options.lanPassword}).toJson(QJsonDocument::Compact))+"\n";
        m_generatedConfig+=m_options.lanSkipLocalAuthentication?"skip-auth-prefixes: ['127.0.0.1/8', '::1/128']\n":"skip-auth-prefixes: []\n";
    }
    else if(!m_options.inboundUsername.isEmpty()){
        m_generatedConfig+="authentication: "+QString::fromUtf8(QJsonDocument(QJsonArray{m_options.inboundUsername+":"+m_options.inboundPassword}).toJson(QJsonDocument::Compact))+"\n";
        m_generatedConfig+="skip-auth-prefixes: []\n";
    }
    if(m_options.tunEnabled&&(!m_options.selectedNodeId.isEmpty()||m_options.directSession)) {
        const QJsonObject tun{{"enable",true},{"device","Swirl"},{"stack","gvisor"},{"auto-route",true},
            {"auto-detect-interface",true},{"strict-route",!m_options.gatewayForwarding},{"mtu",1500},{"dns-hijack",QJsonArray{"any:53","tcp://any:53"}}};
        m_generatedConfig.replace("tun:\n  enable: false\n  auto-route: false\n  auto-detect-interface: false\n","tun: "+QString::fromUtf8(QJsonDocument(tun).toJson(QJsonDocument::Compact))+"\n");
        if(m_generatedConfig.contains("dns:\n  enable: false\n"))m_generatedConfig.replace("dns:\n  enable: false\n","dns: {enable: true, enhanced-mode: redir-host, nameserver: [system]}\n");
    }
    // Diagnose explicit user overrides; do not silently rewrite user rules or
    // copy client-specific Clash Verge settings into a Mihomo configuration.
    const QStringList protectedDomains{"chatgpt.com","openai.com","oaistatic.com","oaiusercontent.com"};
    int ruleIndex=0;
    for(const auto &rule:m_options.customRules){
        ++ruleIndex;const auto parts=rule.split(',');if(parts.size()<3)continue;
        const auto pattern=parts[1].toLower();bool affects=false;
        if(parts[0]=="PROCESS-NAME")affects=pattern=="codex.exe"||pattern=="chatgpt.exe";
        else if(parts[0]=="DOMAIN"||parts[0]=="DOMAIN-SUFFIX")for(const auto &domain:protectedDomains)
            affects=affects||pattern==domain||pattern.endsWith("."+domain)||(parts[0]=="DOMAIN-SUFFIX"&&domain.endsWith("."+pattern));
        if(affects&&parts[2]!="SWIRL"&&parts[2]!="GLOBAL")emit diagnostic("Mihomo","CodexRoutingOverride",QStringLiteral("第 %1 条自定义规则覆盖了 Codex 默认选择器；请核对实际连接链，未自动改写规则。").arg(ruleIndex));
    }
    for(const auto &value:m_options.dnsConfig.value("hosts").toList()){
        const auto name=value.toMap().value("name").toString().toLower();
        for(const auto &domain:protectedDomains)if(name==domain||name.endsWith("."+domain))
            emit diagnostic("Mihomo","CodexDnsHostOverride",QStringLiteral("存在 Codex/OpenAI 域名的显式 hosts 映射；重连时需核对映射，未清空系统或用户 DNS 缓存。"));
    }
    QSaveFile file(m_status.configPath);
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFile::ReadOwner | QFile::WriteOwner)) return false;
    const auto bytes = m_generatedConfig.toUtf8();
    return file.write(bytes) == bytes.size() && file.commit();
}

bool MihomoAdapter::reserveControlPort() {
    if(reservePort(m_reservation,m_options.controlPort))return true;
    if(!m_options.autoControlPort)return false;
    // The authenticated controller is private to this session. Keep a real
    // reservation on an OS-assigned port instead of colliding with another app.
    for(int attempt=0;attempt<3;++attempt){
        if(!reservePort(m_reservation,0))return false;
        if(m_reservation.serverPort()!=m_options.proxyPort){
            m_options.controlPort=m_reservation.serverPort();return true;
        }
        m_reservation.close();
    }
    return false;
}
bool MihomoAdapter::reservePort(QTcpServer &server, quint16 port) {
#ifdef Q_OS_WIN
    // A wildcard listener using SO_REUSEADDR can coexist with a specific bind
    // even if the second socket is exclusive. Reject existing listeners from
    // both address families before reserving, rather than trusting bind alone.
    for (const auto family : {AF_INET, AF_INET6}) {
        DWORD size = 0;
        const auto queried = GetExtendedTcpTable(nullptr, &size, FALSE, family, TCP_TABLE_OWNER_PID_LISTENER, 0);
        if (queried != ERROR_INSUFFICIENT_BUFFER) return false;
        QByteArray table(qsizetype(size), Qt::Uninitialized);
        if (GetExtendedTcpTable(table.data(), &size, FALSE, family, TCP_TABLE_OWNER_PID_LISTENER, 0) != NO_ERROR) return false;
        if (family == AF_INET) {
            const auto *entries = reinterpret_cast<const MIB_TCPTABLE_OWNER_PID *>(table.constData());
            for (DWORD i = 0; i < entries->dwNumEntries; ++i)
                if (ntohs(u_short(entries->table[i].dwLocalPort)) == port) return false;
        } else {
            const auto *entries = reinterpret_cast<const MIB_TCP6TABLE_OWNER_PID *>(table.constData());
            for (DWORD i = 0; i < entries->dwNumEntries; ++i)
                if (ntohs(u_short(entries->table[i].dwLocalPort)) == port) return false;
        }
    }
    // Qt's default Windows bind permits wildcard/specific-address overlap.
    // Exclusive binding detects both existing loopback and wildcard listeners.
    WSADATA winsock{};
    if (WSAStartup(MAKEWORD(2, 2), &winsock) != 0) return false;
    SOCKET descriptor = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    bool ready = false;
    if (descriptor != INVALID_SOCKET) {
        const BOOL exclusive = TRUE;
        sockaddr_in address{}; address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK); address.sin_port = htons(port);
        ready = setsockopt(descriptor, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
                    reinterpret_cast<const char *>(&exclusive), sizeof(exclusive)) == 0 &&
            bind(descriptor, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == 0 &&
            listen(descriptor, SOMAXCONN) == 0 && server.setSocketDescriptor(qintptr(descriptor));
        if (!ready) closesocket(descriptor);
    }
    WSACleanup();
    return ready;
#else
    return server.listen(QHostAddress::LocalHost, port);
#endif
}

void MihomoAdapter::start(const EngineStartOptions &options) {
    if (m_process.state() != QProcess::NotRunning || m_status.state == State::Validating ||
        m_status.state == State::Starting || m_status.state == State::Stopping) return;
    m_modeUnconfirmed=false;cancelRequest(); cancelNodeRequests(); m_poll.stop(); m_deadline.stop(); m_killTimer.stop();
    unlockExecutable(); m_directory.reset(); m_uptime.invalidate();
    m_secret.clear(); m_generatedConfig.clear(); m_output.clear();
    m_options = options; m_status = {}; m_failureExit = false;
    for(const auto &node:options.nodes)if(node.id==options.selectedNodeId&&!node.conversionIssues.isEmpty()){
        fail(Error::InvalidNode,QStringLiteral("此节点存在未映射的订阅选项，不能安全执行。原始配置已加密保留；请使用完整 Clash 节点配置重新导入。"));return;
    }
    m_options.nodes.removeIf([](const ProxyNode &node){return !node.conversionIssues.isEmpty();});
    m_status.executablePath = options.executablePath;
    m_status.controlEndpoint = QStringLiteral("http://127.0.0.1:%1").arg(options.controlPort);
    m_status.state = State::Validating; publish();
    if(options.inboundUsername.isEmpty()!=options.inboundPassword.isEmpty()||options.inboundUsername.toUtf8().size()>255||options.inboundPassword.toUtf8().size()>255||options.inboundUsername.contains(':')||options.inboundUsername.contains(QRegularExpression("[\\x00-\\x1f]"))||options.inboundPassword.contains(QRegularExpression("[\\x00-\\x1f]"))||
       (options.allowLan&&!options.inboundUsername.isEmpty()&&(options.inboundUsername!=options.lanUsername||options.inboundPassword!=options.lanPassword||options.lanSkipLocalAuthentication))){fail(Error::InvalidOptions,QStringLiteral("入站认证参数无效或与 LAN 认证冲突；未启动无认证回退。"));return;}
    if (!QFileInfo(options.executablePath).isAbsolute() || options.controlPort == 0 ||
        options.expectedSha256.size() != 64 || QByteArray::fromHex(options.expectedSha256).size() != 32 ||
        options.expectedVersion.isEmpty() || options.startupTimeoutMs < 100 ||
        options.requestTimeoutMs < 50 || options.healthIntervalMs < 50) {
        fail(Error::InvalidOptions, QStringLiteral("引擎参数无效：需要绝对路径、已校验哈希、版本、端口和有效超时。")); return;
    }
    if (!m_process.ownershipReady()) {
        fail(Error::OwnershipFailed, QStringLiteral("无法建立 Windows 进程归属 Job；已拒绝启动。")); return;
    }
    QSet<QString> nodeIds;
    for (const auto &node : m_options.nodes) {
        const auto error=ProxyNode::validate(node);
        if (!error.isEmpty() || nodeIds.contains(node.id)) { fail(Error::InvalidNode, error.isEmpty()?QStringLiteral("节点标识重复。"):error); return; }
        nodeIds.insert(node.id);
        QSet<QString> visited;auto cursor=&node;
        while(cursor) {
            if(visited.contains(cursor->id)){fail(Error::InvalidNode,QStringLiteral("节点链式代理存在循环引用。"));return;}
            visited.insert(cursor->id);const auto target=cursor->parameters.value("dialer-proxy").toString();
            if(target.isEmpty())break;
            const auto source=cursor->sourceId;cursor=nullptr;
            for(const auto &candidate:m_options.nodes)if(candidate.sourceId==source && candidate.name==target){cursor=&candidate;break;}
            if(!cursor){fail(Error::InvalidNode,QStringLiteral("链式代理引用了未保存的节点。"));return;}
        }
    }
    if(options.routingMode!="rule"&&options.routingMode!="global"&&options.routingMode!="direct") {
        fail(Error::InvalidOptions,QStringLiteral("分流模式无效。"));return;
    }
    if ((!options.selectedNodeId.isEmpty() && !nodeIds.contains(options.selectedNodeId)) || ((!options.selectedNodeId.isEmpty() || options.directSession) && (options.proxyPort==0 || options.proxyPort==options.controlPort))) {
        fail(Error::InvalidNode,QStringLiteral("所选节点或本机代理端口无效。")); return;
    }
    m_status.selectedNodeId=options.selectedNodeId;
    m_status.proxyPort=(options.selectedNodeId.isEmpty()&&!options.directSession)?0:options.proxyPort;
    if (!lockAndVerifyExecutable()) return;
    if (!reserveControlPort()) {
        fail(Error::PortConflict, QStringLiteral("本机控制端口 %1 已占用或不允许绑定；请更换端口。").arg(options.controlPort));
        unlockExecutable(); return;
    }
    m_status.controlEndpoint=QStringLiteral("http://127.0.0.1:%1").arg(m_options.controlPort);
    if (!prepareConfiguration()) {
        fail(Error::ConfigurationFailed, QStringLiteral("无法创建安全运行配置，或国内规则数据缺失/哈希校验失败。请修复安装，未使用空规则回退。"));
        unlockExecutable(); return;
    }
    // Mihomo's mixed listener binds TCP and UDP on the same port. If its UDP
    // bind fails it can close TCP while /configs still advertises mixed-port.
    if ((!options.selectedNodeId.isEmpty()||options.directSession) &&
        (!reservePort(m_proxyReservation,options.proxyPort) ||
         !m_proxyUdpReservation.bind(QHostAddress::LocalHost,options.proxyPort,QUdpSocket::DontShareAddress))) {
        fail(Error::PortConflict,QStringLiteral("本机代理端口 %1 的 TCP 或 UDP 已占用或不允许绑定。请检查是否同时运行了多个 Swirl 或其他代理程序，或更换设置中的本机代理端口。").arg(options.proxyPort));
        unlockExecutable(); m_directory.reset(); return;
    }
    m_deadline.start(options.startupTimeoutMs);
    launch(Stage::Version);
}

void MihomoAdapter::launch(Stage stage) {
    if (m_failureExit || m_status.state == State::Stopped || m_status.state == State::Stopping) return;
    m_stage = stage; m_output.clear();
    auto environment = QProcessEnvironment::systemEnvironment();
    for (const auto &key : environment.keys()) {
        if (key.startsWith(QStringLiteral("CLASH_"), Qt::CaseInsensitive) ||
            key.startsWith(QStringLiteral("MIHOMO_"), Qt::CaseInsensitive) ||
            key == QStringLiteral("SAFE_PATHS")) environment.remove(key);
    }
    m_process.setProcessEnvironment(environment);
    m_process.setProgram(m_options.executablePath);
    m_process.setWorkingDirectory(m_directory->path());
    m_process.setProcessChannelMode(QProcess::MergedChannels);
    QStringList args;
    if (stage == Stage::Version) args = {QStringLiteral("-v")};
    else {
        args = {QStringLiteral("-d"), m_directory->path(), QStringLiteral("-f"), m_status.configPath};
        if (stage == Stage::ValidateConfig) args.prepend(QStringLiteral("-t"));
    }
    if (stage == Stage::Engine) {
        m_status.state = State::Starting;
        m_reservation.close();
        m_proxyReservation.close();
        m_proxyUdpReservation.close();
        m_uptime.start();
    }
    m_process.setArguments(args);
#ifdef Q_OS_WIN
    // Invalid PE files must produce a failed-start signal, not an OS error dialog
    // that blocks CreateProcess and defeats Swirl's asynchronous deadline.
    DWORD previousErrorMode = 0;
    SetThreadErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX, &previousErrorMode);
#endif
    m_process.start();
#ifdef Q_OS_WIN
    SetThreadErrorMode(previousErrorMode, nullptr);
#endif
    publish();
    if (stage == Stage::Engine) m_poll.start(m_options.healthIntervalMs);
}

void MihomoAdapter::processFinished(int code, QProcess::ExitStatus exitStatus) {
    if (m_status.state == State::Stopping || m_failureExit) {
        m_killTimer.stop(); m_deadline.stop(); m_poll.stop();
        m_status.apiHealthy = false;
        m_status.state = m_failureExit ? State::Failed : State::Stopped;
        unlockExecutable(); m_directory.reset(); publish(); return;
    }
    if (m_stage != Stage::Engine) {
        m_output = (m_output + m_process.readAllStandardOutput()).left(16384);
        if (code != 0 || exitStatus != QProcess::NormalExit) {
            fail(m_stage == Stage::Version ? Error::ProcessStartFailed : Error::ConfigurationFailed,
                QStringLiteral("Mihomo %1检查失败（退出码 %2）。")
                    .arg(m_stage == Stage::Version ? QStringLiteral("版本") : QStringLiteral("配置")).arg(code));
            unlockExecutable(); m_directory.reset(); return;
        }
        if (m_stage == Stage::Version && !QString::fromUtf8(m_output).contains(
                QStringLiteral("Mihomo Meta %1 ").arg(m_options.expectedVersion))) {
            fail(Error::IntegrityMismatch, QStringLiteral("Mihomo 版本不符合固定版本要求。"));
            unlockExecutable(); m_directory.reset(); return;
        }
        const auto next = m_stage == Stage::Version ? Stage::ValidateConfig : Stage::Engine;
        const auto generation = m_generation;
        QTimer::singleShot(0, this, [this, next, generation] { if (generation == m_generation) launch(next); }); return;
    }
    fail(Error::UnexpectedExit, QStringLiteral("Mihomo 意外退出（退出码 %1，%2）。")
        .arg(code).arg(exitStatus == QProcess::CrashExit ? QStringLiteral("异常终止") : QStringLiteral("正常退出")));
    unlockExecutable(); m_directory.reset();
}

void MihomoAdapter::fail(Error error, const QString &message) {
    m_failureExit = true;
    m_poll.stop(); m_deadline.stop(); m_reservation.close(); cancelRequest();
    m_proxyReservation.close(); m_proxyUdpReservation.close(); cancelNodeRequests();
    m_status.proxyPort=0; m_status.nodeHealth=NodeHealth::Unknown; m_status.requestState=RequestState::NotTested;
    m_status.nodeMessage.clear(); m_status.latencyMs=-1; m_status.responseCode=0;
    m_status.state = State::Failed; m_status.error = error; m_status.message = message;
    m_status.apiHealthy = false;
    if (m_process.state() != QProcess::NotRunning) m_process.kill();
    publish();
}

void MihomoAdapter::cancelRequest() {
    // Invalidate callbacks BEFORE abort(), which can emit finished inline.
    ++m_generation;
    if(m_startupListener){auto *socket=m_startupListener.data();m_startupListener=nullptr;socket->disconnect(this);socket->abort();socket->deleteLater();}
    if(m_connectionsReply){m_connectionsReply->abort();m_connectionsReply->deleteLater();m_connectionsReply=nullptr;}
    if(m_trafficReply){auto reply=m_trafficReply.data();m_trafficReply=nullptr;reply->disconnect(this);reply->abort();reply->deleteLater();}
    if(m_logsReply){auto reply=m_logsReply.data();m_logsReply=nullptr;reply->disconnect(this);reply->abort();reply->deleteLater();}m_logsBuffer.clear();
    m_trafficBuffer.clear();m_status.trafficAt=0;m_status.connectionsAt=0;
    m_status.connections.clear();m_status.routingBusy=false;
    if(m_modeReply){m_modeReply->abort();m_modeReply->deleteLater();m_modeReply=nullptr;}
    if (m_reply) {
        auto *reply = m_reply.data(); m_reply = nullptr;
        reply->disconnect(this); reply->abort(); reply->deleteLater();
    }
}

void MihomoAdapter::cancelNodeRequests() {
    ++m_nodeGeneration;
    for (auto *reply : {m_nodeReply.data(),m_probeReply.data()}) {
        if (reply) { reply->disconnect(this); reply->abort(); reply->deleteLater(); }
    }
    m_nodeReply=nullptr; m_probeReply=nullptr; m_status.nodeBusy=false;
    m_selectionPending=false;
}
void MihomoAdapter::nodeFailure(const QString &message) {
    m_status.nodeBusy=false; m_status.nodeMessage=message;
    m_status.nodeHealth=NodeHealth::Unavailable; m_status.requestState=RequestState::NotTested; publish();
}
static void boundReply(QNetworkReply *reply, int milliseconds) {
    auto *timer=new QTimer(reply); timer->setSingleShot(true);
    QObject::connect(timer,&QTimer::timeout,reply,[reply]{reply->abort();});
    QObject::connect(reply,&QNetworkReply::finished,timer,&QTimer::stop);
    QObject::connect(reply,&QNetworkReply::readyRead,reply,[reply]{if(reply->bytesAvailable()>65536)reply->abort();});
    timer->start(milliseconds);
}

void MihomoAdapter::selectNode(const QString &id) {
    if (!m_status.apiHealthy || m_status.nodeBusy || m_options.selectedNodeId.isEmpty()) return;
    if (std::none_of(m_options.nodes.begin(),m_options.nodes.end(),[&](const ProxyNode &n){return n.id==id;})) {
        nodeFailure(QStringLiteral("节点不在已启动的引擎配置中。")); return;
    }
    cancelNodeRequests(); const auto generation=m_nodeGeneration;
    m_selectionPending=true;
    m_status.nodeBusy=true; m_status.nodeHealth=NodeHealth::Unknown; m_status.requestState=RequestState::NotTested; m_status.nodeMessage.clear(); publish();
    QNetworkRequest request(QUrl(m_status.controlEndpoint+"/proxies/SWIRL"));
    request.setRawHeader("Authorization","Bearer "+m_secret); request.setHeader(QNetworkRequest::ContentTypeHeader,"application/json");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto *reply=m_network.put(request,QJsonDocument(QJsonObject{{"name",id}}).toJson(QJsonDocument::Compact));
    m_nodeReply=reply; boundReply(reply,m_options.requestTimeoutMs);
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation,id,request] {
        reply->deleteLater(); if(generation!=m_nodeGeneration)return; m_nodeReply=nullptr;
        // Even when PUT's response is lost, the selection may have succeeded.
        // Reconcile with GET instead of killing unrelated application tunnels.
        auto *verify=m_network.get(request); m_nodeReply=verify; boundReply(verify,m_options.requestTimeoutMs);
        connect(verify,&QNetworkReply::finished,this,[this,verify,generation,id] {
            verify->deleteLater(); if(generation!=m_nodeGeneration)return; m_nodeReply=nullptr;
            const auto object=QJsonDocument::fromJson(verify->readAll()).object();
            const auto actual=object.value("now").toString();
            if (verify->error()!=QNetworkReply::NoError || verify->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()!=200 ||
                std::none_of(m_options.nodes.begin(),m_options.nodes.end(),[&](const ProxyNode &n){return n.id==actual;})) {
                m_status.nodeBusy=false;m_selectionPending=false;
                apiFailure(Error::SelectionFailed,QStringLiteral("切换结果暂未确认；保留引擎与现有连接，请等待控制接口恢复后重试。"));return;
            }
            m_options.selectedNodeId=actual; m_status.selectedNodeId=actual; m_status.nodeBusy=false;
            m_selectionPending=false;
            m_status.latencyMs=-1; m_status.responseCode=0;
            m_status.nodeMessage=actual==id?QString():QStringLiteral("此次切换未生效，引擎仍使用原节点；现有连接已保留。");publish();
        });
    });
}

void MihomoAdapter::probeNode(const QUrl &url) {
    if (!m_status.apiHealthy || m_status.nodeBusy || m_options.selectedNodeId.isEmpty()) return;
    if (!url.isValid() || (url.scheme()!="http" && url.scheme()!="https") || url.host().isEmpty() ||
        !url.userInfo().isEmpty() || url.toString().size()>2048 || url.hasFragment()) {
        nodeFailure(QStringLiteral("测试地址须为不含凭据或片段的 HTTP/HTTPS URL。")); return;
    }
    cancelNodeRequests(); const auto generation=m_nodeGeneration;
    m_status.nodeBusy=true; m_status.nodeHealth=NodeHealth::Checking; m_status.requestState=RequestState::NotTested;
    m_status.nodeMessage.clear(); m_status.responseCode=0; m_status.latencyMs=-1; publish();
    QUrl endpoint(m_status.controlEndpoint+"/proxies/"+m_options.selectedNodeId+"/delay");
    QUrlQuery query; query.addQueryItem("timeout","5000"); query.addQueryItem("url",url.toString(QUrl::FullyEncoded)); endpoint.setQuery(query);
    QNetworkRequest request(endpoint); request.setRawHeader("Authorization","Bearer "+m_secret);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto *reply=m_network.get(request); m_nodeReply=reply; boundReply(reply,6000);
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation,url] {
        reply->deleteLater(); if(generation!=m_nodeGeneration)return; m_nodeReply=nullptr;
        const auto delay=QJsonDocument::fromJson(reply->readAll()).object().value("delay");
        if (reply->error()!=QNetworkReply::NoError || !delay.isDouble() || delay.toInt(-1)<0) {
            nodeFailure(QStringLiteral("所选节点的真实可用性检测失败；实际请求未执行。请检查服务器、凭据或网络。")); return;
        }
        m_status.nodeHealth=NodeHealth::Available; m_status.latencyMs=delay.toInt(); m_status.requestState=RequestState::InProgress; publish();
        m_probeNetwork.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,QStringLiteral("127.0.0.1"),m_options.proxyPort,m_options.inboundUsername.isEmpty()&&m_options.allowLan&&!m_options.lanSkipLocalAuthentication?m_options.lanUsername:m_options.inboundUsername,m_options.inboundUsername.isEmpty()&&m_options.allowLan&&!m_options.lanSkipLocalAuthentication?m_options.lanPassword:m_options.inboundPassword));
        QNetworkRequest actual(url);
        actual.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
        actual.setAttribute(QNetworkRequest::CacheLoadControlAttribute,QNetworkRequest::AlwaysNetwork);
        actual.setRawHeader("Connection","close");
        auto *probe=m_probeNetwork.get(actual); m_probeReply=probe; boundReply(probe,6000);
        connect(probe,&QNetworkReply::finished,this,[this,probe,generation] {
            probe->deleteLater(); if(generation!=m_nodeGeneration)return; m_probeReply=nullptr;
            m_status.nodeBusy=false;
            const auto code=probe->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(); m_status.responseCode=code;
            const bool ok=probe->error()==QNetworkReply::NoError && code>=200 && code<400;
            m_status.requestState=ok?RequestState::Succeeded:RequestState::Failed;
            m_status.nodeMessage=ok?QStringLiteral("真实请求成功：本机代理按当前 %1 模式完成请求（HTTP %2）。").arg(m_status.mode).arg(code)
                :QStringLiteral("本机代理的实际请求失败（HTTP %1，网络错误 %2）；请检查当前分流、节点或直连网络。").arg(code).arg(int(probe->error()));
            publish();
        });
    });
}

void MihomoAdapter::stop() {
    if (m_status.state == State::Stopped) return;
    m_modeUnconfirmed=false; m_failureExit = false; cancelRequest();
    cancelNodeRequests(); m_proxyReservation.close(); m_proxyUdpReservation.close();
    m_status.proxyPort=0; m_status.nodeHealth=NodeHealth::Unknown; m_status.requestState=RequestState::NotTested;
    m_status.nodeMessage.clear(); m_status.latencyMs=-1; m_status.responseCode=0;
    m_poll.stop(); m_deadline.stop(); m_reservation.close();
    m_status.error = Error::None; m_status.message.clear(); m_status.apiHealthy = false;
    if (m_process.state() == QProcess::NotRunning) {
        m_status.state = State::Stopped; unlockExecutable(); m_directory.reset(); publish(); return;
    }
    m_status.state = State::Stopping; publish();
    m_process.terminate(); m_killTimer.start(1000);
}

void MihomoAdapter::refresh() {
    if(m_modeReply)return;
    if (m_stage != Stage::Engine || m_process.state() != QProcess::Running || m_reply ||
        (m_status.state != State::Starting && m_status.state != State::Running && m_status.state != State::Degraded)) return;
    request(true);
}

void MihomoAdapter::apiFailure(Error error, const QString &message) {
    // Polling belongs to the control plane. A short polling timeout must not
    // stop forwarding or cancel independently bounded selection/probe requests.
    m_status.apiHealthy = false;
    // Startup retries are bounded by the original deadline; never reset it.
    if (m_status.state != State::Starting) m_status.state = State::Degraded;
    m_status.error = error; m_status.message = message; publish();
}

void MihomoAdapter::request(bool version) {
    const auto generation = m_generation;
    QNetworkRequest request(QUrl(m_status.controlEndpoint + (version ? QStringLiteral("/version") : QStringLiteral("/configs"))));
    request.setRawHeader("Authorization", "Bearer " + m_secret);
    request.setRawHeader("Accept", "application/json");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setAttribute(QNetworkRequest::CacheLoadControlAttribute, QNetworkRequest::AlwaysNetwork);
    auto *reply = m_network.get(request); m_reply = reply;
    auto *timer = new QTimer(reply); timer->setSingleShot(true);
    connect(timer, &QTimer::timeout, reply, [reply] { reply->setProperty("swirlTimeout", true); reply->abort(); });
    timer->start(m_options.requestTimeoutMs);
    connect(reply, &QNetworkReply::readyRead, this, [reply] {
        if (reply->bytesAvailable() > 65536) { reply->setProperty("swirlOversize", true); reply->abort(); }
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply, timer, generation, version] {
        timer->stop(); reply->deleteLater();
        if (generation != m_generation) return;
        m_reply = nullptr;
        const int http = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (http == 401 || http == 403) {
            apiFailure(Error::AuthenticationFailed, QStringLiteral("Mihomo 控制接口认证失败。")); return;
        }
        if (reply->error() != QNetworkReply::NoError || http != 200) {
            apiFailure(Error::ApiUnavailable, reply->property("swirlTimeout").toBool()
                ? QStringLiteral("Mihomo 控制接口请求超时；进程状态与 API 健康状态分别显示。")
                : QStringLiteral("Mihomo 控制接口不可用（HTTP %1）。").arg(http)); return;
        }
        const auto bytes = reply->readAll();
        QJsonParseError error;
        const auto json = QJsonDocument::fromJson(bytes, &error);
        if (bytes.size() > 65536 || error.error != QJsonParseError::NoError || !json.isObject()) {
            apiFailure(Error::InvalidResponse, QStringLiteral("Mihomo 控制接口返回了无效或过大的 JSON。")); return;
        }
        const auto object = json.object();
        if (version) {
            if (object.value(QStringLiteral("version")).toString() != m_options.expectedVersion ||
                object.value(QStringLiteral("meta")) != QJsonValue(true)) {
                apiFailure(Error::InvalidResponse, QStringLiteral("控制接口版本与已校验的 Mihomo 程序不匹配。")); return;
            }
            m_status.version = object.value(QStringLiteral("version")).toString();
            this->request(false); return;
        }
        const bool connected=!m_options.selectedNodeId.isEmpty()||m_options.directSession;
        const auto actualMode=object.value("mode").toString();
        if(m_modeUnconfirmed && QStringList{"rule","global","direct"}.contains(actualMode) && (!m_options.meteredNetwork||actualMode=="rule")){
            m_options.routingMode=actualMode;m_modeUnconfirmed=false;
            emit diagnostic("Mihomo","RoutingModeReconciled",QStringLiteral("已核实实际路由模式为 %1；没有清空现有连接。").arg(actualMode));
        }
        bool safe = object.value(QStringLiteral("mode")).toString() == (connected ? m_options.routingMode:QStringLiteral("direct")) &&
            object.value(QStringLiteral("allow-lan")) == QJsonValue(connected&&m_options.allowLan) &&
            object.value(QStringLiteral("tun")).isObject() &&
            object.value(QStringLiteral("tun")).toObject().value(QStringLiteral("enable")) == QJsonValue(connected&&m_options.tunEnabled);
        for (const auto &key : {"port", "socks-port", "redir-port", "tproxy-port"})
            safe = safe && object.value(QLatin1String(key)).isDouble() && object.value(QLatin1String(key)).toInt(-1) == 0;
        safe=safe && object.value("mixed-port").isDouble() && object.value("mixed-port").toInt(-1)==(connected?m_options.proxyPort:0);
        if (!safe) {
            fail(Error::ConfigurationFailed, QStringLiteral("引擎运行配置不符合 Swirl 安全约束；已停止进程。")); return;
        }
        if(m_status.state==State::Starting && connected){verifyStartupListener();return;}
        publishRunning();
    });
}

void MihomoAdapter::verifyStartupListener() {
    if(m_startupListener || m_status.state!=State::Starting)return;
    // This is a local startup readiness check, not a recurring health probe.
    // It does not send application traffic or extend the original deadline.
    auto *socket=new QTcpSocket(this);m_startupListener=socket;
    socket->setProxy(QNetworkProxy::NoProxy);const auto generation=m_generation;
    const auto rejected=[this,socket,generation](QAbstractSocket::SocketError error){
        if(generation!=m_generation || m_startupListener!=socket)return;
        m_startupListener=nullptr;socket->disconnect(this);socket->abort();socket->deleteLater();
        apiFailure(Error::ApiUnavailable,QStringLiteral("控制接口已核验，但本机代理监听尚未就绪（socket 错误 %1）；继续等待原启动期限。").arg(int(error)));
    };
    connect(socket,&QTcpSocket::errorOccurred,this,rejected);
    connect(socket,&QTcpSocket::connected,this,[this,socket,generation]{
        if(generation!=m_generation || m_startupListener!=socket)return;
        m_startupListener=nullptr;socket->disconnect(this);socket->abort();socket->deleteLater();
        if(m_status.state==State::Starting)publishRunning();
    });
    auto *timer=new QTimer(socket);timer->setSingleShot(true);
    connect(timer,&QTimer::timeout,this,[rejected]{rejected(QAbstractSocket::SocketTimeoutError);});
    timer->start(m_options.requestTimeoutMs);
    socket->connectToHost(QHostAddress::LocalHost,m_options.proxyPort);
}

void MihomoAdapter::publishRunning() {
    const bool connected=!m_options.selectedNodeId.isEmpty() || m_options.directSession;
    m_status.mode=connected?m_options.routingMode:QStringLiteral("direct");
    m_status.state=State::Running;m_status.apiHealthy=true;m_status.gatewayForwarding=m_options.gatewayForwarding;
    m_status.directSession=m_options.directSession&&m_options.selectedNodeId.isEmpty();
    m_status.tunEnabled=connected&&m_options.tunEnabled;m_status.allowLan=connected&&m_options.allowLan;
    m_status.error=Error::None;m_status.message.clear();m_status.routingBusy=false;m_deadline.stop();
    publish();readConnections();readTraffic();readLogs();
}

void MihomoAdapter::setRoutingMode(const QString &mode) {
    if(m_options.meteredNetwork&&mode!="rule")return;
    if((mode!="rule"&&mode!="global"&&mode!="direct")||!m_status.apiHealthy||(m_options.selectedNodeId.isEmpty()&&!m_options.directSession)||m_modeReply)return;
    if(mode==m_options.routingMode)return;
    // No in-flight health read may observe the old mode after a successful PATCH.
    cancelRequest();
    const auto generation=m_generation;
    QNetworkRequest request(QUrl(m_status.controlEndpoint+"/configs"));
    request.setRawHeader("Authorization","Bearer "+m_secret);
    request.setHeader(QNetworkRequest::ContentTypeHeader,"application/json");
    request.setTransferTimeout(2000);
    auto reply=m_network.sendCustomRequest(request,"PATCH",QJsonDocument(QJsonObject{{"mode",mode}}).toJson(QJsonDocument::Compact));
    m_modeReply=reply;
    m_status.routingBusy=true;publish();
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation,mode] {
        reply->deleteLater();if(generation!=m_generation)return;m_modeReply=nullptr;
        if(reply->error()!=QNetworkReply::NoError||reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()!=204){
            m_modeUnconfirmed=true;m_status.routingBusy=false;
            apiFailure(Error::ApiUnavailable,QStringLiteral("路由控制响应未确认；正在读取实际模式，保留已有连接。"));
            refresh();return;}
        m_modeUnconfirmed=true;m_options.routingMode=mode;
        m_status.nodeHealth=NodeHealth::Unknown;m_status.requestState=RequestState::NotTested;
        m_status.nodeMessage.clear();m_status.apiHealthy=false;publish();refresh();
    });
}

QVariantList MihomoAdapter::routingRules() const {
    QVariantList result;
    const auto start=m_generatedConfig.indexOf("\nrules:\n");
    if(start<0)return result;
    auto section=m_generatedConfig.mid(start+8);
    const auto end=section.indexOf("\nrule-providers:");if(end>=0)section=section.left(end);
    int order=0;
    for(const auto &line:section.split('\n')) {
        if(!line.startsWith("  - "))continue;
        auto rule=line.mid(4);
        if(rule.startsWith('"')){const auto value=QJsonDocument::fromJson(("["+rule+"]").toUtf8());if(value.isArray())rule=value.array().first().toString();}
        const auto parts=rule.split(',');if(parts.size()<2)continue;
        const bool match=parts[0]=="MATCH";
        result.append(QVariantMap{{"id",QString::number(++order)},{"order",order},{"type",parts[0]},
            {"pattern",match?QStringLiteral("其他流量"):parts[1]},
            {"policy",match?parts[1]:parts.value(2)},{"hits",QStringLiteral("—")},
            {"enabled",m_status.mode=="rule"&&m_status.apiHealthy?QStringLiteral("生效"):QStringLiteral("规则模式使用")}});
    }
    return result;
}
void MihomoAdapter::readConnections() {
    if(m_connectionsReply||!m_status.apiHealthy)return;
    const auto generation=m_generation;
    QNetworkRequest req(QUrl(m_status.controlEndpoint+"/connections"));
    req.setRawHeader("Authorization","Bearer "+m_secret);req.setTransferTimeout(1500);
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto reply=m_network.get(req);m_connectionsReply=reply;reply->setReadBufferSize(1024*1024+1);
    connect(reply,&QNetworkReply::readyRead,this,[reply]{if(reply->bytesAvailable()>1024*1024)reply->abort();});
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation]{
        reply->deleteLater();if(generation!=m_generation)return;m_connectionsReply=nullptr;
        if(reply->error()!=QNetworkReply::NoError||reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()!=200){m_status.telemetryError=QStringLiteral("连接采集失败");publish();return;}
        const auto bytes=reply->readAll();if(bytes.size()>1024*1024){m_status.telemetryError=QStringLiteral("连接接口响应超出 1 MiB 上限");publish();return;}
        QJsonParseError parseError;const auto doc=QJsonDocument::fromJson(bytes,&parseError);
        // Mihomo serializes its nil Go slice as null when no connections are
        // active. This valid idle snapshot still carries final byte counters.
        const auto list=doc.object().value("connections");
        if(parseError.error!=QJsonParseError::NoError||!doc.isObject()||(!list.isArray()&&!list.isNull())){m_status.telemetryError=QStringLiteral("连接接口返回无效数据");publish();return;}
        const auto snapshot=doc.object();
        auto validCounter=[](const QJsonValue &value){const auto number=value.toDouble(-1);return value.isDouble()&&std::isfinite(number)&&number>=0&&number<9.22e18;};
        if(!validCounter(snapshot.value("uploadTotal"))||!validCounter(snapshot.value("downloadTotal"))){m_status.telemetryError=QStringLiteral("连接接口累计计数无效");publish();return;}
        m_status.uploadTotal=qint64(snapshot.value("uploadTotal").toDouble());m_status.downloadTotal=qint64(snapshot.value("downloadTotal").toDouble());
        QVariantList rows;
        const auto array=snapshot.value("connections").toArray();
        for(const auto &entry:array) {
            if(rows.size()>=2000)break;
            const auto c=entry.toObject(),m=c.value("metadata").toObject();QStringList chain,nodeChain;
            if(!validCounter(c.value("upload"))||!validCounter(c.value("download"))||c.value("id").toString().isEmpty())continue;
            for(const auto &hop:c.value("chains").toArray()) {
                auto label=hop.toString();nodeChain.append(label);
                for(const auto &node:m_options.nodes)if(node.id==label){label=node.name;break;}
                chain.append(label);
            }
            const auto rule=c.value("rule").toString()+" "+c.value("rulePayload").toString();
            rows.append(QVariantMap{{"id",QString::fromLatin1(QCryptographicHash::hash(c.value("id").toString().toUtf8(),QCryptographicHash::Sha256).toHex().left(12))},
                {"host",m.value("host").toString().isEmpty()?m.value("destinationIP").toString():m.value("host").toString()},{"ip",m.value("destinationIP").toString()},{"sourceIp",m.value("sourceIP").toString()},
                {"process",QFileInfo(m.value("processPath").toString().isEmpty()?m.value("process").toString():m.value("processPath").toString()).fileName().isEmpty()?QStringLiteral("未知进程"):QFileInfo(m.value("processPath").toString().isEmpty()?m.value("process").toString():m.value("processPath").toString()).fileName()},
                {"protocol",m.value("network").toString()+" / "+m.value("type").toString()},
                {"policy",chain.join(QStringLiteral(" → "))},{"rule",rule},{"sourcePort",m.value("sourcePort").toVariant().toInt()},{"nodeChain",nodeChain},
                {"category",chain.contains("REJECT")||chain.contains("REJECT-DROP")?"reject":chain.contains("DIRECT")?"direct":chain.isEmpty()?"other":"proxy"},
                {"uploadBytes",qint64(c.value("upload").toDouble())},{"downloadBytes",qint64(c.value("download").toDouble())},
                {"up",QString::number(qint64(c.value("upload").toDouble()))+" B"},
                {"down",QString::number(qint64(c.value("download").toDouble()))+" B"},
                {"latency",QStringLiteral("—")},{"time",c.value("start").toString()},
                {"status",QStringLiteral("Active")}});
        }
        m_status.connections=rows;m_status.connectionsAt=QDateTime::currentMSecsSinceEpoch();m_status.telemetryError.clear();publish();
    });
}

void MihomoAdapter::readTraffic() {
    if(m_trafficReply||!m_status.apiHealthy)return;
    const auto generation=m_generation;
    QNetworkRequest request(QUrl(m_status.controlEndpoint+"/traffic"));
    request.setRawHeader("Authorization","Bearer "+m_secret);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto reply=m_network.get(request);m_trafficReply=reply;m_trafficBuffer.clear();
    connect(reply,&QNetworkReply::readyRead,this,[this,reply,generation]{
        if(generation!=m_generation)return;m_trafficBuffer+=reply->readAll();
        if(m_trafficBuffer.size()>65536){reply->abort();return;}
        while(m_trafficBuffer.contains('\n')){
            const auto end=m_trafficBuffer.indexOf('\n');const auto line=m_trafficBuffer.left(end);m_trafficBuffer.remove(0,end+1);
            QJsonParseError error;const auto object=QJsonDocument::fromJson(line,&error).object();
            const auto up=object.value("up").toDouble(-1),down=object.value("down").toDouble(-1);
            if(error.error!=QJsonParseError::NoError||up<0||down<0||!std::isfinite(up)||!std::isfinite(down)||up>1e12||down>1e12){m_status.telemetryError=QStringLiteral("流量接口返回无效采样");continue;}
            m_status.uploadRate=up;m_status.downloadRate=down;m_status.trafficAt=QDateTime::currentMSecsSinceEpoch();publish();
        }
    });
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation]{reply->deleteLater();if(generation!=m_generation)return;m_trafficReply=nullptr;m_trafficBuffer.clear();m_status.trafficAt=0;m_status.telemetryError=QStringLiteral("流量流已断开，等待重新采集");publish();});
}

void MihomoAdapter::readLogs() {
    if(m_logsReply||!m_status.apiHealthy)return;const auto generation=m_generation;
    QNetworkRequest request(QUrl(m_status.controlEndpoint+"/logs?level=warning"));request.setRawHeader("Authorization","Bearer "+m_secret);request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto reply=m_network.get(request);m_logsReply=reply;m_logsBuffer.clear();
    connect(reply,&QNetworkReply::readyRead,this,[this,reply,generation]{
        if(generation!=m_generation)return;m_logsBuffer+=reply->readAll();if(m_logsBuffer.size()>65536){reply->abort();return;}
        while(m_logsBuffer.contains('\n')){const auto end=m_logsBuffer.indexOf('\n');const auto line=m_logsBuffer.left(end);m_logsBuffer.remove(0,end+1);const auto event=QJsonDocument::fromJson(line).object();if(event.isEmpty())continue;
            const auto payload=event.value("payload").toString();
            const auto fault=classifyMihomoLog(payload);
            emit diagnostic("Mihomo",fault.code,fault.message);
        }
    });
    connect(reply,&QNetworkReply::finished,this,[this,reply,generation]{reply->deleteLater();if(generation!=m_generation)return;m_logsReply=nullptr;m_logsBuffer.clear();});
}

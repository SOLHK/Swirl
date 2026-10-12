#include "MihomoAdapter.h"
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
void MihomoAdapter::publish() { emit statusChanged(); }

QString MihomoAdapter::configurationSummary() const {
    // A redacted copy is inspectable; the authenticated file is kept private.
    auto result = m_generatedConfig;
    if (!m_options.selectedNodeId.isEmpty()) {
        result = result.left(result.indexOf(QStringLiteral("proxies:"))) + QStringLiteral("节点配置已生成，全部节点凭据已隐藏。\n");
    }
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
        "ipv6: false\nlog-level: silent\nfind-process-mode: off\ngeodata-mode: false\n"
        "geo-auto-update: false\nprofile:\n  store-selected: false\n  store-fake-ip: false\n"
        "tun:\n  enable: false\n  auto-route: false\n  auto-detect-interface: false\n"
        "dns:\n  enable: false\nproxies: []\nproxy-groups: []\nrules: []\n")
        .arg(m_options.controlPort).arg(QString::fromLatin1(m_secret));
    if (!m_options.selectedNodeId.isEmpty()) {
        QJsonArray proxies, names;
        names.append(m_options.selectedNodeId);
        for (const auto &n : m_options.nodes) {
            QJsonObject proxy{{"name",n.id},{"type",n.protocol},{"server",n.host},{"port",n.port},{"udp",false}};
            if (!n.password.isEmpty()) proxy.insert("password",n.password);
            if (n.protocol=="socks5" && !n.username.isEmpty()) proxy.insert("username",n.username);
            if (n.protocol=="ss") proxy.insert("cipher",n.cipher);
            if (n.protocol=="trojan") { proxy.insert("sni",n.serverName.isEmpty()?n.host:n.serverName); proxy.insert("skip-cert-verify",false); }
            proxies.append(proxy); if (n.id!=m_options.selectedNodeId) names.append(n.id);
        }
        const QJsonArray groups{QJsonObject{{"name","SWIRL"},{"type","select"},{"proxies",names}}};
        m_generatedConfig.replace("mode: direct\n","mode: rule\n");
        m_generatedConfig.replace("mixed-port: 0\n",QStringLiteral("mixed-port: %1\n").arg(m_options.proxyPort));
        m_generatedConfig.replace("proxies: []\n",QStringLiteral("proxies: ")+QString::fromUtf8(QJsonDocument(proxies).toJson(QJsonDocument::Compact))+"\n");
        m_generatedConfig.replace("proxy-groups: []\n",QStringLiteral("proxy-groups: ")+QString::fromUtf8(QJsonDocument(groups).toJson(QJsonDocument::Compact))+"\n");
        m_generatedConfig.replace("rules: []\n","rules: ['MATCH,SWIRL']\n");
    }
    QSaveFile file(m_status.configPath);
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFile::ReadOwner | QFile::WriteOwner)) return false;
    const auto bytes = m_generatedConfig.toUtf8();
    return file.write(bytes) == bytes.size() && file.commit();
}

bool MihomoAdapter::reserveControlPort() { return reservePort(m_reservation,m_options.controlPort); }
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
    cancelRequest(); cancelNodeRequests(); m_poll.stop(); m_deadline.stop(); m_killTimer.stop();
    unlockExecutable(); m_directory.reset(); m_uptime.invalidate();
    m_secret.clear(); m_generatedConfig.clear(); m_output.clear();
    m_options = options; m_status = {}; m_failureExit = false;
    m_status.executablePath = options.executablePath;
    m_status.controlEndpoint = QStringLiteral("http://127.0.0.1:%1").arg(options.controlPort);
    m_status.state = State::Validating; publish();
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
    for (const auto &node : options.nodes) {
        const auto error=ProxyNode::validate(node);
        if (!error.isEmpty() || nodeIds.contains(node.id)) { fail(Error::InvalidNode, error.isEmpty()?QStringLiteral("节点标识重复。"):error); return; }
        nodeIds.insert(node.id);
    }
    if (!options.selectedNodeId.isEmpty() && (!nodeIds.contains(options.selectedNodeId) || options.proxyPort==0 || options.proxyPort==options.controlPort)) {
        fail(Error::InvalidNode,QStringLiteral("所选节点或本机代理端口无效。")); return;
    }
    m_status.selectedNodeId=options.selectedNodeId;
    m_status.proxyPort=options.selectedNodeId.isEmpty()?0:options.proxyPort;
    if (!lockAndVerifyExecutable()) return;
    if (!reserveControlPort()) {
        fail(Error::PortConflict, QStringLiteral("本机控制端口 %1 已占用或不允许绑定；请更换端口。").arg(options.controlPort));
        unlockExecutable(); return;
    }
    if (!prepareConfiguration()) {
        fail(Error::ConfigurationFailed, QStringLiteral("无法创建只允许当前用户访问的引擎运行配置。"));
        unlockExecutable(); return;
    }
    if (!options.selectedNodeId.isEmpty() && !reservePort(m_proxyReservation,options.proxyPort)) {
        fail(Error::PortConflict,QStringLiteral("本机代理端口 %1 已占用或不允许绑定。").arg(options.proxyPort));
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
    m_proxyReservation.close(); cancelNodeRequests();
    m_status.proxyPort=0; m_status.nodeHealth=NodeHealth::Unknown; m_status.requestState=RequestState::NotTested;
    m_status.state = State::Failed; m_status.error = error; m_status.message = message;
    m_status.apiHealthy = false;
    if (m_process.state() != QProcess::NotRunning) m_process.kill();
    publish();
}

void MihomoAdapter::cancelRequest() {
    ++m_generation;
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
        if (reply->error()!=QNetworkReply::NoError || reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()!=204) {
            fail(Error::SelectionFailed,QStringLiteral("节点切换未获得控制接口确认，已停止引擎以避免错误出口。")); return;
        }
        auto *verify=m_network.get(request); m_nodeReply=verify; boundReply(verify,m_options.requestTimeoutMs);
        connect(verify,&QNetworkReply::finished,this,[this,verify,generation,id] {
            verify->deleteLater(); if(generation!=m_nodeGeneration)return; m_nodeReply=nullptr;
            const auto object=QJsonDocument::fromJson(verify->readAll()).object();
            if (verify->error()!=QNetworkReply::NoError || verify->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt()!=200 || object.value("now").toString()!=id) {
                fail(Error::SelectionFailed,QStringLiteral("无法确认当前节点，已停止引擎。")); return;
            }
            m_options.selectedNodeId=id; m_status.selectedNodeId=id; m_status.nodeBusy=false;
            m_selectionPending=false;
            m_status.latencyMs=-1; m_status.responseCode=0; m_status.nodeMessage.clear(); publish();
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
        m_probeNetwork.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,QStringLiteral("127.0.0.1"),m_options.proxyPort));
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
            m_status.nodeMessage=ok?QStringLiteral("真实请求成功：已通过所选节点完成请求（HTTP %1）。").arg(code)
                :QStringLiteral("本机代理的实际请求失败（HTTP %1）；未使用直连回退。").arg(code);
            publish();
        });
    });
}

void MihomoAdapter::stop() {
    if (m_status.state == State::Stopped) return;
    m_failureExit = false; cancelRequest();
    cancelNodeRequests(); m_proxyReservation.close();
    m_status.proxyPort=0; m_status.nodeHealth=NodeHealth::Unknown; m_status.requestState=RequestState::NotTested;
    m_poll.stop(); m_deadline.stop(); m_reservation.close();
    m_status.error = Error::None; m_status.message.clear(); m_status.apiHealthy = false;
    if (m_process.state() == QProcess::NotRunning) {
        m_status.state = State::Stopped; unlockExecutable(); m_directory.reset(); publish(); return;
    }
    m_status.state = State::Stopping; publish();
    m_process.terminate(); m_killTimer.start(1000);
}

void MihomoAdapter::refresh() {
    if (m_stage != Stage::Engine || m_process.state() != QProcess::Running || m_reply ||
        (m_status.state != State::Starting && m_status.state != State::Running && m_status.state != State::Degraded)) return;
    request(true);
}

void MihomoAdapter::apiFailure(Error error, const QString &message) {
    if(m_selectionPending){fail(Error::SelectionFailed,QStringLiteral("节点切换期间控制接口异常，已停止引擎以避免错误出口。"));return;}
    cancelNodeRequests(); m_status.nodeHealth=NodeHealth::Unknown; m_status.requestState=RequestState::NotTested;
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
        const bool connected=!m_options.selectedNodeId.isEmpty();
        bool safe = object.value(QStringLiteral("mode")).toString() == (connected ? QStringLiteral("rule"):QStringLiteral("direct")) &&
            object.value(QStringLiteral("allow-lan")) == QJsonValue(false) &&
            object.value(QStringLiteral("tun")).isObject() &&
            object.value(QStringLiteral("tun")).toObject().value(QStringLiteral("enable")) == QJsonValue(false);
        for (const auto &key : {"port", "socks-port", "redir-port", "tproxy-port"})
            safe = safe && object.value(QLatin1String(key)).isDouble() && object.value(QLatin1String(key)).toInt(-1) == 0;
        safe=safe && object.value("mixed-port").isDouble() && object.value("mixed-port").toInt(-1)==(connected?m_options.proxyPort:0);
        if (!safe) {
            fail(Error::ConfigurationFailed, QStringLiteral("引擎运行配置不符合 Swirl 安全约束；已停止进程。")); return;
        }
        m_status.mode = connected?QStringLiteral("rule"):QStringLiteral("direct");
        m_status.state = State::Running; m_status.apiHealthy = true;
        m_status.error = Error::None; m_status.message.clear(); m_deadline.stop(); publish();
    });
}

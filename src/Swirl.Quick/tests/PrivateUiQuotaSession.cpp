#include "PrivateUiQuotaSession.h"
#include "RuntimeEvidence.h"
#include "engine/NodeImportService.h"

#include <QCryptographicHash>
#include <QElapsedTimer>
#include <QJsonDocument>
#include <QJsonParseError>
#ifdef Q_OS_WIN
#include <windows.h>
#else
#include <cerrno>
#include <poll.h>
#include <unistd.h>
#endif

namespace {
constexpr qsizetype maximumFrame=16*1024;

bool readLine(QByteArray *line) {
    // Read exactly one line. Never prefetch bytes from the following original
    // binary fixture proof; that proof still requires its original EOF gate.
    QElapsedTimer clock;clock.start();line->clear();
    while(clock.elapsed()<2000&&line->size()<maximumFrame) {
        char byte=0;
#ifdef Q_OS_WIN
        const auto input=GetStdHandle(STD_INPUT_HANDLE);
        DWORD available=0,received=0;
        if(!input||input==INVALID_HANDLE_VALUE||GetFileType(input)!=FILE_TYPE_PIPE
            ||!PeekNamedPipe(input,nullptr,0,nullptr,&available,nullptr))return false;
        if(!available){Sleep(1);continue;}
        if(!ReadFile(input,&byte,1,&received,nullptr)||received!=1)return false;
#else
        pollfd input{STDIN_FILENO,POLLIN,0};
        const auto ready=poll(&input,1,1);
        if(ready<0&&errno==EINTR)continue;
        if(ready<0)return false;
        if(ready==0)continue;
        if(read(STDIN_FILENO,&byte,1)!=1)return false;
#endif
        line->append(byte);
        if(byte=='\n')return true;
    }
    return false;
}

bool emitLine(const QByteArray &value) {
    if(value.isEmpty()||value.size()>=maximumFrame||value.contains('\n'))return false;
    const auto bytes=value+'\n';
#ifdef Q_OS_WIN
    const auto output=GetStdHandle(STD_OUTPUT_HANDLE);DWORD written=0;
    return output&&output!=INVALID_HANDLE_VALUE&&GetFileType(output)==FILE_TYPE_PIPE
        &&WriteFile(output,bytes.constData(),DWORD(bytes.size()),&written,nullptr)&&written==DWORD(bytes.size());
#else
    qsizetype offset=0;
    while(offset<bytes.size()) {
        const auto written=write(STDOUT_FILENO,bytes.constData()+offset,size_t(bytes.size()-offset));
        if(written<0&&errno==EINTR)continue;
        if(written<=0)return false;offset+=written;
    }
    return true;
#endif
}
}

bool PrivateUiQuotaSession::invoke(const QByteArray &input,QByteArray *raw,QJsonObject *value) {
    if(!m_command||input.isEmpty()||input.size()>maximumFrame)return false;
    QByteArray output(maximumFrame,Qt::Uninitialized);
    const auto length=m_command(reinterpret_cast<const unsigned char *>(input.constData()),size_t(input.size()),
        reinterpret_cast<unsigned char *>(output.data()),size_t(output.size()));
    if(length<=0||length>output.size())return false;
    output.resize(length);QJsonParseError error;
    const auto document=QJsonDocument::fromJson(output,&error);
    if(error.error!=QJsonParseError::NoError||!document.isObject())return false;
    *raw=output;*value=document.object();return true;
}

int PrivateUiQuotaSession::writeBuildIdentity() {
    PrivateUiQuotaSession session;auto &library=RustCoreLibrary::instance();
    if(!library.load())return 64;
    session.m_command=library.privateUiQuota();
    QByteArray raw;QJsonObject identity;
    if(!session.invoke(QByteArrayLiteral("{\"schema\":1,\"op\":\"identity\"}"),&raw,&identity)
        ||identity.value("role").toString()!=QStringLiteral("swirl_private_qt_ui")
        ||identity.value("source_sha").toString()!=library.expectedSourceSha()
        ||identity.value("build_id").toString()!=library.expectedBuildId())return 64;
    const QJsonObject result{{"identity",identity},{"qt_version",QString::fromLatin1(qVersion())},
        {"scope",QStringLiteral("fixed-synthetic-qt-ui")}};
    return emitLine(QJsonDocument(result).toJson(QJsonDocument::Compact))?0:64;
}

bool PrivateUiQuotaSession::begin() {
    auto &library=RustCoreLibrary::instance();
    if(!library.load())return false;
    m_command=library.privateUiQuota();QByteArray input,raw;QJsonObject value;
    if(!readLine(&input)||!invoke(input,&raw,&value)||value.value("op").toString()!=QStringLiteral("ready")
        ||!value.value("ok").toBool())return false;
    // Only parse Qt fields after Rust has rejected duplicate/unknown fields and
    // authenticated the immutable content digest and paired source/build.
    const auto request=QJsonDocument::fromJson(input).object();
    m_grant=request.value("grant").toObject();
    for(const auto *key:{"schema","reservation_id","nonce","plan_digest"})m_binding[key]=request.value(key);
    if(!emitLine(raw)||!readLine(&input)||!invoke(input,&raw,&value)
        ||value.value("op").toString()!=QStringLiteral("started")||!value.value("ok").toBool())return false;
    m_started=true;return true;
}

QByteArray PrivateUiQuotaSession::control(const char *operation) const {
    auto message=m_binding;message["op"]=QString::fromLatin1(operation);
    return QJsonDocument(message).toJson(QJsonDocument::Compact);
}

bool PrivateUiQuotaSession::fixtureReady(const ControlledNodeSession &session) {
    if(!m_started||session.nonce!=m_binding.value("nonce").toString()
        ||session.sourceSha!=m_grant.value("source_sha").toString()
        ||session.fixtureSocksPort!=m_grant.value("endpoint").toObject().value("port").toInt()
        ||session.proxyPort!=m_grant.value("listener").toObject().value("port").toInt()
        ||session.nodeOrdinal!=1)return false;
    QByteArray raw;QJsonObject value;
    m_fixtureVerified=invoke(control("fixture_ready"),&raw,&value)&&value.value("ok").toBool()
        &&value.value("op").toString()==QStringLiteral("running")&&emitLine(raw);
    return m_fixtureVerified;
}

bool PrivateUiQuotaSession::runningQuota() {
    if(!m_started||m_finished||!m_fixtureVerified)return false;
    QByteArray raw;QJsonObject value;
    if(!invoke(control("snapshot"),&raw,&value)||!value.value("ok").toBool()
        ||value.value("op").toString()!=QStringLiteral("snapshot"))return false;
    const auto guard=value.value("guard").toObject();
    return guard.value("stopped")==QJsonValue(false)&&guard.value("timed_out")==QJsonValue(false)
        &&guard.value("connection_limit")==QJsonValue(6)&&guard.value("timeout_ms")==QJsonValue(8000);
}

bool PrivateUiQuotaSession::attachImportCapability(NodeImportService *imports,const ControlledNodeSession &session) {
    if(!imports||!session.uiImportPolicy||!runningQuota()||imports->m_shuttingDown||imports->m_privateUiImport
        ||session.nonce!=m_binding.value("nonce").toString()
        ||session.sourceSha!=m_grant.value("source_sha").toString()
        ||session.proxyPort!=m_grant.value("listener").toObject().value("port").toInt()
        ||session.fixtureSocksPort!=m_grant.value("endpoint").toObject().value("port").toInt())return false;
    // Fixed negative control: the real form must fail without any capability.
    // This creates no token, socket, alternate route or successful import flag.
    if(session.uiImportControl==QStringLiteral("missing-capability"))return true;
    auto capability=std::make_unique<NodeImportService::PrivateUiImportCapability>();
    capability->url=session.subscriptionUrl();capability->ca=session.fixtureCa;
    capability->bodyDigest=QCryptographicHash::hash(session.subscriptionBody(),QCryptographicHash::Sha256);
    capability->proxyPort=quint16(session.proxyPort);
    capability->guardActive=[this]{return runningQuota();};
    imports->m_privateUiImport=std::move(capability);
    return true;
}

bool PrivateUiQuotaSession::finish() {
    if(!m_started||m_finished)return false;
    QByteArray raw;QJsonObject value;
    const bool valid=invoke(control("finish"),&raw,&value)&&value.value("ok").toBool()
        &&value.value("op").toString()==QStringLiteral("finished");
    m_finished=valid;
    return valid&&emitLine(raw);
}

PrivateUiQuotaSession::~PrivateUiQuotaSession() {
    if(m_command&&!m_binding.isEmpty()&&!m_finished) {
        QByteArray raw;QJsonObject value;invoke(control("cancel"),&raw,&value);
    }
}

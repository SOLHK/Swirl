#include "TlsCertificateService.h"
#include "../app/StoragePaths.h"
#include <QSaveFile>
#include <QFile>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QRegularExpression>
#include <QCryptographicHash>
#include <QHostAddress>
#include <QSslSocket>
#include <QDateTime>
#include <QDebug>
#include <algorithm>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

struct TlsCertificateService::Impl {
#ifdef Q_OS_WIN
    HCRYPTPROV provider=0;
    HCRYPTKEY key=0;
    ~Impl(){if(key)CryptDestroyKey(key);if(provider)CryptReleaseContext(provider,0);}
#endif
    QByteArray privateBlob;
};

#ifdef Q_OS_WIN
namespace {
struct KeyPair {
    HCRYPTPROV provider=0;HCRYPTKEY key=0;
    ~KeyPair(){if(key)CryptDestroyKey(key);if(provider)CryptReleaseContext(provider,0);}
    bool create(){return CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&CryptGenKey(provider,AT_SIGNATURE,(2048u<<16)|CRYPT_EXPORTABLE,&key);}
};
QByteArray encoded(LPCSTR type,const void *value) {
    BYTE *data=nullptr;DWORD size=0;
    if(!CryptEncodeObjectEx(X509_ASN_ENCODING,type,value,CRYPT_ENCODE_ALLOC_FLAG,nullptr,&data,&size)){qWarning()<<"CA_ENCODE"<<GetLastError();return {};}
    const QByteArray result(reinterpret_cast<char *>(data),size);LocalFree(data);return result;
}
QByteArray exportBlob(HCRYPTKEY key) {
    DWORD size=0;if(!CryptExportKey(key,0,PRIVATEKEYBLOB,0,nullptr,&size))return {};
    QByteArray bytes(size,Qt::Uninitialized);if(!CryptExportKey(key,0,PRIVATEKEYBLOB,0,reinterpret_cast<BYTE *>(bytes.data()),&size))return {};return bytes;
}
QByteArray der(unsigned char tag,const QByteArray &value) {
    QByteArray out(1,char(tag));const auto size=value.size();
    if(size<128)out.append(char(size));else {QByteArray length;auto n=size;while(n){length.prepend(char(n&255));n>>=8;}out.append(char(0x80|length.size()));out+=length;}
    return out+value;
}
QByteArray integer(QByteArray littleEndian) {
    std::reverse(littleEndian.begin(),littleEndian.end());
    while(littleEndian.size()>1&&littleEndian[0]==0)littleEndian.remove(0,1);
    if(!littleEndian.isEmpty()&&(static_cast<unsigned char>(littleEndian[0])&0x80))littleEndian.prepend(char(0));
    return der(2,littleEndian);
}
QSslKey sslKey(const QByteArray &blob) {
    if(blob.size()<20)return {};
    const auto *header=reinterpret_cast<const RSAPUBKEY *>(blob.constData()+sizeof(BLOBHEADER));
    const int n=int(header->bitlen/8);if(n<128||n>512||blob.size()!=20+n*9/2)return {};
    QByteArray body=der(2,QByteArray(1,char(0)));int offset=20;
    body+=integer(blob.mid(offset,n));offset+=n;
    DWORD exponent=header->pubexp;body+=integer(QByteArray(reinterpret_cast<char *>(&exponent),sizeof(exponent)));
    // PRIVATEKEYBLOB puts d last; PKCS #1 puts d before p, q and CRT parameters.
    body+=integer(blob.mid(offset+5*n/2,n));
    for(int i=0;i<5;++i){body+=integer(blob.mid(offset,n/2));offset+=n/2;}
    return QSslKey(der(0x30,body),QSsl::Rsa,QSsl::Der,QSsl::PrivateKey);
}
// Read only the bounded PKCS #1 integer sequence returned by Qt's RSA serializer.
QByteArray privateBlobFromDer(const QByteArray &bytes) {
    int cursor=0;
    const auto read=[&](unsigned char tag)->QByteArray {
        if(cursor+2>bytes.size()||static_cast<unsigned char>(bytes[cursor++])!=tag)return {};
        int length=static_cast<unsigned char>(bytes[cursor++]);
        if(length&0x80){const int count=length&0x7f;if(count==0||count>3||cursor+count>bytes.size())return {};length=0;for(int i=0;i<count;++i)length=(length<<8)|static_cast<unsigned char>(bytes[cursor++]);}
        if(length<0||cursor+length>bytes.size())return {};
        const auto value=bytes.mid(cursor,length);cursor+=length;return value;
    };
    const auto sequence=read(0x30);if(sequence.isEmpty()||cursor!=bytes.size())return {};
    cursor=int(bytes.size()-sequence.size());QList<QByteArray> values;
    for(int i=0;i<9;++i){auto value=read(2);if(value.isEmpty())return {};while(value.size()>1&&value[0]==0)value.remove(0,1);values.append(value);}
    if(cursor!=bytes.size()||values[0]!=QByteArray(1,char(0)))return {};
    const int n=values[1].size();if(n<256||n>512||n%2||values[2].size()>4)return {};
    DWORD exponent=0;for(const auto byte:values[2])exponent=(exponent<<8)|static_cast<unsigned char>(byte);
    if(exponent<3||(exponent&1)==0)return {};
    const BLOBHEADER header{PRIVATEKEYBLOB,CUR_BLOB_VERSION,0,CALG_RSA_SIGN};const RSAPUBKEY pub{0x32415352,DWORD(n*8),exponent};
    QByteArray blob(reinterpret_cast<const char *>(&header),sizeof(header));blob.append(reinterpret_cast<const char *>(&pub),sizeof(pub));
    const auto append=[&](int index,int size){auto value=values[index];if(value.size()>size)return false;std::reverse(value.begin(),value.end());value.append(QByteArray(size-value.size(),char(0)));blob+=value;return true;};
    if(!append(1,n))return {};
    for(int i=4;i<9;++i)if(!append(i,n/2))return {};
    if(!append(3,n))return {};return blob;
}
QByteArray certificateFor(HCRYPTPROV subjectKey,HCRYPTPROV signingKey,const QByteArray &issuer,const QString &name,bool ca) {
    DWORD subjectSize=0;
    const auto subjectText=QStringLiteral("CN=")+name;
    if(!CertStrToNameW(X509_ASN_ENCODING,reinterpret_cast<LPCWSTR>(subjectText.utf16()),CERT_X500_NAME_STR,nullptr,nullptr,&subjectSize,nullptr))return {};
    QByteArray subject(subjectSize,Qt::Uninitialized);
    if(!CertStrToNameW(X509_ASN_ENCODING,reinterpret_cast<LPCWSTR>(subjectText.utf16()),CERT_X500_NAME_STR,nullptr,reinterpret_cast<BYTE *>(subject.data()),&subjectSize,nullptr))return {};
    DWORD publicSize=0;if(!CryptExportPublicKeyInfo(subjectKey,AT_SIGNATURE,X509_ASN_ENCODING,nullptr,&publicSize)){qWarning()<<"CA_PUBLIC_SIZE"<<GetLastError();return {};}
    QByteArray publicStorage(publicSize,Qt::Uninitialized);auto *publicKey=reinterpret_cast<CERT_PUBLIC_KEY_INFO *>(publicStorage.data());
    if(!CryptExportPublicKeyInfo(subjectKey,AT_SIGNATURE,X509_ASN_ENCODING,publicKey,&publicSize)){qWarning()<<"CA_PUBLIC_KEY"<<GetLastError();return {};}
    CERT_INFO info{};info.dwVersion=CERT_V3;
    QByteArray serial(16,Qt::Uninitialized);if(!CryptGenRandom(subjectKey,serial.size(),reinterpret_cast<BYTE *>(serial.data())))return {};serial[15]=char(static_cast<unsigned char>(serial[15])&0x7f);serial[0]=char(static_cast<unsigned char>(serial[0])|1);
    info.SerialNumber={DWORD(serial.size()),reinterpret_cast<BYTE *>(serial.data())};
    info.SignatureAlgorithm.pszObjId=const_cast<LPSTR>(szOID_RSA_SHA256RSA);
    info.Subject={DWORD(subject.size()),reinterpret_cast<BYTE *>(subject.data())};
    info.Issuer=issuer.isEmpty()?info.Subject:CERT_NAME_BLOB{DWORD(issuer.size()),reinterpret_cast<BYTE *>(const_cast<char *>(issuer.constData()))};
    GetSystemTimeAsFileTime(&info.NotBefore);ULARGE_INTEGER time{};time.LowPart=info.NotBefore.dwLowDateTime;time.HighPart=info.NotBefore.dwHighDateTime;
    time.QuadPart-=60ull*10000000ull;info.NotBefore={time.LowPart,time.HighPart};time.QuadPart+=quint64(ca?3650:7)*86400ull*10000000ull;info.NotAfter={time.LowPart,time.HighPart};
    info.SubjectPublicKeyInfo=*publicKey;
    CERT_BASIC_CONSTRAINTS2_INFO constraints{ca?TRUE:FALSE,FALSE,0};const auto basic=encoded(X509_BASIC_CONSTRAINTS2,&constraints);
    BYTE usage=ca?CERT_KEY_CERT_SIGN_KEY_USAGE|CERT_CRL_SIGN_KEY_USAGE:CERT_DIGITAL_SIGNATURE_KEY_USAGE|CERT_KEY_ENCIPHERMENT_KEY_USAGE;
    CRYPT_BIT_BLOB usageBlob{1,&usage,0};const auto keyUsage=encoded(X509_KEY_USAGE,&usageBlob);
    QList<QByteArray> extensionData{basic,keyUsage};
    QList<CERT_EXTENSION> extensions{{const_cast<LPSTR>(szOID_BASIC_CONSTRAINTS2),TRUE,{}},{const_cast<LPSTR>(szOID_KEY_USAGE),TRUE,{}}};
    if(!ca){
        CERT_ALT_NAME_ENTRY san{};QByteArray ip;QString dns=QString::fromLatin1(QUrl::toAce(name));const QHostAddress address(name);
        if(!address.isNull()){
            san.dwAltNameChoice=CERT_ALT_NAME_IP_ADDRESS;
            if(address.protocol()==QAbstractSocket::IPv4Protocol){const auto number=address.toIPv4Address();for(int i=3;i>=0;--i)ip.append(char((number>>(8*i))&255));}else {const auto bytes=address.toIPv6Address();ip=QByteArray(reinterpret_cast<const char *>(bytes.c),16);}
            san.IPAddress={DWORD(ip.size()),reinterpret_cast<BYTE *>(ip.data())};
        }else {san.dwAltNameChoice=CERT_ALT_NAME_DNS_NAME;san.pwszDNSName=reinterpret_cast<LPWSTR>(dns.data());}
        CERT_ALT_NAME_INFO sanInfo{1,&san};extensionData.append(encoded(X509_ALTERNATE_NAME,&sanInfo));extensions.append({const_cast<LPSTR>(szOID_SUBJECT_ALT_NAME2),FALSE,{}});
        LPSTR serverOid=const_cast<LPSTR>(szOID_PKIX_KP_SERVER_AUTH);CERT_ENHKEY_USAGE eku{1,&serverOid};extensionData.append(encoded(X509_ENHANCED_KEY_USAGE,&eku));extensions.append({const_cast<LPSTR>(szOID_ENHANCED_KEY_USAGE),FALSE,{}});
    }
    for(int i=0;i<extensions.size();++i){if(extensionData[i].isEmpty())return {};extensions[i].Value={DWORD(extensionData[i].size()),reinterpret_cast<BYTE *>(extensionData[i].data())};}
    info.cExtension=extensions.size();info.rgExtension=extensions.data();
    const auto tbs=encoded(X509_CERT_TO_BE_SIGNED,&info);
    if(tbs.isEmpty())return {};
    HCRYPTHASH hash=0;
    if(!CryptCreateHash(signingKey,CALG_SHA_256,0,0,&hash))return {};
    DWORD signatureSize=0;
    const bool sized=CryptHashData(hash,reinterpret_cast<const BYTE *>(tbs.constData()),DWORD(tbs.size()),0)
        &&CryptSignHashW(hash,AT_SIGNATURE,nullptr,0,nullptr,&signatureSize);
    if(!sized){const auto error=GetLastError();CryptDestroyHash(hash);SetLastError(error);return {};}
    QByteArray signature(signatureSize,Qt::Uninitialized);
    const bool signedHash=CryptSignHashW(hash,AT_SIGNATURE,nullptr,0,reinterpret_cast<BYTE *>(signature.data()),&signatureSize);
    const auto error=GetLastError();CryptDestroyHash(hash);
    if(!signedHash){SetLastError(error);return {};}
    signature.resize(signatureSize);
    // CryptoAPI returns RSA signatures little endian; X.509 uses big endian.
    std::reverse(signature.begin(),signature.end());
    const auto algorithm=encoded(X509_ALGORITHM_IDENTIFIER,&info.SignatureAlgorithm);
    if(algorithm.isEmpty())return {};
    return der(0x30,tbs+algorithm+der(3,QByteArray(1,char(0))+signature));
}
}
#endif

TlsCertificateService::TlsCertificateService(QString path,QObject *parent):QObject(parent),d(std::make_unique<Impl>()),m_path(path) {
    if(m_path.isEmpty())m_path=SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/certificates/ca.dpapi";
    load();
}
TlsCertificateService::~TlsCertificateService()=default;
QString TlsCertificateService::fingerprint() const {return QString::fromLatin1(m_certificate.digest(QCryptographicHash::Sha256).toHex(':'));}
void TlsCertificateService::setEnabled(bool enabled){if(enabled&&!ready()){m_error=QStringLiteral("请先生成 CA 证书。");emit changed();return;}m_enabled=enabled;emit changed();}
void TlsCertificateService::setHostnames(const QStringList &hostnames) {
    if(hostnames.size()>256){m_error=QStringLiteral("最多保存 256 个 MitM 主机名。");emit changed();return;}
    QStringList valid;
    for(const auto &host:hostnames){const auto name=host.trimmed().toLower();if(name.isEmpty()||name.size()>253||!QRegularExpression("^[A-Za-z0-9_.:*?-]+$").match(name).hasMatch()){m_error=QStringLiteral("主机名只能包含域名、IP 和通配符。");emit changed();return;}valid.append(name);}
    valid.removeDuplicates();const auto previous=m_hostnames;m_hostnames=valid;m_error.clear();
    if(!persist())m_hostnames=previous;emit changed();
}
bool TlsCertificateService::addHostname(const QString &hostname) {const auto name=hostname.trimmed().toLower();auto hosts=m_hostnames;if(!hosts.contains(name))hosts.append(name);setHostnames(hosts);return m_hostnames.contains(name);}
void TlsCertificateService::removeHostname(const QString &hostname) {auto hosts=m_hostnames;hosts.removeAll(hostname);setHostnames(hosts);}
bool TlsCertificateService::shouldIntercept(const QString &host) const {
    return m_enabled&&ready()&&matchesHost(host);
}
bool TlsCertificateService::matchesHost(const QString &host) const {
    bool included=false;
    for(const auto &pattern:m_hostnames){const bool exclude=pattern.startsWith('-');const auto match=exclude?pattern.mid(1):pattern;
        if(QRegularExpression(QRegularExpression::wildcardToRegularExpression(match),QRegularExpression::CaseInsensitiveOption).match(host).hasMatch()){if(exclude)return false;included=true;}}
    return included;
}
bool TlsCertificateService::generate() {
#ifdef Q_OS_WIN
    auto next=std::make_unique<Impl>();
    if(!CryptAcquireContextW(&next->provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)||!CryptGenKey(next->provider,AT_SIGNATURE,(2048u<<16)|CRYPT_EXPORTABLE,&next->key)){m_error=QStringLiteral("Windows 无法生成 RSA 密钥。");emit changed();return false;}
    const auto certificate=certificateFor(next->provider,next->provider,{},"Swirl Local CA",true);
    const auto signingError=GetLastError();next->privateBlob=exportBlob(next->key);
    const QSslCertificate parsed(certificate,QSsl::Der);if(parsed.isNull()||next->privateBlob.isEmpty()){m_error=QStringLiteral("Windows 无法签发 CA 证书 (错误 %1，证书 %2 字节，密钥 %3 字节)。").arg(signingError).arg(certificate.size()).arg(next->privateBlob.size());emit changed();return false;}
    auto old=std::move(d);const auto previous=m_certificate;d=std::move(next);m_certificate=parsed;
    if(!persist()){d=std::move(old);m_certificate=previous;return false;}
    m_cache.clear();m_enabled=false;m_error.clear();emit changed();return true;
#else
    m_error=QStringLiteral("当前平台暂不支持生成 CA。");emit changed();return false;
#endif
}
bool TlsCertificateService::persist() {
#ifdef Q_OS_WIN
    const auto plain=QJsonDocument(QJsonObject{{"schema",1},{"certificate",QString::fromLatin1(m_certificate.toDer().toBase64())},{"key",QString::fromLatin1(d->privateBlob.toBase64())},{"hosts",QJsonArray::fromStringList(m_hostnames)}}).toJson(QJsonDocument::Compact);
    DATA_BLOB input{DWORD(plain.size()),reinterpret_cast<BYTE *>(const_cast<char *>(plain.constData()))},output{};
    if(!CryptProtectData(&input,L"Swirl CA",nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output)){m_error=QStringLiteral("无法保护 CA 私钥。");emit changed();return false;}
    const QByteArray encrypted(reinterpret_cast<char *>(output.pbData),output.cbData);LocalFree(output.pbData);
    QDir().mkpath(QFileInfo(m_path).absolutePath());QSaveFile file(m_path);
    if(!file.open(QIODevice::WriteOnly)||file.write(encrypted)!=encrypted.size()||!file.commit()){m_error=QStringLiteral("CA 保存失败。");emit changed();return false;}return true;
#else
    return false;
#endif
}
void TlsCertificateService::load() {
#ifdef Q_OS_WIN
    QFile file(m_path);if(!file.open(QIODevice::ReadOnly)||file.size()>128*1024)return;auto bytes=file.readAll();
    DATA_BLOB input{DWORD(bytes.size()),reinterpret_cast<BYTE *>(bytes.data())},output{};
    if(!CryptUnprotectData(&input,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output))return;
    const auto object=QJsonDocument::fromJson(QByteArray(reinterpret_cast<char *>(output.pbData),output.cbData)).object();SecureZeroMemory(output.pbData,output.cbData);LocalFree(output.pbData);
    if(object.value("schema").toInt()!=1)return;
    for(const auto &host:object.value("hosts").toArray())if(host.isString()&&m_hostnames.size()<256)m_hostnames.append(host.toString());
    const auto key=QByteArray::fromBase64(object.value("key").toString().toLatin1());const QSslCertificate certificate(QByteArray::fromBase64(object.value("certificate").toString().toLatin1()),QSsl::Der);
    if(certificate.isNull()||certificate.expiryDate()<QDateTime::currentDateTimeUtc()||key.size()>16384)return;
    if(!CryptAcquireContextW(&d->provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)||!CryptImportKey(d->provider,reinterpret_cast<const BYTE *>(key.constData()),key.size(),0,CRYPT_EXPORTABLE,&d->key))return;
    d->privateBlob=key;m_certificate=certificate;
#endif
}
TlsCertificateService::Identity TlsCertificateService::identityFor(const QString &host) {
    if(m_cache.contains(host))return m_cache.value(host);
#ifdef Q_OS_WIN
    if(!ready()||host.size()>253||!QRegularExpression("^[A-Za-z0-9_.:-]+$").match(host).hasMatch())return Identity{QSslCertificate{}, QSslKey{}};
    KeyPair key;if(!key.create())return Identity{QSslCertificate{}, QSslKey{}};
    const auto root=m_certificate.toDer();auto *context=CertCreateCertificateContext(X509_ASN_ENCODING,reinterpret_cast<const BYTE *>(root.constData()),root.size());if(!context)return Identity{QSslCertificate{}, QSslKey{}};
    const QByteArray issuer(reinterpret_cast<const char *>(context->pCertInfo->Subject.pbData),context->pCertInfo->Subject.cbData);CertFreeCertificateContext(context);
    Identity identity{QSslCertificate(certificateFor(key.provider,d->provider,issuer,host,false),QSsl::Der),sslKey(exportBlob(key.key))};
    if(identity.certificate.isNull()||identity.key.isNull()){m_error=QStringLiteral("无法为目标主机创建 TLS 证书。");emit changed();return Identity{QSslCertificate{}, QSslKey{}};}
    if(m_cache.size()>=50)m_cache.clear();m_cache.insert(host,identity);return identity;
#else
    Q_UNUSED(host);return Identity{QSslCertificate{}, QSslKey{}};
#endif
}
bool TlsCertificateService::trusted() const {
#ifdef Q_OS_WIN
    if(!ready())return false;const auto hash=m_certificate.digest(QCryptographicHash::Sha1);CRYPT_HASH_BLOB blob{DWORD(hash.size()),reinterpret_cast<BYTE *>(const_cast<char *>(hash.constData()))};
    auto store=CertOpenStore(CERT_STORE_PROV_SYSTEM_W,0,0,CERT_SYSTEM_STORE_CURRENT_USER|CERT_STORE_READONLY_FLAG,L"ROOT");if(!store)return false;
    auto *context=CertFindCertificateInStore(store,X509_ASN_ENCODING,0,CERT_FIND_SHA1_HASH,&blob,nullptr);const bool result=context!=nullptr;if(context)CertFreeCertificateContext(context);CertCloseStore(store,0);return result;
#else
    return false;
#endif
}
bool TlsCertificateService::installTrust() {
#ifdef Q_OS_WIN
    if(!ready())return false;const auto bytes=m_certificate.toDer();auto store=CertOpenStore(CERT_STORE_PROV_SYSTEM_W,0,0,CERT_SYSTEM_STORE_CURRENT_USER,L"ROOT");
    if(!store){m_error=QStringLiteral("无法打开当前用户的证书存储。");emit changed();return false;}
    const bool result=CertAddEncodedCertificateToStore(store,X509_ASN_ENCODING,reinterpret_cast<const BYTE *>(bytes.constData()),bytes.size(),CERT_STORE_ADD_REPLACE_EXISTING,nullptr);CertCloseStore(store,0);
    if(!result)m_error=QStringLiteral("安装 CA 证书失败。");emit changed();return result;
#else
    return false;
#endif
}
bool TlsCertificateService::exportCertificate(const QUrl &destination) {
    if(!ready()||!destination.isLocalFile())return false;QSaveFile file(destination.toLocalFile());const auto pem=m_certificate.toPem();
    if(!file.open(QIODevice::WriteOnly)||file.write(pem)!=pem.size()||!file.commit()){m_error=QStringLiteral("证书导出失败。");emit changed();return false;}return true;
}

bool TlsCertificateService::importPkcs12(const QUrl &source,const QString &password) {
#ifdef Q_OS_WIN
    QFile file(source.toLocalFile());
    if(!source.isLocalFile()||!file.open(QIODevice::ReadOnly)||file.size()>1024*1024){m_error=QStringLiteral("请选择不超过 1 MB 的 PKCS #12 文件。");emit changed();return false;}
    QSslKey privateKey;QSslCertificate certificate;QList<QSslCertificate> chain;
    if(!QSslCertificate::importPkcs12(&file,&privateKey,&certificate,&chain,password.toUtf8())||privateKey.algorithm()!=QSsl::Rsa||certificate.isNull()){
        m_error=QStringLiteral("证书导入失败：密码错误、文件损坏或并非 RSA 证书。");emit changed();return false;
    }
    const auto certBytes=certificate.toDer();auto *context=CertCreateCertificateContext(X509_ASN_ENCODING,reinterpret_cast<const BYTE *>(certBytes.constData()),DWORD(certBytes.size()));
    bool isCa=false;
    if(context){auto *extension=CertFindExtension(szOID_BASIC_CONSTRAINTS2,context->pCertInfo->cExtension,context->pCertInfo->rgExtension);CERT_BASIC_CONSTRAINTS2_INFO *constraints=nullptr;DWORD size=0;
        if(extension&&CryptDecodeObjectEx(X509_ASN_ENCODING,X509_BASIC_CONSTRAINTS2,extension->Value.pbData,extension->Value.cbData,CRYPT_DECODE_ALLOC_FLAG,nullptr,&constraints,&size)){isCa=constraints->fCA;LocalFree(constraints);}CertFreeCertificateContext(context);}
    if(!isCa||certificate.expiryDate()<=QDateTime::currentDateTimeUtc()||certificate.effectiveDate()>QDateTime::currentDateTimeUtc()){
        m_error=QStringLiteral("需要尚在有效期内且允许签发证书的 CA 证书。");emit changed();return false;
    }
    auto next=std::make_unique<Impl>();next->privateBlob=privateBlobFromDer(privateKey.toDer());
    if(next->privateBlob.isEmpty()||!CryptAcquireContextW(&next->provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)
        ||!CryptImportKey(next->provider,reinterpret_cast<const BYTE *>(next->privateBlob.constData()),DWORD(next->privateBlob.size()),0,CRYPT_EXPORTABLE,&next->key)){
        m_error=QStringLiteral("无法导入 CA 私钥，需要 2048 至 4096 位 RSA 密钥。");emit changed();return false;
    }
    // Qt's PKCS #12 importer pairs the matching certificate and private key.
    auto previous=std::move(d);const auto oldCertificate=m_certificate;d=std::move(next);m_certificate=certificate;
    if(!persist()){d=std::move(previous);m_certificate=oldCertificate;return false;}
    m_enabled=false;m_cache.clear();m_error.clear();emit changed();return true;
#else
    Q_UNUSED(source);Q_UNUSED(password);m_error=QStringLiteral("当前平台暂不支持导入 CA。");emit changed();return false;
#endif
}

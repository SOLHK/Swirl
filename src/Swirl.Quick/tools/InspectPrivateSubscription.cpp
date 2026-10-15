#include "engine/NodeImporter.h"
#include "engine/NodeStore.h"
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QTextStream>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif
// Test-only local inspector. Its input is a Windows-DPAPI-encrypted response;
// stdout contains only format/protocol counts and fixed, redacted diagnostics.
int main(int argc,char **argv){
    QCoreApplication app(argc,argv);QTextStream output(stdout);if(app.arguments().size()!=3)return 2;
    QFile file(app.arguments()[1]);if(!file.open(QIODevice::ReadOnly)||file.size()>8*1024*1024)return 3;
    QByteArray plain;
#ifdef Q_OS_WIN
    auto encrypted=file.readAll();DATA_BLOB source{DWORD(encrypted.size()),reinterpret_cast<BYTE *>(encrypted.data())},out{};
    if(!CryptUnprotectData(&source,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out))return 4;
    plain=QByteArray(reinterpret_cast<char *>(out.pbData),out.cbData);SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);
#else
    return 4;
#endif
    auto result=NodeImporter::parse(plain);plain.fill('\0');
    if(!result){output<<QJsonDocument(QJsonObject{{"error",result.error},{"format",result.format}}).toJson(QJsonDocument::Compact)<<Qt::endl;return 5;}
    NodeStore store(app.arguments()[2]);if(!store.importNodes(result.nodes)){output<<store.error()<<Qt::endl;return 6;}
    QJsonObject counts;QSet<QString> issues;
    for(const auto &node:result.nodes){counts[node.protocol]=counts.value(node.protocol).toInt()+1;for(const auto &message:node.conversionIssues)issues.insert(message);}
    output<<QJsonDocument(QJsonObject{{"format",result.format},{"nodes",result.nodes.size()},{"protocols",counts},{"incompleteNodes",result.incompleteNodes},{"issues",QJsonArray::fromStringList(issues.values())}}).toJson(QJsonDocument::Compact)<<Qt::endl;return 0;
}

#pragma once
#include <QFile>
#include <QJsonArray>
#include <QJsonObject>
#include <QCryptographicHash>
#include <QRawFont>
#include <QtEndian>
#include <QTextLayout>
#include <QGlyphRun>

namespace SwirlFontSource {
inline QJsonArray faces(const QString &path) {
    QFile input(path);if(!input.open(QIODevice::ReadOnly))return {};
    const auto data=input.readAll();if(data.size()<12)return {};
    auto u16=[&](qsizetype at){return qFromBigEndian<quint16>(data.constData()+at);};
    auto u32=[&](qsizetype at){return qFromBigEndian<quint32>(data.constData()+at);};
    QList<quint32> offsets;
    if(data.first(4)=="ttcf"){
        const auto count=u32(8);if(count>quint64(data.size()-12)/4)return {};
        for(quint32 i=0;i<count;++i)offsets.append(u32(12+i*4));
    }else offsets.append(0);
    QJsonArray result;
    for(int index=0;index<offsets.size();++index){
        const quint64 offset=offsets[index];if(offset+12>quint64(data.size()))return {};
        const auto count=u16(offset+4);if(offset+12+quint64(count)*16>quint64(data.size()))return {};
        QJsonObject tables;
        for(int i=0;i<count;++i){
            const auto at=offset+12+i*16;const auto tag=data.mid(at,4);
            const quint64 start=u32(at+8),size=u32(at+12);if(start+size>quint64(data.size()))return {};
            if(tag!="name"&&tag!="cmap"&&tag!="fvar"&&tag!="gvar")continue;
            tables[QString::fromLatin1(tag)]=QString::fromLatin1(QCryptographicHash::hash(data.mid(start,size),QCryptographicHash::Sha256).toHex());
        }
        result.append(QJsonObject{{"index",index},{"tables",tables}});
    }
    return result;
}
inline QJsonObject identity(const QRawFont &font,const QJsonArray &expected,bool full=true){
    QJsonObject tables;for(auto tag:{"name","cmap","fvar","gvar"}){
        if(!full&&QByteArray(tag)=="gvar")continue;
        const auto bytes=font.fontTable(tag);
        if(!bytes.isEmpty())tables[tag]=QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex());
    }
    int index=-1;
    for(const auto &entry:expected){const auto face=entry.toObject();const auto wanted=face["tables"].toObject();bool same=true;
        for(auto it=wanted.begin();it!=wanted.end();++it){
            if(!full&&it.key()==QStringLiteral("gvar"))continue;
            if(tables[it.key()]!=it.value())same=false;
        }
        for(auto it=tables.begin();it!=tables.end();++it)if(wanted[it.key()]!=it.value())same=false;
        if(same&&tables.contains("name")&&tables.contains("cmap")){index=face["index"].toInt();break;}}
    return {{"family",font.familyName()},{"faceIndex",index},{"matchesSource",index>=0},{"tables",tables}};
}
}

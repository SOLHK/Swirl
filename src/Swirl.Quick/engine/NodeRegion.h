#pragma once
#include <QLocale>
#include <QRegularExpression>
#include <QString>

// Labels supplied by a subscription are hints, never IP geolocation claims.
// Country flags cover all ISO territories; aliases cover common CJK node names.
namespace NodeRegion {
struct Region { QString code; QString name; };
inline Region fromName(const QString &name) {
    struct Alias { const char *code; const char *name; const char *pattern; };
    static const Alias aliases[] = {
        {"HK","香港","香港|Hong[ -]?Kong"},{"MO","澳门","澳门|澳門|Macao|Macau"},
        {"TW","台湾","台湾|台灣|Taiwan"},{"JP","日本","日本|东京|東京|大阪|Japan|Tokyo|Osaka"},
        {"SG","新加坡","新加坡|狮城|獅城|Singapore"},{"US","美国","美国|美國|洛杉矶|洛杉磯|United States|America|Los Angeles"},
        {"GB","英国","英国|英國|伦敦|倫敦|United Kingdom|Britain|London"},
        {"DE","德国","德国|德國|法兰克福|法蘭克福|Germany|Frankfurt"},{"FR","法国","法国|法國|巴黎|France|Paris"},
        {"KR","韩国","韩国|韓國|首尔|首爾|Korea|Seoul"},{"CA","加拿大","加拿大|Canada"},
        {"AU","澳大利亚","澳大利亞|澳大利亚|澳洲|悉尼|Australia|Sydney"},
        {"NL","荷兰","荷兰|荷蘭|Netherlands"},{"RU","俄罗斯","俄罗斯|俄羅斯|Russia"},
        {"IN","印度","印度|India"},{"ID","印度尼西亚","印度尼西亚|印度尼西亞|印尼|Indonesia"},
        {"TH","泰国","泰国|泰國|Thailand"},{"VN","越南","越南|Vietnam"},
        {"MY","马来西亚","马来西亚|馬來西亞|Malaysia"},{"PH","菲律宾","菲律宾|菲律賓|Philippines"},
        {"TR","土耳其","土耳其|Turkey|Türkiye"},{"BR","巴西","巴西|Brazil"},
        {"ZA","南非","南非|South Africa"},{"CH","瑞士","瑞士|Switzerland"},
        {"SE","瑞典","瑞典|Sweden"},{"FI","芬兰","芬兰|芬蘭|Finland"},
        {"NO","挪威","挪威|Norway"},{"IT","意大利","意大利|義大利|Italy"},
        {"ES","西班牙","西班牙|Spain"},{"AE","阿联酋","阿联酋|阿聯酋|迪拜|United Arab Emirates|Dubai"},
        {"CN","中国大陆","中国|中國|大陆|大陸|China"}
    };
    auto regionForCode=[&](const QString &code)->Region {
        for(const auto &a:aliases)if(code==QLatin1String(a.code))return {code,QString::fromUtf8(a.name)};
        const auto territory=QLocale::codeToTerritory(code);
        return territory==QLocale::AnyTerritory?Region{}:Region{code,QLocale::territoryToString(territory)};
    };
    const auto points=name.toUcs4();
    for(qsizetype i=0;i+1<points.size();++i) {
        if(points[i]>=0x1f1e6 && points[i]<=0x1f1ff && points[i+1]>=0x1f1e6 && points[i+1]<=0x1f1ff) {
            const QString code=QString(QChar('A'+points[i]-0x1f1e6))+QChar('A'+points[i+1]-0x1f1e6);
            const auto region=regionForCode(code);if(!region.code.isEmpty())return region;
        }
    }
    // Match longer aliases first, so 印度尼西亚 is not mistaken for 印度.
    Region best;qsizetype length=0;
    static const auto patterns=[] {
        QList<QRegularExpression> result;
        for(const auto &a:aliases)result.append(QRegularExpression(QString::fromUtf8(a.pattern),QRegularExpression::CaseInsensitiveOption));
        return result;
    }();
    for(qsizetype i=0;i<patterns.size();++i) {
        const auto match=patterns[i].match(name);
        if(match.hasMatch() && match.capturedLength()>length){best={QString::fromLatin1(aliases[i].code),QString::fromUtf8(aliases[i].name)};length=match.capturedLength();}
    }
    if(!best.code.isEmpty())return best;
    // Only standalone, uppercase ISO tokens count. Do not match 'us' in words.
    static const QRegularExpression token(QStringLiteral("(?:^|[^A-Za-z])([A-Z]{2})(?=$|[^A-Za-z])"));
    auto matches=token.globalMatch(name);
    while(matches.hasNext()) {const auto region=regionForCode(matches.next().captured(1));if(!region.code.isEmpty())return region;}
    return {QStringLiteral("unknown"),QStringLiteral("未标注地区")};
}
}

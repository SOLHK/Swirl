// Independent authored-source comparisons through Qt's actual native font engine.
// No private fonts, system installation, hardware-DPI or source-font acceptance.
#include <QGuiApplication>
#include <QFontDatabase>
#include <QFontInfo>
#include <QRawFont>
#include <QPainterPath>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QSysInfo>
#include <QCryptographicHash>
#include <cmath>
#include <algorithm>
#include <cstdio>

static QString sha(const QByteArray &data) {
    return QString::fromLatin1(QCryptographicHash::hash(data,QCryptographicHash::Sha256).toHex());
}
static QPainterPath expectedPath(const QJsonArray &commands, bool &valid) {
    QPainterPath path;
    for (const auto &entry:commands) {
        const auto c=entry.toArray();
        if(c.isEmpty()){valid=false;continue;}
        const auto op=c[0].toString();
        auto p=[&](int i){return QPointF(c[i].toDouble(),-c[i+1].toDouble());};
        if(op=="moveTo"&&c.size()==3)path.moveTo(p(1));
        else if(op=="lineTo"&&c.size()==3)path.lineTo(p(1));
        else if(op=="qCurveTo"&&c.size()==5)path.quadTo(p(1),p(3));
        else if(op=="curveTo"&&c.size()==7)path.cubicTo(p(1),p(3),p(5));
        else if(op=="closePath"&&c.size()==1)path.closeSubpath();
        else valid=false;
    }
    return path;
}
int main(int argc,char **argv) {
    QGuiApplication app(argc,argv);
    if(argc!=4)return 2;
    QFile input(QString::fromUtf8(argv[1])),manifest(QString::fromUtf8(argv[2]));
    if(!input.open(QIODevice::ReadOnly)||!manifest.open(QIODevice::ReadOnly))return 3;
    const auto bytes=input.readAll(),planBytes=manifest.readAll();
    const auto plan=QJsonDocument::fromJson(planBytes).object();
    if(plan["schema"].toInt()!=1||plan["scope"]!="independent_authored_CFF2_controls_only"||
       plan["font_sha256"].toString()!=sha(bytes)||plan["limit_source_units"].toDouble()!=1./32)return 4;
    const int id=QFontDatabase::addApplicationFontFromData(bytes);
    const auto families=QFontDatabase::applicationFontFamilies(id);
    QJsonArray rows;int failures=0;double maximum=0.;
    bool ok=id>=0&&families.size()==2&&plan["faces"].toArray().size()==2;
    for(const auto &faceEntry:plan["faces"].toArray()) {
        const auto face=faceEntry.toObject();const auto family=face["family"].toString();
        const int upm=face["upm"].toInt();ok&=families.contains(family)&&upm>0;
        for(const auto &caseEntry:face["cases"].toArray()) {
            const auto test=caseEntry.toObject();const auto user=test["user"].toObject();
            QFont font(family);font.setPixelSize(upm);font.setStyleName({});font.clearVariableAxes();
            font.setHintingPreference(QFont::PreferNoHinting);font.setStyleStrategy(QFont::NoFontMerging);
            bool axes=user.size()==3;
            for(const auto &tag:{"WDTH","wght","HGHT"}) {
                axes&=user.contains(tag);
                font.setVariableAxis(*QFont::Tag::fromString(QByteArray(tag)),user[tag].toDouble());
            }
            const auto raw=QRawFont::fromFont(font);
            bool identity=axes&&raw.isValid()&&raw.familyName()==family&&raw.unitsPerEm()==upm&&
                raw.pixelSize()==upm&&sha(raw.fontTable("CFF2"))==face["cff2_sha256"].toString()&&
                QFontInfo(font).variableAxes().size()==3;
            for(const auto &glyphEntry:test["glyphs"].toArray()) {
                const auto glyph=glyphEntry.toObject();const int gid=glyph["gid"].toInt(-1);
                bool valid=gid>=0;const auto reference=expectedPath(glyph["commands"].toArray(),valid);
                const auto actual=gid>=0?raw.pathForGlyph(gid):QPainterPath();
                bool topology=valid&&actual.elementCount()==reference.elementCount();double error=0.;
                if(topology)for(int i=0;i<actual.elementCount();++i) {
                    const auto a=actual.elementAt(i),b=reference.elementAt(i);
                    topology&=a.type==b.type;
                    if(!std::isfinite(a.x)||!std::isfinite(a.y)){topology=false;continue;}
                    error=std::max(error,std::hypot(a.x-b.x,a.y-b.y));
                }
                const bool passed=identity&&topology&&error<=1./32;
                failures+=!passed;maximum=std::max(maximum,error);ok&=passed;
                rows.append(QJsonObject{{"family",family},{"gid",gid},{"user",user},
                    {"identity",identity},{"topology",topology},{"error_source_units",error},
                    {"actual_elements",actual.elementCount()},{"reference_elements",reference.elementCount()},
                    {"passed",passed}});
            }
        }
    }
    const bool removed=id>=0&&QFontDatabase::removeApplicationFont(id);ok&=removed&&rows.size()==546;
    QJsonObject report{{"schema",1},{"qt",qVersion()},{"qpa",QGuiApplication::platformName()},
        {"os",QSysInfo::prettyProductName()},{"kernel",QSysInfo::kernelVersion()},
        {"build_architecture",QSysInfo::buildCpuArchitecture()},
        {"current_architecture",QSysInfo::currentCpuArchitecture()},
        {"scope","independent_authored_CFF2_geometry_only"},{"font_sha256",sha(bytes)},
        {"manifest_sha256",sha(planBytes)},{"observations",rows.size()},{"failures",failures},
        {"max_error_source_units",maximum},{"limit_source_units",1./32},{"font_removed",removed},
        {"production_accepted",false},{"physical_display_verified",false},{"rows",rows},
        {"status",ok?"PASS_AUTHORED_QT_GEOMETRY":"FAIL"}};
    QFile output(QString::fromUtf8(argv[3]));QDir().mkpath(QFileInfo(output.fileName()).absolutePath());
    if(!output.open(QIODevice::WriteOnly))return 5;output.write(QJsonDocument(report).toJson());
    std::printf("%s: %d observations, %d failures, %.9f FUnit\n",ok?"PASS":"FAIL",int(rows.size()),failures,maximum);
    return ok?0:1;
}

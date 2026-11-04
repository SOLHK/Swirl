// Independent source comparisons through Qt's actual native font engine.
// Private local-box input requires an explicit switch and cannot accept a font.
// No system installation, hardware-DPI or whole-source-font acceptance.
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
static bool emptyOrigin(const QPainterPath &path, bool serializedEmpty, bool referenceEmpty) {
    // Qt's Windows sink starts an empty path with moveTo(0,0). This has no
    // contour or ink. Permit only that exact representation, backed by an
    // actually empty saved CFF2 CharString and an independently empty source.
    if(!serializedEmpty||!referenceEmpty||!path.isEmpty()||path.elementCount()!=1)return false;
    const auto p=path.elementAt(0);
    return p.type==QPainterPath::MoveToElement&&p.x==0.&&p.y==0.;
}
static bool emptyRuleControls() {
    QPainterPath origin;origin.moveTo(0,0);
    QPainterPath displaced;displaced.moveTo(1,0);
    QPainterPath edge;edge.moveTo(0,0);edge.lineTo(1./65536,0);
    QPainterPath curve;curve.moveTo(0,0);curve.cubicTo(1,2,3,4,0,0);
    return emptyOrigin(origin,true,true)&&!emptyOrigin(origin,false,true)&&
        !emptyOrigin(origin,true,false)&&!emptyOrigin(displaced,true,true)&&
        !emptyOrigin(edge,true,true)&&!emptyOrigin(curve,true,true);
}
static QJsonArray pathData(const QPainterPath &path) {
    QJsonArray result;
    for(int i=0;i<path.elementCount();++i) {
        const auto e=path.elementAt(i);result.append(QJsonArray{int(e.type),e.x,e.y});
    }
    return result;
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
    if(!emptyRuleControls())return 6;
    const bool privateBox=argc==5&&QByteArray(argv[4])=="--private-box";
    if(argc!=4&&!privateBox)return 2;
    QFile input(QString::fromUtf8(argv[1])),manifest(QString::fromUtf8(argv[2]));
    if(!input.open(QIODevice::ReadOnly)||!manifest.open(QIODevice::ReadOnly))return 3;
    const auto bytes=input.readAll(),planBytes=manifest.readAll();
    const auto plan=QJsonDocument::fromJson(planBytes).object();
    const QString requiredScope=privateBox?"private_source_local_box_only":"independent_authored_CFF2_controls_only";
    const int expectedFaces=privateBox?1:2;
    const int expectedObservations=privateBox?plan["expected_observations"].toInt():546;
    if(plan["schema"].toInt()!=1||plan["scope"].toString()!=requiredScope||
       plan["font_sha256"].toString()!=sha(bytes)||plan["limit_source_units"].toDouble()!=1./32)return 4;
    if(privateBox&&(expectedObservations<1||expectedObservations>4096||
        plan["source_sha256"].toString().size()!=64||plan["source_glyph_id"].toInt(-1)<0||
        plan["box"].toArray().size()!=3||plan["source_font_acceptance"]!=QJsonValue(false)))return 4;
    const int id=QFontDatabase::addApplicationFontFromData(bytes);
    const auto families=QFontDatabase::applicationFontFamilies(id);
    QJsonArray rows;int failures=0,rawTopologyFailures=0,emptyRepresentations=0,measured=0;double maximum=0.;
    bool ok=id>=0&&families.size()==expectedFaces&&plan["faces"].toArray().size()==expectedFaces;
    for(const auto &faceEntry:plan["faces"].toArray()) {
        const auto face=faceEntry.toObject();const auto family=face["family"].toString();
        const int upm=face["upm"].toInt();ok&=families.contains(family)&&upm>0;
        for(const auto &caseEntry:face["cases"].toArray()) {
            const auto test=caseEntry.toObject();const auto user=test["user"].toObject();
            QFont font(family);font.setPixelSize(upm);font.setStyleName({});font.clearVariableAxes();
            font.setHintingPreference(QFont::PreferNoHinting);font.setStyleStrategy(QFont::NoFontMerging);
            bool axes=user.size()==3;
            int axisIndex=0;
            for(const auto &tag:{"WDTH","wght","HGHT"}) {
                axes&=user[tag].isDouble()&&std::isfinite(user[tag].toDouble());
                if(privateBox) {
                    const auto bounds=plan["box"].toArray()[axisIndex].toArray();
                    const auto value=test["normalized"].toObject()[tag];
                    axes&=bounds.size()==2&&value.isDouble();
                    if(bounds.size()==2)axes&=bounds[0].toDouble()<bounds[1].toDouble()&&
                        value.toDouble()>=bounds[0].toDouble()&&value.toDouble()<=bounds[1].toDouble();
                }
                font.setVariableAxis(*QFont::Tag::fromString(QByteArray(tag)),user[tag].toDouble());
                ++axisIndex;
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
                    topology&=a.type==b.type&&std::isfinite(a.x)&&std::isfinite(a.y);
                }
                if(topology)for(int i=0;i<actual.elementCount();++i) {
                    const auto a=actual.elementAt(i),b=reference.elementAt(i);
                    error=std::max(error,std::hypot(a.x-b.x,a.y-b.y));
                }
                const bool rawTopology=topology;
                const bool emptyRepresentation=valid&&emptyOrigin(actual,
                    glyph["serialized_empty_cff2"].toBool(false),glyph["commands"].toArray().isEmpty());
                rawTopologyFailures+=!rawTopology;emptyRepresentations+=emptyRepresentation;
                topology|=emptyRepresentation;
                const bool passed=identity&&topology&&error<=1./32;
                failures+=!passed;ok&=passed;
                if(identity&&topology){++measured;maximum=std::max(maximum,error);}
                QJsonObject row{{"family",family},{"gid",gid},{"user",user},
                    {"identity",identity},{"topology",topology},
                    {"error_source_units",identity&&topology?QJsonValue(error):QJsonValue()},
                    {"raw_element_topology",rawTopology},{"verified_empty_origin",emptyRepresentation},
                    {"actual_elements",actual.elementCount()},{"reference_elements",reference.elementCount()},
                    {"passed",passed}};
                if(privateBox&&!passed) {
                    row["actual_path"]=pathData(actual);row["reference_path"]=pathData(reference);
                }
                rows.append(row);
            }
        }
    }
    const bool removed=id>=0&&QFontDatabase::removeApplicationFont(id);ok&=removed&&rows.size()==expectedObservations;
    QJsonObject report{{"schema",1},{"qt",qVersion()},{"qpa",QGuiApplication::platformName()},
        {"os",QSysInfo::prettyProductName()},{"kernel",QSysInfo::kernelVersion()},
        {"build_architecture",QSysInfo::buildCpuArchitecture()},
        {"current_architecture",QSysInfo::currentCpuArchitecture()},
        {"scope",requiredScope},{"font_sha256",sha(bytes)},
        {"source_sha256",plan["source_sha256"]},{"source_glyph_id",plan["source_glyph_id"]},
        {"box",plan["box"]},{"source_font_acceptance",false},
        {"manifest_sha256",sha(planBytes)},{"observations",rows.size()},{"failures",failures},
        {"raw_topology_failures",rawTopologyFailures},{"verified_empty_origin_representations",emptyRepresentations},
        {"empty_representation_positive_and_negative_controls",true},
        {"geometry_observations",measured},
        {"max_error_source_units",measured?QJsonValue(maximum):QJsonValue()},
        {"limit_source_units",1./32},{"font_removed",removed},
        {"production_accepted",false},{"physical_display_verified",false},{"rows",rows},
        {"status",ok?(privateBox?"PASS_PRIVATE_BOX_QT_GEOMETRY":"PASS_AUTHORED_QT_GEOMETRY"):"FAIL"}};
    QFile output(QString::fromUtf8(argv[3]));QDir().mkpath(QFileInfo(output.fileName()).absolutePath());
    if(!output.open(QIODevice::WriteOnly))return 5;output.write(QJsonDocument(report).toJson());
    std::printf("%s: %d observations, %d failures, %.9f FUnit\n",ok?"PASS":"FAIL",int(rows.size()),failures,maximum);
    return ok?0:1;
}

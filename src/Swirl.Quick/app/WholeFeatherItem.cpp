#include "WholeFeatherItem.h"
#include <QImage>
#include <QPainter>
#include <QPainterPath>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSGGeometryNode>
#include <QSGImageNode>
#include <QSGVertexColorMaterial>
#include <QtMath>
#include <algorithm>
#include <array>
#include <cmath>

namespace {
constexpr int sections = 96;
constexpr int vertices = sections*18;
qreal magnitude(const QPointF &p) { return std::hypot(p.x(),p.y()); }
qreal cross(const QPointF &a,const QPointF &b) { return a.x()*b.y()-a.y()*b.x(); }

void flatten(const QPointF &a,const QPointF &b,const QPointF &c,const QPointF &d,
             int depth,QVector<QPointF> &points) {
    const QPointF chord=d-a;
    const qreal length=magnitude(chord);
    const qreal distance=length>0?qMax(std::abs(cross(chord,b-a)),std::abs(cross(chord,c-a)))/length
                                 :qMax(magnitude(b-a),magnitude(c-a));
    if (depth==10 || (distance<0.10 && magnitude(b-a)+magnitude(c-b)+magnitude(d-c)-length<0.10)) {
        if (magnitude(d-points.last())>0.0001) points.append(d);
        return;
    }
    const auto ab=(a+b)*0.5,bc=(b+c)*0.5,cd=(c+d)*0.5;
    const auto abc=(ab+bc)*0.5,bcd=(bc+cd)*0.5,middle=(abc+bcd)*0.5;
    flatten(a,ab,abc,middle,depth+1,points);
    flatten(middle,bcd,cd,d,depth+1,points);
}

QVector<QPointF> outline(const QString &path) {
    static const QRegularExpression token(QStringLiteral("[A-Za-z]|[-+]?(?:\\d*\\.\\d+|\\d+\\.?\\d*)(?:[eE][-+]?\\d+)?"));
    QStringList tokens;
    auto matches=token.globalMatch(path);
    while (matches.hasNext()) tokens.append(matches.next().captured());
    if (tokens.size()<4 || tokens[0]!=QStringLiteral("M")) return {};
    QPointF current(tokens[1].toDouble(),tokens[2].toDouble());
    QVector<QPointF> points{current};
    bool closed=false;
    for (qsizetype i=3;i<tokens.size();) {
        const auto command=tokens[i++];
        if (command==QStringLiteral("Z") && i==tokens.size()) { closed=true; break; }
        if (command!=QStringLiteral("C") || i+6>tokens.size()) return {};
        const QPointF b(tokens[i].toDouble(),tokens[i+1].toDouble());
        const QPointF c(tokens[i+2].toDouble(),tokens[i+3].toDouble());
        const QPointF d(tokens[i+4].toDouble(),tokens[i+5].toDouble());
        i+=6;
        flatten(current,b,c,d,0,points); current=d;
    }
    if (!closed || points.size()<3) return {};
    if (magnitude(points.last()-points.first())<0.0001) points.removeLast();
    qreal area=0;
    for (qsizetype i=0;i<points.size();++i) area+=cross(points[i],points[(i+1)%points.size()]);
    if (area<0) std::reverse(points.begin(),points.end());
    return points;
}

QVector<QPointF> sampleArc(const QVector<QPointF> &polygon,int root,int tip,int direction) {
    QVector<QPointF> arc{polygon[root]};
    QVector<qreal> lengths{0};
    const int count=polygon.size();
    for (int i=(root+direction+count)%count;i!=root;i=(i+direction+count)%count) {
        lengths.append(lengths.last()+magnitude(polygon[i]-arc.last()));
        arc.append(polygon[i]);
        if (i==tip) break;
    }
    if (arc.size()<2 || lengths.last()<=0) return {};
    QVector<QPointF> result;
    result.reserve(sections+1);
    qsizetype next=1;
    for (int i=0;i<=sections;++i) {
        const qreal distance=lengths.last()*i/sections;
        while (next<lengths.size()-1 && lengths[next]<distance) ++next;
        const qreal fraction=(distance-lengths[next-1])/(lengths[next]-lengths[next-1]);
        result.append(arc[next-1]+(arc[next]-arc[next-1])*fraction);
    }
    return result;
}

void cacheEdges(const QString &path,const QPointF &root,const QPointF &tip,
                QVector<QPointF> &first,QVector<QPointF> &second) {
    first.clear(); second.clear();
    const auto polygon=outline(path);
    if (polygon.isEmpty()) return;
    const auto nearest=[&](const QPointF &point) {
        return int(std::min_element(polygon.cbegin(),polygon.cend(),[&](const auto &a,const auto &b) {
            return magnitude(a-point)<magnitude(b-point);
        })-polygon.cbegin());
    };
    const int rootIndex=nearest(root),tipIndex=nearest(tip);
    if (rootIndex==tipIndex) return;
    first=sampleArc(polygon,rootIndex,tipIndex,1);
    second=sampleArc(polygon,rootIndex,tipIndex,-1);
}

struct FeatherNode final : QSGNode {
    QSGGeometryNode *mesh=nullptr;
    QSGImageNode *image=nullptr;
};
}

WholeFeatherItem::WholeFeatherItem(QQuickItem *parent):QQuickItem(parent) {
    setFlag(ItemHasContents,true);
    setAcceptedMouseButtons(Qt::NoButton);
    setAcceptHoverEvents(false);
}
#define FEATHER_GEOMETRY_SETTER(Name, Type, member, dirty, signal) \
void WholeFeatherItem::Name(const Type &value) { \
    if (member==value) return; \
    member=value; dirty=true; emit signal(); update(); \
}
FEATHER_GEOMETRY_SETTER(setSourcePath,QString,m_sourcePath,m_sourceDirty,sourcePathChanged)
FEATHER_GEOMETRY_SETTER(setSourceRoot,QPointF,m_sourceRoot,m_sourceDirty,sourceRootChanged)
FEATHER_GEOMETRY_SETTER(setSourceTip,QPointF,m_sourceTip,m_sourceDirty,sourceTipChanged)
FEATHER_GEOMETRY_SETTER(setTargetPath,QString,m_targetPath,m_targetDirty,targetPathChanged)
FEATHER_GEOMETRY_SETTER(setTargetRoot,QPointF,m_targetRoot,m_targetDirty,targetRootChanged)
FEATHER_GEOMETRY_SETTER(setTargetTip,QPointF,m_targetTip,m_targetDirty,targetTipChanged)
#undef FEATHER_GEOMETRY_SETTER
void WholeFeatherItem::setMorphProgress(qreal value) {
    value=qBound<qreal>(0,value,1);
    if (qFuzzyCompare(m_morphProgress+1,value+1)) return;
    m_morphProgress=value; emit morphProgressChanged(); update();
}
void WholeFeatherItem::setInk(const QColor &value) {
    if (m_ink==value) return;
    m_ink=value; emit inkChanged(); update();
}
void WholeFeatherItem::itemChange(ItemChange change,const ItemChangeData &data) {
    QQuickItem::itemChange(change,data);
    if (change==ItemDevicePixelRatioHasChanged || change==ItemScaleHasChanged || change==ItemTransformHasChanged)
        update();
}

QSGNode *WholeFeatherItem::updatePaintNode(QSGNode *old,UpdatePaintNodeData *) {
    if (m_sourceDirty) { cacheEdges(m_sourcePath,m_sourceRoot,m_sourceTip,m_sourceFirst,m_sourceSecond); m_sourceDirty=false; }
    if (m_targetDirty) { cacheEdges(m_targetPath,m_targetRoot,m_targetTip,m_targetFirst,m_targetSecond); m_targetDirty=false; }
    const bool hasTarget=!m_targetPath.isEmpty();
    if (!window() || m_ink.alpha()==0 || m_sourceFirst.isEmpty() || m_sourceSecond.isEmpty()
        || (hasTarget && (m_targetFirst.isEmpty() || m_targetSecond.isEmpty()))) {
        delete old; return nullptr;
    }
    const auto origin=mapToScene(QPointF(0,0));
    const auto sceneX=mapToScene(QPointF(1,0))-origin,sceneY=mapToScene(QPointF(0,1))-origin;
    const qreal sceneScale=qMax(magnitude(sceneX),magnitude(sceneY));
    if (qMin(magnitude(sceneX),magnitude(sceneY))<0.0001) { delete old; return nullptr; }
    const qreal dpr=window()->devicePixelRatio();
    std::array<QPointF,sections+1> first,second;
    for (int i=0;i<=sections;++i) {
        first[i]=hasTarget?m_sourceFirst[i]+(m_targetFirst[i]-m_sourceFirst[i])*m_morphProgress:m_sourceFirst[i];
        second[i]=hasTarget?m_sourceSecond[i]+(m_targetSecond[i]-m_sourceSecond[i])*m_morphProgress:m_sourceSecond[i];
    }
    auto *node=old?static_cast<FeatherNode *>(old):new FeatherNode;
    if (window()->rendererInterface()->graphicsApi()==QSGRendererInterface::Software) {
        QPainterPath shape;
        shape.setFillRule(Qt::WindingFill);
        shape.moveTo(first[0]);
        for (int i=1;i<=sections;++i) shape.lineTo(first[i]);
        for (int i=sections-1;i>=0;--i) shape.lineTo(second[i]);
        shape.closeSubpath();
        const qreal pixelScale=sceneScale*dpr,margin=1/pixelScale;
        const auto bounds=shape.boundingRect().adjusted(-margin,-margin,margin,margin);
        QImage image(QSize(qMax(1,qCeil(bounds.width()*pixelScale)),qMax(1,qCeil(bounds.height()*pixelScale))),QImage::Format_ARGB32_Premultiplied);
        image.fill(Qt::transparent);
        QPainter painter(&image);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.scale(pixelScale,pixelScale); painter.translate(-bounds.topLeft());
        painter.fillPath(shape,m_ink); painter.end();
        if (!node->image) { node->image=window()->createImageNode(); node->appendChildNode(node->image); }
        auto *previous=node->image->texture();
        node->image->setOwnsTexture(false);
        node->image->setTexture(window()->createTextureFromImage(image));
        node->image->setOwnsTexture(true); node->image->setFiltering(QSGTexture::Linear); node->image->setRect(bounds);
        delete previous;
        return node;
    }
    if (!node->mesh) {
        node->mesh=new QSGGeometryNode;
        auto *geometry=new QSGGeometry(QSGGeometry::defaultAttributes_ColoredPoint2D(),vertices);
        geometry->setDrawingMode(QSGGeometry::DrawTriangles);
        geometry->setVertexDataPattern(QSGGeometry::DynamicPattern);
        node->mesh->setGeometry(geometry); node->mesh->setFlag(QSGNode::OwnsGeometry);
        node->mesh->setMaterial(new QSGVertexColorMaterial); node->mesh->setFlag(QSGNode::OwnsMaterial);
        node->appendChildNode(node->mesh);
    }
    std::array<std::array<QPointF,4>,sections+1> rails;
    const auto fringe=[&](QPointF tangent,bool clockwise) {
        const qreal length=magnitude(tangent);
        if (length==0) return QPointF();
        tangent/=length;
        const QPointF normal=clockwise?QPointF(tangent.y(),-tangent.x()):QPointF(-tangent.y(),tangent.x());
        return normal/(magnitude(sceneX*normal.x()+sceneY*normal.y())*dpr);
    };
    for (int i=0;i<=sections;++i) {
        const int before=qMax(0,i-1),after=qMin(sections,i+1);
        rails[i]={first[i]+fringe(first[after]-first[before],true),first[i],second[i],
                  second[i]+fringe(second[after]-second[before],false)};
    }
    const QRgb color=qPremultiply(m_ink.rgba());
    auto *data=node->mesh->geometry()->vertexDataAsColoredPoint2D();
    int vertex=0;
    const auto put=[&](const QPointF &point,bool solid) {
        data[vertex++].set(float(point.x()),float(point.y()),solid?uchar(qRed(color)):0,solid?uchar(qGreen(color)):0,
                           solid?uchar(qBlue(color)):0,solid?uchar(qAlpha(color)):0);
    };
    for (int i=0;i<sections;++i) {
        for (int rail=0;rail<3;++rail) {
            const bool a=rail!=0,b=rail!=2;
            put(rails[i][rail],a); put(rails[i+1][rail],a); put(rails[i][rail+1],b);
            put(rails[i][rail+1],b); put(rails[i+1][rail],a); put(rails[i+1][rail+1],b);
        }
    }
    node->mesh->geometry()->markVertexDataDirty();
    node->mesh->markDirty(QSGNode::DirtyGeometry);
    return node;
}

#include "RibbonStroke.h"
#include <QQuickWindow>
#include <QImage>
#include <QRegularExpression>
#include <QSGGeometryNode>
#include <QSGImageNode>
#include <QSGVertexColorMaterial>
#include <QtMath>
#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>

namespace {
qreal magnitude(const QPointF &p) { return std::hypot(p.x(), p.y()); }
qreal lineDistance(const QPointF &p, const QPointF &a, const QPointF &b) {
    const auto d = b - a;
    const auto length = magnitude(d);
    return length > 0 ? std::abs(d.x() * (a.y() - p.y()) - d.y() * (a.x() - p.x())) / length : magnitude(p - a);
}
void flatten(const QPointF &a, const QPointF &b, const QPointF &c, const QPointF &d,
             int depth, QVector<QPointF> &points) {
    // An arc-length table is rebuilt only for a changed guide. Splitting also
    // catches collinear reversals, where a line-distance test alone is wrong.
    const qreal polygon = magnitude(b-a) + magnitude(c-b) + magnitude(d-c);
    if (depth == 9 || (qMax(lineDistance(b,a,d), lineDistance(c,a,d)) < 0.12
                      && polygon - magnitude(d-a) < 0.12)) {
        if (magnitude(d - points.last()) > 0.0001) points.append(d);
        return;
    }
    const auto ab = (a+b)*0.5, bc = (b+c)*0.5, cd = (c+d)*0.5;
    const auto abc = (ab+bc)*0.5, bcd = (bc+cd)*0.5, middle = (abc+bcd)*0.5;
    flatten(a,ab,abc,middle,depth+1,points);
    flatten(middle,bcd,cd,d,depth+1,points);
}
constexpr int flatSegments = 96;
constexpr int maxFeatherSegments = 4096;
constexpr std::array<qreal,11> vaneRails = {-1,-0.8,-0.55,-0.3,-0.1,0,0.1,0.3,0.55,0.8,1};
constexpr int featherRails = vaneRails.size()+2;
struct Station {
    std::array<QPointF,featherRails> points;
    std::array<QRgb,featherRails> colors;
};
struct RibbonNode final : QSGNode {
    QVector<Station> stations;
    QVector<qreal> distances;
    QSGGeometryNode *mesh = nullptr;
    QSGImageNode *image = nullptr;
    int vertexCapacity = 0;
};

QRgb featherColor(const QColor &ink, qreal amount, qreal phase, qreal across) {
    // A fine central rachis separates two matte vanes. Paired barbs fan
    // outwards from it; their spacing and phase stay fixed on the feather.
    const qreal shaft=std::exp(-across*across/(0.065*0.065));
    const qreal barbDistance=std::remainder(phase-5.8*std::abs(across),2*std::numbers::pi);
    const qreal barb=std::exp(-barbDistance*barbDistance/(0.30*0.30));
    const qreal barbStrength=qMin<qreal>(1,std::abs(across)/0.20);
    const qreal shade=1+amount*(0.16*shaft-barbStrength*0.06*barb);
    const int alpha = ink.alpha();
    const auto channel = [shade,alpha](int value) {
        const qreal lit = shade<=1 ? value*shade : value+(255-value)*(shade-1);
        return (qBound(0,qRound(lit),255)*alpha+127)/255;
    };
    return qRgba(channel(ink.red()),channel(ink.green()),channel(ink.blue()),alpha);
}

void rasterTriangle(QImage &image, QPointF a, QPointF b, QPointF c, QRgb ca, QRgb cb, QRgb cc) {
    const auto edge = [](const QPointF &p, const QPointF &q, const QPointF &r) {
        return (q.x()-p.x())*(r.y()-p.y())-(q.y()-p.y())*(r.x()-p.x());
    };
    qreal area = edge(a,b,c);
    if (qFuzzyIsNull(area)) return;
    if (area<0) { std::swap(b,c); std::swap(cb,cc); area=-area; }
    const auto inclusive = [](const QPointF &p, const QPointF &q) {
        return q.y()>p.y() || (q.y()==p.y() && q.x()<p.x());
    };
    const bool ab=inclusive(a,b), bc=inclusive(b,c), cEdge=inclusive(c,a);
    const int left=qMax(0,qFloor(qMin(a.x(),qMin(b.x(),c.x()))));
    const int right=qMin(image.width()-1,qCeil(qMax(a.x(),qMax(b.x(),c.x()))));
    const int top=qMax(0,qFloor(qMin(a.y(),qMin(b.y(),c.y()))));
    const int bottom=qMin(image.height()-1,qCeil(qMax(a.y(),qMax(b.y(),c.y()))));
    for (int y=top; y<=bottom; ++y) {
        auto *row=reinterpret_cast<QRgb *>(image.scanLine(y));
        for (int x=left; x<=right; ++x) {
            const QPointF pixel(x+0.5,y+0.5);
            const qreal wa=edge(b,c,pixel), wb=edge(c,a,pixel), wc=edge(a,b,pixel);
            if (wa<0 || (wa==0 && !bc) || wb<0 || (wb==0 && !cEdge) || wc<0 || (wc==0 && !ab)) continue;
            const int alpha=qBound(0,qRound((qAlpha(ca)*wa+qAlpha(cb)*wb+qAlpha(cc)*wc)/area),255);
            const QRgb previous=row[x];
            const auto blend = [=](int va,int vb,int vc,int destination) {
                return qMin(255,qRound((va*wa+vb*wb+vc*wc)/area)+(destination*(255-alpha)+127)/255);
            };
            row[x]=qRgba(blend(qRed(ca),qRed(cb),qRed(cc),qRed(previous)),
                         blend(qGreen(ca),qGreen(cb),qGreen(cc),qGreen(previous)),
                         blend(qBlue(ca),qBlue(cb),qBlue(cc),qBlue(previous)),
                         alpha+(qAlpha(previous)*(255-alpha)+127)/255);
        }
    }
}
}

RibbonStroke::RibbonStroke(QQuickItem *parent) : QQuickItem(parent) {
    setFlag(ItemHasContents, true);
    setAcceptedMouseButtons(Qt::NoButton);
    setAcceptHoverEvents(false);
}
void RibbonStroke::setGuide(const QString &value) {
    if (m_guide == value) return;
    m_guide = value; rebuildGuide(); emit guideChanged(); update();
}
#define RIBBON_REAL_SETTER(Name, member, signal, minimum, maximum) \
void RibbonStroke::Name(qreal value) { \
    value = qBound<qreal>(minimum, value, maximum); \
    if (qFuzzyCompare(member + 1, value + 1)) return; \
    member = value; emit signal(); update(); \
}
RIBBON_REAL_SETTER(setTrimStart, m_trimStart, trimStartChanged, 0, 1)
RIBBON_REAL_SETTER(setTrimEnd, m_trimEnd, trimEndChanged, 0, 1)
RIBBON_REAL_SETTER(setCapStart, m_capStart, capStartChanged, -1, 1)
RIBBON_REAL_SETTER(setCapEnd, m_capEnd, capEndChanged, -1, 1)
RIBBON_REAL_SETTER(setRibbonWidth, m_ribbonWidth, ribbonWidthChanged, 0, 64)
RIBBON_REAL_SETTER(setSettlement, m_settlement, settlementChanged, 0, 1)
RIBBON_REAL_SETTER(setBroadening, m_broadening, broadeningChanged, 0, 1)
RIBBON_REAL_SETTER(setFeatherTexture, m_featherTexture, featherTextureChanged, 0, 1)
RIBBON_REAL_SETTER(setTextureOrigin, m_textureOrigin, textureOriginChanged, 0, 1)
#undef RIBBON_REAL_SETTER
void RibbonStroke::setInk(const QColor &value) {
    if (m_ink == value) return;
    m_ink = value; emit inkChanged(); update();
}
void RibbonStroke::itemChange(ItemChange change, const ItemChangeData &data) {
    QQuickItem::itemChange(change,data);
    if (change == ItemDevicePixelRatioHasChanged) update();
}
void RibbonStroke::rebuildGuide() {
    m_points.clear(); m_lengths.clear();
    static const QRegularExpression token(QStringLiteral("[A-Za-z]|[-+]?(?:\\d*\\.\\d+|\\d+\\.?\\d*)(?:[eE][-+]?\\d+)?"));
    QStringList tokens;
    auto matches = token.globalMatch(m_guide);
    while (matches.hasNext()) tokens.append(matches.next().captured());
    if (tokens.size() < 3 || tokens[0] != QStringLiteral("M")) return;
    QPointF current(tokens[1].toDouble(), tokens[2].toDouble());
    m_points.append(current);
    for (qsizetype i=3; i<tokens.size();) {
        if (tokens[i++] != QStringLiteral("C") || i+6 > tokens.size()) {
            m_points.clear(); return;
        }
        const QPointF b(tokens[i].toDouble(), tokens[i+1].toDouble());
        const QPointF c(tokens[i+2].toDouble(), tokens[i+3].toDouble());
        const QPointF d(tokens[i+4].toDouble(), tokens[i+5].toDouble());
        i += 6;
        flatten(current,b,c,d,0,m_points); current=d;
    }
    m_lengths.reserve(m_points.size());
    qreal length=0;
    for (qsizetype i=0; i<m_points.size(); ++i) {
        if (i) length += magnitude(m_points[i]-m_points[i-1]);
        m_lengths.append(length);
    }
}
QPointF RibbonStroke::pointAt(qreal distance) const {
    if (distance <= 0) return m_points.first();
    if (distance >= m_lengths.last()) return m_points.last();
    const auto next = std::lower_bound(m_lengths.cbegin()+1,m_lengths.cend(),distance);
    const qsizetype index=next-m_lengths.cbegin();
    const qreal fraction=(distance-m_lengths[index-1])/(m_lengths[index]-m_lengths[index-1]);
    return m_points[index-1]+(m_points[index]-m_points[index-1])*fraction;
}
QSGNode *RibbonStroke::updatePaintNode(QSGNode *old, UpdatePaintNodeData *) {
    if (!window() || m_points.size()<2 || m_trimEnd<=m_trimStart || m_ribbonWidth<=0 || m_ink.alpha()==0) {
        delete old; return nullptr;
    }
    const qreal total=m_lengths.last(), begin=m_trimStart*total, end=m_trimEnd*total, length=end-begin;
    const qreal capBegin=(m_capStart<0?m_trimStart:m_capStart)*total;
    const qreal capEnd=(m_capEnd<0?m_trimEnd:m_capEnd)*total;
    const qreal capLength=qMax<qreal>(0,capEnd-capBegin);
    const auto sceneOrigin=mapToScene(QPointF(0,0));
    const qreal sceneScale=qMax(magnitude(mapToScene(QPointF(1,0))-sceneOrigin),
                               magnitude(mapToScene(QPointF(0,1))-sceneOrigin));
    if (sceneScale<0.0001) { delete old; return nullptr; }
    const qreal pixelScale=sceneScale*window()->devicePixelRatio();
    const qreal fringe=1.0/pixelScale;
    const qreal halfWidth=m_ribbonWidth*0.5*(1+0.7*m_broadening);
    const qreal plainTip=halfWidth+(1-m_settlement)*qMax<qreal>(8,m_ribbonWidth*3);
    const qreal tipLength=qMin(capLength*0.48,plainTip*(1-m_featherTexture)+m_ribbonWidth*1.35*m_featherTexture);
    auto *node=old ? static_cast<RibbonNode *>(old) : new RibbonNode;
    const bool textured=m_featherTexture>0;
    const int rails=textured?featherRails:4;
    const qreal textureOrigin=m_textureOrigin*total;
    const qreal pitch=m_ribbonWidth*0.90;
    auto &distances=node->distances;
    distances.clear();
    if (textured) {
        // Fixed stations share the texture's absolute origin. Extending a trim
        // adds stations; it never slides the already woven surface's samples.
        const qreal step=qMax(m_ribbonWidth*0.04,total/(maxFeatherSegments-2));
        distances.append(begin);
        qreal station=textureOrigin+(std::floor((begin-textureOrigin)/step)+1)*step;
        for (; station<end; station+=step) distances.append(station);
        if (distances.size()==1) distances.append((begin+end)*0.5);
        distances.append(end);
    } else {
        for (int i=0; i<=flatSegments; ++i) distances.append(begin+length*i/flatSegments);
    }
    const int segments=distances.size()-1;
    auto &stations=node->stations;
    stations.resize(distances.size());
    const QRgb flatColor=qPremultiply(m_ink.rgba());
    for (int i=0; i<=segments; ++i) {
        const qreal distance=distances[i];
        const auto center=pointAt(distance);
        auto tangent=pointAt(qMin(total,distance+0.3))-pointAt(qMax<qreal>(0,distance-0.3));
        const auto norm=magnitude(tangent);
        tangent=norm>0 ? tangent/norm : QPointF(1,0);
        const QPointF normal(-tangent.y(),tangent.x());
        const qreal tip=qBound<qreal>(0,qMin(distance-capBegin,capEnd-distance)/qMax<qreal>(tipLength,0.001),1);
        const qreal roundedCap=std::sqrt(qMax<qreal>(0,1-(1-tip)*(1-tip)));
        const qreal pointedCap=tip*(1.6-0.6*tip);
        const qreal cap=roundedCap*(1-m_featherTexture)+pointedCap*m_featherTexture;
        const qreal turn=std::sin(distance/qMax<qreal>(total,1)*std::numbers::pi*3);
        // Once deposited past the join, the vane's silhouette belongs to its
        // permanent guide, not the changing visible interval or a local copy.
        const qreal featherPosition=qBound<qreal>(0,(distance-textureOrigin)/qMax<qreal>(total-textureOrigin,0.001),1);
        qreal profile=0.72+0.28*std::sin(featherPosition*std::numbers::pi);
        if (distance<textureOrigin) {
            const qreal flyingPosition=qBound<qreal>(0,(distance-capBegin)/qMax<qreal>(capLength,0.001),1);
            const qreal flyingProfile=0.72+0.28*std::sin(flyingPosition*std::numbers::pi);
            const qreal blend=qBound<qreal>(0,(textureOrigin-distance)/(m_ribbonWidth*4),1);
            profile+=(flyingProfile-profile)*blend*blend*(3-2*blend);
        }
        const qreal width=halfWidth*cap*(1+m_featherTexture*(profile-1))
            *(1-(1-m_settlement)*0.16*turn*turn);
        const qreal phase=(distance-textureOrigin)/pitch*2*std::numbers::pi;
        // Smooth asymmetric vanes carry the silhouette; their edges do not
        // repeat the fine barb pattern or acquire a raised-material highlight.
        const qreal leftEdge=1-m_featherTexture*0.03;
        const qreal rightEdge=1+m_featherTexture*0.03;
        auto &station=stations[i];
        station.points[0]=center-normal*(width*leftEdge+fringe);
        station.points[rails-1]=center+normal*(width*rightEdge+fringe);
        station.colors[0]=station.colors[rails-1]=0;
        for (int rail=1; rail<rails-1; ++rail) {
            const qreal across=textured?vaneRails[rail-1]:-1+2.0*(rail-1)/(rails-3);
            const qreal offset=width*across*(across<0?leftEdge:rightEdge);
            station.points[rail]=center+normal*offset;
            // Using the untapered section also matches local overpass copies:
            // the same physical surface point has the same shade at either cap.
            station.colors[rail]=textured
                ? featherColor(m_ink,m_featherTexture,phase,offset/halfWidth)
                : flatColor;
        }
    }
    if (window()->rendererInterface()->graphicsApi()==QSGRendererInterface::Software) {
        // The software adaptation cannot render arbitrary coloured geometry.
        // Rasterize the same coloured triangles into only the visible strip's
        // bounds, preserving the shaft and barbs without a second feather design.
        qreal left=stations[0].points[0].x(), right=left;
        qreal top=stations[0].points[0].y(), bottom=top;
        for (const auto &station:stations) {
            for (int rail=0; rail<rails; ++rail) {
                left=qMin(left,station.points[rail].x()); right=qMax(right,station.points[rail].x());
                top=qMin(top,station.points[rail].y()); bottom=qMax(bottom,station.points[rail].y());
            }
        }
        const QRectF bounds(QPointF(left,top),QPointF(right,bottom));
        QImage image(QSize(qMax(1,qCeil(bounds.width()*pixelScale)),
                           qMax(1,qCeil(bounds.height()*pixelScale))),QImage::Format_ARGB32_Premultiplied);
        image.fill(Qt::transparent);
        const auto pixelPoint=[&](const QPointF &p) { return (p-bounds.topLeft())*pixelScale; };
        for (int i=0; i<segments; ++i) {
            const auto &a=stations[i], &b=stations[i+1];
            for (int rail=0; rail<rails-1; ++rail) {
                rasterTriangle(image,pixelPoint(a.points[rail]),pixelPoint(b.points[rail]),pixelPoint(a.points[rail+1]),
                               a.colors[rail],b.colors[rail],a.colors[rail+1]);
                rasterTriangle(image,pixelPoint(a.points[rail+1]),pixelPoint(b.points[rail]),pixelPoint(b.points[rail+1]),
                               a.colors[rail+1],b.colors[rail],b.colors[rail+1]);
            }
        }
        if (!node->image) { node->image=window()->createImageNode(); node->appendChildNode(node->image); }
        auto *previous=node->image->texture();
        node->image->setOwnsTexture(false);
        node->image->setTexture(window()->createTextureFromImage(image));
        node->image->setOwnsTexture(true);
        node->image->setFiltering(QSGTexture::Linear);
        node->image->setRect(bounds);
        delete previous;
        return node;
    }
    if (!node->mesh) {
        node->mesh=new QSGGeometryNode;
        auto *mesh=new QSGGeometry(QSGGeometry::defaultAttributes_ColoredPoint2D(),0);
        mesh->setDrawingMode(QSGGeometry::DrawTriangles);
        mesh->setVertexDataPattern(QSGGeometry::DynamicPattern);
        node->mesh->setGeometry(mesh); node->mesh->setFlag(QSGNode::OwnsGeometry);
        node->mesh->setMaterial(new QSGVertexColorMaterial); node->mesh->setFlag(QSGNode::OwnsMaterial);
        node->appendChildNode(node->mesh);
    }
    auto *geometry=node->mesh->geometry();
    const int vertexCount=segments*(rails-1)*6;
    if (vertexCount>node->vertexCapacity) {
        node->vertexCapacity=qMax(vertexCount,node->vertexCapacity*2);
        geometry->allocate(node->vertexCapacity);
    }
    geometry->setVertexCount(vertexCount);
    auto *vertices=geometry->vertexDataAsColoredPoint2D();
    // QSGVertexColorMaterial expects premultiplied vertex colour; transparent
    // outer rails interpolate a one-physical-pixel AA fringe on both sides.
    int vertex=0;
    const auto put=[&](const Station &station,int rail) {
        const auto &point=station.points[rail];
        const QRgb color=station.colors[rail];
        vertices[vertex++].set(float(point.x()),float(point.y()),uchar(qRed(color)),uchar(qGreen(color)),uchar(qBlue(color)),uchar(qAlpha(color)));
    };
    for (int i=0; i<segments; ++i) {
        for (int rail=0; rail<rails-1; ++rail) {
            put(stations[i],rail); put(stations[i+1],rail); put(stations[i],rail+1);
            put(stations[i],rail+1); put(stations[i+1],rail); put(stations[i+1],rail+1);
        }
    }
    geometry->markVertexDataDirty();
    node->mesh->markDirty(QSGNode::DirtyGeometry);
    return node;
}

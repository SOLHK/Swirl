#include "RibbonStroke.h"
#include <QQuickWindow>
#include <QImage>
#include <QPainter>
#include <QPainterPath>
#include <QPolygonF>
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
constexpr int segments = 96;
constexpr int verticesPerSegment = 18;
struct RibbonNode final : QSGGeometryNode {
    RibbonNode() {
        auto *mesh = new QSGGeometry(QSGGeometry::defaultAttributes_ColoredPoint2D(), segments * verticesPerSegment);
        mesh->setDrawingMode(QSGGeometry::DrawTriangles);
        mesh->setVertexDataPattern(QSGGeometry::DynamicPattern);
        setGeometry(mesh); setFlag(OwnsGeometry);
        setMaterial(new QSGVertexColorMaterial); setFlag(OwnsMaterial);
    }
};
struct Station {
    std::array<QPointF,4> points;
};
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
RIBBON_REAL_SETTER(setRibbonWidth, m_ribbonWidth, ribbonWidthChanged, 0, 64)
RIBBON_REAL_SETTER(setSettlement, m_settlement, settlementChanged, 0, 1)
RIBBON_REAL_SETTER(setBroadening, m_broadening, broadeningChanged, 0, 1)
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
    const auto sceneOrigin=mapToScene(QPointF(0,0));
    const qreal sceneScale=qMax(magnitude(mapToScene(QPointF(1,0))-sceneOrigin),
                               magnitude(mapToScene(QPointF(0,1))-sceneOrigin));
    if (sceneScale<0.0001) { delete old; return nullptr; }
    const qreal pixelScale=sceneScale*window()->devicePixelRatio();
    const qreal fringe=1.0/pixelScale;
    const qreal halfWidth=m_ribbonWidth*0.5*(1+0.7*m_broadening);
    const qreal tipLength=qMin(length*0.48,halfWidth+(1-m_settlement)*qMax<qreal>(8,m_ribbonWidth*3));
    std::array<Station,segments+1> stations;
    for (int i=0; i<=segments; ++i) {
        const qreal distance=begin+length*i/segments;
        const auto center=pointAt(distance);
        auto tangent=pointAt(qMin(total,distance+0.3))-pointAt(qMax<qreal>(0,distance-0.3));
        const auto norm=magnitude(tangent);
        tangent=norm>0 ? tangent/norm : QPointF(1,0);
        const QPointF normal(-tangent.y(),tangent.x());
        const qreal tip=qBound<qreal>(0,qMin(distance-begin,end-distance)/qMax<qreal>(tipLength,0.001),1);
        const qreal cap=std::sqrt(qMax<qreal>(0,1-(1-tip)*(1-tip)));
        const qreal turn=std::sin(distance/qMax<qreal>(total,1)*std::numbers::pi*3);
        const qreal width=halfWidth*cap*(1-(1-m_settlement)*0.16*turn*turn);
        stations[i].points={center-normal*(width+fringe),center-normal*width,center+normal*width,center+normal*(width+fringe)};
    }
    if (window()->rendererInterface()->graphicsApi()==QSGRendererInterface::Software) {
        // The software adaptation cannot render arbitrary coloured geometry.
        // Rasterize only this finite strip's bounds, never the whole window.
        QPainterPath strip;
        strip.setFillRule(Qt::WindingFill);
        for (int i=0; i<segments; ++i) {
            strip.addPolygon(QPolygonF{stations[i].points[1],stations[i+1].points[1],
                                       stations[i+1].points[2],stations[i].points[2]});
            strip.closeSubpath();
        }
        const QRectF bounds=strip.boundingRect().adjusted(-fringe,-fringe,fringe,fringe);
        QImage image(QSize(qMax(1,qCeil(bounds.width()*pixelScale)),
                           qMax(1,qCeil(bounds.height()*pixelScale))),QImage::Format_ARGB32_Premultiplied);
        image.fill(Qt::transparent);
        QPainter painter(&image);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.scale(pixelScale,pixelScale);
        painter.translate(-bounds.topLeft());
        painter.fillPath(strip,m_ink);
        painter.end();
        auto *node=old ? static_cast<QSGImageNode *>(old) : window()->createImageNode();
        auto *previous=node->texture();
        node->setOwnsTexture(false);
        node->setTexture(window()->createTextureFromImage(image));
        node->setOwnsTexture(true);
        node->setFiltering(QSGTexture::Linear);
        node->setRect(bounds);
        delete previous;
        return node;
    }
    auto *node=old ? static_cast<RibbonNode *>(old) : new RibbonNode;
    auto *vertices=node->geometry()->vertexDataAsColoredPoint2D();
    // QSGVertexColorMaterial expects premultiplied vertex colour; transparent
    // outer rails interpolate a one-physical-pixel AA fringe on both sides.
    const int alpha=m_ink.alpha();
    const uchar red=uchar((m_ink.red()*alpha+127)/255), green=uchar((m_ink.green()*alpha+127)/255), blue=uchar((m_ink.blue()*alpha+127)/255);
    int vertex=0;
    const auto put=[&](const QPointF &point,bool opaque) {
        vertices[vertex++].set(float(point.x()),float(point.y()),opaque?red:0,opaque?green:0,opaque?blue:0,opaque?uchar(alpha):0);
    };
    for (int i=0; i<segments; ++i) {
        for (int rail=0; rail<3; ++rail) {
            const bool left=rail!=0,right=rail!=2;
            put(stations[i].points[rail],left); put(stations[i+1].points[rail],left); put(stations[i].points[rail+1],right);
            put(stations[i].points[rail+1],right); put(stations[i+1].points[rail],left); put(stations[i+1].points[rail+1],right);
        }
    }
    node->markDirty(QSGNode::DirtyGeometry);
    return node;
}

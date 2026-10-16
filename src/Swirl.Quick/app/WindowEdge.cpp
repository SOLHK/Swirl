#include "WindowEdge.h"
#include <QQuickWindow>
#include <QSGGeometryNode>
#include <QSGMaterialShader>
#include <QSGMaterial>
#include <functional>
#include <cstring>

namespace {
class EdgeMaterial;
class EdgeShader final : public QSGMaterialShader {
public:
 EdgeShader(){setShaderFileName(VertexStage,":/swirl/shaders/window-edge.vert.qsb");setShaderFileName(FragmentStage,":/swirl/shaders/window-edge.frag.qsb");setFlag(UpdatesGraphicsPipelineState,true);}
 bool updateUniformData(RenderState &,QSGMaterial *,QSGMaterial *) override;
 bool updateGraphicsPipelineState(RenderState &,GraphicsPipelineState *p,QSGMaterial *,QSGMaterial *) override {
  p->blendEnable=true;p->srcColor=GraphicsPipelineState::Zero;p->dstColor=GraphicsPipelineState::OneMinusSrcAlpha;
  p->separateBlendFactors=true;p->srcAlpha=GraphicsPipelineState::Zero;p->dstAlpha=GraphicsPipelineState::OneMinusSrcAlpha;
  return true;
 }
};
class EdgeMaterial final : public QSGMaterial {
public:
 float radius=0,dpr=1;
 EdgeMaterial(){setFlag(Blending,true);}
 QSGMaterialType *type() const override {static QSGMaterialType type;return &type;}
 QSGMaterialShader *createShader(QSGRendererInterface::RenderMode) const override{return new EdgeShader;}
 int compare(const QSGMaterial *other) const override {return this==other?0:(std::less<const QSGMaterial *>{}(this,other)?-1:1);}
};
bool EdgeShader::updateUniformData(RenderState &s,QSGMaterial *material,QSGMaterial *){
 auto *m=static_cast<EdgeMaterial *>(material);auto *data=s.uniformData();
 if(s.isMatrixDirty())std::memcpy(data->data(),s.combinedMatrix().constData(),64);
 std::memcpy(data->data()+64,&m->radius,4);std::memcpy(data->data()+68,&m->dpr,4);return true;
}
}
WindowEdge::WindowEdge(QQuickItem *parent):QQuickItem(parent){setFlag(ItemHasContents,true);setAcceptedMouseButtons(Qt::NoButton);}
void WindowEdge::setRadius(qreal value){if(qFuzzyCompare(value,m_radius))return;m_radius=value;emit radiusChanged();update();}
void WindowEdge::geometryChange(const QRectF &now,const QRectF &old){QQuickItem::geometryChange(now,old);update();}
void WindowEdge::itemChange(ItemChange change,const ItemChangeData &data){QQuickItem::itemChange(change,data);if(change==ItemDevicePixelRatioHasChanged)update();}
QSGNode *WindowEdge::updatePaintNode(QSGNode *old,UpdatePaintNodeData *){
 if(!window()||window()->rendererInterface()->graphicsApi()==QSGRendererInterface::Software||m_radius<=0){delete old;return nullptr;}
 auto *root=old?old:new QSGNode;
 if(!root->firstChild())for(int i=0;i<4;++i){
  auto *node=new QSGGeometryNode;auto *geometry=new QSGGeometry(QSGGeometry::defaultAttributes_TexturedPoint2D(),4);geometry->setDrawingMode(QSGGeometry::DrawTriangleStrip);
  node->setGeometry(geometry);node->setFlag(QSGNode::OwnsGeometry);node->setMaterial(new EdgeMaterial);node->setFlag(QSGNode::OwnsMaterial);root->appendChildNode(node);
 }
 const float r=qMin(m_radius,qMin(width(),height())/2),extent=r+1/window()->devicePixelRatio();int index=0;
 for(auto *child=root->firstChild();child;child=child->nextSibling(),++index){
  auto *node=static_cast<QSGGeometryNode *>(child);auto *v=node->geometry()->vertexDataAsTexturedPoint2D();
  const float x=index%2?width()-extent:0,y=index/2?height()-extent:0;
  const float u0=index%2?extent:0,u1=index%2?0:extent,t0=index/2?extent:0,t1=index/2?0:extent;
  v[0].set(x,y,u0,t0);v[1].set(x,y+extent,u0,t1);v[2].set(x+extent,y,u1,t0);v[3].set(x+extent,y+extent,u1,t1);
  auto *m=static_cast<EdgeMaterial *>(node->material());m->radius=r;m->dpr=window()->devicePixelRatio();node->markDirty(QSGNode::DirtyGeometry|QSGNode::DirtyMaterial);
 }
 return root;
}

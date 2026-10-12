#include "HdrChecks.h"
#include <QQuickRenderControl>
#include <QQuickWindow>
#include <QQuickRenderTarget>
#include <QQuickItem>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QDebug>
#include <QtCore/qfloat16.h>
#include <rhi/qrhi.h>
#include <memory>
#include <cstring>
#include <cmath>
int runHdrChecks() {
    int checks=0,failures=0;
    const auto check=[&](bool ok,const char *name){++checks;if(!ok)++failures;qInfo()<<(ok?"PASS":"FAIL")<<name;};
    QQuickRenderControl control;QQuickWindow window(&control);
    window.resize(64,64);window.setColor(Qt::transparent);
    if(!control.initialize()){qCritical()<<"HDR_TEST GPU initialization unavailable";return 3;}
    auto *rhi=control.rhi();
    check(rhi && rhi->isTextureFormatSupported(QRhiTexture::RGBA16F),"GPU supports FP16 render target without requiring an HDR monitor");
    if(!rhi || !rhi->isTextureFormatSupported(QRhiTexture::RGBA16F))return 3;
    std::unique_ptr<QRhiTexture> texture(rhi->newTexture(QRhiTexture::RGBA16F,QSize(64,64),1,QRhiTexture::RenderTarget|QRhiTexture::UsedAsTransferSource));
    std::unique_ptr<QRhiRenderBuffer> depth(rhi->newRenderBuffer(QRhiRenderBuffer::DepthStencil,QSize(64,64),1));
    if(!texture->create() || !depth->create())return 3;
    QRhiTextureRenderTargetDescription desc(QRhiColorAttachment(texture.get()));desc.setDepthStencilBuffer(depth.get());
    std::unique_ptr<QRhiTextureRenderTarget> target(rhi->newTextureRenderTarget(desc));
    std::unique_ptr<QRhiRenderPassDescriptor> pass(target->newCompatibleRenderPassDescriptor());
    target->setRenderPassDescriptor(pass.get());if(!target->create())return 3;
    auto rt=QQuickRenderTarget::fromRhiRenderTarget(target.get());rt.setDevicePixelRatio(1);window.setRenderTarget(rt);
    QQmlEngine engine;QQmlComponent component(&engine);
    component.setData(R"QML(
import QtQuick
Item {
    id:root; width:64; height:64
    property real hdrMode:0
    property real glow:1
    property bool glyph:false
    Item {
        id:input; width:64; height:64
        Rectangle { anchors.fill:parent; color:"#808080" }
        Rectangle { x:24; y:24; width:16; height:16; radius:8; color:"#FF453A" }
        Rectangle { visible:root.glyph; x:29; y:29; width:6; height:6; color:"#703030" }
    }
    ShaderEffect {
        width:64; height:64
        property var source:ShaderEffectSource { sourceItem:input; hideSource:true; textureSize:Qt.size(64,64) }
        property vector2d outputSize:Qt.vector2d(64,64)
        property real hdrActive:root.hdrMode
        property real whiteScale:2.5
        property real peakValue:5
        property real glowEnabled:root.glow
        property vector4d redLamp:Qt.vector4d(32,32,8,1)
        property vector4d yellowLamp:Qt.vector4d(-100,-100,8,1)
        property vector4d greenLamp:Qt.vector4d(-100,-100,8,1)
        fragmentShader:"qrc:/swirl/shaders/hdr-ui.frag.qsb"
    }
}
)QML",QUrl("qrc:/hdr-proof.qml"));
    std::unique_ptr<QObject> root(component.create());
    if(!root){qCritical()<<component.errors();return 3;}
    auto *item=qobject_cast<QQuickItem *>(root.get());item->setParentItem(window.contentItem());
    const auto render=[&] {
        QRhiReadbackResult read;bool complete=false;read.completed=[&]{complete=true;};
        control.polishItems();control.beginFrame();control.sync();control.render();
        auto *updates=rhi->nextResourceUpdateBatch();updates->readBackTexture(QRhiReadbackDescription(texture.get()),&read);
        control.commandBuffer()->resourceUpdate(updates);control.endFrame();rhi->finish();
        return complete?read.data:QByteArray();
    };
    const auto pixel=[](const QByteArray &data,int x,int y) {
        qfloat16 channels[4];const auto offset=(y*64+x)*8;
        if(data.size()<offset+8)return -1.0f;
        std::memcpy(channels,data.constData()+offset,8);
        return qMax(float(channels[0]),qMax(float(channels[1]),float(channels[2])));
    };
    auto sdr=render();
    check(pixel(sdr,30,30)<=1.01f && pixel(sdr,30,30)>0.5f,"SDR fallback retains display colors within 0 to 1");
    root->setProperty("hdrMode",1);auto hdr=render();
    const float emitted=pixel(hdr,30,30);
    qInfo()<<"HDR_FP16_READBACK peak="<<emitted<<"SDR white=2.5 (200 nits)";
    check(emitted>2.5f && emitted<=5.01f,"same production shader emits real above-SDR-white values into FP16 GPU texture");
    qfloat16 channels[4];std::memcpy(channels,hdr.constData()+(30*64+30)*8,8);
    const float luminance=float(channels[0])*0.2126f+float(channels[1])*0.7152f+float(channels[2])*0.0722f;
    qInfo()<<"HDR_FP16_READBACK luminance_nits="<<luminance*80;
    check(luminance>2.5f && luminance<=5.01f,"emissive highlight luminance exceeds 200 nit SDR white without exceeding display peak");
    check(std::abs(pixel(hdr,4,4)-0.53965f)<0.03f,"ordinary UI sRGB is linearized and SDR white corrected without emission");
    root->setProperty("glow",0);auto disabled=render();
    check(pixel(disabled,30,30)<=2.51f,"disabled HDR headroom clamps traffic light back to normal SDR white");
    root->setProperty("glow",1);root->setProperty("glyph",true);auto glyph=render();
    check(pixel(glyph,32,32)<0.5f,"dark hover symbols remain legible and do not become emissive");
    root.reset();control.invalidate();window.setRenderTarget({});
    qInfo()<<"HDR_CHECKS"<<checks<<"checks"<<failures<<"failures";
    return failures?2:0;
}

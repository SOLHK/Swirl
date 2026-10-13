#include "HdrOutput.h"
#include <QGuiApplication>
#include <QVariantMap>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QTimer>
#include <QDebug>
#include <rhi/qrhi.h>
#include <cmath>
#include <QtMath>
#include <QQuickItem>
#include <QFile>
#include <QTextStream>
#include <QtCore/qfloat16.h>
#include <cstring>
#include <functional>
void HdrOutput::attach(QQuickWindow *window) {
    if(!window || m_window)return;
    m_window=window;
    const auto request=[this] { m_probe=true; if(m_window)m_window->update(); };
    connect(window,&QQuickWindow::screenChanged,this,request);
    auto *poll=new QTimer(this);poll->setInterval(2000);
    connect(poll,&QTimer::timeout,this,request);poll->start();
    // RHI resources belong to the render thread. Transfer only sampled values
    // to the GUI thread; never retain a swapchain pointer across frames.
    connect(window,&QQuickWindow::beforeSynchronizing,this,[this,window] {
        if(!m_probe.exchange(false))return;
        auto *sc=static_cast<QRhiSwapChain *>(window->rendererInterface()->getResource(window,QSGRendererInterface::RhiSwapchainResource));
        if(!sc && window->rendererInterface()->graphicsApi()!=QSGRendererInterface::Software) { m_probe=true; return; }
        const bool active=sc && sc->format()==QRhiSwapChain::HDRExtendedSrgbLinear;
        bool glow=false;qreal white=1,peak=1;
        if(active) {
            const auto info=sc->hdrInfo();
            white=info.luminanceBehavior==QRhiSwapChainHdrInfo::SceneReferred ? qBound(1.0,qreal(info.sdrWhiteLevel)/80.0,12.5) : 1.0;
            const qreal maximum=info.limitsType==QRhiSwapChainHdrInfo::LuminanceInNits ? info.limits.luminanceInNits.maxLuminance/80.0 : info.limits.colorComponentValue.maxColorComponentValue;
            peak=std::isfinite(maximum) && maximum>0 ? qMax(white,qMin(maximum,white*2.0)) : white;
            glow=sc->isFormatSupported(QRhiSwapChain::HDRExtendedSrgbLinear) && peak>white*1.05;
        }
        QMetaObject::invokeMethod(this,[this,active,glow,white,peak] {
            if(m_reported && m_active==active && m_glow==glow && qAbs(m_white-white)<0.001 && qAbs(m_peak-peak)<0.001)return;
            m_reported=true;m_active=active;m_glow=glow;m_white=white;m_peak=peak;
            qInfo()<<"HDR_OUTPUT"<<(active?"FP16 scRGB":"SDR fallback")<<"emissive="<<glow<<"SDR white scale="<<white<<"peak="<<peak;
            qApp->setProperty("swirlHdr",QVariantMap{{"fp16Active",active},{"glow",glow},{"whiteScale",white},{"peak",peak}});
            emit changed();
        },Qt::QueuedConnection);
    },Qt::DirectConnection);
    connect(window,&QQuickWindow::afterRendering,this,[this,window] {
        if(!m_capture.exchange(false))return;
        auto *sc=static_cast<QRhiSwapChain *>(window->rendererInterface()->getResource(window,QSGRendererInterface::RhiSwapchainResource));
        auto *rhi=window->rhi();
        if(!sc || !rhi || sc->format()!=QRhiSwapChain::HDRExtendedSrgbLinear) {
            QMetaObject::invokeMethod(this,[this]{qCritical()<<"HDR_DISPLAY_TEST actual FP16 swapchain is unavailable";emit displayTestFinished(false);},Qt::QueuedConnection);return;
        }
        m_readback.completed=[this] {
            const auto data=m_readback.data;const auto size=m_readback.pixelSize;
            const auto format=m_readback.format;
            QMetaObject::invokeMethod(this,[this,data,size,format] {
                bool success=format==QRhiTexture::RGBA16F && data.size()==size.width()*size.height()*8;
                QFile file(m_captureFile);success=success && file.open(QIODevice::WriteOnly|QIODevice::Text);
                QTextStream stream(&file);stream<<"button,peak_luminance_nits,sdr_white_nits,red_linear,green_linear,blue_linear,alpha\n";
                const QStringList names={"close","minimize","maximize"};
                for(int index=0;index<m_lampBounds.size() && success;++index) {
                    const auto bounds=m_lampBounds[index].intersected(QRect(QPoint(),size));
                    float best=-1;float rgb[4]={};
                    for(int y=bounds.top();y<=bounds.bottom();++y)for(int x=bounds.left();x<=bounds.right();++x) {
                        qfloat16 pixel[4];std::memcpy(pixel,data.constData()+(y*size.width()+x)*8,8);
                        const float luminance=float(pixel[0])*0.2126f+float(pixel[1])*0.7152f+float(pixel[2])*0.0722f;
                        if(luminance>best){best=luminance;for(int c=0;c<4;++c)rgb[c]=float(pixel[c]);}
                    }
                    stream<<names[index]<<','<<best*80<<','<<m_captureWhite*80<<','<<rgb[0]<<','<<rgb[1]<<','<<rgb[2]<<','<<rgb[3]<<'\n';
                    qInfo()<<"HDR_DISPLAY_READBACK"<<names[index]<<"luminance_nits="<<best*80<<"SDR_white_nits="<<m_captureWhite*80<<"FP16";
                    success=best>m_captureWhite*1.05;
                }
                file.close();qInfo()<<"HDR_DISPLAY_TEST"<<(success?"PASS":"FAIL");emit displayTestFinished(success);
            },Qt::QueuedConnection);
        };
        QRhiReadbackDescription description;description.setRect(m_captureRect);
        auto *updates=rhi->nextResourceUpdateBatch();updates->readBackTexture(description,&m_readback);
        sc->currentFrameCommandBuffer()->resourceUpdate(updates);
    },Qt::DirectConnection);
}
void HdrOutput::startDisplayTest(const QString &outputFile) {
    if(!m_window || !m_active || !m_glow){qCritical()<<"HDR_DISPLAY_TEST requires actual HDR output with luminance headroom";emit displayTestFinished(false);return;}
    std::function<QQuickItem *(QQuickItem *,const QString &)> find;
    find=[&](QQuickItem *item,const QString &name)->QQuickItem * {if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *match=find(child,name))return match;return nullptr;};
    const auto dpr=m_window->devicePixelRatio();m_lampBounds.clear();QRect all;
    for(const auto &name : {"windowCloseButton","windowMinimizeButton","windowMaximizeButton"}) {
        auto *lamp=find(m_window->contentItem(),QString::fromLatin1(name));
        if(!lamp){emit displayTestFinished(false);return;}
        const auto position=lamp->mapToScene(QPointF());
        const QRect bounds(qFloor(position.x()*dpr),qFloor(position.y()*dpr),qCeil(lamp->width()*dpr),qCeil(lamp->height()*dpr));
        m_lampBounds.append(bounds);all=all.united(bounds);
    }
    m_captureRect=all;m_captureFile=outputFile;m_captureWhite=m_white;
    for(auto &bounds:m_lampBounds)bounds.translate(-all.topLeft());
    m_capture=true;m_window->update();
}

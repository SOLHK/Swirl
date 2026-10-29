#pragma once
#include "FontSourceIdentity.h"
#include "app/FontDisplayContext.h"
#include "app/FontManager.h"
#include "app/VariableFontPreview.h"
#include <QDateTime>
#include <QJsonDocument>
#include <QDir>
#include <QTimer>
#include <QQuickWindow>
#include <QScreen>
#include <memory>
#include <functional>

// Opt-in observation of the SAME application window while Windows changes its
// actual scale. No simulated DPR, font changes or system-setting writes here.
inline void startFontDpiWatch(QQuickWindow *window,FontManager *manager,
                              const QString &source,const QString &output) {
    if(!window||source.isEmpty()||output.isEmpty())return;
    const auto expected=SwirlFontSource::faces(source);if(expected.isEmpty())return;
    QDir().mkpath(output);
    auto *metrics=qobject_cast<FontDisplayContext *>(qmlAttachedPropertiesObject<FontDisplayContext>(window,true));
    auto *timer=new QTimer(window);timer->setSingleShot(true);timer->setInterval(250);
    auto observations=std::make_shared<QJsonArray>();
    QObject::connect(timer,&QTimer::timeout,window,[window,manager,expected,output,metrics,observations]{
        const auto image=window->grabWindow();QJsonArray previews;
        std::function<void(QQuickItem *)> collect=[&](QQuickItem *item){
            if(auto *preview=qobject_cast<VariableFontPreview *>(item)){
                QJsonObject axes;for(const auto tag:preview->font().variableAxisTags())axes[QString::fromLatin1(tag.toString())]=preview->font().variableAxisValue(tag);
                const QRectF bounds(preview->mapToScene(QPointF()),preview->size());
                previews.append(QJsonObject{{"name",preview->objectName()},{"visible",preview->isVisible()},{"insideWindow",QRectF(0,0,window->width(),window->height()).contains(bounds)},{"rasterDpr",preview->rasterDevicePixelRatio()},{"pixelWidth",preview->rasterPixelSize().width()},{"pixelHeight",preview->rasterPixelSize().height()},{"logicalWidth",preview->width()},{"axes",axes}});
            }
            for(auto *child:item->childItems())collect(child);
        };collect(window->contentItem());
        const auto name=QString("same-window-%1-dpr-%2.png").arg(observations->size()).arg(window->devicePixelRatio());
        auto *loader=window->findChild<QObject *>("pageLoader");auto *page=loader?qvariant_cast<QObject *>(loader->property("item")):nullptr;
        observations->append(QJsonObject{{"utc",QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)},{"windowObject",QString::number(reinterpret_cast<quintptr>(window))},{"pageObject",QString::number(reinterpret_cast<quintptr>(page))},{"nativeWindow",QString::number(window->winId())},{"logicalWidth",window->width()},{"logicalHeight",window->height()},{"dpr",window->devicePixelRatio()},{"displayContextDpr",metrics->devicePixelRatio()},{"logicalDpi",metrics->logicalDpi()},{"refreshHz",window->screen()->refreshRate()},{"automatic",manager->automatic()},{"family",manager->currentFamily()},{"source",SwirlFontSource::identity(QRawFont::fromFont(QFont(manager->currentFamily())),expected,false)},{"previews",previews},{"capture",name},{"captured",!image.isNull()&&image.save(output+"/"+name)}});
        QFile file(output+"/same-window-dpi.json");if(file.open(QIODevice::WriteOnly))file.write(QJsonDocument(QJsonObject{{"observations",*observations},{"limits","Actual live QWindow and retained preview raster observations. Human clarity/flicker and physical display scanout remain separate."}}).toJson());
    });
    QObject::connect(metrics,&FontDisplayContext::metricsChanged,timer,[timer]{timer->start();});
    QObject::connect(window,&QWindow::screenChanged,timer,[timer]{timer->start();});
    QTimer::singleShot(1000,window,[window]{QMetaObject::invokeMethod(window,"previewScrollBottom");});
    timer->start(1500);
}

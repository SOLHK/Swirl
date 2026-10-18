#pragma once
#include <QTextLayout>
#include <QTextOption>
#include <QGlyphRun>
#include <QSignalSpy>
#include <QPainterPath>
#include <cmath>

void FontTests::optionalRasterQualityMatrix()
{
    const auto source=qEnvironmentVariable("SWIRL_TEST_TTC"),output=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
    if(source.isEmpty()||output.isEmpty())QSKIP("An authorized local font and local evidence directory are required");
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY2(manager.importFont(QUrl::fromLocalFile(source)),qPrintable(manager.error()));
    const auto defaults=manager.previewValues();QList<QVariantMap> coordinates{defaults};
    for(const auto &entry:manager.previewAxes()){const auto axis=entry.toMap();for(const auto &bound:{"minimum","maximum"}){auto values=defaults;values[axis["tag"].toString()]=axis[bound];coordinates.append(values);}}
    for(double w:{100.,900.})for(double d:{80.,120.})for(double h:{1.,1000.})coordinates.append({{"wght",w},{"wdth",d},{"HGHT",h}});
    coordinates.append({{"wght",300.25},{"wdth",90.125},{"HGHT",250.75}});coordinates.append({{"wght",700.75},{"wdth",110.375},{"HGHT",750.25}});coordinates.append({{"wght",500.5},{"wdth",100.5},{"HGHT",500.5}});
    const bool full=qEnvironmentVariableIsSet("SWIRL_QUALITY_FULL");
    const bool focused=qEnvironmentVariableIsSet("SWIRL_QUALITY_FOCUSED");
    const auto selected=qEnvironmentVariable("SWIRL_QUALITY_CASES").split(',',Qt::SkipEmptyParts);
    const auto families=full&&!qEnvironmentVariableIsSet("SWIRL_QUALITY_SC_ONLY")?manager.importedFamilies():QStringList{manager.previewFamily()};
    const QString specimen=QStringLiteral("苹方字体显示效果测试 圆国口日田目中永 The quick brown fox jumps over the lazy dog. 0123456789 @ # ¥ % & jgy () [] / \\");
    QQuickWindow window;window.setColor(Qt::white);window.resize(1060,640);
    QQuickItem placement(window.contentItem());
    VariableFontPreview item(&placement);item.setPosition(QPointF(16,16));item.setWidth(1024);item.setText(specimen);item.setColor(Qt::black);
    window.show();window.hide();window.show();QVERIFY(QTest::qWaitForWindowExposed(&window));
    const qreal dpr=window.devicePixelRatio();QDir().mkpath(output);QJsonArray cases;int failures=0,savedFailures=0,index=0;
    for(const auto &family:families){
      const auto points=full?(family==manager.previewFamily()?QList<int>{9,10,11,12,13,14,16,24,32,48,72}:QList<int>{9,16,72}):QList<int>{9,16,72};
      for(int pt:points)for(int axisCase=0;axisCase<(full||focused?coordinates.size():1);++axisCase)for(double phase:full?QList<double>{0}:QList<double>{0,.5}){
        const int caseId=index++;if(!selected.isEmpty()&&!selected.contains(QString::number(caseId)))continue;
        const auto name=QString("case-%1").arg(caseId,4,10,QChar('0'));
        QFont font(family);font.setPointSizeF(pt);font.setStyleName(QString());font.setHintingPreference(QFont::PreferFullHinting);font.setStyleStrategy(QFont::PreferAntialias);
        for(auto it=coordinates[axisCase].cbegin();it!=coordinates[axisCase].cend();++it)font.setVariableAxis(QFont::Tag::fromString(it.key().toUtf8()).value(),it.value().toDouble());
        QTextLayout layout(specimen,font);QTextOption option;option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);layout.beginLayout();qreal y=0;
        while(true){auto line=layout.createLine();if(!line.isValid())break;line.setLineWidth(item.width());line.setPosition(QPointF(0,y));y+=line.height();}layout.endLayout();
        item.setY(16+phase/dpr);item.setFont(font);item.setHeight(std::ceil(y));item.ensurePolished();window.resize(1060,640);window.update();QTest::qWait(1);
        constexpr int margin=128;QImage padded(QSize(std::ceil((item.width()+2*margin)*dpr),std::ceil((item.height()+2*margin)*dpr)),QImage::Format_ARGB32_Premultiplied);padded.setDevicePixelRatio(dpr);padded.fill(Qt::transparent);
        {QPainter painter(&padded);painter.setPen(Qt::black);painter.setRenderHint(QPainter::TextAntialiasing,true);painter.translate(margin,margin);layout.draw(&painter,QPointF());}
        int outside=0;const QRect allowed(qRound(margin*dpr),qRound(margin*dpr),std::ceil(item.width()*dpr),std::ceil(item.height()*dpr));
        for(int py=0;py<padded.height();++py){const auto *row=reinterpret_cast<const QRgb *>(padded.constScanLine(py));for(int px=0;px<padded.width();++px)if(qAlpha(row[px])&&!allowed.contains(px,py))++outside;}
        int missing=0,nonfinite=0;QStringList used;
        for(const auto &run:layout.glyphRuns()){
          const auto raw=run.rawFont();if(!used.contains(raw.familyName()))used.append(raw.familyName());
          for(const auto glyph:run.glyphIndexes()){if(!glyph)++missing;const auto path=raw.pathForGlyph(glyph);for(int e=0;e<path.elementCount();++e){const auto v=path.elementAt(e);if(!std::isfinite(v.x)||!std::isfinite(v.y))++nonfinite;}}
        }
        int changed=0,maxDelta=0,fringes=0;quint64 totalDelta=0;double snapError=0;
        QImage actual;QJsonArray tiles;
        const int chunk=qMax(1,qFloor((window.height()-32)*dpr));
        const int tileCount=qMax(1,qCeil((item.height()*dpr+32)/chunk));
        for(int tile=0;tile<tileCount;++tile){
          placement.setY(-tile*chunk/dpr);window.update();QTest::qWait(20);
          const auto capture=window.grabWindow();QVERIFY(!capture.isNull());if(!tile)actual=capture;
          const auto origin=item.mapToScene(QPointF());const QPoint offset(qRound(origin.x()*dpr),qRound(origin.y()*dpr));
          snapError=qMax(snapError,qMax(qAbs(origin.x()*dpr-offset.x()),qAbs(origin.y()*dpr-offset.y())));
          for(int py=0;py<capture.height();++py)for(int px=0;px<capture.width();++px){
            const auto a=capture.pixel(px,py);const int rx=px-offset.x()+qRound(margin*dpr),ry=py-offset.y()+qRound(margin*dpr);
            const int gray=rx>=0&&ry>=0&&rx<padded.width()&&ry<padded.height()?255-qAlpha(padded.pixel(rx,ry)):255;
            const int delta=qMax(std::abs(qRed(a)-gray),qMax(std::abs(qGreen(a)-gray),std::abs(qBlue(a)-gray)));
            if(delta>2)++changed;maxDelta=qMax(maxDelta,delta);totalDelta+=delta;if(qRed(a)!=qGreen(a)||qRed(a)!=qBlue(a))++fringes;
          }
          const auto file=name+QString("-tile-%1.png").arg(tile);QVERIFY(capture.save(output+"/"+file));
          tiles.append(QJsonObject{{"file",file},{"originPhysicalX",offset.x()},{"originPhysicalY",offset.y()},{"pixelWidth",capture.width()},{"pixelHeight",capture.height()}});
        }
        const bool viewportComplete=actual.size()==QSize(qRound(window.width()*dpr),qRound(window.height()*dpr))&&tileCount*chunk>=item.height()*dpr+32;
        const auto reference=padded;
        const bool fallback=used.size()!=1||used.first()!=family;
        const bool bad=!viewportComplete||snapError>.0001||missing||nonfinite||fallback||changed||fringes;if(bad)++failures;
        const bool save=(!axisCase&&family==manager.previewFamily())||(family==manager.previewFamily()&&pt==72&&axisCase>=7)||(bad&&savedFailures++<12);
        if(save){actual.save(output+"/"+name+"-actual.png");reference.save(output+"/"+name+"-direct-reference.png");padded.save(output+"/"+name+"-padded-ink.png");}
        cases.append(QJsonObject{{"case",name},{"family",family},{"points",pt},{"axes",QJsonObject::fromVariantMap(coordinates[axisCase])},{"physicalYPhase",phase},{"renderX",item.mapToScene(QPointF()).x()},{"renderY",item.mapToScene(QPointF()).y()},{"layoutY",item.y()},{"channelTolerance",2},{"tiles",tiles},{"completeViewportCoverage",viewportComplete},{"overhangPreserved",outside>0&&changed==0},{"physicalSnapError",snapError},{"width",item.width()},{"height",item.height()},{"layoutHeight",y},{"directRasterChangedPixels",changed},{"maxChannelDelta",maxDelta},{"totalChannelDelta",double(totalDelta)},{"outOfBoundsInkPixels",outside},{"missingGlyphs",missing},{"nonfiniteOutlinePoints",nonfinite},{"fallback",fallback},{"usedFamilies",QJsonArray::fromStringList(used)},{"colourFringePixels",fringes},{"smooth",item.smooth()},{"saved",save},{"pass",!bad}});
      }
    }
    placement.setY(0);
    // Parent scrolling and scale animations must keep their transform and layout behavior.
    const auto originalGeometry=QRectF(item.position(),item.size());const auto originalFont=item.font();
    placement.setY(.5/dpr);window.update();QTest::qWait(25);
    const auto moved=item.mapToScene(QPointF());
    const bool ancestorAligned=qAbs(moved.y()*dpr-qRound(moved.y()*dpr))<.0001;
    placement.setScale(.9);window.update();QTest::qWait(25);
    const auto scaledOrigin=item.mapToScene(QPointF());const auto scaledUnit=item.mapToScene(QPointF(1,0))-scaledOrigin;
    const bool scalePreserved=qAbs(scaledUnit.x()-.9)<.0001&&item.font()==originalFont&&QRectF(item.position(),item.size())==originalGeometry;
    window.grabWindow().save(output+"/scale-animation-sample.png");
    placement.setScale(1);window.update();
    // A fixed sleep can observe geometry before the next afterAnimating pass.
    // Await the renderer's observable alignment; this is outside timing tests.
    QElapsedTimer restoreWait;restoreWait.start();
    const bool restoredAligned=QTest::qWaitFor([&]{const auto p=item.mapToScene(QPointF());return qAbs(p.y()*dpr-qRound(p.y()*dpr))<.0001;},250);
    const auto restoreSettleMs=restoreWait.elapsed();
    QTest::qWait(50);QSignalSpy idleFrames(&window,&QQuickWindow::frameSwapped);QTest::qWait(120);
    const bool idleStable=idleFrames.count()<=1;
    if(!ancestorAligned||!scalePreserved||!restoredAligned||!idleStable)++failures;
    QFile report(output+"/raster-quality.json");QVERIFY(report.open(QIODevice::WriteOnly));report.write(QJsonDocument(QJsonObject{{"dpr",dpr},{"qtRefreshRate",window.screen()->refreshRate()},{"qpa",qEnvironmentVariable("QT_QPA_PLATFORM")},{"scaleOverride",qEnvironmentVariable("QT_SCALE_FACTOR")},{"caseCount",cases.size()},{"ancestorTranslationAligned",ancestorAligned},{"scaleTransformPreserved",scalePreserved},{"alignedAfterScaleRestore",restoredAligned},{"restoreSettleMs",restoreSettleMs},{"idleFrameCount120ms",idleFrames.count()},{"idleStable",idleStable},{"failures",failures},{"cases",cases},{"method","Each target point size and real axes rendered anew. Compare live QQuickWindow output with direct same-engine target-size origin-zero raster by integer pixel indexing (no image translation/filtering); record the effective snapped screen origin separately. This avoids native glyph subpixel-rounding differences from drawing the reference at a fractional logical origin. Fixed 1060x640 logical pixel window; integer-pixel viewport tiles cover the entire target-size specimen. Padded native ink reference includes overhang; overhang alone is diagnostic, only missing or changed output fails. Glyph-outline/fallback checks remain independent. No image resizing, sharpening or postprocessing. This detects pipeline regressions, not every intrinsic outline defect or physical-panel perception."}}).toJson());report.close();
    QCOMPARE(failures,0);
}

#pragma once
#include <QTextLayout>
#include <QTextOption>
#include <QGlyphRun>
#include <QSignalSpy>
#include <QDeadlineTimer>
#include <QScopeGuard>
#include <QPainterPath>
#include <cmath>
#include "FontRasterReferenceChecks.h"

void FontTests::optionalRasterQualityMatrix()
{
    const auto source=qEnvironmentVariable("SWIRL_TEST_TTC"),output=qEnvironmentVariable("SWIRL_FONT_EVIDENCE");
    if(source.isEmpty()||output.isEmpty())QSKIP("An authorized local font and local evidence directory are required");
    const bool canonicalReference=!qEnvironmentVariableIsSet("SWIRL_QUALITY_LEGACY_REFERENCE");
    const auto mutationCase=qEnvironmentVariable("SWIRL_QUALITY_MUTATION_CASE");
    QTemporaryDir directory;QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,directory.path());QSettings().clear();
    FontManager manager(nullptr,directory.filePath("fonts"));QVERIFY2(manager.importFont(QUrl::fromLocalFile(source)),qPrintable(manager.error()));
    const auto defaults=manager.previewValues();QList<QVariantMap> coordinates{defaults};
    for(const auto &entry:manager.previewAxes()){const auto axis=entry.toMap();for(const auto &bound:{"minimum","maximum"}){auto values=defaults;values[axis["tag"].toString()]=axis[bound];coordinates.append(values);}}
    for(double w:{100.,900.})for(double d:{80.,120.})for(double h:{1.,1000.})coordinates.append({{"wght",w},{"wdth",d},{"HGHT",h}});
    coordinates.append({{"wght",300.25},{"wdth",90.125},{"HGHT",250.75}});coordinates.append({{"wght",700.75},{"wdth",110.375},{"HGHT",750.25}});coordinates.append({{"wght",500.5},{"wdth",100.5},{"HGHT",500.5}});
    const bool full=qEnvironmentVariableIsSet("SWIRL_QUALITY_FULL");
    const bool focused=qEnvironmentVariableIsSet("SWIRL_QUALITY_FOCUSED");
    const bool includeHalfPhases=!full||qEnvironmentVariableIsSet("SWIRL_QUALITY_HALF_PHASES");
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
      for(int pt:points)for(int axisCase=0;axisCase<(full||focused?coordinates.size():1);++axisCase)for(double phase:includeHalfPhases?QList<double>{0,.5}:QList<double>{0}){
        const int caseId=index++;if(!selected.isEmpty()&&!selected.contains(QString::number(caseId)))continue;
        const auto name=QString("case-%1").arg(caseId,4,10,QChar('0'));
        QFont font(family);font.setPointSizeF(pt);font.setStyleName(QString());font.setHintingPreference(QFont::PreferFullHinting);font.setStyleStrategy(QFont::PreferAntialias);
        for(auto it=coordinates[axisCase].cbegin();it!=coordinates[axisCase].cend();++it)font.setVariableAxis(QFont::Tag::fromString(it.key().toUtf8()).value(),it.value().toDouble());
        QTextLayout layout(specimen,font);QTextOption option;option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);layout.beginLayout();qreal y=0;
        while(true){auto line=layout.createLine();if(!line.isValid())break;line.setLineWidth(item.width());line.setPosition(QPointF(0,y));y+=line.height();}layout.endLayout();
        item.setY(16+phase/dpr);item.setFont(font);item.setHeight(std::ceil(y));item.ensurePolished();window.resize(1060,640);window.update();QTest::qWait(1);
        QTextLayout independentLayout(specimen,font);independentLayout.setTextOption(option);independentLayout.beginLayout();qreal independentHeight=0;while(true){auto line=independentLayout.createLine();if(!line.isValid())break;line.setLineWidth(item.width());line.setPosition(QPointF(0,independentHeight));independentHeight+=line.height();}independentLayout.endLayout();if(canonicalReference)QVERIFY(qAbs(independentHeight-y)<.001);
        int shapingMismatches=0;const auto primaryRuns=layout.glyphRuns(),referenceRuns=independentLayout.glyphRuns();if(primaryRuns.size()!=referenceRuns.size())++shapingMismatches;for(qsizetype ri=0;ri<qMin(primaryRuns.size(),referenceRuns.size());++ri){const auto a=primaryRuns[ri].glyphIndexes();const auto b=referenceRuns[ri].glyphIndexes();const auto ap=primaryRuns[ri].positions();const auto bp=referenceRuns[ri].positions();if(primaryRuns[ri].rawFont().familyName()!=referenceRuns[ri].rawFont().familyName()||a!=b||ap.size()!=bp.size())++shapingMismatches;else for(qsizetype gi=0;gi<ap.size();++gi)if(qAbs(ap[gi].x()-bp[gi].x())>1e-6||qAbs(ap[gi].y()-bp[gi].y())>1e-6)++shapingMismatches;}
        QPoint referenceOriginPhysical;QSize referencePixelSize;
        if(canonicalReference){QRectF ink=independentLayout.boundingRect();for(const auto &run:referenceRuns){const auto raw=run.rawFont();const auto glyphs=run.glyphIndexes();const auto positions=run.positions();ink=ink.united(run.boundingRect());for(qsizetype gi=0;gi<qMin(glyphs.size(),positions.size());++gi)ink=ink.united(raw.pathForGlyph(glyphs[gi]).boundingRect().translated(positions[gi]));}const int left=qFloor(qMin(0.,ink.left())*dpr)-2,top=qFloor(qMin(0.,ink.top())*dpr)-2;const int right=qCeil(qMax(item.width(),ink.right())*dpr)+2,bottom=qCeil(qMax(independentHeight,ink.bottom())*dpr)+2;referenceOriginPhysical=QPoint(-left,-top);referencePixelSize=QSize(qMax(1,right-left),qMax(1,bottom-top));}
        else{constexpr qreal margin=128.;referenceOriginPhysical=QPoint(qRound(margin*dpr),qRound(margin*dpr));referencePixelSize=QSize(std::ceil((item.width()+2*margin)*dpr),std::ceil((item.height()+2*margin)*dpr));}
        QImage padded(referencePixelSize,QImage::Format_ARGB32_Premultiplied);padded.setDevicePixelRatio(dpr);padded.fill(Qt::transparent);
        {QPainter painter(&padded);painter.setPen(Qt::black);painter.setRenderHint(QPainter::TextAntialiasing,true);painter.translate(referenceOriginPhysical.x()/dpr,referenceOriginPhysical.y()/dpr);(canonicalReference?independentLayout:layout).draw(&painter,QPointF());}
        int outside=0;const QRect allowed(referenceOriginPhysical,QSize(std::ceil(item.width()*dpr),std::ceil(item.height()*dpr)));
        for(int py=0;py<padded.height();++py){const auto *row=reinterpret_cast<const QRgb *>(padded.constScanLine(py));for(int px=0;px<padded.width();++px)if(qAlpha(row[px])&&!allowed.contains(px,py))++outside;}
        int missing=0,nonfinite=0;QStringList used;
        for(const auto &run:layout.glyphRuns()){
          const auto raw=run.rawFont();if(!used.contains(raw.familyName()))used.append(raw.familyName());
          for(const auto glyph:run.glyphIndexes()){if(!glyph)++missing;const auto path=raw.pathForGlyph(glyph);for(int e=0;e<path.elementCount();++e){const auto v=path.elementAt(e);if(!std::isfinite(v.x)||!std::isfinite(v.y))++nonfinite;}}
        }
        const auto glyphReference=canonicalReference?SwirlFontReference::alphaReference(independentLayout,dpr):SwirlFontReference::AlphaReference{};
        int changed=0,maxDelta=0,fringes=0;quint64 totalDelta=0;double snapError=0;
        QImage actual;QPoint firstTileOffset;QJsonArray tiles;
        const int chunk=qMax(1,qFloor((window.height()-32)*dpr));
        const int tileCount=qMax(1,qCeil((item.height()*dpr+32)/chunk));
        for(int tile=0;tile<tileCount;++tile){
          placement.setY(-tile*chunk/dpr);window.update();QTest::qWait(20);
          const auto capture=window.grabWindow();QVERIFY(!capture.isNull());if(!tile)actual=capture;
          const auto origin=item.mapToScene(QPointF());const QPoint offset(qRound(origin.x()*dpr),qRound(origin.y()*dpr));if(!tile)firstTileOffset=offset;
          snapError=qMax(snapError,qMax(qAbs(origin.x()*dpr-offset.x()),qAbs(origin.y()*dpr-offset.y())));
          for(int py=0;py<capture.height();++py)for(int px=0;px<capture.width();++px){
            const auto a=capture.pixel(px,py);const int rx=px-offset.x()+referenceOriginPhysical.x(),ry=py-offset.y()+referenceOriginPhysical.y();
            const int gray=rx>=0&&ry>=0&&rx<padded.width()&&ry<padded.height()?255-qAlpha(padded.pixel(rx,ry)):255;
            const int delta=SwirlFontReference::maxChannelDeltaFromGray(a,gray);
            if(delta>2)++changed;maxDelta=qMax(maxDelta,delta);totalDelta+=delta;if(qRed(a)!=qGreen(a)||qRed(a)!=qBlue(a))++fringes;
          }
          const auto file=name+QString("-tile-%1.png").arg(tile);QVERIFY(capture.save(output+"/"+file));
          tiles.append(QJsonObject{{"file",file},{"originPhysicalX",offset.x()},{"originPhysicalY",offset.y()},{"pixelWidth",capture.width()},{"pixelHeight",capture.height()}});
        }
        QJsonObject mutationSensitivity;bool mutationProbeValid=true;
        if(canonicalReference&&!mutationCase.isEmpty()&&mutationCase.toInt()==caseId){
          quint32 firstGlyph=0;QPointF firstGlyphPosition;QPainterPath firstGlyphPath;
          for(const auto &run:independentLayout.glyphRuns()){const auto glyphs=run.glyphIndexes();const auto positions=run.positions();for(qsizetype gi=0;gi<qMin(glyphs.size(),positions.size());++gi){auto path=run.rawFont().pathForGlyph(glyphs[gi]);if(!path.isEmpty()){firstGlyph=glyphs[gi];firstGlyphPosition=positions[gi];firstGlyphPath=std::move(path);break;}}if(!firstGlyphPath.isEmpty())break;}
          const QRectF glyphBounds=firstGlyphPath.boundingRect().translated(firstGlyphPosition);
          const int refLeft=referenceOriginPhysical.x()+qFloor(glyphBounds.left()*dpr),refTop=referenceOriginPhysical.y()+qFloor(glyphBounds.top()*dpr);
          const int refRight=referenceOriginPhysical.x()+qCeil(glyphBounds.right()*dpr),refBottom=referenceOriginPhysical.y()+qCeil(glyphBounds.bottom()*dpr);
          const QRect captureGlyph(refLeft-referenceOriginPhysical.x()+firstTileOffset.x(),refTop-referenceOriginPhysical.y()+firstTileOffset.y(),refRight-refLeft,refBottom-refTop);
          auto compareMutation=[&](QImage mutated,const QString &label){const auto stats=SwirlFontReference::compareWindowToReference(mutated,padded,firstTileOffset,referenceOriginPhysical);mutationSensitivity.insert(label,QJsonObject{{"pixelsOverTolerance2",stats.pixelsOverTolerance},{"maxChannelDelta",stats.maxChannelDelta}});return stats.pixelsOverTolerance>0;};
          if(!firstGlyphPath.isEmpty()&&captureGlyph.intersects(actual.rect())){
            QImage missingGlyph=actual.copy();{QPainter painter(&missingGlyph);painter.fillRect(captureGlyph,Qt::white);}
            const bool missingDetected=compareMutation(missingGlyph,"missingGlyph");
            QImage clipped=actual.copy();int clipX=-1;
            for(int x=refLeft;x<refRight&&clipX<0;++x)for(int y=refTop;y<refBottom;++y)if(x>=0&&y>=0&&x<padded.width()&&y<padded.height()&&qAlpha(padded.pixel(x,y))>2){clipX=x;break;}
            bool clippedDetected=false;if(clipX>=0){QPainter painter(&clipped);painter.fillRect(QRect(clipX-referenceOriginPhysical.x()+firstTileOffset.x(),refTop-referenceOriginPhysical.y()+firstTileOffset.y(),1,refBottom-refTop),Qt::white);painter.end();clippedDetected=compareMutation(clipped,"clippedEdge");}else mutationSensitivity.insert("clippedEdge",QJsonObject{{"pixelsOverTolerance2",0},{"maxChannelDelta",0}});
            QImage antialias=actual.copy();int edgeX=-1,edgeY=-1;
            for(int y=refTop;y<refBottom&&edgeY<0;++y)for(int x=refLeft;x<refRight;++x)if(x>=0&&y>=0&&x<padded.width()&&y<padded.height()){const int alpha=qAlpha(padded.pixel(x,y));if(alpha>16&&alpha<239){edgeX=x;edgeY=y;break;}}
            bool antialiasDetected=false;if(edgeX>=0){const int ax=edgeX-referenceOriginPhysical.x()+firstTileOffset.x(),ay=edgeY-referenceOriginPhysical.y()+firstTileOffset.y();if(actual.rect().contains(ax,ay)){antialias.setPixel(ax,ay,qRgb(255,255,255));antialiasDetected=compareMutation(antialias,"antialiasEdge");}}else mutationSensitivity.insert("antialiasEdge",QJsonObject{{"pixelsOverTolerance2",0},{"maxChannelDelta",0}});
            mutationProbeValid=missingDetected&&clippedDetected&&antialiasDetected;
          }else{mutationProbeValid=false;mutationSensitivity.insert("targetGlyphAvailable",false);}
          mutationSensitivity.insert("targetCase",name);mutationSensitivity.insert("targetGlyph",int(firstGlyph));mutationSensitivity.insert("passed",mutationProbeValid);
        }
        const bool viewportComplete=actual.size()==QSize(qRound(window.width()*dpr),qRound(window.height()*dpr))&&tileCount*chunk>=item.height()*dpr+32;
        const auto reference=padded;
        const bool fallback=used.size()!=1||used.first()!=family;
        const bool glyphOracleValid=!canonicalReference||(glyphReference.invalidMaps==0&&glyphReference.clippedMaps==0&&glyphReference.nonEmptyOutlines>0&&glyphReference.nonEmptyOutlinesWithoutMask==0&&glyphReference.intermediateCoveragePixels>0);
        const bool bad=!viewportComplete||snapError>.0001||missing||nonfinite||fallback||changed||fringes||(canonicalReference&&shapingMismatches)||!glyphOracleValid||(canonicalReference&&!mutationCase.isEmpty()&&mutationCase.toInt()==caseId&&!mutationProbeValid);if(bad)++failures;
        const bool save=(!axisCase&&family==manager.previewFamily())||(family==manager.previewFamily()&&pt==72&&axisCase>=7)||(bad&&savedFailures++<12);
        if(save){actual.save(output+"/"+name+"-actual.png");reference.save(output+"/"+name+"-direct-reference.png");padded.save(output+"/"+name+"-padded-ink.png");}
        QJsonObject alternateReference;
        if(canonicalReference){const auto file=name+"-rawfont-alpha-reference.png";const bool saved=glyphReference.image.save(output+"/"+file);alternateReference={{"file",file},{"saved",saved},{"originPhysical",QJsonArray{glyphReference.origin.x(),glyphReference.origin.y()}},{"glyphCount",glyphReference.glyphCount},{"nonEmptyOutlines",glyphReference.nonEmptyOutlines},{"nonEmptyOutlinesWithoutMask",glyphReference.nonEmptyOutlinesWithoutMask},{"emptyMaps",glyphReference.emptyMaps},{"invalidMaps",glyphReference.invalidMaps},{"clippedMaps",glyphReference.clippedMaps},{"boundsSizeMismatches",glyphReference.boundsSizeMismatches},{"nonzeroCoveragePixels",glyphReference.nonzeroCoveragePixels},{"intermediateCoveragePixels",glyphReference.intermediateCoveragePixels},{"firstGlyphMetrics",glyphReference.firstGlyphMetrics}};}
        cases.append(QJsonObject{{"mutationSensitivity",mutationSensitivity},{"independentAlphaReference",alternateReference},{"shapingLayoutMismatches",shapingMismatches},{"glyphOracleValid",glyphOracleValid},{"referenceOriginPhysical",QJsonArray{referenceOriginPhysical.x(),referenceOriginPhysical.y()}},{"case",name},{"family",family},{"points",pt},{"axes",QJsonObject::fromVariantMap(coordinates[axisCase])},{"physicalYPhase",phase},{"renderX",item.mapToScene(QPointF()).x()},{"renderY",item.mapToScene(QPointF()).y()},{"layoutY",item.y()},{"channelTolerance",2},{"tiles",tiles},{"completeViewportCoverage",viewportComplete},{"overhangPreserved",outside>0&&changed==0},{"physicalSnapError",snapError},{"width",item.width()},{"height",item.height()},{"layoutHeight",y},{"directRasterChangedPixels",changed},{"maxChannelDelta",maxDelta},{"totalChannelDelta",double(totalDelta)},{"outOfBoundsInkPixels",outside},{"missingGlyphs",missing},{"nonfiniteOutlinePoints",nonfinite},{"fallback",fallback},{"usedFamilies",QJsonArray::fromStringList(used)},{"colourFringePixels",fringes},{"smooth",item.smooth()},{"saved",save},{"pass",!bad}});
      }
    }
    placement.setY(0);
    // Parent scrolling and scale animations must keep their transform and layout behavior.
    const auto originalGeometry=QRectF(item.position(),item.size());const auto originalFont=item.font();
    const auto originalTransformOrigin=item.transformOrigin();
    struct GeometrySample { QPointF origin,base,unitX,unitY; qreal snapError=0,baseError=0; bool layoutAndFontPreserved=false; };
    const auto sampleGeometry=[&]{GeometrySample v;v.origin=item.mapToScene(QPointF());v.base=placement.mapToScene(item.position());v.unitX=item.mapToScene(QPointF(1,0))-v.origin;v.unitY=item.mapToScene(QPointF(0,1))-v.origin;v.snapError=qAbs(v.origin.y()*dpr-qRound(v.origin.y()*dpr));v.baseError=qMax(qAbs(v.origin.x()-v.base.x()),qAbs(v.origin.y()-v.base.y()))*dpr;v.layoutAndFontPreserved=item.font()==originalFont&&QRectF(item.position(),item.size())==originalGeometry;return v;};
    struct GeometryObservation { GeometrySample first,sampled;bool firstSeen=false,withinDeadline=false;qint64 firstNs=-1,sampledNs=0,waitNs=0;int sampleDelayMs=0; };
    const auto observeFirstPass=[&](auto mutate,int delayMs){GeometryObservation o;o.sampleDelayMs=delayMs;QElapsedTimer elapsed;const auto connection=QObject::connect(&window,&QQuickWindow::afterAnimating,&window,[&]{if(o.firstSeen)return;o.firstNs=elapsed.nsecsElapsed();o.first=sampleGeometry();o.firstSeen=true;},Qt::DirectConnection);const auto disconnect=qScopeGuard([&]{QObject::disconnect(connection);});elapsed.start();const QDeadlineTimer deadline(250,Qt::PreciseTimer);mutate();window.update();if(delayMs)QTest::qWait(delayMs);o.sampled=sampleGeometry();o.sampledNs=elapsed.nsecsElapsed();const bool seen=QTest::qWaitFor([&]{return o.firstSeen;},deadline);o.withinDeadline=seen&&o.firstNs<=250000000;o.waitNs=elapsed.nsecsElapsed();return o;};
    const auto translation=observeFirstPass([&]{placement.setY(.5/dpr);},25);const bool legacyAncestorAligned=translation.sampled.snapError<.0001;const bool ancestorAligned=translation.withinDeadline&&translation.first.snapError<.0001;
    const auto scale=observeFirstPass([&]{placement.setScale(.9);},25);const bool legacyScalePreserved=qAbs(scale.sampled.unitX.x()-.9)<.0001&&scale.sampled.layoutAndFontPreserved;const bool scalePreserved=scale.withinDeadline&&qAbs(scale.first.unitX.x()-.9)<.0001&&scale.first.layoutAndFontPreserved;const bool scaleCompensationCleared=scale.withinDeadline&&scale.first.baseError<.0001;
    window.grabWindow().save(output+"/scale-animation-sample.png");
    const auto restore=observeFirstPass([&]{placement.setScale(1);},0);const bool restoredAligned=restore.withinDeadline&&restore.first.snapError<.0001;const auto restoreSettleMs=restore.waitNs/1000000;
    const qreal rotationRadians=qDegreesToRadians(17.0);
    const auto rotation=observeFirstPass([&]{item.setTransformOrigin(QQuickItem::TopLeft);item.setRotation(17);},25);
    const bool rotationTransformPreserved=rotation.withinDeadline&&qAbs(rotation.first.unitX.x()-qCos(rotationRadians))<.0001&&qAbs(rotation.first.unitX.y()-qSin(rotationRadians))<.0001&&qAbs(rotation.first.unitY.x()+qSin(rotationRadians))<.0001&&qAbs(rotation.first.unitY.y()-qCos(rotationRadians))<.0001&&rotation.first.layoutAndFontPreserved;
    const bool rotationCompensationCleared=rotation.withinDeadline&&rotation.first.baseError<.0001;
    window.grabWindow().save(output+"/rotation-animation-sample.png");
    const auto rotationRestore=observeFirstPass([&]{item.setRotation(0);item.setTransformOrigin(originalTransformOrigin);},0);
    const bool rotationRestoredAligned=rotationRestore.withinDeadline&&rotationRestore.first.snapError<.0001&&rotationRestore.first.layoutAndFontPreserved;
    const auto observationJson=[](const GeometryObservation &o){const auto n=[&](double x){return o.firstSeen?QJsonValue(x):QJsonValue(QJsonValue::Null);};return QJsonObject{{"firstAfterAnimatingSeen",o.firstSeen},{"firstPassWithin250ms",o.withinDeadline},{"firstAfterAnimatingMs",n(o.firstNs/1000000.0)},{"waitElapsedMs",o.waitNs/1000000.0},{"firstPhysicalSnapError",n(o.first.snapError)},{"firstUncompensatedOriginErrorPhysical",n(o.first.baseError)},{"firstSceneX",n(o.first.origin.x())},{"firstSceneY",n(o.first.origin.y())},{"sampleDelayRequestedMs",o.sampleDelayMs},{"sampleActualElapsedMs",o.sampledNs/1000000.0},{"samplePhysicalSnapError",o.sampled.snapError},{"sampleUncompensatedOriginErrorPhysical",o.sampled.baseError}};};
    QTest::qWait(50);QSignalSpy idleFrames(&window,&QQuickWindow::frameSwapped);QTest::qWait(120);
    const bool idleStable=idleFrames.count()<=1;
    if(!ancestorAligned||!scalePreserved||!scaleCompensationCleared||!restoredAligned||!rotationTransformPreserved||!rotationCompensationCleared||!rotationRestoredAligned||!idleStable)++failures;
    QFile report(output+"/raster-quality.json");QVERIFY(report.open(QIODevice::WriteOnly));report.write(QJsonDocument(QJsonObject{{"schemaVersion",2},{"dpr",dpr},{"qtRefreshRate",window.screen()->refreshRate()},{"qpa",qEnvironmentVariable("QT_QPA_PLATFORM")},{"scaleOverride",qEnvironmentVariable("QT_SCALE_FACTOR")},{"canonicalReference",canonicalReference},{"referenceMethod",canonicalReference?QStringLiteral("Independent QTextLayout drawn at the minimum per-case physical origin derived from its RawFont outline extents plus a two-device-pixel coverage margin; full comparisons use integer pixel indexing and tolerance 2."):QStringLiteral("Legacy 128-logical-pixel origin retained for baseline evidence.")},{"caseCount",cases.size()},{"ancestorTranslationAligned",ancestorAligned},{"scaleTransformPreserved",scalePreserved},{"scaleCompensationCleared",scaleCompensationCleared},{"alignedAfterScaleRestore",restoredAligned},{"rotationTransformPreserved",rotationTransformPreserved},{"rotationCompensationCleared",rotationCompensationCleared},{"rotationRestoredAligned",rotationRestoredAligned},{"restoreSettleMs",restoreSettleMs},{"legacyAncestorTranslationAlignedAt25Ms",legacyAncestorAligned},{"legacyScaleTransformPreservedAt25Ms",legacyScalePreserved},{"restoreImmediateAligned",restore.sampled.snapError<.0001},{"geometryObservations",QJsonObject{{"translation",observationJson(translation)},{"scale",observationJson(scale)},{"restore",observationJson(restore)},{"rotation",observationJson(rotation)},{"rotationRestore",observationJson(rotationRestore)}}},{"idleFrameCount120ms",idleFrames.count()},{"idleStable",idleStable},{"failures",failures},{"cases",cases},{"method","Each target point size and real axes rendered anew. The independent reference uses a second QTextLayout instance. Per-case canvas origin and extent are derived from that instance's RawFont glyph paths and retain all glyph ink. Additional QRawFont path/coverage checks verify glyph presence, finite outlines, antialias coverage, and that all masks fit. The comparator uses no image resizing, sharpening, value editing, or fractional image shift."}}).toJson());report.close();
    QCOMPARE(failures,0);
}

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
    const auto families=full&&!qEnvironmentVariableIsSet("SWIRL_QUALITY_SC_ONLY")?manager.importedFamilies():QStringList{manager.previewFamily()};
    const QString specimen=QStringLiteral("苹方字体显示效果测试 圆国口日田目中永 The quick brown fox jumps over the lazy dog. 0123456789 @ # ¥ % & jgy () [] / \\");
    QQuickWindow window;window.setColor(Qt::white);window.resize(1060,900);
    QQuickItem placement(window.contentItem());
    VariableFontPreview item(&placement);item.setPosition(QPointF(16,16));item.setWidth(1024);item.setText(specimen);item.setColor(Qt::black);
    window.show();window.hide();window.show();QVERIFY(QTest::qWaitForWindowExposed(&window));
    const qreal dpr=window.devicePixelRatio();QDir().mkpath(output);QJsonArray cases;int failures=0,savedFailures=0,index=0;
    for(const auto &family:families){
      const auto points=full?(family==manager.previewFamily()?QList<int>{9,10,11,12,13,14,16,24,32,48,72}:QList<int>{9,16,72}):QList<int>{9,16,72};
      for(int pt:points)for(int axisCase=0;axisCase<(full||focused?coordinates.size():1);++axisCase)for(double phase:full?QList<double>{0}:QList<double>{0,.5}){
        QFont font(family);font.setPointSizeF(pt);font.setStyleName(QString());font.setHintingPreference(QFont::PreferFullHinting);font.setStyleStrategy(QFont::PreferAntialias);
        for(auto it=coordinates[axisCase].cbegin();it!=coordinates[axisCase].cend();++it)font.setVariableAxis(QFont::Tag::fromString(it.key().toUtf8()).value(),it.value().toDouble());
        QTextLayout layout(specimen,font);QTextOption option;option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);layout.beginLayout();qreal y=0;
        while(true){auto line=layout.createLine();if(!line.isValid())break;line.setLineWidth(item.width());line.setPosition(QPointF(0,y));y+=line.height();}layout.endLayout();
        item.setY(16+phase/dpr);item.setFont(font);item.setHeight(std::ceil(y));item.ensurePolished();window.resize(1060,qMax(200,int(std::ceil(y))+40));window.update();QTest::qWait(1);
        const auto actual=window.grabWindow();QVERIFY(!actual.isNull());
        const auto sceneOrigin=item.mapToScene(QPointF());
        const QPointF pixelOrigin(qRound(sceneOrigin.x()*dpr)/dpr,qRound(sceneOrigin.y()*dpr)/dpr);
        const double snapError=qMax(qAbs(sceneOrigin.x()-pixelOrigin.x()),qAbs(sceneOrigin.y()-pixelOrigin.y()))*dpr;
        QImage reference(actual.size(),QImage::Format_ARGB32_Premultiplied);reference.setDevicePixelRatio(dpr);reference.fill(Qt::white);
        {QPainter painter(&reference);painter.setPen(Qt::black);painter.setRenderHint(QPainter::TextAntialiasing,true);layout.draw(&painter,QPointF());}
        constexpr int margin=128;QImage padded(QSize(std::ceil((item.width()+2*margin)*dpr),std::ceil((item.height()+2*margin)*dpr)),QImage::Format_ARGB32_Premultiplied);padded.setDevicePixelRatio(dpr);padded.fill(Qt::transparent);
        {QPainter painter(&padded);painter.setPen(Qt::black);painter.setRenderHint(QPainter::TextAntialiasing,true);layout.draw(&painter,QPointF(margin,margin));}
        int outside=0;const QRect allowed(qRound(margin*dpr),qRound(margin*dpr),std::ceil(item.width()*dpr),std::ceil(item.height()*dpr));
        for(int py=0;py<padded.height();++py){const auto *row=reinterpret_cast<const QRgb *>(padded.constScanLine(py));for(int px=0;px<padded.width();++px)if(qAlpha(row[px])&&!allowed.contains(px,py))++outside;}
        int missing=0,nonfinite=0;QStringList used;
        for(const auto &run:layout.glyphRuns()){
          const auto raw=run.rawFont();if(!used.contains(raw.familyName()))used.append(raw.familyName());
          for(const auto glyph:run.glyphIndexes()){if(!glyph)++missing;const auto path=raw.pathForGlyph(glyph);for(int e=0;e<path.elementCount();++e){const auto v=path.elementAt(e);if(!std::isfinite(v.x)||!std::isfinite(v.y))++nonfinite;}}
        }
        int changed=0,maxDelta=0,fringes=0;quint64 totalDelta=0;
        for(int py=0;py<actual.height();++py)for(int px=0;px<actual.width();++px){const auto a=actual.pixel(px,py);const int rx=px-qRound(pixelOrigin.x()*dpr),ry=py-qRound(pixelOrigin.y()*dpr);const auto b=rx>=0&&ry>=0&&rx<reference.width()&&ry<reference.height()?reference.pixel(rx,ry):qRgb(255,255,255);const int delta=qMax(std::abs(qRed(a)-qRed(b)),qMax(std::abs(qGreen(a)-qGreen(b)),std::abs(qBlue(a)-qBlue(b))));if(delta>2)++changed;maxDelta=qMax(maxDelta,delta);totalDelta+=delta;if(qRed(a)!=qGreen(a)||qRed(a)!=qBlue(a))++fringes;}
        const bool fallback=used.size()!=1||used.first()!=family;
        const bool bad=snapError>.0001||outside||missing||nonfinite||fallback||changed||fringes;if(bad)++failures;
        const bool save=(!axisCase&&family==manager.previewFamily())||(family==manager.previewFamily()&&pt==72&&axisCase>=7)||(bad&&savedFailures++<12);
        const auto name=QString("case-%1").arg(index++,4,10,QChar('0'));
        if(save){actual.save(output+"/"+name+"-actual.png");reference.save(output+"/"+name+"-direct-reference.png");padded.save(output+"/"+name+"-padded-ink.png");}
        cases.append(QJsonObject{{"case",name},{"family",family},{"points",pt},{"axes",QJsonObject::fromVariantMap(coordinates[axisCase])},{"physicalYPhase",phase},{"renderX",item.mapToScene(QPointF()).x()},{"renderY",item.mapToScene(QPointF()).y()},{"layoutY",item.y()},{"channelTolerance",2},{"physicalSnapError",snapError},{"width",item.width()},{"height",item.height()},{"layoutHeight",y},{"directRasterChangedPixels",changed},{"maxChannelDelta",maxDelta},{"totalChannelDelta",double(totalDelta)},{"outOfBoundsInkPixels",outside},{"missingGlyphs",missing},{"nonfiniteOutlinePoints",nonfinite},{"fallback",fallback},{"usedFamilies",QJsonArray::fromStringList(used)},{"colourFringePixels",fringes},{"smooth",item.smooth()},{"saved",save},{"pass",!bad}});
      }
    }
    // Parent scrolling and scale animations must keep their transform and layout behavior.
    const auto originalGeometry=QRectF(item.position(),item.size());const auto originalFont=item.font();
    placement.setY(.5/dpr);window.update();QTest::qWait(25);
    const auto moved=item.mapToScene(QPointF());
    const bool ancestorAligned=qAbs(moved.y()*dpr-qRound(moved.y()*dpr))<.0001;
    placement.setScale(.9);window.update();QTest::qWait(25);
    const auto scaledOrigin=item.mapToScene(QPointF());const auto scaledUnit=item.mapToScene(QPointF(1,0))-scaledOrigin;
    const bool scalePreserved=qAbs(scaledUnit.x()-.9)<.0001&&item.font()==originalFont&&QRectF(item.position(),item.size())==originalGeometry;
    window.grabWindow().save(output+"/scale-animation-sample.png");
    placement.setScale(1);window.update();QTest::qWait(25);
    const auto restored=item.mapToScene(QPointF());const bool restoredAligned=qAbs(restored.y()*dpr-qRound(restored.y()*dpr))<.0001;
    QTest::qWait(50);QSignalSpy idleFrames(&window,&QQuickWindow::frameSwapped);QTest::qWait(120);
    const bool idleStable=idleFrames.count()<=1;
    if(!ancestorAligned||!scalePreserved||!restoredAligned||!idleStable)++failures;
    QFile report(output+"/raster-quality.json");QVERIFY(report.open(QIODevice::WriteOnly));report.write(QJsonDocument(QJsonObject{{"dpr",dpr},{"qtRefreshRate",window.screen()->refreshRate()},{"qpa",qEnvironmentVariable("QT_QPA_PLATFORM")},{"scaleOverride",qEnvironmentVariable("QT_SCALE_FACTOR")},{"caseCount",cases.size()},{"ancestorTranslationAligned",ancestorAligned},{"scaleTransformPreserved",scalePreserved},{"alignedAfterScaleRestore",restoredAligned},{"idleFrameCount120ms",idleFrames.count()},{"idleStable",idleStable},{"failures",failures},{"cases",cases},{"method","Each target point size and real axes rendered anew. Compare live QQuickWindow output with direct same-engine target-size origin-zero raster by integer pixel indexing (no image translation/filtering); record the effective snapped screen origin separately. This avoids native glyph subpixel-rounding differences from drawing the reference at a fractional logical origin. Also check plus padded ink and glyph-outline/fallback checks. No image resizing, sharpening or postprocessing. This detects pipeline regressions, not every intrinsic outline defect or physical-panel perception."}}).toJson());report.close();
    QCOMPARE(failures,0);
}

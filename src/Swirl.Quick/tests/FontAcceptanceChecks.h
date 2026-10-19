#pragma once
#include "FontSourceIdentity.h"
#include "FontUiChecks.h"
#include <QFontMetricsF>
#include <QTextDocument>

// Local-only physical-face and live-layout evidence. Private glyphs and source
// table fingerprints are written exclusively to the requested evidence folder.
inline int runFontAcceptanceChecks(QQuickWindow *window,FontManager *manager,
                                  const QString &source,const QString &output,bool currentPageOnly=false) {
    if(!window||source.isEmpty()||output.isEmpty()||!manager->automatic())return 3;
    const auto expected=SwirlFontSource::faces(source);if(expected.isEmpty())return 3;
    QDir().mkpath(output);QJsonArray cases;int failures=0;
    auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);const auto value=expression.evaluate();if(expression.hasError()){++failures;qWarning()<<expression.error();}return value;};
    const auto routes=QJsonDocument::fromJson(eval(currentPageOnly?"JSON.stringify([AppState.currentPage])":"JSON.stringify(AppState.allPageIds)").toString().toUtf8()).array();
    auto ready=[&]{return eval("pageLoader.item && !pageLoader.moving && !pageLoader.pendingGrab && pageLoader.activeLoader.routeId===pageLoader.routeKey").toBool();};
    for(const auto &theme:QStringList{"Light","Dark"})for(const auto &size:QList<QSize>{{1100,900},{900,680}}){
        eval("Theme.mode='"+theme+"'");window->resize(size);window->showNormal();window->raise();window->requestActivate();
        for(const auto &entry:routes){
            const auto route=entry.toString();eval("AppState.navigate('"+route+"')");
            const bool settled=QTest::qWaitFor(ready,8000);QTest::qWait(40);
            int texts=0,badFaces=0,badWeights=0,narrowed=0,missing=0,elided=0,wrapped=0;QJsonArray items;
            std::function<void(QQuickItem *)> inspect=[&](QQuickItem *item){
                if(!item->isVisible())return;
                if(item->inherits("QQuickText")||item->inherits("QQuickTextInput")||item->inherits("QQuickTextEdit")){
                    auto text=item->property("text").toString();const auto font=item->property("font").value<QFont>();
                    if(!text.isEmpty()&&font.family()==manager->currentFamily()){
                        if(Qt::mightBeRichText(text)){QTextDocument document;document.setHtml(text);text=document.toPlainText();}
                        text=text.left(8192);++texts;
                        const auto role=item->property("textRole").toString();const auto requested=manager->resolvedAxesForFont(font,window->screen()->logicalDotsPerInchY(),window->devicePixelRatio(),role);
                        const bool weightOk=!requested.contains("wght")||qAbs(font.variableAxisValue(QFont::Tag("wght"))-requested.value("wght").toDouble())<.001;
                        if(!weightOk)++badWeights;
                        if(font.isVariableAxisSet(QFont::Tag("wdth"))&&font.variableAxisValue(QFont::Tag("wdth"))<100)++narrowed;
                        const bool truncated=item->property("truncated").toBool();if(truncated)++elided;
                        if(item->property("lineCount").toInt()>1)++wrapped;
                        QTextLayout layout(text,font);layout.beginLayout();auto line=layout.createLine();if(line.isValid())line.setLineWidth(1e6);layout.endLayout();
                        QJsonArray runs;
                        const auto requestedRaw=QRawFont::fromFont(font);
                        for(const auto &run:layout.glyphRuns(0,-1,QTextLayout::RetrieveAll)){
                            auto identity=SwirlFontSource::identity(run.rawFont(),expected,false);
                            if(!identity["matchesSource"].toBool()){
                                ++badFaces;QJsonArray characters;bool expectedFallback=true;
                                for(auto index:run.stringIndexes())if(index>=0&&index<text.size()){
                                    const auto points=text.mid(index,2).toUcs4();if(points.isEmpty())continue;
                                    const auto point=points.first();const bool supported=requestedRaw.supportsCharacter(point);
                                    if(supported)expectedFallback=false;
                                    characters.append(QJsonObject{{"codepoint",QString("U+%1").arg(uint(point),4,16,QLatin1Char('0'))},{"sourceSupports",supported}});
                                }
                                identity["fallbackCharacters"]=characters;identity["expectedMissingCharacterFallback"]=expectedFallback&&!characters.isEmpty();
                            }
                            for(auto glyph:run.glyphIndexes())if(!glyph)++missing;
                            runs.append(identity);
                        }
                        items.append(QJsonObject{{"name",item->objectName()},{"role",role},{"textSha256",QString::fromLatin1(QCryptographicHash::hash(text.toUtf8(),QCryptographicHash::Sha256).toHex())},{"weight",int(font.weight())},{"actualWght",font.variableAxisValue(QFont::Tag("wght"))},{"actualWdth",font.variableAxisValue(QFont::Tag("wdth"))},{"pixelSize",font.pixelSize()},{"width",item->width()},{"height",item->height()},{"elided",truncated},{"runs",runs}});
                    }
                }
                for(auto *child:item->childItems())inspect(child);
            };
            inspect(window->contentItem());
            const auto stem=QString("%1-%2-%3x%4").arg(route,theme).arg(size.width()).arg(size.height());
            const auto image=window->grabWindow();const bool captured=!image.isNull()&&image.save(output+"/"+stem+".png");
            // Preserve fallback observations separately. A missing private-font
            // symbol is not automatically an application layout failure.
            const bool pass=settled&&captured&&texts>0&&badWeights==0;
            if(!pass)++failures;
            cases.append(QJsonObject{{"route",route},{"theme",theme},{"width",size.width()},{"height",size.height()},{"settled",settled},{"captured",captured},{"texts",texts},{"foreignSourceRuns",badFaces},{"wrongWeights",badWeights},{"missingGlyphs",missing},{"narrowedLabels",narrowed},{"elidedLabels",elided},{"wrappedTexts",wrapped},{"items",items},{"pass",pass}});
        }
    }
    QFile report(output+"/font-acceptance.json");if(!report.open(QIODevice::WriteOnly))return 3;
    report.write(QJsonDocument(QJsonObject{{"cases",cases},{"failures",failures},{"sourceFaceCount",expected.size()},{"dpr",window->devicePixelRatio()},{"qtRefreshRate",window->screen()->refreshRate()},{"limits","Raw Qt renders and actual QTextLayout font-table evidence. Human clarity, unexpected clipping, physical scanout and other unvisited dialog states require separate review."}}).toJson());
    return failures?2:0;
}

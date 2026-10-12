import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string tab:"Installed"
    property var chosen:null
    property var modules:[]
    readonly property var filtered:modules.filter(function(m){return (m.name+" "+m.author).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"扩展目录"; tone:"accent" }
            Text { text:"尚未加载第三方脚本或扩展。"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:"本地导入"; onClicked:importDialog.open() }
            SwirlButton { enabled:false; text:"添加远程"; primary:true; onClicked:importDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Installed","Marketplace","Updates"]
                SwirlButton { enabled:false; text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlSearchField { id:search; implicitWidth:Theme.dp(250); placeholderText:"搜索扩展" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Installed"
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.filtered
                    selectedId:page.chosen?page.chosen.id:""
                    columns:[{key:"name",label:"模块名称",w:220},{key:"version",label:"版本",w:102},
                             {key:"source",label:"来源",w:172},{key:"update",label:"更新",w:153},
                             {key:"state",label:"状态",w:110}]
                    onRowSelected:function(r){page.chosen=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Installed"
                    anchors.fill:parent; anchors.margins:Theme.dp(19); spacing:Theme.dp(16)
                    Text { text:page.tab==="Marketplace"?"扩展市场（界面预览）":"模块更新"; color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold }
                    Repeater {
                        model:[]
                        SwirlGlassPanel {
                            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(66)
                            RowLayout {
                                anchors.fill:parent; anchors.margins:Theme.dp(12)
                                SwirlIcon { name:"grid"; color:Theme.accent; size:Theme.dp(22) }
                                Text { text:modelData; color:Theme.text; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                                SwirlButton { enabled:false; text:page.tab==="Marketplace"?"View":"Details"; onClicked:AppState.notice("扩展列表") }
                            }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(305); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(14)
                    Text { text:"扩展详情"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    Text { text:page.chosen?page.chosen.name:"选择模块"; color:Theme.accent; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                    Repeater {
                        model:[["VERSION",page.chosen?page.chosen.version:"—"],["AUTHOR",page.chosen?page.chosen.author:"—"],
                               ["SOURCE",page.chosen?page.chosen.source:"—"],["UPDATE",page.chosen?page.chosen.update:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(4)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(12) }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"启用扩展（预览）"; color:Theme.text; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.WordWrap }
                        SwirlToggle { enabled:false;checked:false;

                            onToggled:if(page.chosen){
                                var id=page.chosen.id
                                page.modules=page.modules.map(function(m){return m.id===id?
                                    {id:m.id,name:m.name,author:m.author,version:m.version,state:checked?"Enabled":"Disabled",source:m.source,update:m.update}:m})
                                page.chosen=page.modules.find(function(m){return m.id===id})
                            }
                        }
                    }
                    Text { text:"参数"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"模块参数" }

                        }
                    }

                    SwirlButton { enabled:false; text:"保存本地参数"; onClicked:AppState.notice("保存扩展参数") }
                    SwirlButton { enabled:false; text:"检查更新"; onClicked:AppState.notice("检查扩展更新") }

                }
            }
        }
    }
    SwirlDialog {
        id:importDialog; title:"导入扩展"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:"模块名称"; color:Theme.text }
            SwirlTextField { id:moduleName; Layout.fillWidth:true; placeholderText:"我的扩展" }
            Text { text:"来源 URL（可选）"; color:Theme.text }
            SwirlTextField { id:sourceUrl; Layout.fillWidth:true; placeholderText:"https://example.test/module" }
            Text { text:"不会下载文件或执行脚本。"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:"取消"; onClicked:importDialog.close() }
                SwirlButton { enabled:false;
                    text:"添加"; primary:true;
                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}

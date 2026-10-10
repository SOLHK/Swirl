import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string tab:"Installed"
    property var chosen:null
    property var modules:[
        {id:"mod1",name:"隐私规则",author:"本地示例",version:"1.4.2",state:"Enabled",source:"本地模块",update:"Current"},
        {id:"mod2",name:"请求头工具",author:"本地示例",version:"2.0.1",state:"Enabled",source:"本地模块",update:"有可用更新"},
        {id:"mod3",name:"设备监控",author:"本地示例",version:"0.9.0",state:"Disabled",source:"远程（示例）",update:"Current"},
        {id:"mod4",name:"请求工具",author:"本地示例",version:"1.0.3",state:"Disabled",source:"远程（示例）",update:"Current"}
    ]
    readonly property var filtered:modules.filter(function(m){return (m.name+" "+m.author).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"扩展目录 · 演示"; tone:"accent" }
            Text { text:"尚未加载第三方脚本或扩展。"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"本地导入"; onClicked:importDialog.open() }
            SwirlButton { text:"添加远程"; primary:true; onClicked:importDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Installed","Marketplace","Updates"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlSearchField { id:search; implicitWidth:250; placeholderText:"搜索扩展" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Installed"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.filtered
                    selectedId:page.chosen?page.chosen.id:""
                    columns:[{key:"name",label:"模块名称",w:220},{key:"version",label:"VERSION",w:102},
                             {key:"source",label:"SOURCE",w:172},{key:"update",label:"UPDATES",w:153},
                             {key:"state",label:"STATE",w:110}]
                    onRowSelected:function(r){page.chosen=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Installed"
                    anchors.fill:parent; anchors.margins:19; spacing:16
                    Text { text:page.tab==="Marketplace"?"扩展市场（界面预览）":"模块更新"; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="Marketplace"?["规则辅助工具 · 演示","DNS 工具 · 演示","流量可视化 · 演示"]:
                            ["请求头工具 · v2.1 可更新（演示）","没有其他可用更新"]
                        SwirlGlassPanel {
                            Layout.fillWidth:true; Layout.preferredHeight:66
                            RowLayout {
                                anchors.fill:parent; anchors.margins:12
                                SwirlIcon { name:"grid"; color:Theme.accent; size:22 }
                                Text { text:modelData; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                                SwirlButton { text:page.tab==="Marketplace"?"View":"Details"; onClicked:AppState.notice("扩展列表") }
                            }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:305; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:"扩展详情"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.chosen?page.chosen.name:"选择模块"; color:Theme.accent; font.pixelSize:16; font.weight:Font.DemiBold; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                    Repeater {
                        model:[["VERSION",page.chosen?page.chosen.version:"—"],["AUTHOR",page.chosen?page.chosen.author:"—"],
                               ["SOURCE",page.chosen?page.chosen.source:"—"],["UPDATE",page.chosen?page.chosen.update:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:4
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:12 }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"启用扩展（预览）"; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                        SwirlToggle {
                            checked:page.chosen&&page.chosen.state==="Enabled"
                            onToggled:if(page.chosen){
                                var id=page.chosen.id
                                page.modules=page.modules.map(function(m){return m.id===id?
                                    {id:m.id,name:m.name,author:m.author,version:m.version,state:checked?"Enabled":"Disabled",source:m.source,update:m.update}:m})
                                page.chosen=page.modules.find(function(m){return m.id===id})
                            }
                        }
                    }
                    Text { text:"Parameters"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"模块参数" }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"保存本地参数"; onClicked:AppState.notice("保存扩展参数") }
                    SwirlButton { text:"检查更新"; onClicked:AppState.notice("检查扩展更新") }
                }
            }
        }
    }
    SwirlDialog {
        id:importDialog; title:"导入扩展"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"模块名称"; color:Theme.text }
            SwirlTextField { id:moduleName; Layout.fillWidth:true; placeholderText:"我的扩展" }
            Text { text:"来源 URL（可选）"; color:Theme.text }
            SwirlTextField { id:sourceUrl; Layout.fillWidth:true; placeholderText:"https://example.test/module" }
            Text { text:"不会下载文件或执行脚本。"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:importDialog.close() }
                SwirlButton {
                    text:"添加演示"; primary:true; enabled:moduleName.text.trim().length>0
                    onClicked:{
                        page.modules=page.modules.concat([{id:"mod"+Date.now(),name:moduleName.text.trim(),
                            author:"演示作者",version:"0.1",state:"Disabled",
                            source:sourceUrl.text.trim()||"本地演示",update:"未检查"}])
                        moduleName.text="";sourceUrl.text="";importDialog.close()
                    }
                }
            }
        }
    }
}
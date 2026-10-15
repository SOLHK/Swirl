import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string selectedTab:"本地映射"
    property var selection:null
    property var entries:[]
    readonly property var visibleRows:entries.filter(function(r){return r.type===selectedTab &&
        (r.name+" "+r.match+" "+r.target).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"响应映射"; tone:"accent" }
            Text { text:"不会读取文件或重定向实际请求"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { development:true; enabled:false; text:"新建映射"; primary:true; onClicked:newDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["本地映射","远程映射"]
                SwirlButton { development:true; enabled:false; text:modelData; quiet:page.selectedTab!==modelData; onClicked:AppState.notice("研发中") }
            }
            Item { Layout.fillWidth:true }
            SwirlSearchField { id:search; implicitWidth:Theme.dp(260); placeholderText:"筛选映射 URL" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.visibleRows
                    selectedId:page.selection?page.selection.id:""
                    columns:[{key:"name",label:"映射",w:180},{key:"match",label:"请求 URL",w:280},
                             {key:"target",label:"替换目标",w:270},{key:"status",label:"状态",w:105}]
                    onRowSelected:function(r){page.selection=r;nameField.text=r.name;matchField.text=r.match;targetField.text=r.target}
                }
                SwirlEmptyState { visible:page.visibleRows.length===0; anchors.centerIn:parent; headline:"暂无映射" }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(313); Layout.fillHeight:true
                ScrollView {
                    id:detailScroll0; anchors.fill:parent; anchors.margins:Theme.dp(18); clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                    width:detailScroll0.availableWidth; height:Math.max(implicitHeight,detailScroll0.availableHeight); spacing:Theme.dp(12)
                    Text { text:"映射详情"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    Text { text:page.selectedTab; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    Text { text:"显示名称"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    SwirlTextField { id:nameField; Layout.fillWidth:true; placeholderText:"映射名称" }
                    Text { text:"匹配请求 URL"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    SwirlTextField { id:matchField; Layout.fillWidth:true; placeholderText:"https://example.test/*" }
                    Text { text:page.selectedTab==="本地映射"?"替换文件或目录":"远程替换 URL"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    SwirlTextField { id:targetField; Layout.fillWidth:true; placeholderText:page.selectedTab==="本地映射"?"fixtures/file.json":"https://mirror.example.test/" }
                    Text { text:"预览"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height); color:Theme.field; border.color:Theme.border
                        Text {
                            anchors.fill:parent; anchors.margins:Theme.dp(12)
                            text:(matchField.text||"原始 URL")+"\n  ↓\n"+(targetField.text||"替换目标")+
                                 "\n\n尚未接入网络或文件操作。"
                            color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere
                        }
                    }
                    SwirlButton { development:true; enabled:false;
                        text:"保存映射"; primary:true

                        onClicked:AppState.notice("研发中")
                    }
                }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"创建响应映射"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:"请求 URL 匹配表达式"; color:Theme.text }
            SwirlTextField { id:urlInput; Layout.fillWidth:true; placeholderText:"https://example.test/api/*" }
            Text { text:page.selectedTab==="本地映射"?"本地文件路径":"远程替换 URL"; color:Theme.text }
            SwirlTextField { id:destination; Layout.fillWidth:true; placeholderText:page.selectedTab==="本地映射"?"fixtures/response.json":"https://mirror.example.test/" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { development:true; enabled:false; text:"取消"; onClicked:newDialog.close() }
                SwirlButton { development:true; enabled:false;
                    text:"添加"; primary:true

                    onClicked:AppState.notice("研发中")
                }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property bool tlsPreview:false
    property string activeTab:"包含的域名"
    property var selected:null
    property var domainRows:[]
    readonly property var shown:domainRows.filter(function(r){
        return (activeTab==="包含的域名"?r.type==="Include":r.type==="Exclude") &&
               r.name.toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(15)
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(157)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(18)
                Rectangle {
                    width:Theme.dp(52); height:Theme.dp(52); radius:Theme.roundedRadius(width,height); color:Theme.selected
                    SwirlIcon { name:"shield"; size:Theme.dp(27); color:Theme.accent; anchors.centerIn:parent }
                }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(7)
                    Text { text:AppState.zh("HTTPS inspection"); color:Theme.text; font.pixelSize:Theme.fontSize(21); font.weight:Font.DemiBold }
                    Text {
                        text:"尚未实现 HTTPS 解密；没有生成或安装证书。"
                        color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.WordWrap; Layout.fillWidth:true
                    }
                    RowLayout {
                        SwirlStatusBadge { label:AppState.zh("LOCAL CA: NOT INSTALLED"); tone:"warning" }
                        SwirlStatusBadge { label:"TLS 会话：未采集"; tone:"neutral" }
                    }
                }
                ColumnLayout {
                    Text { text:"HTTPS 解密（尚未实现）"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    SwirlToggle { enabled:false;checked:false;  onToggled:{page.tlsPreview=checked;AppState.notice("HTTPS 解密预览")} }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(7)
            Repeater {
                model:["包含的域名","Excluded domains"]
                SwirlButton { enabled:false; text:modelData; quiet:page.activeTab!==modelData; onClicked:page.activeTab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { enabled:false; text:AppState.zh("证书管理"); iconName:"shield"; onClicked:certDialog.open() }
            SwirlButton { enabled:false; text:AppState.zh("Add domain"); primary:true; onClicked:addDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Filter host patterns") }
            SwirlStatusBadge { label:page.shown.length+" 个域名"; tone:"accent" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(15)
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.shown
                    selectedId:page.selected?page.selected.id:""
                    columns:[{key:"name",label:AppState.zh("HOST PATTERN"),w:258},{key:"type",label:AppState.zh("RULE"),w:107},
                             {key:"mode",label:AppState.zh("ACTION"),w:166},{key:"status",label:AppState.zh("STATE"),w:110}]
                    onRowSelected:function(r){page.selected=r}
                }
                SwirlEmptyState {
                    anchors.centerIn:parent; visible:page.shown.length===0
                    headline:AppState.zh("No host patterns")
                    detail:"尚未实现"
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(285); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(14)
                    Text { text:AppState.zh("Certificate & session"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    Repeater {
                        model:[["证书状态","未安装"],["TRUST","未配置"],
                               ["真实活动会话","0"],["TLS 版本","TLS 1.3"],
                               ["CIPHER","AES_128_GCM_SHA256"],
                               ["选中的域名",page.selected?page.selected.name:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            Text { text:AppState.zh(modelData[0]); font.pixelSize:Theme.fontSize(10); color:Theme.muted }
                            Text { text:AppState.zh(modelData[1]); font.pixelSize:Theme.fontSize(12); color:Theme.text; wrapMode:Text.WrapAnywhere; Layout.fillWidth:true }
                        }
                    }

                        }
                    }

                    SwirlButton { enabled:false; text:AppState.zh("信任证书"); onClicked:AppState.notice("信任证书：模式不支持") }
                    SwirlButton { enabled:false; text:AppState.zh("撤销信任"); danger:true; onClicked:AppState.notice("撤销证书：模式不支持") }

                }
            }
        }
    }
    SwirlDialog {
        id:certDialog; title:"CA 证书管理"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(11)
            SwirlStatusBadge { label:AppState.zh("NO CERTIFICATE MATERIAL AVAILABLE"); tone:"warning" }
            Text {
                text:"尚未实现"
                color:Theme.text; font.pixelSize:Theme.fontSize(13); wrapMode:Text.WordWrap; Layout.fillWidth:true
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("Close"); onClicked:certDialog.close() }
                SwirlButton { enabled:false; text:AppState.zh("证书预览"); onClicked:AppState.notice("证书详情") }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"添加 HTTPS 域名规则"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(11)
            Text { text:AppState.zh("Host pattern"); color:Theme.text }
            SwirlTextField { id:hostName; Layout.fillWidth:true; placeholderText:AppState.zh("*.example.test") }
            SwirlComboBox { id:ruleType; Layout.fillWidth:true; model:["Include","Exclude"]; currentIndex:page.activeTab==="包含的域名"?0:1 }
            Text { text:"尚未实现"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("Cancel"); onClicked:addDialog.close() }
                SwirlButton { enabled:false;
                    text:AppState.zh("保存"); primary:true

                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}

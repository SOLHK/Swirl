import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string category:"全部"
    readonly property var filtered:FeatureCatalog.entries.filter(function(f){return (page.category==="全部" || f.group===page.category) && (f.title+" "+f.keywords).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; spacing:14
        RowLayout {
            Layout.fillWidth:true; Layout.topMargin:14; spacing:16
            ColumnLayout {
                Layout.fillWidth:true; spacing:6
                Text {text:"功能模块";color:Theme.text;font.pixelSize:27;font.weight:Font.DemiBold}
                Text {text:FeatureCatalog.entries.length+" 个入口 · 配置草稿与界面预览";color:Theme.muted;font.pixelSize:15;Layout.fillWidth:true;elide:Text.ElideRight}
            }
            SwirlSearchField {id:search;objectName:"moduleSearch";Layout.preferredWidth:280;placeholderText:"搜索模块或协议…"}
        }
        Text {text:"真实 HTTP 抓包已接入。其他页面用于配置与交互预览，保存草稿不会启动网络服务。";color:Theme.muted;font.pixelSize:14;Layout.fillWidth:true;wrapMode:Text.WordWrap}
        ScrollView {
            Layout.fillWidth:true; Layout.preferredHeight:45
            ScrollBar.vertical.policy:ScrollBar.AlwaysOff
            Row {spacing:8;Repeater {
                model:["全部"].concat(FeatureCatalog.categories)
                SwirlButton {required property string modelData;text:modelData;implicitHeight:38;font.pixelSize:14;quiet:page.category!==modelData;onClicked:page.category=modelData}
            }}
        }
        ScrollView {
            id:scroll;Layout.fillWidth:true;Layout.fillHeight:true;clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            GridLayout {
                width:scroll.availableWidth;columns:width>=1000 ? 3 : width>=620 ? 2 : 1;columnSpacing:14;rowSpacing:14
                Repeater {
                    model:page.filtered
                    Button {
                        required property var modelData
                        Layout.fillWidth:true;Layout.preferredHeight:148
                        hoverEnabled:true;padding:18
                        background:SwirlGlassPanel {color:parent.down ? Theme.selected : parent.hovered ? Theme.hover : Theme.surface}
                        contentItem:ColumnLayout {
                            spacing:8
                            RowLayout {
                                Layout.fillWidth:true;spacing:12
                                SwirlIcon {name:modelData.icon;size:26;color:Theme.accent}
                                Text {text:modelData.title;font.pixelSize:18;font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true;elide:Text.ElideRight}
                                SwirlIcon {name:"chevron-right";size:16}
                            }
                            Text {text:modelData.sub;color:Theme.muted;font.pixelSize:14;Layout.fillWidth:true;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
                            Item {Layout.fillHeight:true}
                            Text {text:modelData.id==="capture" ? "HTTP 已接入" : modelData.id.indexOf("feature-")===0 ? "配置草稿" : "交互预览";color:modelData.id==="capture" ? Theme.green : Theme.muted;font.pixelSize:12}
                        }
                        onClicked:AppState.navigate(modelData.id)
                        Accessible.name:modelData.title
                    }
                }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string category:"全部"
    property string statusFilter:"全部状态"
    readonly property var filtered:FeatureCatalog.entries.filter(function(f){return (page.category==="全部" || f.group===page.category) && (page.statusFilter==="全部状态" || f.status===page.statusFilter) && (f.title+" "+f.keywords).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true; Layout.topMargin:14; spacing:Theme.dp(16)
            ColumnLayout {
                Layout.fillWidth:true; spacing:Theme.dp(6)
                Text {text:"全部功能";color:Theme.text;font.pixelSize:Theme.fontSize(27);font.weight:Font.DemiBold}
                Text {text:FeatureCatalog.entries.length+" 个模块 · 对照官方手册逐项归属";color:Theme.muted;font.pixelSize:Theme.fontSize(15);Layout.fillWidth:true;elide:Text.ElideRight}
            }
            SwirlSearchField {id:search;objectName:"moduleSearch";Layout.preferredWidth:Math.min(Theme.dp(280),page.width*0.34);placeholderText:"搜索模块或协议…"}
        }
        Text {text:"部分实现的模块连接真实业务接口；待开发模块仅保存本机草稿。保存草稿不会使网络配置生效。";color:Theme.muted;font.pixelSize:Theme.fontSize(14);Layout.fillWidth:true;wrapMode:Text.WordWrap}
        SwirlComboBox {model:["全部状态","部分实现","待开发","平台受限"];onActivated:page.statusFilter=currentText;Accessible.name:"功能状态筛选"}
        ScrollView {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(45)
            ScrollBar.vertical.policy:ScrollBar.AlwaysOff
            Row {spacing:Theme.dp(8);Repeater {
                model:["全部"].concat(FeatureCatalog.categories)
                SwirlButton {required property string modelData;text:modelData;implicitHeight:Theme.dp(38);font.pixelSize:Theme.fontSize(14);quiet:page.category!==modelData;onClicked:page.category=modelData}
            }}
        }
        ScrollView {
            id:scroll;objectName:"motion-hub-scroll";Layout.fillWidth:true;Layout.fillHeight:true;clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            GridLayout {
                width:scroll.availableWidth;columns:width>=1000 ? 3 : width>=620 ? 2 : 1;columnSpacing:14;rowSpacing:14
                Repeater {
                    model:page.filtered
                    SwirlMotionButton {
                        required property var modelData
                        objectName:modelData.id.indexOf("feature-")===0?"motion-feature-card":"motion-hub-card"
                        Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(148)
                        hoverEnabled:true;padding:Theme.dp(18)
                        opacity:SwirlMotion.transitioning && SwirlMotion.shared &&
                                (SwirlMotion.shared.reverse?SwirlMotion.shared.previous:SwirlMotion.shared.route)===modelData.id ? 0 : 1
                        background:SwirlGlassPanel {color:parent.down ? Theme.selected : parent.hovered ? Theme.hover : Theme.surface
 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 }
                        contentItem:ColumnLayout {
                            spacing:Theme.dp(8)
                            RowLayout {
                                Layout.fillWidth:true;spacing:Theme.dp(12)
                                SwirlIcon {name:modelData.icon;size:Theme.dp(26);color:Theme.accent}
                                Text {text:modelData.title;font.pixelSize:Theme.fontSize(18);font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true;elide:Text.ElideRight}
                                SwirlIcon {name:"chevron-right";size:Theme.dp(16)}
                            }
                            Text {text:modelData.sub;color:Theme.muted;font.pixelSize:Theme.fontSize(14);Layout.fillWidth:true;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
                            Item {Layout.fillHeight:true}
                            Text {text:modelData.status+" · "+modelData.capabilities.length+" 个归属细项";color:modelData.status==="部分实现" ? Theme.green : Theme.muted;font.pixelSize:Theme.fontSize(12)}
                        }
                        onClicked:SwirlMotion.navigateFrom(this,modelData.id)
                        Accessible.name:modelData.title
                    }
                }
            }
        }
    }
}

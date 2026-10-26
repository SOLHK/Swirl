pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id: page
    SwirlText {textRole:"pageTitle"; x:Theme.dp(24); y:Theme.dp(30); text:"设置"; color:Theme.text; font.pixelSize:Theme.fontSize(26); font.weight:Font.Bold }
    ScrollView {
        id: scroll; x:Theme.dp(24); y:Theme.dp(94); width:parent.width-Theme.dp(48); height:parent.height-y-Theme.dp(20)
        clip:true; ScrollBar.horizontal.policy:ScrollBar.AlwaysOff; ScrollBar.vertical:SwirlScrollBar {}
        GridLayout {
            id: grid; width:scroll.availableWidth
            columns:Math.max(1,Math.floor(width/Theme.dp(210))); columnSpacing:Theme.dp(10);rowSpacing:Theme.dp(10)
            Repeater {
                model:[
                    {title:"通用",icon:"settings",route:"settings",description:"基础配置、主题、文字与动画"},
                    {title:"DNS",icon:"dns",route:"dns",description:"解析服务与本地映射"},
                    {title:"模块",icon:"modules",route:"modules",description:"管理配置扩展模块"},
                    {title:"配置",icon:"profiles",route:"profiles",description:"管理与切换本地配置"},
                    {title:"脚本",icon:"scripts",route:"scripts",description:"运行本地 JavaScript 扩展"},
                    {title:"订阅管理",icon:"subscriptions",route:"subscriptions",description:"更新节点与自动更新周期"},
                    {title:"节点管理",icon:"proxies",route:"proxies",description:"连接、测速与编辑节点"}]
                SwirlMotionButton {
                    id: entry; required property var modelData;required property int index
                    readonly property Item motionTitle:entryTitle
                    readonly property string motionIcon:modelData.icon
                    readonly property string motionDescription:modelData.description
                    objectName:"settings-"+modelData.route
                    Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredWidth:1;Layout.preferredHeight:Theme.dp(156)
                    Layout.columnSpan:index===6?grid.columns-(index%grid.columns):1
                    padding:Theme.cardPadding; hoverEnabled:true
                    readonly property Item motionSurface:background
                    motionScale:1-(1-SwirlMotion.pressScale)*entryFeedback.contact
                    SwirlInteractionMotion { id:entryFeedback; hovered:entry.hovered; pressed:entry.down; focused:entry.visualFocus; controlEnabled:entry.enabled }
                    // The cached hub stays mounted during in-window navigation.
                    opacity:1
                    background:Rectangle {
                        id:entrySurface
                        property bool surfaceHidden:false
                        color:Theme.material("content"); radius:Theme.cardRadius
                        Rectangle { anchors.fill:parent; radius:parent.radius; color:Theme.withAlpha(Theme.accent,entryFeedback.light*0.055) }
                        opacity:surfaceHidden?0:1
                        border.width:surfaceHidden?0:Theme.borderWidth; border.color:entryFeedback.focusAmount>0?Theme.focusBorder:Theme.withAlpha(Theme.accent,0.12+entryFeedback.light*0.24)
                    }
                    contentItem:Column {
                        spacing:Theme.dp(12)
                        SwirlIcon { name:entry.modelData.icon; size:Theme.dp(34); color:Theme.accent }
                        SwirlText { id:entryTitle;text:entry.modelData.title; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                        SwirlText { width:parent.width; text:entry.modelData.description; color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WordWrap }
                    }
                    onClicked: page.Window.window.openSettings(modelData.route,entry)
                    Accessible.name:modelData.title
                }
            }
        }
    }
}

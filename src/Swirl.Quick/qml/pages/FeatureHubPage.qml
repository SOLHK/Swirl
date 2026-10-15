pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id: page
    SwirlText { x:Theme.dp(24); y:Theme.dp(30); text:"设置"; color:Theme.text; font.pixelSize:Theme.fontSize(26); font.weight:Font.Bold }
    Rectangle { y:Theme.dp(78); width:parent.width; height:Theme.dp(1); color:Theme.border }
    ScrollView {
        id: scroll; x:Theme.dp(24); y:Theme.dp(94); width:parent.width-Theme.dp(48); height:parent.height-y-Theme.dp(20)
        clip:true; ScrollBar.horizontal.policy:ScrollBar.AlwaysOff; ScrollBar.vertical:SwirlScrollBar {}
        Grid {
            id: grid; width:scroll.availableWidth
            columns:Math.max(1,Math.floor(width/Theme.dp(210))); spacing:Theme.dp(10)
            Repeater {
                model:[
                    {title:"通用",icon:"settings",route:"settings",description:"基础配置与应用行为"},
                    {title:"外观",icon:"appearance",route:"appearance",description:"主题、文字大小与动画"},
                    {title:"字体",icon:"typography",route:"fonts",description:"按系统选择清晰字体，也可导入本机字体"},
                    {title:"DNS",icon:"dns",route:"dns",description:"解析服务与本地映射"},
                    {title:"模块",icon:"modules",route:"modules",description:"管理配置扩展模块"},
                    {title:"配置",icon:"profiles",route:"profiles",description:"管理与切换本地配置"},
                    {title:"脚本",icon:"scripts",route:"scripts",description:"运行本地 JavaScript 扩展"},
                    {title:"订阅管理",icon:"subscriptions",route:"subscriptions",description:"更新节点与自动更新周期"},
                    {title:"节点管理",icon:"proxies",route:"proxies",description:"连接、测速与编辑节点"}]
                SwirlMotionButton {
                    id: entry; required property var modelData
                    readonly property Item motionTitle:entryTitle
                    readonly property string motionIcon:modelData.icon
                    readonly property string motionDescription:modelData.description
                    objectName:"settings-"+modelData.route
                    width:Math.floor((grid.width-(grid.columns-1)*grid.spacing)/grid.columns); height:Theme.dp(156)
                    padding:Theme.cardPadding; hoverEnabled:true
                    readonly property real transfer: page.Window.window.settingsOrigin===entry ? page.Window.window.settingsOriginProgress : 0
                    motionScale:enabled && down?SwirlMotion.pressScale:1
                    opacity:page.Window.window.settingsOrigin===entry && page.Window.window.settingsOriginMoving?0:1
                    background:Rectangle {
                        color:entry.hovered?Theme.hover:Theme.material("content"); radius:Theme.cardRadius
                        border.width:Theme.borderWidth; border.color:entry.activeFocus?Theme.focusBorder:Theme.border
                        Behavior on color { ColorAnimation { duration:SwirlMotion.hoverDuration } }
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

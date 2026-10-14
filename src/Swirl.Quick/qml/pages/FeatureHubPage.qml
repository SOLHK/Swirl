pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"设置";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 Rectangle{x:0;y:Theme.dp(78);width:parent.width;height:Theme.dp(1);color:Theme.border}
 Grid {
  x:Theme.dp(24);y:Theme.dp(100);width:parent.width-Theme.dp(48);columns:3;rowSpacing:0;columnSpacing:0
  Repeater {model:[
   {title:"通用",icon:"general",route:"settings",description:"可以在这里找到大部分 Swirl 的基础配置。"},
   {title:"外观",icon:"appearance",route:"appearance",description:"菜单栏图标、Dock 图标和通知相关设置。"},
   {title:"DNS",icon:"dns",route:"dns",description:"本地 DNS 映射和 DNS 相关设置。"},
   {title:"模块",icon:"modules",route:"modules",description:"模块是一系列设置的集合，可用于覆盖当前配置的部分设定。"},
   {title:"配置",icon:"profiles",route:"profiles",description:"Swirl 的大部分功能都可以被配置式管理，可以在这里管理所有的配置式。"},
   {title:"授权 & 更新",icon:"license",route:"license",description:"管理你的授权和升级设定。"},
   {title:"脚本",icon:"scripts",route:"scripts",description:"使用 JavaScript 来扩展 Swirl 的功能。"},
   {title:"订阅管理",icon:"profiles",route:"subscriptions",description:"添加、更新和管理远程订阅与自动更新周期。"}]
   SwirlMotionButton {id:entry;objectName:"settings-"+modelData.route;required property var modelData;required property int index;width:Theme.dp(216);height:Theme.dp(189);padding:0;hoverEnabled:true
    background:Rectangle{color:entry.hovered?Theme.withAlpha(Theme.hover,0.25):"transparent";radius:Theme.tileRadius;Behavior on color {ColorAnimation{duration:SwirlMotion.hoverDuration}}}
    contentItem:Item {
     Image{x:Theme.dp(16);y:Theme.dp(14);width:Theme.dp(52);height:Theme.dp(52);source:Theme.dark?"image://swirl/reference-"+entry.modelData.icon:"qrc:/swirl/icons/ui/reference-"+entry.modelData.icon+".png";fillMode:Image.PreserveAspectFit}
     Text{x:Theme.dp(16);y:Theme.dp(86);text:entry.modelData.title;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
     Text{x:Theme.dp(16);y:Theme.dp(112);width:Theme.dp(175);text:entry.modelData.description;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WordWrap}
     Rectangle{visible:entry.index<6;y:Theme.dp(170);width:parent.width;height:Theme.dp(1);color:Theme.border}
    }
    onClicked:page.Window.window.openSettings(entry.modelData.route)
    Accessible.name:entry.modelData.title
   }
  }
 }
}

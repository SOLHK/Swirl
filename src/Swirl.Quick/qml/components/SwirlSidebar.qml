import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
Item {
 id:sidebar
 property bool compactByWindow:false
 readonly property bool effectivelyCollapsed:false
 property alias searchField:pageSearch
 function openSearch(){ searchPopup.open();pageSearch.forceActiveFocus() }
 Row {
  x:Theme.dp(8);y:Theme.dp(8);spacing:Theme.dp(7)
  Repeater {
   model:["#FF5F57","#FEBC2E","#28C840"]
   SwirlMotionButton {
    required property int index;required property string modelData
    width:Theme.dp(16);height:width;hoverEnabled:true
    objectName:index===0?"windowCloseButton":index===1?"windowMinimizeButton":"windowMaximizeButton"
    background:Rectangle { anchors.centerIn:parent;width:Theme.dp(14);height:width;radius:width/2;color:Theme.windowActive?parent.modelData:"#D1D9DE" }
    contentItem:Item {}
    onClicked:{if(index===0)sidebar.Window.window.close();else if(index===1)sidebar.Window.window.showMinimized();else if(sidebar.Window.window.visibility===Window.Maximized)sidebar.Window.window.showNormal();else sidebar.Window.window.showMaximized()}
    Accessible.name:index===0?"关闭":index===1?"最小化":"最大化或还原"
   }
  }
 }
 Column {
  x:Theme.dp(10);y:Theme.dp(55);width:parent.width-Theme.dp(20);spacing:0
  Repeater {
   model:AppState.navigationGroups
   Column {
    required property var modelData;required property int index
    width:parent.width;spacing:0
    Item { width:parent.width;height:modelData.title.length?Theme.dp(36):0
     Text {x:Theme.dp(7);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(5);text:modelData.title;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
    }
    Repeater {model:modelData.pages
     SwirlNavigationItem {required property var modelData;width:parent.width;pageId:modelData.id;title:modelData.title;iconName:modelData.icon;onActivated:AppState.navigate(pageId)}
    }
   }
  }
 }
 Column {
  x:Theme.dp(10);width:parent.width-Theme.dp(20);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(12);spacing:0
  SwirlNavigationItem {width:parent.width;pageId:"featurehub";title:"更多";iconName:"sliders";onActivated:AppState.navigate(pageId)}
  Item{width:parent.width;height:Theme.dp(12)}
  Rectangle {x:Theme.dp(5);width:parent.width-Theme.dp(10);height:Theme.dp(1);color:Theme.border}
  SwirlNavigationItem {width:parent.width;pageId:"external";title:"面板";iconName:"gauge";onActivated:sidebar.Window.window.openDashboard()}
 }
 Popup {
  id:searchPopup;x:Theme.dp(10);y:Theme.dp(40);width:Theme.dp(300);padding:Theme.dp(8);modal:false;focus:true
  background:Rectangle {color:Theme.surface;radius:Theme.controlRadius;border.color:Theme.border}
  SwirlSearchField {id:pageSearch;objectName:"pageSearch";width:parent.width;placeholderText:"搜索功能";Accessible.name:"搜索功能、节点或设置"
   onAccepted:{const q=text.trim().toLowerCase();const pages=AppState.groups.reduce((a,g)=>a.concat(g.pages),[]).concat(FeatureCatalog.entries);const found=pages.find(p=>(p.title+" "+(p.keywords||"")).toLowerCase().indexOf(q)>=0);if(found){AppState.navigate(found.id);searchPopup.close()}else AppState.notice("没有找到对应功能");text=""}
  }
 }
}

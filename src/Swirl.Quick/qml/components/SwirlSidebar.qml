import QtQuick
import QtQuick.Effects
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
Item {
 id:sidebar
 property int geometryRevision:0
 property var entries:({})
 readonly property Item selectedEntry:entries[AppState.sidebarPage] || null
 function registerEntry(item){const next=Object.assign({},entries);next[item.pageId]=item;entries=next}
 function unregisterEntry(item){const next=Object.assign({},entries);delete next[item.pageId];entries=next}
 RectangularShadow {
  anchors.fill:floatingBackground
  radius:floatingBackground.radius
  blur:Theme.dp(16)
  offset:Qt.vector2d(Theme.dp(2),Theme.dp(3))
  color:Theme.withAlpha(Theme.dark?"#000000":"#4C6380",Theme.dark?0.22:0.14)
  visible:Theme.effectsSupported
 }
 Rectangle {
  id:floatingBackground;objectName:"sidebarFloatingBackground"
  x:Theme.dp(5);y:Theme.dp(5)
  width:sidebar.width-Theme.dp(10);height:sidebar.height-Theme.dp(10)
  radius:Theme.dp(14)
  color:Theme.dark?Theme.withAlpha("#333B46",0.90):Theme.withAlpha("#FFFFFF",0.88)
  border.width:Theme.dp(1)
  border.color:Theme.dark?Theme.withAlpha("#758296",0.42):Theme.withAlpha("#FFFFFF",0.78)
 }
 // A single visual owner: retarget y from its rendered position, in local coordinates.
 Rectangle {
  id:selection;objectName:"sidebarSelectionIndicator"
  visible:sidebar.selectedEntry!==null
  x:Theme.dp(10);width:sidebar.width-Theme.dp(20);height:Theme.sidebarRowHeight;radius:height/2
  y:{sidebar.geometryRevision;sidebar.height;Theme.uiScale;const item=sidebar.selectedEntry;if(!item)return 0;item.y;return item.mapToItem(sidebar,0,0).y}
  color:sidebar.selectedEntry && sidebar.selectedEntry.down?Theme.navigationPressed:Theme.navigationSelected
  scale:sidebar.selectedEntry && sidebar.selectedEntry.down?SwirlMotion.pressScale:1
  Behavior on y {enabled:!SwirlMotion.reduced;SmoothedAnimation {duration:SwirlMotion.selectionDuration;velocity:-1;reversingMode:SmoothedAnimation.Immediate}}
  Behavior on scale {NumberAnimation {duration:SwirlMotion.releaseDuration;easing.type:Easing.OutCubic}}
  Behavior on color {ColorAnimation {duration:SwirlMotion.pressDuration}}
  RectangularShadow {anchors.fill:parent;z:-1;radius:selection.radius;blur:Theme.dp(5);offset:Qt.vector2d(0,Theme.dp(1));color:Theme.withAlpha("#000000",0.035);visible:Theme.effectsSupported}
 }
 property bool compactByWindow:false
 readonly property bool effectivelyCollapsed:false
 property alias searchField:pageSearch
 function openSearch(){ searchPopup.open();pageSearch.forceActiveFocus() }
 SwirlTrafficLights{x:Theme.dp(8);y:Theme.dp(4);targetWindow:sidebar.Window.window}
 SwirlText {
  objectName:"engineIdentityLabel"
  x:Theme.dp(16);y:Theme.dp(31);width:sidebar.width-Theme.dp(32)
  text:engineController.engineIdentityLabel
  color:Theme.muted;font.pixelSize:Theme.fontSize(11)
  elide:Text.ElideRight
  Accessible.name:text
 }
 Column {
  onPositioningComplete:++sidebar.geometryRevision
  x:Theme.dp(10);y:Theme.dp(55);width:parent.width-Theme.dp(20);spacing:0
  Repeater {
   model:AppState.navigationGroups
   Column {
  onPositioningComplete:++sidebar.geometryRevision
    required property var modelData;required property int index
    width:parent.width;spacing:0
    Item { width:parent.width;height:modelData.title.length?Theme.dp(36):0
     SwirlText {x:Theme.dp(7);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(5);text:modelData.title;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
    }
    Repeater {model:modelData.pages
     SwirlNavigationItem {selectionOwner:sidebar;required property var modelData;width:parent.width;pageId:modelData.id;title:modelData.title;iconName:modelData.icon;onActivated:AppState.navigate(pageId)}
    }
   }
  }
 }
 Column {
  onPositioningComplete:++sidebar.geometryRevision
  x:Theme.dp(10);width:parent.width-Theme.dp(20);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(12);spacing:0
  SwirlNavigationItem {selectionOwner:sidebar;width:parent.width;pageId:"featurehub";title:"更多";iconName:"sliders";onActivated:AppState.navigate(pageId)}
  Item{width:parent.width;height:Theme.dp(8)}
  SwirlNavigationItem {selectionOwner:sidebar;width:parent.width;pageId:"external";title:"面板";iconName:"gauge";onActivated:sidebar.Window.window.openDashboard()}
 }
 Popup {
  id:searchPopup;x:Theme.dp(10);y:Theme.dp(40);width:Theme.dp(300);padding:Theme.dp(8);modal:false;focus:true
  background:Rectangle {color:Theme.surface;radius:Theme.controlRadius;border.color:Theme.border}
  SwirlSearchField {id:pageSearch;objectName:"pageSearch";width:parent.width;placeholderText:"搜索功能";Accessible.name:"搜索功能、节点或设置"
   onAccepted:{const q=text.trim().toLowerCase();const pages=AppState.groups.reduce((a,g)=>a.concat(g.pages),[]).concat(FeatureCatalog.entries);const found=pages.find(p=>(p.title+" "+(p.keywords||"")).toLowerCase().indexOf(q)>=0);if(found){AppState.navigate(found.id);searchPopup.close()}else AppState.notice("没有找到对应功能");text=""}
  }
 }
}

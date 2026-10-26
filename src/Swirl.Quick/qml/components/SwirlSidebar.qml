import QtQuick
import QtQuick.Effects
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
Item {
 id:sidebar
 objectName:"sidebar"
 property int geometryRevision:0
 property var entries:({})
 readonly property Item selectedEntry:entries[AppState.sidebarPage] || null
 function registerEntry(item){const next=Object.assign({},entries);next[item.pageId]=item;entries=next}
 function unregisterEntry(item){const next=Object.assign({},entries);delete next[item.pageId];entries=next}
 Item {
  id:floatingBackground;objectName:"sidebarFloatingBackground"
  x:Theme.dp(8);y:Theme.dp(8)
  width:sidebar.width-Theme.dp(16);height:sidebar.height-Theme.dp(16)
  readonly property real radius:Theme.sidebarRadius
  SwirlShellOutline {
   anchors.fill:parent;radius:floatingBackground.radius
   fillColor:Theme.sidebar
   strokeColor:Theme.increaseContrast?Theme.text:Theme.dark?Qt.rgba(1,1,1,0.12):Qt.rgba(0,0,0,0.04)
  }
  // The light sidebar uses the shared window canvas; no extra darkening pass.
  ShaderEffect {
   readonly property real padding:Theme.dp(24)
   x:-padding;y:-padding;width:floatingBackground.width+2*padding;height:floatingBackground.height+2*padding
   z:-1;visible:Theme.effectsSupported && !Theme.increaseContrast
   property vector2d surfaceSize:Qt.vector2d(floatingBackground.width,floatingBackground.height)
   property real cornerRadius:floatingBackground.radius
   property vector2d shadowOffset:Qt.vector2d(Theme.dp(3),Theme.dp(3))
   property real softness:Theme.dp(9)
   property color shadowColor:Theme.withAlpha("#000000",Theme.sidebarShadowOpacity)
   fragmentShader:"qrc:/swirl/shaders/sidebar-shadow.frag.qsb"
  }
 }
 SwirlArcMotion {
  id:selectionMotion;objectName:"sidebarArcMotion"
  targetX:Theme.dp(10)
  targetY:{sidebar.geometryRevision;sidebar.height;Theme.uiScale;const item=sidebar.selectedEntry;if(!item)return 0;item.y;return item.mapToItem(sidebar,0,0).y}
 }
 // The hit targets remain in their layout while one visual owner follows a
 // continuous curved trajectory, including reversal and a third destination.
 Rectangle {
  id:selection;objectName:"sidebarSelectionIndicator"
  visible:sidebar.selectedEntry!==null
  x:selectionMotion.position.x;width:sidebar.width-Theme.dp(20);height:Theme.sidebarRowHeight;radius:height/2
  y:selectionMotion.position.y
  color:sidebar.selectedEntry && sidebar.selectedEntry.down?Theme.navigationPressed:Theme.navigationSelected
  scale:sidebar.selectedEntry && sidebar.selectedEntry.down?SwirlMotion.pressScale:1
  Behavior on scale {NumberAnimation {duration:SwirlMotion.releaseDuration;easing.type:Easing.OutCubic}}
  Behavior on color {ColorAnimation {duration:SwirlMotion.pressDuration}}
 }
 property bool compactByWindow:false
 readonly property bool effectivelyCollapsed:AppState.sidebarCollapsed || compactByWindow
 readonly property real expansion:widthClock.progress
 readonly property real animatedWidth:Theme.sidebarCollapsedWidth+(Theme.sidebarWidth-Theme.sidebarCollapsedWidth)*expansion
 property bool initialized:false
 SwirlTransitionCoordinator {id:widthClock;progress:1;destination:1;duration:SwirlMotion.expandDuration}
 onEffectivelyCollapsedChanged:if(initialized)widthClock.moveTo(effectivelyCollapsed?0:1)
 Component.onCompleted:{widthClock.progress=effectivelyCollapsed?0:1;widthClock.destination=widthClock.progress;initialized=true}
 SwirlIconButton {
  objectName:"sidebarCollapseButton";x:sidebar.width-width-Theme.dp(13);y:Theme.dp(8)
  width:Theme.dp(28);height:Theme.dp(26);iconName:sidebar.effectivelyCollapsed?"chevron-right":"chevron-left"
  onClicked:AppState.sidebarCollapsed=!AppState.sidebarCollapsed
  Accessible.name:sidebar.effectivelyCollapsed?qsTr("展开导航"):qsTr("收起导航")
 }
 property alias searchField:pageSearch
 function openSearch(){ searchPopup.open();pageSearch.forceActiveFocus() }
 SwirlText {
  objectName:"engineIdentityLabel"
  x:Theme.dp(16);y:Theme.dp(31);width:sidebar.width-Theme.dp(32)
  text:engineController.engineIdentityLabel
  visible:sidebar.expansion>0.6;opacity:Math.max(0,(sidebar.expansion-0.6)/0.4)
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
     SwirlText {x:Theme.dp(7);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(5);text:modelData.title;color:Theme.muted;font.pixelSize:Theme.fontSize(12);opacity:sidebar.expansion}
    }
    Repeater {model:modelData.pages
     SwirlNavigationItem {selectionOwner:sidebar;compact:sidebar.effectivelyCollapsed;required property var modelData;width:parent.width;pageId:modelData.id;title:modelData.title;iconName:modelData.icon;onActivated:AppState.navigate(pageId)}
    }
   }
  }
 }
 Column {
  onPositioningComplete:++sidebar.geometryRevision
  x:Theme.dp(10);width:parent.width-Theme.dp(20);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(12);spacing:0
  SwirlNavigationItem {selectionOwner:sidebar;compact:sidebar.effectivelyCollapsed;width:parent.width;pageId:"featurehub";title:"更多";iconName:"sliders";onActivated:AppState.navigate(pageId)}
  Item{width:parent.width;height:Theme.dp(8)}
  SwirlNavigationItem {selectionOwner:sidebar;compact:sidebar.effectivelyCollapsed;width:parent.width;pageId:"external";title:"面板";iconName:"gauge";onActivated:sidebar.Window.window.openDashboard()}
 }
 Popup {
  id:searchPopup;x:Theme.dp(10);y:Theme.dp(40);width:Theme.dp(300);padding:Theme.dp(8);modal:false;focus:true
  background:Rectangle {color:Theme.surface;radius:Theme.controlRadius;border.color:Theme.border}
  SwirlSearchField {id:pageSearch;objectName:"pageSearch";width:parent.width;placeholderText:"搜索功能";Accessible.name:"搜索功能、节点或设置"
   onAccepted:{const q=text.trim().toLowerCase();const pages=AppState.groups.reduce((a,g)=>a.concat(g.pages),[]).concat(FeatureCatalog.entries);const found=pages.find(p=>(p.title+" "+(p.keywords||"")).toLowerCase().indexOf(q)>=0);if(found){AppState.navigate(found.id);searchPopup.close()}else AppState.notice("没有找到对应功能");text=""}
  }
 }
}

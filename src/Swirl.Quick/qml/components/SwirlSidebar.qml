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
 property Item backdropSource:null
 readonly property Item glassSurface:floatingBackground
 readonly property bool glassSampled:liquidGlass.sampled
 readonly property Item selectedEntry:entries[AppState.sidebarPage] || null
 function registerEntry(item){const next=Object.assign({},entries);next[item.pageId]=item;entries=next}
 function unregisterEntry(item){const next=Object.assign({},entries);delete next[item.pageId];entries=next}
 Item {
  id:floatingBackground;objectName:"sidebarFloatingBackground"
  x:Theme.shellInset;y:Theme.shellInset
  width:sidebar.width-2*Theme.shellInset;height:sidebar.height-2*Theme.shellInset
  readonly property real radius:Theme.sidebarRadius
  SwirlInteractionMotion {id:materialResponse;hovered:glassHover.hovered;pressed:sidebar.selectedEntry && sidebar.selectedEntry.down;focused:sidebar.selectedEntry && sidebar.selectedEntry.visualFocus}
  HoverHandler {id:glassHover}
  SwirlLiquidGlass {
   id:liquidGlass
   objectName:"sidebarLiquidGlass";anchors.fill:parent;cornerRadius:floatingBackground.radius
   backdropSource:sidebar.backdropSource;interaction:materialResponse.light
   lightPoint:glassHover.hovered?Qt.point(glassHover.point.position.x/width,glassHover.point.position.y/height):Qt.point(0.18,(selectionMotion.position.y-floatingBackground.y+Theme.sidebarRowHeight*.5)/height)
  }
  ShaderEffect {
   objectName:"sidebarExteriorShadow"
   readonly property real padding:Theme.dp(24)
   x:-padding;y:-padding;width:floatingBackground.width+2*padding;height:floatingBackground.height+2*padding
   z:-1;visible:Theme.effectsSupported && !Theme.increaseContrast
   property vector2d surfaceSize:Qt.vector2d(floatingBackground.width,floatingBackground.height)
   property real cornerRadius:floatingBackground.radius
   property vector2d shadowOffset:Qt.vector2d(Theme.dp(2),Theme.dp(4))
   property real softness:Theme.dp(8)
   property color shadowColor:Theme.withAlpha(Theme.shadowColor,Theme.dark?0.16:0.06)
   fragmentShader:"qrc:/swirl/shaders/sidebar-shadow.frag.qsb"
  }
 }
 SwirlArcMotion {
  id:selectionMotion;objectName:"sidebarArcMotion"
  bend:Math.min(SwirlMotion.navigationArc,Theme.dp(7))
  targetX:Theme.dp(20)
  targetY:{sidebar.geometryRevision;sidebar.height;Theme.uiScale;const item=sidebar.selectedEntry;if(!item)return 0;item.y;return item.mapToItem(sidebar,0,0).y}
 }
 // The hit targets remain in their layout while one visual owner follows a
 // continuous curved trajectory, including reversal and a third destination.
 Rectangle {
  id:selection;objectName:"sidebarSelectionIndicator"
  visible:sidebar.selectedEntry!==null
  x:selectionMotion.position.x;width:sidebar.width-Theme.dp(40);height:Theme.sidebarRowHeight;radius:Theme.sidebarRowRadius
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
  objectName:"sidebarCollapseButton";x:sidebar.effectivelyCollapsed?Theme.dp(24):sidebar.width-width-Theme.dp(24);y:sidebar.effectivelyCollapsed?Theme.dp(57):Theme.dp(29)
  width:Theme.dp(28);height:Theme.dp(26);iconName:sidebar.effectivelyCollapsed?"chevron-right":"chevron-left"
  quiet:true
  onClicked:AppState.sidebarCollapsed=!AppState.sidebarCollapsed
  Accessible.name:sidebar.effectivelyCollapsed?qsTr("展开导航"):qsTr("收起导航")
 }
 property alias searchField:pageSearch
 function openSearch(){ searchPopup.open();pageSearch.forceActiveFocus() }
 SwirlBrandIcon {x:Theme.dp(25);y:Theme.dp(25);width:Theme.dp(28);height:width}
 SwirlText {x:Theme.dp(62);y:Theme.dp(27);text:"Swirl";font.pixelSize:Theme.fontSize(22);font.weight:Font.DemiBold;color:Theme.text;opacity:sidebar.expansion;visible:opacity>0.1}
 SwirlText {
  objectName:"engineIdentityLabel"
  x:Theme.dp(26);y:Theme.dp(62);width:sidebar.width-Theme.dp(52)
  text:engineController.engineIdentityLabel
  visible:sidebar.expansion>0.6;opacity:Math.max(0,(sidebar.expansion-0.6)/0.4)
  color:Theme.muted;font.pixelSize:Theme.fontSize(11)
  elide:Text.ElideRight
  Accessible.name:text
 }
 Column {
  onPositioningComplete:++sidebar.geometryRevision
  x:Theme.dp(20);y:Theme.dp(96);width:parent.width-Theme.dp(40);spacing:0
  Repeater {
   model:AppState.navigationGroups
   Column {
  onPositioningComplete:++sidebar.geometryRevision
    required property var modelData;required property int index
    width:parent.width;spacing:0
    Item { width:parent.width;height:modelData.title.length?Theme.dp(28):0
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
  x:Theme.dp(20);width:parent.width-Theme.dp(40);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(24);spacing:0
  SwirlNavigationItem {selectionOwner:sidebar;compact:sidebar.effectivelyCollapsed;width:parent.width;pageId:"featurehub";title:"更多";iconName:"sliders";onActivated:AppState.navigate(pageId)}
  Item{width:parent.width;height:Theme.dp(8)}
  SwirlNavigationItem {selectionOwner:sidebar;compact:sidebar.effectivelyCollapsed;width:parent.width;pageId:"external";title:"面板";iconName:"gauge";onActivated:sidebar.Window.window.openDashboard()}
 }
 Popup {
  id:searchPopup;objectName:"navigationSearchPopup";x:Theme.dp(20);y:Theme.dp(88);width:Theme.dp(300);padding:Theme.dp(8);modal:false;focus:true
  function requestDismiss(){close()}
  readonly property SwirlPopupMotion popupMotion:SwirlPopupMotion {id:searchReveal;popup:searchPopup;enterDuration:SwirlMotion.menuEnterDuration;leaveDuration:SwirlMotion.menuExitDuration}
  enter:searchReveal.enterTransition;exit:searchReveal.exitTransition
  onAboutToShow:{searchReveal.prepare(Qt.point(0,-SwirlMotion.popupDistance));dismissals.push(searchPopup,sidebar.Window.window)}
  onClosed:{dismissals.pop(searchPopup);searchReveal.reset()}
  background:Rectangle {transform:Translate{x:searchReveal.xOffset;y:searchReveal.yOffset}
   color:Theme.surface;radius:Theme.controlRadius;border.color:Theme.border}
  SwirlSearchField {id:pageSearch;objectName:"pageSearch";width:parent.width;placeholderText:"搜索功能";Accessible.name:"搜索功能、节点或设置"
   transform:Translate{x:searchReveal.xOffset;y:searchReveal.yOffset}
   onAccepted:{const q=text.trim().toLowerCase();const pages=AppState.groups.reduce((a,g)=>a.concat(g.pages),[]).concat(FeatureCatalog.entries);const found=pages.find(p=>(p.title+" "+(p.keywords||"")).toLowerCase().indexOf(q)>=0);if(found){AppState.navigate(found.id);searchPopup.close()}else AppState.notice("没有找到对应功能");text=""}
  }
 }
}

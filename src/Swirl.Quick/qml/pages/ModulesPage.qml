pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;
    readonly property Item motionTitle:pageHeader.titleItem
property string selectedId:""
 readonly property var shownModules:extensionsProvider.modules.filter(function(row){return (row.name+" "+row.description).toLowerCase().indexOf(moduleSearch.text.trim().toLowerCase())>=0})
 SwirlAnimatedModel{id:animatedModules;source:page.shownModules;keyRole:"id"}
 ColumnLayout{anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
  SwirlPageHeader{id:pageHeader;Layout.fillWidth:true;title:qsTr("配置模块");description:qsTr("按顺序覆盖 DNS、规则与策略组，底部模块优先。");metadata:qsTr("停用全部模块后恢复基础配置")
   SwirlButton{objectName:"localModuleImport";text:qsTr("安装本地模块");primary:true;onClicked:moduleFile.open()}
  }
  RowLayout{Layout.fillWidth:true;SwirlText{text:qsTr("应用顺序");font.pixelSize:Theme.captionSize;color:Theme.muted;Layout.fillWidth:true}SwirlText{text:qsTr("%1 个模块").arg(extensionsProvider.modules.length);font.pixelSize:Theme.captionSize;color:Theme.muted}}
  Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
  SwirlSearchField{id:moduleSearch;Layout.fillWidth:true;placeholderText:qsTr("搜索模块名称或说明");Accessible.name:placeholderText}
  ListView { pixelAligned: true;id:moduleList;objectName:"localModuleList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:Theme.dp(10);model:animatedModules
   add:Transition{enabled:page.visible&&!SwirlMotion.reduced;NumberAnimation{property:"opacity";from:0;to:1;duration:SwirlMotion.listDuration}}
   remove:Transition{enabled:page.visible&&!SwirlMotion.reduced;NumberAnimation{property:"opacity";to:0;duration:SwirlMotion.exitDuration}}
   move:Transition{enabled:page.visible&&!SwirlMotion.reduced;SmoothedAnimation{properties:"x,y";duration:SwirlMotion.listDuration}}
   displaced:Transition{enabled:page.visible&&!SwirlMotion.reduced;SmoothedAnimation{properties:"x,y";duration:SwirlMotion.listDuration}}
   SwirlText {visible:moduleList.count===0;anchors.centerIn:parent;text:moduleSearch.text.length?qsTr("没有匹配模块"):qsTr("没有已安装模块");color:Theme.muted;font.pixelSize:Theme.fontSize(16)}
   delegate:Rectangle{id:moduleRow;required property var entry;readonly property var modelData:entry;required property int index;readonly property int sourceIndex:extensionsProvider.modules.findIndex(function(row){return row.id===moduleRow.modelData.id});width:Math.floor(moduleList.width);height:Theme.dp(104);radius:Theme.controlRadius;color:page.selectedId===modelData.id?Theme.selected:"transparent"
    SwirlButton{anchors.fill:parent;anchors.rightMargin:Theme.dp(70);quiet:true;Accessible.name:moduleRow.modelData.name;onClicked:page.selectedId=moduleRow.modelData.id}
    SwirlText{x:Theme.dp(8);y:Theme.dp(16);text:moduleRow.sourceIndex+1;color:Theme.muted;font.pixelSize:Theme.captionSize}
    Column{x:Theme.dp(42);y:Theme.dp(14);width:parent.width-Theme.dp(112);spacing:Theme.dp(6)
     SwirlText {text:moduleRow.modelData.name;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(15);font.weight:Font.DemiBold}
     SwirlText {text:moduleRow.modelData.description;textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);width:parent.width;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
     SwirlText {text:Object.keys(moduleRow.modelData.overrides).join(" · ");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
    }
    SwirlToggle{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(16);checked:parent.modelData.enabled;enabled:engineController.canStart;onToggled:{const row=parent.modelData;extensionsProvider.setModuleEnabled(row.id,checked);checked=Qt.binding(()=>parent.modelData.enabled)}}
   }
  }
  SwirlText {visible:text.length>0;text:extensionsProvider.error||(!engineController.canStart?"请先断开引擎，再更改模块状态和生效顺序。":"");color:Theme.orange;font.pixelSize:Theme.fontSize(12);textFormat:Text.PlainText;Layout.fillWidth:true;wrapMode:Text.WordWrap}
  RowLayout{SwirlButton{text:"上移";enabled:page.selectedId.length>0&&engineController.canStart;onClicked:extensionsProvider.moveModule(page.selectedId,-1)}SwirlButton{text:"下移";enabled:page.selectedId.length>0&&engineController.canStart;onClicked:extensionsProvider.moveModule(page.selectedId,1)}SwirlButton{text:"移除";enabled:page.selectedId.length>0&&engineController.canStart;onClicked:extensionsProvider.removeModule(page.selectedId)}}
 }
 FileDialog{id:moduleFile;parentWindow:page.Window.window;objectName:"settingsModuleFileDialog";title:"安装 Swirl 本地配置模块";nameFilters:["Swirl 配置模块 (*.json)"];onAccepted:extensionsProvider.importModule(selectedFile)}
}

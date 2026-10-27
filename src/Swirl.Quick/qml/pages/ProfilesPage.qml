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
 readonly property var shownProfiles:extensionsProvider.profiles.filter(function(row){return (row.name+" "+row.mode).toLowerCase().indexOf(profileSearch.text.trim().toLowerCase())>=0})
 readonly property var selected:extensionsProvider.profiles.find(r=>r.id===selectedId)||null
 function editProfile(fresh){profileEditor.profileId=fresh?"":selectedId;profileName.text=fresh?"":selected.name;profileSource.text=JSON.stringify(fresh?engineController.networkConfigurationSnapshot():selected.network,null,2);profileMode.currentIndex=["rule","global","direct"].indexOf(fresh?engineController.routingMode:selected.mode);profileEditor.open()}
 ColumnLayout{anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
  SwirlPageHeader{id:pageHeader;Layout.fillWidth:true;title:qsTr("配置");description:qsTr("管理 DNS、规则、策略组和出站模式。");metadata:qsTr("切换配置前先断开引擎")
   SwirlButton{objectName:"profileAddButton";text:qsTr("新建配置");primary:true;onClicked:page.editProfile(true)}
   SwirlButton{text:qsTr("导入");onClicked:profileImport.open()}
  }
  RowLayout{Layout.fillWidth:true;SwirlStatusBadge{label:qsTr("当前配置");tone:"accent"}SwirlText{text:extensionsProvider.profileName;color:Theme.text;font.pixelSize:Theme.bodySize;font.weight:Font.Medium;Layout.fillWidth:true}SwirlText{text:qsTr("%1 个本地配置").arg(extensionsProvider.profiles.length);color:Theme.muted;font.pixelSize:Theme.captionSize}}
  Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
  SwirlSearchField{id:profileSearch;Layout.fillWidth:true;placeholderText:qsTr("搜索配置名称或模式");Accessible.name:placeholderText}
  Item{Layout.fillWidth:true;Layout.fillHeight:true
  SwirlDataTable{objectName:"localProfileTable";incrementalRows:true;animateRowChanges:true;anchors.fill:parent;fillEmptyRows:false;rows:page.shownProfiles;selectedId:page.selectedId;columns:[{key:"name",label:"名称",w:260},{key:"mode",label:"出站模式",w:140}];onRowSelected:r=>page.selectedId=r.id}
   SwirlEmptyState{anchors.centerIn:parent;width:parent.width;visible:page.shownProfiles.length===0;headline:profileSearch.text.length?qsTr("没有匹配结果"):qsTr("还没有本地配置");detail:qsTr("从当前设置新建配置，或导入已有 Swirl 配置。")}
  }
  SwirlText {visible:text.length>0;text:extensionsProvider.error;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap;textFormat:Text.PlainText}
  RowLayout{Layout.fillWidth:true;spacing:Theme.dp(8)
   SwirlButton{text:qsTr("移除");enabled:page.selected!==null;onClicked:extensionsProvider.removeProfile(page.selectedId)}
   SwirlButton{text:qsTr("导出所选");enabled:page.selected!==null;onClicked:profileExport.open()}
   Item{Layout.fillWidth:true}
   SwirlButton{text:qsTr("恢复默认配置");enabled:engineController.canStart;onClicked:extensionsProvider.useProfile("")}
   SwirlButton{text:qsTr("编辑");enabled:page.selected!==null;onClicked:page.editProfile(false)}
   SwirlButton{text:"使用配置";primary:true;enabled:page.selected!==null&&engineController.canStart;onClicked:extensionsProvider.useProfile(page.selectedId)}
  }
 }
 FileDialog{id:profileImport;parentWindow:page.Window.window;objectName:"settingsProfileImportDialog";title:"导入 Swirl 配置";nameFilters:["Swirl 配置 (*.json)"];onAccepted:extensionsProvider.importProfile(selectedFile)}
 FileDialog{id:profileExport;parentWindow:page.Window.window;objectName:"settingsProfileExportDialog";title:"导出 Swirl 配置";fileMode:FileDialog.SaveFile;nameFilters:["Swirl 配置 (*.json)"];defaultSuffix:"json";onAccepted:extensionsProvider.exportProfile(page.selectedId,selectedFile)}
 SwirlDialog{ownerItem:page;id:profileEditor;objectName:"localProfileEditor";title:"配置编辑器";width:Math.min(Theme.dp(760),page.width-Theme.dp(24));height:Math.min(Theme.dp(600),page.height-Theme.dp(24));property string profileId:""
  ColumnLayout{anchors.fill:parent;spacing:Theme.dp(10)
   SwirlTextField{id:profileName;Layout.fillWidth:true;placeholderText:"配置名称"}
   SwirlComboBox{id:profileMode;model:["rule","global","direct"];Layout.fillWidth:true}
   SwirlText {text:"JSON 字段：dns、rules、groups。保存后点击“使用配置”应用。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
   ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true;SwirlTextArea {id:profileSource;selectByMouse:true;textFormat:TextEdit.PlainText;font.family:Theme.codeFontFamily;font.pixelSize:Theme.fontSize(12);wrapMode:TextEdit.NoWrap}}
   SwirlText {text:extensionsProvider.error;textFormat:Text.PlainText;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
   RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:profileEditor.close()}SwirlButton{text:"保存";primary:true;enabled:profileName.text.trim().length>0;onClicked:{if(extensionsProvider.saveProfile(profileEditor.profileId,profileName.text,profileSource.text,profileMode.currentText))profileEditor.close()}}}
  }
 }
}

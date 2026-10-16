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
    readonly property Item motionTitle:routeTitle
property string selectedId:""
 readonly property var selected:extensionsProvider.profiles.find(r=>r.id===selectedId)||null
 function editProfile(fresh){profileEditor.profileId=fresh?"":selectedId;profileName.text=fresh?"":selected.name;profileSource.text=JSON.stringify(fresh?engineController.networkConfigurationSnapshot():selected.network,null,2);profileMode.currentIndex=["rule","global","direct"].indexOf(fresh?engineController.routingMode:selected.mode);profileEditor.open()}
 ColumnLayout{anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(12)
  SwirlText {id:routeTitle;text:"配置";color:Theme.text;font.pixelSize:Theme.fontSize(24);font.weight:Font.DemiBold}
  SwirlText {text:"当前配置："+extensionsProvider.profileName;color:Theme.text;font.pixelSize:Theme.fontSize(14);textFormat:Text.PlainText}
  SwirlText {text:"管理 Swirl 的 DNS、规则、策略组和出站模式。切换配置前先断开引擎。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  SwirlDataTable{objectName:"localProfileTable";Layout.fillWidth:true;Layout.fillHeight:true;fillEmptyRows:true;rows:extensionsProvider.profiles;selectedId:page.selectedId;columns:[{key:"name",label:"名称",w:260},{key:"mode",label:"出站模式",w:140}];onRowSelected:r=>page.selectedId=r.id}
  SwirlText {text:extensionsProvider.error;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap;textFormat:Text.PlainText}
  RowLayout{Layout.fillWidth:true;spacing:Theme.dp(8)
   SwirlButton{objectName:"profileAddButton";text:"+";implicitWidth:Theme.dp(40);onClicked:page.editProfile(true)}
   SwirlButton{text:"−";implicitWidth:Theme.dp(40);enabled:page.selected!==null;onClicked:extensionsProvider.removeProfile(page.selectedId)}
   SwirlButton{text:"导入…";onClicked:profileImport.open()}
   SwirlButton{text:"导出…";enabled:page.selected!==null;onClicked:profileExport.open()}
   Item{Layout.fillWidth:true}
   SwirlButton{text:"Default";enabled:engineController.canStart;onClicked:extensionsProvider.useProfile("")}
   SwirlButton{text:"编辑…";enabled:page.selected!==null;onClicked:page.editProfile(false)}
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
   ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true;TextArea { renderType: TextEdit.NativeRendering; font.weight: Theme.bodyFontWeight; font.hintingPreference: Font.PreferFullHinting; Binding on font.variableAxes { delayed:true; value:Theme.variableAxesFor(font.family,font.weight) }id:profileSource;selectByMouse:true;textFormat:TextEdit.PlainText;font.family:"Cascadia Code";font.pixelSize:Theme.fontSize(12);wrapMode:TextEdit.NoWrap}}
   SwirlText {text:extensionsProvider.error;textFormat:Text.PlainText;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
   RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:profileEditor.close()}SwirlButton{text:"保存";primary:true;enabled:profileName.text.trim().length>0;onClicked:{if(extensionsProvider.saveProfile(profileEditor.profileId,profileName.text,profileSource.text,profileMode.currentText))profileEditor.close()}}}
  }
 }
}

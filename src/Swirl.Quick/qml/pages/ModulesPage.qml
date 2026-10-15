pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;property string selectedId:""
 ColumnLayout{anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(12)
  RowLayout{Layout.fillWidth:true;SwirlText {text:"模块";color:Theme.text;font.pixelSize:Theme.fontSize(24);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton{objectName:"localModuleImport";text:"安装本地模块…";onClicked:moduleFile.open()}}
  SwirlText {text:"模块覆盖 DNS、规则和策略组；从上向下应用，底部模块优先。停用全部模块后恢复基础配置。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  ListView { pixelAligned: true;id:moduleList;objectName:"localModuleList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:Theme.dp(10);model:extensionsProvider.modules
   SwirlText {visible:moduleList.count===0;anchors.centerIn:parent;text:"没有已安装模块";color:Theme.muted;font.pixelSize:Theme.fontSize(16)}
   delegate:Rectangle{required property var modelData;required property int index;width:Math.floor(moduleList.width);height:Theme.dp(126);radius:Theme.cardRadius;color:page.selectedId===modelData.id?Theme.selected:Theme.field
    Column{x:Theme.dp(16);y:Theme.dp(16);width:parent.width-Theme.dp(84);spacing:Theme.dp(6)
     SwirlText {text:parent.parent.modelData.name;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(15);font.weight:Font.DemiBold}
     SwirlText {text:parent.parent.modelData.description;textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);width:parent.width;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
     SwirlText {text:Object.keys(parent.parent.modelData.overrides).join(" · ");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
    }
    SwirlToggle{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(16);checked:parent.modelData.enabled;enabled:engineController.canStart;onToggled:{const row=parent.modelData;extensionsProvider.setModuleEnabled(row.id,checked);checked=Qt.binding(()=>parent.modelData.enabled)}}
    MouseArea{anchors.fill:parent;anchors.rightMargin:Theme.dp(70);onClicked:page.selectedId=parent.modelData.id}
   }
  }
  SwirlText {text:extensionsProvider.error||(!engineController.canStart?"请先断开引擎，再更改模块状态和生效顺序。":"");color:Theme.orange;font.pixelSize:Theme.fontSize(12);textFormat:Text.PlainText;Layout.fillWidth:true;wrapMode:Text.WordWrap}
  RowLayout{SwirlButton{text:"上移";enabled:page.selectedId.length>0&&engineController.canStart;onClicked:extensionsProvider.moveModule(page.selectedId,-1)}SwirlButton{text:"下移";enabled:page.selectedId.length>0&&engineController.canStart;onClicked:extensionsProvider.moveModule(page.selectedId,1)}SwirlButton{text:"移除";enabled:page.selectedId.length>0&&engineController.canStart;onClicked:extensionsProvider.removeModule(page.selectedId)}}
 }
 FileDialog{id:moduleFile;title:"安装 Swirl 本地配置模块";nameFilters:["Swirl 配置模块 (*.json)"];onAccepted:extensionsProvider.importModule(selectedFile)}
}

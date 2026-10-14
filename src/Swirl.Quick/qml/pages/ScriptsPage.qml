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
 readonly property var selected:extensionsProvider.scripts.find(r=>r.id===selectedId)||null
 function editScript(fresh){scriptEditor.scriptId=fresh?"":selectedId;scriptName.text=fresh?"":selected.name;scriptCode.text=fresh?"function main(input) {\n    console.log('Swirl local script');\n    return input;\n}\n":selected.source;scriptInput.text="{}";scriptEditor.open()}
 ColumnLayout{anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(12)
  Text{text:"脚本";color:Theme.text;font.pixelSize:Theme.fontSize(24);font.weight:Font.DemiBold}
  Text{text:"本地 JavaScript 脚本在独立进程中执行，输入和结果使用 JSON。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  SwirlDataTable{objectName:"localScriptTable";Layout.fillWidth:true;Layout.fillHeight:true;fillEmptyRows:true;rows:extensionsProvider.scripts;selectedId:page.selectedId;columns:[{key:"type",label:"类型",w:140},{key:"name",label:"名称",w:260}];onRowSelected:r=>page.selectedId=r.id}
  Text{text:extensionsProvider.error;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap;textFormat:Text.PlainText}
  RowLayout{Layout.fillWidth:true;spacing:Theme.dp(8)
   SwirlButton{objectName:"scriptAddButton";text:"+";implicitWidth:Theme.dp(40);enabled:!extensionsProvider.busy;onClicked:page.editScript(true)}
   SwirlButton{text:"−";implicitWidth:Theme.dp(40);enabled:page.selected!==null&&!extensionsProvider.busy;onClicked:extensionsProvider.removeScript(page.selectedId)}
   SwirlButton{text:"导入本地脚本…";enabled:!extensionsProvider.busy;onClicked:scriptFile.open()}
   Item{Layout.fillWidth:true}
   SwirlButton{text:"Script Editor…";enabled:page.selected!==null&&!extensionsProvider.busy;onClicked:page.editScript(false)}
  }
 }
 FileDialog{id:scriptFile;title:"导入本地 JavaScript";nameFilters:["JavaScript (*.js)"];onAccepted:extensionsProvider.importScript(selectedFile)}
 SwirlDialog{id:scriptEditor;objectName:"localScriptEditor";title:"Script Editor";width:Math.min(Theme.dp(780),page.width-Theme.dp(24));height:Math.min(Theme.dp(650),page.height-Theme.dp(24));property string scriptId:""
  ColumnLayout{anchors.fill:parent;spacing:Theme.dp(8)
   SwirlTextField{id:scriptName;objectName:"localScriptName";Layout.fillWidth:true;placeholderText:"脚本名称";enabled:!extensionsProvider.busy}
   Text{text:"定义 function main(input)，返回 JSON 可表示的值；可使用 console.log。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.WordWrap}
   ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true;TextArea{id:scriptCode;objectName:"localScriptSource";textFormat:TextEdit.PlainText;font.family:"Cascadia Code";font.pixelSize:Theme.fontSize(12);selectByMouse:true;readOnly:extensionsProvider.busy;wrapMode:TextEdit.NoWrap;JavascriptHighlighter{qmlDocument:scriptCode.textDocument}}}
   Text{text:"输入 JSON";color:Theme.text;font.pixelSize:Theme.fontSize(12)}
   ScrollView{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(60);clip:true;TextArea{id:scriptInput;objectName:"localScriptInput";textFormat:TextEdit.PlainText;font.family:"Cascadia Code";font.pixelSize:Theme.fontSize(12);selectByMouse:true;readOnly:extensionsProvider.busy}}
   ScrollView{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(100);clip:true;TextArea{text:extensionsProvider.error||extensionsProvider.output;textFormat:TextEdit.PlainText;readOnly:true;selectByMouse:true;font.family:"Cascadia Code";font.pixelSize:Theme.fontSize(12)}}
   RowLayout{Layout.alignment:Qt.AlignRight
    SwirlButton{text:"关闭";onClicked:scriptEditor.close()}
    SwirlButton{objectName:"localScriptSave";text:"保存";enabled:!extensionsProvider.busy&&scriptName.text.trim().length>0;onClicked:{if(extensionsProvider.saveScript(scriptEditor.scriptId,scriptName.text,scriptCode.text)){const row=extensionsProvider.scripts.find(r=>r.name===scriptName.text.trim());if(row){scriptEditor.scriptId=row.id;page.selectedId=row.id}}}}
    SwirlButton{objectName:"localScriptRun";text:extensionsProvider.busy?"执行中…":"Evaluate";primary:true;enabled:!extensionsProvider.busy&&scriptEditor.scriptId.length>0;onClicked:{if(extensionsProvider.saveScript(scriptEditor.scriptId,scriptName.text,scriptCode.text))extensionsProvider.runScript(scriptEditor.scriptId,scriptInput.text)}}
   }
  }
 }
}

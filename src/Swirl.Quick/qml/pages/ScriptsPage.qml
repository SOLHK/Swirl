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
 readonly property var shownScripts:extensionsProvider.scripts.filter(function(row){return (row.name+" "+row.type).toLowerCase().indexOf(scriptSearch.text.trim().toLowerCase())>=0})
 readonly property string executionPhase:extensionsProvider.busy?"pending":extensionsProvider.error.length?"failed":extensionsProvider.output.length?"succeeded":"idle"
 readonly property var selected:extensionsProvider.scripts.find(r=>r.id===selectedId)||null
 function editScript(fresh){scriptEditor.scriptId=fresh?"":selectedId;scriptName.text=fresh?"":selected.name;scriptCode.text=fresh?"function main(input) {\n    console.log('Swirl local script');\n    return input;\n}\n":selected.source;scriptInput.text="{}";scriptEditor.open()}
 ColumnLayout{anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
  SwirlPageHeader{id:pageHeader;Layout.fillWidth:true;title:qsTr("本地脚本");description:qsTr("在独立进程中运行 JavaScript，使用 JSON 传递输入与结果。");metadata:qsTr("%1 个已保存脚本").arg(extensionsProvider.scripts.length)
   SwirlButton{objectName:"scriptAddButton";text:qsTr("新建脚本");primary:true;enabled:!extensionsProvider.busy;onClicked:page.editScript(true)}
   SwirlButton{text:qsTr("导入本地脚本");enabled:!extensionsProvider.busy;onClicked:scriptFile.open()}
  }
  Rectangle{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
  SwirlSearchField{id:scriptSearch;Layout.fillWidth:true;placeholderText:qsTr("搜索脚本名称或类型");Accessible.name:placeholderText}
  Item{Layout.fillWidth:true;Layout.fillHeight:true
  SwirlDataTable{objectName:"localScriptTable";incrementalRows:true;animateRowChanges:true;anchors.fill:parent;fillEmptyRows:false;rows:page.shownScripts;selectedId:page.selectedId;columns:[{key:"type",label:"类型",w:140},{key:"name",label:"名称",w:260}];onRowSelected:r=>page.selectedId=r.id}
   SwirlEmptyState{anchors.centerIn:parent;width:parent.width;visible:page.shownScripts.length===0;headline:scriptSearch.text.length?qsTr("没有匹配结果"):qsTr("还没有本地脚本");detail:qsTr("新建脚本后，可在独立进程中运行并查看 JSON 结果。")}
  }
  SwirlText {visible:text.length>0;text:extensionsProvider.error;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap;textFormat:Text.PlainText}
  RowLayout{Layout.fillWidth:true;spacing:Theme.dp(8)
   SwirlButton{text:qsTr("移除所选");enabled:page.selected!==null&&!extensionsProvider.busy;onClicked:extensionsProvider.removeScript(page.selectedId)}
   Item{Layout.fillWidth:true}
   SwirlButton{text:qsTr("编辑脚本");enabled:page.selected!==null&&!extensionsProvider.busy;onClicked:page.editScript(false)}
  }
 }
 FileDialog{id:scriptFile;parentWindow:page.Window.window;objectName:"settingsScriptFileDialog";title:"导入本地 JavaScript";nameFilters:["JavaScript (*.js)"];onAccepted:extensionsProvider.importScript(selectedFile)}
 SwirlDialog{ownerItem:page;id:scriptEditor;objectName:"localScriptEditor";title:qsTr("脚本编辑器");width:Math.min(Theme.dp(780),page.width-Theme.dp(24));height:Math.min(Theme.dp(650),page.height-Theme.dp(24));property string scriptId:""
  ColumnLayout{anchors.fill:parent;spacing:Theme.dp(8)
   SwirlTextField{id:scriptName;objectName:"localScriptName";Layout.fillWidth:true;placeholderText:"脚本名称";enabled:!extensionsProvider.busy}
   SwirlText {text:"定义 function main(input)，返回 JSON 可表示的值；可使用 console.log。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.WordWrap}
   ScrollView{Layout.fillWidth:true;Layout.fillHeight:true;clip:true;SwirlTextArea {id:scriptCode;objectName:"localScriptSource";textFormat:TextEdit.PlainText;font.family:Theme.codeFontFamily;font.pixelSize:Theme.fontSize(12);selectByMouse:true;readOnly:extensionsProvider.busy;wrapMode:TextEdit.NoWrap;JavascriptHighlighter{qmlDocument:scriptCode.textDocument}}}
   SwirlText {text:"输入 JSON";color:Theme.text;font.pixelSize:Theme.fontSize(12)}
   ScrollView{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(60);clip:true;SwirlTextArea {id:scriptInput;objectName:"localScriptInput";textFormat:TextEdit.PlainText;font.family:Theme.codeFontFamily;font.pixelSize:Theme.fontSize(12);selectByMouse:true;readOnly:extensionsProvider.busy}}
   ScrollView{Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(100);clip:true;SwirlTextArea {text:extensionsProvider.error||extensionsProvider.output;textFormat:TextEdit.PlainText;readOnly:true;selectByMouse:true;font.family:Theme.codeFontFamily;font.pixelSize:Theme.fontSize(12)}}
   RowLayout{Layout.alignment:Qt.AlignRight
    SwirlFlow{objectName:"scriptExecutionFlow";phase:page.executionPhase;Layout.preferredWidth:Theme.dp(48);Layout.preferredHeight:Theme.dp(20)}
    SwirlButton{text:"完成";onClicked:scriptEditor.requestDismiss()}
    SwirlButton{objectName:"localScriptSave";text:"保存";enabled:!extensionsProvider.busy&&scriptName.text.trim().length>0;onClicked:{if(extensionsProvider.saveScript(scriptEditor.scriptId,scriptName.text,scriptCode.text)){const row=extensionsProvider.scripts.find(r=>r.name===scriptName.text.trim());if(row){scriptEditor.scriptId=row.id;page.selectedId=row.id;scriptEditor.markSaved()}}}}
    SwirlButton{objectName:"localScriptRun";text:extensionsProvider.busy?qsTr("执行中…"):qsTr("运行脚本");primary:true;enabled:!extensionsProvider.busy&&scriptEditor.scriptId.length>0;onClicked:{if(extensionsProvider.saveScript(scriptEditor.scriptId,scriptName.text,scriptCode.text))extensionsProvider.runScript(scriptEditor.scriptId,scriptInput.text)}}
   }
  }
 }
}

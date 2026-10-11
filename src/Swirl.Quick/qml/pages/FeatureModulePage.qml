import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string moduleId:""
    readonly property var feature:FeatureCatalog.find(moduleId)
    property var settings:({})
    property var records:[]
    property int tab:0
    property bool dirty:false
    property string savedAt:""
    property int editing:-1
    property int revision:0
    function restore() {
        var draft=moduleDrafts.load(moduleId)
        settings=draft.settings || {};records=draft.records || [];savedAt=draft.savedAt || "";dirty=false;revision++
    }
    function update(key,value) {var next=Object.assign({},settings);next[key]=value;settings=next;dirty=true}
    function draft() {return {settings:settings,records:records,savedAt:Qt.formatDateTime(new Date(),"yyyy-MM-dd HH:mm:ss")}}
    function save() {var data=draft();if(moduleDrafts.save(moduleId,data)){savedAt=data.savedAt;dirty=false;AppState.toast="模块草稿已保存，未启用网络服务。"}else AppState.toast=moduleDrafts.lastError}
    function reorder(index,step) {var next=records.slice();var other=index+step;if(other<0 || other>=next.length)return;var row=next[index];next[index]=next[other];next[other]=row;records=next;dirty=true}
    onModuleIdChanged:if(moduleId.length)restore()
    ColumnLayout {
        anchors.fill:parent;spacing:14
        RowLayout {
            Layout.fillWidth:true;Layout.topMargin:12;spacing:15
            SwirlIconButton {iconName:"chevron-left";tooltip:"功能模块中心";onClicked:AppState.navigate("featurehub")}
            ColumnLayout {
                Layout.fillWidth:true;spacing:5
                Text {text:page.feature ? page.feature.title : "功能模块";font.pixelSize:25;font.weight:Font.DemiBold;color:Theme.text}
                Text {text:page.feature ? page.feature.sub : "";font.pixelSize:14;color:Theme.muted;Layout.fillWidth:true;elide:Text.ElideRight}
            }
            SwirlButton {text:"导入草稿";font.pixelSize:14;onClicked:importDialog.open()}
            SwirlButton {text:"导出草稿";font.pixelSize:14;onClicked:exportDialog.open()}
            SwirlButton {objectName:"moduleSaveButton";text:"保存草稿";font.pixelSize:14;primary:true;onClicked:page.save()}
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSegmentedControl {implicitWidth:285;options:["配置","条目","说明"];currentIndex:page.tab;onActivated:function(index){page.tab=index}}
            Item {Layout.fillWidth:true}
            Text {text:page.dirty ? "尚未保存" : page.savedAt.length ? "已保存 · "+page.savedAt : "未接入 · 本地界面草稿";color:Theme.muted;font.pixelSize:13}
        }
        SwirlGlassPanel {
            Layout.fillWidth:true;Layout.fillHeight:true
            ScrollView {
                id:formScroll;anchors.fill:parent;anchors.margins:22;clip:true;visible:page.tab===0
                ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {
                    width:formScroll.availableWidth;spacing:16
                    Text {text:"配置只保存到本机界面草稿。当前不会设置代理、安装证书、创建网卡或启动此模块的服务。";color:Theme.muted;font.pixelSize:14;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                    Repeater {
                        model:page.feature ? page.feature.fields : []
                        RowLayout {
                            required property var modelData
                            Layout.fillWidth:true;spacing:24
                            Text {text:modelData.label;color:Theme.text;font.pixelSize:16;Layout.preferredWidth:175;wrapMode:Text.WordWrap}
                            Loader {
                                Layout.fillWidth:true;Layout.preferredHeight:44
                                property var field:modelData
                                sourceComponent:field.kind==="toggle" ? toggleField : field.kind==="choice" ? choiceField : textField
                            }
                        }
                    }
                    Rectangle {Layout.fillWidth:true;height:1;color:Theme.border}
                    Text {text:"凭据字段填写引用名称即可；此草稿存储不适合保存实际密码或私钥。";color:Theme.muted;font.pixelSize:13;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                }
            }
            ColumnLayout {
                anchors.fill:parent;anchors.margins:22;spacing:14;visible:page.tab===1
                RowLayout {
                    Layout.fillWidth:true
                    Text {text:"条目与优先级 · "+page.records.length+" 项";color:Theme.text;font.pixelSize:18;Layout.fillWidth:true}
                    SwirlButton {objectName:"moduleAddButton";text:"添加条目";primary:true;font.pixelSize:15;onClicked:{page.editing=-1;nameField.text="";valueField.text="";rowDialog.open()}}
                }
                ListView {
                    Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:8;model:page.records
                    delegate:Rectangle {
                        required property int index
                        required property var modelData
                        width:ListView.view.width;height:72;radius:Theme.controlRadius;color:Theme.material("field")
                        RowLayout {
                            anchors.fill:parent;anchors.margins:12;spacing:12
                            SwirlToggle {checked:modelData.enabled!==false;onToggled:{var rows=page.records.slice();rows[index]=Object.assign({},modelData,{enabled:checked});page.records=rows;page.dirty=true}}
                            ColumnLayout {Layout.fillWidth:true;spacing:3;Text {text:modelData.name || "未命名";color:Theme.text;font.pixelSize:16}Text {text:modelData.value || "—";color:Theme.muted;font.pixelSize:13;Layout.fillWidth:true;elide:Text.ElideRight}}
                            SwirlButton {text:"↑";quiet:true;implicitWidth:36;enabled:index>0;onClicked:page.reorder(index,-1)}
                            SwirlButton {text:"↓";quiet:true;implicitWidth:36;enabled:index<page.records.length-1;onClicked:page.reorder(index,1)}
                            SwirlButton {text:"编辑";quiet:true;font.pixelSize:14;onClicked:{page.editing=index;nameField.text=modelData.name;valueField.text=modelData.value;rowDialog.open()}}
                            SwirlButton {text:"删除";quiet:true;danger:true;font.pixelSize:14;onClicked:{page.records=page.records.filter(function(r,i){return i!==index});page.dirty=true}}
                        }
                    }
                    Text {visible:page.records.length===0;anchors.centerIn:parent;text:"暂无条目，点击添加建立配置草稿。";color:Theme.muted;font.pixelSize:16}
                }
            }
            ColumnLayout {
                anchors.fill:parent;anchors.margins:26;spacing:17;visible:page.tab===2
                SwirlIcon {name:page.feature ? page.feature.icon : "grid";size:38;color:Theme.accent}
                Text {text:"模块界面已具备，实际功能待接入";font.pixelSize:22;font.weight:Font.DemiBold;color:Theme.text}
                Text {text:page.feature ? page.feature.sub : "";color:Theme.muted;font.pixelSize:16;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                Text {text:"可以编辑参数、增删条目、调整优先级、切换草稿启停、保存以及导入导出 JSON。这里的启用选项仅表示草稿意图，不代表操作系统或网络服务已经开启。";color:Theme.muted;font.pixelSize:15;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                Text {text:"Apple / 移动平台专有能力保留参考模块，Windows 的实际实现方式需后续确定。";color:Theme.muted;font.pixelSize:15;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                Item {Layout.fillHeight:true}
            }
        }
    }
    Component {id:textField;SwirlTextField {objectName:"moduleField-"+field.key;font.pixelSize:16;text:{page.revision;return page.settings[field.key] || ""}placeholderText:"填写"+field.label;onTextEdited:page.update(field.key,text)}}
    Component {id:choiceField;SwirlComboBox {model:field.options;currentIndex:Math.max(0,field.options.indexOf(page.settings[field.key] || ""));onActivated:page.update(field.key,currentText)}}
    Component {id:toggleField;Item {SwirlToggle {objectName:field.key==="f0" ? "moduleFirstToggle" : "";anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;checked:page.settings[field.key]===true;onToggled:page.update(field.key,checked)}}}
    SwirlDialog {
        id:rowDialog;title:page.editing<0 ? "添加配置条目" : "编辑配置条目"
        ColumnLayout {
            width:parent.width;spacing:14
            SwirlTextField {id:nameField;objectName:"moduleEntryName";Layout.fillWidth:true;placeholderText:"名称 / 匹配条件"}
            SwirlTextField {id:valueField;objectName:"moduleEntryValue";Layout.fillWidth:true;placeholderText:"值 / 动作 / 目标"}
            RowLayout {Layout.alignment:Qt.AlignRight;SwirlButton {text:"取消";onClicked:rowDialog.close()}SwirlButton {objectName:"moduleEntryConfirm";text:"确定";primary:true;enabled:nameField.text.trim().length>0;onClicked:{var rows=page.records.slice();var record={name:nameField.text.trim(),value:valueField.text,enabled:page.editing>=0 ? rows[page.editing].enabled : true};if(page.editing<0)rows.push(record);else rows[page.editing]=record;page.records=rows;page.dirty=true;rowDialog.close()}}}
        }
    }
    FileDialog {id:exportDialog;title:"导出模块界面草稿";fileMode:FileDialog.SaveFile;nameFilters:["Swirl 草稿 (*.json)"];defaultSuffix:"json";onAccepted:{if(moduleDrafts.exportFile(selectedFile,page.moduleId,page.draft()))AppState.toast="草稿已导出";else AppState.toast=moduleDrafts.lastError}}
    FileDialog {id:importDialog;title:"导入模块界面草稿";fileMode:FileDialog.OpenFile;nameFilters:["Swirl 草稿 (*.json)"];onAccepted:{var data=moduleDrafts.importFile(selectedFile,page.moduleId);if(!moduleDrafts.lastError.length){page.settings=data.settings;page.records=data.records;page.dirty=true;page.revision++;AppState.toast="已导入草稿，尚未启用网络服务"}else AppState.toast=moduleDrafts.lastError}}
}

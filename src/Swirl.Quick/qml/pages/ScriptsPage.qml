import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string selectedScript:"response-transform.js"
    property var scripts:["response-transform.js","request-headers.js","on-network-change.js","daily-cleanup.js"]
    property string consoleText:"[14:08:01] Script console ready (demonstration)\n[14:08:02] No JavaScript runtime attached"
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:12
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"JavaScript · 仅界面演示"; tone:"accent" }
            Text { text:"可以编辑源码，不会实际运行脚本。"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"导入"; iconName:"folder"; onClicked:AppState.notice("导入脚本") }
            SwirlButton { text:"新建脚本"; primary:true; onClicked:newDialog.open() }
        }
        SplitView {
            Layout.fillWidth:true; Layout.fillHeight:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:7; color:Theme.canvas }
            SwirlGlassPanel {
                SplitView.preferredWidth:240; SplitView.minimumWidth:175
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:14; spacing:12
                    Text { text:"脚本库"; color:Theme.text; font.pixelSize:15; font.weight:Font.DemiBold }
                    SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"搜索脚本" }
                    ListView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        clip:true
                        spacing:5
                        model:page.scripts.filter(function(s){return s.toLowerCase().indexOf(search.text.toLowerCase())>=0})
                        delegate:Rectangle {
                            width:ListView.view.width; height:43; radius:9
                            color:page.selectedScript===modelData?Theme.selected:area.containsMouse?Theme.hover:"transparent"
                            RowLayout {
                                anchors.fill:parent; anchors.leftMargin:10; anchors.rightMargin:7
                                SwirlIcon { name:"code"; size:16; color:Theme.muted }
                                Text { text:modelData; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true; elide:Text.ElideRight }
                            }
                            MouseArea { id:area; anchors.fill:parent; hoverEnabled:true; onClicked:page.selectedScript=modelData }
                        }
                    }
                    SwirlButton { Layout.fillWidth:true; text:"脚本设置"; onClicked:AppState.notice("脚本设置") }
                }
            }
            SwirlGlassPanel {
                SplitView.fillWidth:true; SplitView.minimumWidth:300
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:15; spacing:11
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:page.selectedScript; color:Theme.text; font.pixelSize:14; font.weight:Font.DemiBold; Layout.fillWidth:true; elide:Text.ElideRight }
                        SwirlStatusBadge { label:"可编辑演示"; tone:"success" }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlComboBox { model:["响应脚本","请求脚本","定时脚本","网络事件"] }
                        Item { Layout.fillWidth:true }
                        SwirlButton { text:"保存预览"; onClicked:AppState.notice("保存脚本") }
                        SwirlButton {
                            text:"运行"; primary:true; iconName:"play"
                            onClicked:{
                                page.consoleText+="\n[demo] Run requested; backend not connected."
                                AppState.notice("脚本执行")
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10
                        color:Theme.dark?"#121B29":"#F6F8FC"
                        border.color:Theme.border
                        RowLayout {
                            anchors.fill:parent; anchors.margins:8; spacing:0
                            Text {
                                Layout.alignment:Qt.AlignTop
                                Layout.preferredWidth:35
                                text:"1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12"
                                color:Theme.muted
                                font.family:"Cascadia Code"
                                font.pixelSize:12
                                lineHeight:1.35
                                horizontalAlignment:Text.AlignRight
                            }
                            Rectangle { Layout.fillHeight:true; width:1; color:Theme.border }
                            ScrollView {
                                Layout.fillWidth:true; Layout.fillHeight:true
                                TextArea {
                                    id:editor
                                    text:"// Swirl JavaScript demo\n// Editing is local to this preview.\n\nconst requestId = $request?.url;\nconst headers = {\n  'X-Swirl-Preview': 'true'\n};\n\n// No runtime is connected.\nconsole.log(requestId);\n$done({ headers });"
                                    color:Theme.text
                                    selectionColor:Theme.accent
                                    selectedTextColor:"white"
                                    font.family:"Cascadia Code"
                                    font.pixelSize:12
                                    wrapMode:TextEdit.NoWrap
                                    tabStopDistance:32
                                    background:Rectangle { color:"transparent" }
                                    JavascriptHighlighter { qmlDocument:editor.textDocument }
                                    selectByMouse:true
                                }
                            }
                        }
                    }
                    Text { text:"原生 C++ 语法高亮 · 仅本地编辑"; color:Theme.muted; font.pixelSize:11 }
                }
            }
            SwirlGlassPanel {
                SplitView.preferredWidth:270; SplitView.minimumWidth:200
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:15; spacing:12
                    Text { text:"执行与调试"; color:Theme.text; font.pixelSize:15; font.weight:Font.DemiBold }
                    Text { text:"Type     HTTP Response\nStatus   Not connected\nLast run Never"; color:Theme.muted; lineHeight:1.6; font.pixelSize:12 }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:"控制台"; color:Theme.text; font.pixelSize:13; font.weight:Font.DemiBold }
                    ScrollView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        TextArea {
                            readOnly:true
                            text:page.consoleText
                            color:Theme.muted
                            font.pixelSize:11
                            font.family:"Cascadia Code"
                            wrapMode:Text.WrapAnywhere
                            background:Rectangle { color:Theme.field; radius:8 }
                        }
                    }
                    SwirlButton { Layout.fillWidth:true; text:"清空控制台"; onClicked:page.consoleText="" }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"新建脚本预览"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"脚本文件名"; color:Theme.text }
            SwirlTextField { id:newName; Layout.fillWidth:true; placeholderText:"example.js" }
            Text { text:newName.text.trim().endsWith(".js")?"仅供演示，不会保存文件。":"文件名必须以 .js 结尾"; color:Theme.muted; font.pixelSize:12 }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"取消"; onClicked:newDialog.close() }
                SwirlButton {
                    primary:true; text:"创建"
                    enabled:newName.text.trim().length>3 && newName.text.trim().endsWith(".js")
                    onClicked:{
                        page.scripts=page.scripts.concat([newName.text.trim()])
                        page.selectedScript=newName.text.trim()
                        newDialog.close()
                    }
                }
            }
        }
    }
}
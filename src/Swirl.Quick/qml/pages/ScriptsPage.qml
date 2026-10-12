import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    readonly property bool implemented:false
    property string selectedScript: ""
    property var scripts:[]
    property string consoleText: ""
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(12)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"JavaScript · 仅界面"; tone:"accent" }
            Text { text:"可以编辑源码，不会实际运行脚本。"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:"导入"; iconName:"folder"; onClicked:AppState.notice("导入脚本") }
            SwirlButton { enabled:false; text:"新建脚本"; primary:true; onClicked:newDialog.open() }
        }
        SplitView {
            Layout.fillWidth:true; Layout.fillHeight:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:Theme.dp(7); color:Theme.canvas }
            SwirlGlassPanel {
                SplitView.preferredWidth:Theme.dp(240); SplitView.minimumWidth:Theme.dp(175)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(14); spacing:Theme.dp(12)
                    Text { text:"脚本库"; color:Theme.text; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold }
                    SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"搜索脚本" }
                    ListView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        clip:true
                        spacing:Theme.dp(5)
                        model:page.scripts.filter(function(s){return s.toLowerCase().indexOf(search.text.toLowerCase())>=0})
                        delegate:Rectangle {
                            width:ListView.view.width; height:Theme.dp(43); radius:Theme.roundedRadius(width,height)
                            color:page.selectedScript===modelData?Theme.selected:area.containsMouse?Theme.hover:"transparent"
                            RowLayout {
                                anchors.fill:parent; anchors.leftMargin:Theme.dp(10); anchors.rightMargin:Theme.dp(7)
                                SwirlIcon { name:"code"; size:Theme.dp(16); color:Theme.muted }
                                Text { text:modelData; color:Theme.text; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; elide:Text.ElideRight }
                            }
                            MouseArea { id:area; anchors.fill:parent; hoverEnabled:true; onClicked:page.selectedScript=modelData }
                        }
                    }
                    SwirlButton { enabled:false; Layout.fillWidth:true; text:"脚本设置"; onClicked:AppState.notice("脚本设置") }
                }
            }
            SwirlGlassPanel {
                SplitView.fillWidth:true; SplitView.minimumWidth:Theme.dp(300)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(15); spacing:Theme.dp(11)
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:page.selectedScript; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold; Layout.fillWidth:true; elide:Text.ElideRight }
                        SwirlStatusBadge { label:"可编辑"; tone:"success" }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlComboBox { model:["响应脚本","请求脚本","定时脚本","网络事件"] }
                        Item { Layout.fillWidth:true }
                        SwirlButton { enabled:false; text:"保存预览"; onClicked:AppState.notice("保存脚本") }
                        SwirlButton { enabled:false;
                            text:"运行"; primary:true; iconName:"play"
                            onClicked:AppState.notice("尚未实现")
                        }
                    }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height)
                        color:Theme.dark?"#121B29":"#F6F8FC"
                        border.color:Theme.border
                        RowLayout {
                            anchors.fill:parent; anchors.margins:Theme.dp(8); spacing:Theme.dp(0)
                            Text {
                                Layout.alignment:Qt.AlignTop
                                Layout.preferredWidth:Theme.dp(35)
                                text:"1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12"
                                color:Theme.muted
                                font.family:"Cascadia Code"
                                font.pixelSize:Theme.fontSize(12)
                                lineHeight:1.35
                                horizontalAlignment:Text.AlignRight
                            }
                            Rectangle { Layout.fillHeight:true; width:Theme.dp(1); color:Theme.border }
                            ScrollView {
                                Layout.fillWidth:true; Layout.fillHeight:true
                                TextArea {
                                    id:editor
                                    text:"";readOnly:true
                                    color:Theme.text
                                    selectionColor:Theme.accent
                                    selectedTextColor:"white"
                                    font.family:"Cascadia Code"
                                    font.pixelSize:Theme.fontSize(12)
                                    wrapMode:TextEdit.NoWrap
                                    tabStopDistance:32
                                    background:Rectangle { color:"transparent" }
                                    JavascriptHighlighter { qmlDocument:editor.textDocument }
                                    selectByMouse:true
                                }
                            }
                        }
                    }
                    Text { text:"原生 C++ 语法高亮 · 仅本地编辑"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                }
            }
            SwirlGlassPanel {
                SplitView.preferredWidth:Theme.dp(270); SplitView.minimumWidth:Theme.dp(200)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(15); spacing:Theme.dp(12)
                    Text { text:"执行与调试"; color:Theme.text; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold }
                    Text { text:"类型     HTTP 响应\n状态     未连接\n上次运行 从未"; color:Theme.muted; lineHeight:1.6; font.pixelSize:Theme.fontSize(12) }
                    Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                    Text { text:"控制台"; color:Theme.text; font.pixelSize:Theme.fontSize(13); font.weight:Font.DemiBold }
                    ScrollView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        TextArea {
                            readOnly:true
                            text:page.consoleText
                            color:Theme.muted
                            font.pixelSize:Theme.fontSize(11)
                            font.family:"Cascadia Code"
                            wrapMode:Text.WrapAnywhere
                            background:Rectangle { color:Theme.field; radius:Theme.roundedRadius(width,height) }
                        }
                    }
                    SwirlButton { enabled:false; Layout.fillWidth:true; text:"清空控制台"; onClicked:page.consoleText="" }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"新建脚本预览"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:"脚本文件名"; color:Theme.text }
            SwirlTextField { id:newName; Layout.fillWidth:true; placeholderText:"example.js" }
            Text { text:newName.text.trim().endsWith(".js")?"仅在当前页面创建，不会保存文件。":"文件名必须以 .js 结尾"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:"取消"; onClicked:newDialog.close() }
                SwirlButton { enabled:false;
                    primary:true; text:"创建"

                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}

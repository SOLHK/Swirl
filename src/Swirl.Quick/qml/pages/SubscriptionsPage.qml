import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:true
    property var chosen:null
    Connections {target:engineController.imports;function onChanged(){if(page.chosen)page.chosen=page.providers.find(function(p){return p.id===page.chosen.id})||null}}
    property string editingId:""
    function edit(record){editingId=record?record.id:"";displayName.text=record?record.name:"";urlField.text="";interval.currentIndex=record?Math.max(0,[360,720,1440,10080].indexOf(record.intervalMinutes)):0;autoEnabled.checked=record?record.enabled:true;addDialog.open()}
    readonly property var providers:engineController.imports.providers
    readonly property var listed:providers.filter(function(r){
        return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("订阅管理 · "); tone:"accent" }
            Text { text:engineController.imports.message||"订阅地址由 DPAPI 加密；更新失败保留旧节点";elide:Text.ElideRight; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:!engineController.imports.busy; text:"更新全部"; iconName:"refresh"; onClicked:engineController.imports.refreshAll() }
            SwirlButton { enabled:!engineController.imports.busy; text:"添加订阅"; primary:true; onClicked:page.edit(null) }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(12)
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search subscription providers") }
            Text { text:"每个订阅独立设置自动更新"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }


        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ScrollView {
                    id:scroll
                    anchors.fill:parent; anchors.margins:Theme.dp(16); clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                        width:scroll.availableWidth; spacing:Theme.dp(12)
                        Repeater {
                            model:page.listed
                            SwirlGlassPanel {
                                id:provider
                                property var record:modelData
                                Layout.fillWidth:true
                                Layout.preferredHeight:Math.max(Theme.dp(178),providerContent.implicitHeight+Theme.dp(30))
                                selected:page.chosen&&page.chosen.id===record.id
                                ColumnLayout {
                                    id:providerContent
                                    anchors.fill:parent; anchors.margins:Theme.dp(15); spacing:Theme.dp(9)
                                    RowLayout {
                                        Layout.fillWidth:true
                                        SwirlIcon { name:"refresh"; size:Theme.dp(18); color:Theme.accent }
                                        Text { text:record.name;textFormat:Text.PlainText; color:Theme.text; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold; Layout.fillWidth:true }
                                        SwirlStatusBadge { label:AppState.zh(record.status); tone:record.status==="已保存真实节点"?"success":"warning" }
                                    }
                                    Text { text:record.source; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; elide:Text.ElideMiddle }
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text {text:record.enabled?"自动更新 · "+record.intervalMinutes+" 分钟":"自动更新已关闭";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true}
                                        Text {text:record.nodes+" 个节点";color:Theme.text;font.pixelSize:Theme.fontSize(11)}
                                    }
                                    Text {text:record.error;visible:text.length>0;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(11)}
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text { text:AppState.zh("Updated ")+record.update; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
                                        SwirlButton { enabled:true; text:AppState.zh("Details"); implicitHeight:Theme.dp(32); quiet:false; onClicked:page.chosen=record }
                                        SwirlButton { enabled:!engineController.imports.busy; text:AppState.zh("Refresh"); implicitHeight:Theme.dp(32); iconName:"refresh"; onClicked:engineController.imports.refreshSubscription(record.id) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(284); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(13)
                    Text { text:AppState.zh("Provider inspector"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    Text {
                        text:page.chosen?page.chosen.name:"请选择订阅";textFormat:Text.PlainText
                        color:Theme.accent; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold
                        wrapMode:Text.WordWrap; Layout.fillWidth:true
                    }
                    Repeater {
                        model:[["STATUS",page.chosen?page.chosen.status:"—"],
                               ["NODES",page.chosen?String(page.chosen.nodes):"—"],
                               ["上次更新",page.chosen?page.chosen.update:"—"],
                               ["自动刷新",page.chosen?(page.chosen.enabled?page.chosen.intervalMinutes+" 分钟":"关闭"):"—"],
                               ["更新错误",page.chosen?page.chosen.error||"—":"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }

                        }
                    }

                    SwirlButton { enabled:page.chosen!==null&&!engineController.imports.busy; text:AppState.zh("编辑订阅源"); onClicked:page.edit(page.chosen) }
                    SwirlButton { enabled:page.chosen!==null&&!engineController.imports.busy; text:"删除订阅"; onClicked:{if(engineController.imports.removeSubscription(page.chosen.id))page.chosen=null} }

                }
            }
        }
    }
    SwirlDialog {
        id:addDialog;objectName:"subscriptionDialog"; title:"订阅来源";onClosed:urlField.text=""
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            ScrollView {id:subscriptionForm;Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(330),page.height*0.6);clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {width:subscriptionForm.availableWidth;spacing:Theme.dp(12)
            Text { text:AppState.zh("Display name"); color:Theme.text }
            SwirlTextField { id:displayName; Layout.fillWidth:true; placeholderText:AppState.zh("My subscription") }
            Text { text:"HTTPS 订阅地址"; color:Theme.text }
            SwirlTextField { id:urlField; Layout.fillWidth:true;echoMode:TextInput.Password; placeholderText:page.editingId.length?"留空保留已加密地址":"https://…";Accessible.name:"订阅地址" }
            Text { text:"应用运行时按设定间隔更新；只导入节点，不执行远程全局配置。"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.WordWrap }
            SwirlComboBox {id:interval;Layout.fillWidth:true;model:["每 6 小时","每 12 小时","每天","每周"];Accessible.name:"自动更新间隔"}
            RowLayout {Layout.fillWidth:true;Text {text:"自动更新";color:Theme.text;Layout.fillWidth:true}SwirlToggle {id:autoEnabled;checked:true}}
            Text {text:engineController.imports.message;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(11)}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("Cancel"); onClicked:addDialog.close() }
                SwirlButton { enabled:!engineController.imports.busy && displayName.text.trim().length>0 && (page.editingId.length>0 || urlField.text.trim().length>0);
                    text:"保存并更新"; primary:true
                    onClicked:{if(engineController.imports.saveSubscription(page.editingId,displayName.text,urlField.text.trim(),[360,720,1440,10080][interval.currentIndex],autoEnabled.checked)){var id=page.editingId||engineController.imports.providers[engineController.imports.providers.length-1].id;addDialog.close();engineController.imports.refreshSubscription(id)}}
                }
            }
        }
    }
}

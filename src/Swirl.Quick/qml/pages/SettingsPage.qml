import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string section:"外观"
    property var sections:["常规","外观","代理","TUN","DNS","端口","系统集成","启动","通知","数据管理","隐私与安全","快捷键","关于 Swirl"]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            Text { text:AppState.zh("Personalize how Swirl looks and behaves"); color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(15)
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(229); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(12); spacing:Theme.dp(8)
                    Text { text:AppState.zh("PREFERENCES"); color:Theme.muted; font.pixelSize:Theme.fontSize(11); leftPadding:Theme.dp(8); topPadding:Theme.dp(6) }
                    ListView {
                    add: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";from:0;to:1;duration:SwirlMotion.duration} }
                    remove: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} }
                    move: Transition {enabled:!SwirlMotion.reduced;SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration}}
                    displaced: Transition { enabled:!SwirlMotion.reduced; SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration} }
                        Layout.fillWidth:true; Layout.fillHeight:true
                        model:page.sections; clip:true; spacing:Theme.dp(3)
                        delegate:Rectangle {
                            width:ListView.view.width; height:Theme.dp(36); radius:Theme.roundedRadius(width,height)
                            color:page.section===modelData?Theme.selected:hover.containsMouse?Theme.hover:"transparent"
                            Text {
                                anchors.fill:parent; anchors.leftMargin:Theme.dp(11)
                                text:AppState.zh(modelData); color:Theme.text; font.pixelSize:Theme.fontSize(12)
                                verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight
                            }
                            MouseArea { id:hover; anchors.fill:parent; hoverEnabled:true; onClicked:page.section=modelData }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ScrollView {
                    id:options
                    anchors.fill:parent; anchors.margins:Theme.dp(24)
                    clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                        width:options.availableWidth; spacing:Theme.dp(17)
                        Text { text:AppState.zh(page.section); color:Theme.text; font.pixelSize:Theme.fontSize(23); font.weight:Font.DemiBold }
                        Text {
                            text:page.section==="外观"?"主题、窗口材质、动画与界面缩放。":page.section==="代理"?"引擎、真实节点与当前用户系统代理 · 国内外分流。":page.section==="关于 Swirl"?"版本与项目信息":"此项尚未实现。"
                            color:Theme.muted; wrapMode:Text.WordWrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12)
                        }
                        Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                        ColumnLayout {
                            visible:page.section==="外观"; spacing:Theme.dp(21); Layout.fillWidth:true
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Color theme"); color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                                    Text { text:AppState.zh("Choose light, dark or follow Windows"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                }
                                SwirlComboBox {
                                    model:["跟随系统","浅色","深色"]
                                    currentIndex:["System","Light","Dark"].indexOf(Theme.mode)
                                    onActivated:Theme.mode=["System","Light","Dark"][currentIndex]
                                }
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Windows backdrop material"); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                    Text { text:AppState.zh("Uses DWM on supported Windows 11 systems"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                }
                                SwirlToggle { checked:Theme.transparency; onToggled:Theme.transparency=checked }
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Reduce motion"); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                    Text { text:AppState.zh("Disable most transition animations"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                }
                                SwirlToggle { checked:Theme.reduceMotion; onToggled:Theme.reduceMotion=checked }
                            }
                            ColumnLayout {
                                Layout.fillWidth:true; spacing:Theme.dp(10)
                                RowLayout {
                                    Layout.fillWidth:true
                                    ColumnLayout {
                                        Layout.fillWidth:true
                                        Text { text:"界面缩放"; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                                        Text { text:Theme.followSystemScale?"自动跟随 Windows 显示缩放 · Qt 原生 DPI":"手动缩放 · "+Math.round(Theme.uiScale*100)+"%"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                    }
                                    SwirlComboBox {
                                        objectName:"scaleModeCombo"
                                        implicitWidth:Theme.dp(176)
                                        model:["自动跟随系统","手动自定义"]
                                        currentIndex:Theme.followSystemScale?0:1
                                        onActivated:currentIndex===0?Theme.followSystem():Theme.setScalePercent(Theme.uiScale*100)
                                        Accessible.name:"界面缩放模式"
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth:true; spacing:Theme.dp(12)
                                    Slider {
                                        id: scaleSlider
                                        Layout.fillWidth:true; Layout.minimumWidth:Theme.dp(120)
                                        objectName:"scaleSlider"
                                        from:0.75; to:1.5; stepSize:0.01
                                        enabled:!Theme.followSystemScale
                                        onMoved:Theme.setScalePercent(Math.round(value*100))
                                        Binding { target:scaleSlider; property:"value"; value:Theme.uiScale; when:!scaleSlider.pressed }
                                    background: Rectangle {
                                        x: scaleSlider.leftPadding
                                        y: scaleSlider.topPadding + scaleSlider.availableHeight / 2 - height / 2
                                        width: scaleSlider.availableWidth
                                        height:Theme.dp(7)
                                        radius:Theme.roundedRadius(width,height)
                                        color: Theme.material("field")
                                        border.width:Theme.dp(1)
                                        border.color: Theme.glassRim
                                        Rectangle {
                                            height: parent.height
                                            radius:Theme.roundedRadius(width,height)
                                            width: scaleSlider.visualPosition * parent.width
                                            color: Theme.accent
                                        }
                                    }
                                    handle: Rectangle {
                                        x: scaleSlider.leftPadding + scaleSlider.visualPosition * (scaleSlider.availableWidth - width)
                                        y: scaleSlider.topPadding + scaleSlider.availableHeight / 2 - height / 2
                                        implicitWidth:Theme.dp(20); implicitHeight:Theme.dp(20)
                                        radius:Theme.roundedRadius(width,height)
                                        color: "#FBFDFF"
                                        border.width:Theme.dp(1)
                                        border.color: Theme.glassRim
                                    }
                                    }
                                    SwirlButton { text:"恢复默认"; enabled:!Theme.followSystemScale || Theme.uiScale!==1.0; onClicked:Theme.resetScale() }
                                }
                            }
                            SwirlStatusBadge { label:AppState.zh("CHANGES ARE LOCAL TO THIS UI PREVIEW"); tone:"accent" }
                        }
                        ColumnLayout {
                            visible:page.section!=="外观"&&page.section!=="关于 Swirl"&&page.section!=="代理"; Layout.fillWidth:true; spacing:Theme.dp(17)
                            Repeater {
                                model:page.section==="代理"?["系统代理","默认策略","进程绕过","代理身份验证"]:
                                      page.section==="DNS"?["解析器选择","加密 DNS","IPv6","虚拟 IP 处理"]:
                                      page.section==="TUN"?["TUN 入口","网卡选择","路由排除","网关 DNS"]:
                                      page.section==="端口"?["HTTP 端口","SOCKS 端口","API 端口","端口冲突提醒"]:
                                      page.section==="隐私与安全"?["敏感数据脱敏","本地加密","证书信任","诊断授权"]:
                                      page.section==="启动"?["开机启动","启动时最小化","恢复上次窗口"]:
                                      page.section==="通知"?["连接状态通知","订阅更新通知","错误通知"]:
                                      page.section==="系统集成"?["显示托盘图标","关闭窗口后保留托盘","桌面通知"]:
                                      page.section==="数据管理"?["保留连接历史","保留请求日志","自动清理过期记录"]:
                                      page.section==="快捷键"?["全局搜索快捷键","窗口显示快捷键","页面导航快捷键"]:
                                      ["关闭窗口时保留后台","记住窗口尺寸","显示工具提示"]
                                RowLayout {
                                    Layout.fillWidth:true
                                    ColumnLayout {
                                        Layout.fillWidth:true
                                        Text { text:AppState.zh(modelData); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                    }
                                    SwirlTextField { enabled:false;
                                        visible:page.section==="端口"&&modelData.indexOf("端口")>=0&&modelData!=="端口冲突提醒"
                                        implicitWidth:Theme.dp(156); text:modelData==="HTTP 端口"?"7890":modelData==="SOCKS 端口"?"7891":"9090"
                                        validator:IntValidator { bottom:1; top:65535 }
                                        Accessible.name:modelData
                                    }
                                    SwirlComboBox { enabled:false;
                                        visible:modelData==="默认策略"||modelData==="解析器选择"||modelData==="网卡选择"
                                        model:modelData==="默认策略"?["自动选择","直连"]:modelData==="解析器选择"?["系统 DNS","加密 DNS"]:["自动","手动指定"]
                                        Accessible.name:modelData
                                    }
                                    SwirlButton { enabled:false;
                                        visible:page.section==="快捷键"
                                        text:modelData==="全局搜索快捷键"?"Ctrl+K":modelData==="页面导航快捷键"?"Alt+← / →":"未设置"
                                        Accessible.name:modelData
                                    }
                                    SwirlToggle { enabled:false;
                                        visible:page.section!=="快捷键"&&!(page.section==="端口"&&modelData!=="端口冲突提醒")&&modelData!=="默认策略"&&modelData!=="解析器选择"&&modelData!=="网卡选择"
                                        onToggled:AppState.notice(modelData)
                                        Accessible.name:modelData
                                    }
                                }
                            }
                            Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                        }
                        ColumnLayout {
                            visible:page.section==="代理"; Layout.fillWidth:true; spacing:Theme.dp(17)
                            RowLayout {
                                Layout.fillWidth:true
                                Text { text:"代理引擎"; color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true }
                                SwirlStatusBadge { objectName:"engineStatusBadge"; label:engineController.stateText; tone:engineController.apiHealthy?"success":"accent" }
                            }
                            Text {
                                objectName:"engineErrorText"; visible:engineController.error.length>0
                                text:engineController.error; color:Theme.orange; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12)
                            }
                            Text { text:"程序路径"; color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                            SwirlTextField {
                                objectName:"enginePathField"; Layout.fillWidth:true; text:engineController.executablePath
                                enabled:engineController.canStart; onEditingFinished:engineController.executablePath=text
                                Accessible.name:"已校验引擎程序路径"
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                Text { text:"本机控制端口"; color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true }
                                SwirlTextField {
                                    objectName:"enginePortField"; implicitWidth:Theme.dp(156); text:String(engineController.controlPort)
                                    enabled:engineController.canStart; validator:IntValidator { bottom:1; top:65535 }
                                    onEditingFinished:engineController.controlPort=Number(text)
                                    Accessible.name:"本机引擎控制端口"
                                }
                            }
                            Text {
                                objectName:"engineProcessText"
                                text:"进程："+(engineController.processAlive?"运行中 · PID "+engineController.processId:"未运行")+"　API："+(engineController.apiHealthy?"健康":"未就绪")
                                color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap; Layout.fillWidth:true
                            }
                            Text {
                                text:"已校验版本："+engineController.expectedVersion+"　运行版本："+(engineController.version||"未读取")+"　运行时间："+engineController.uptimeSeconds+" 秒"
                                color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap; Layout.fillWidth:true
                            }
                            Text {
                                text:"SHA-256："+engineController.expectedSha256
                                color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere; Layout.fillWidth:true
                            }
                            RowLayout {
                                SwirlButton { objectName:"engineStartButton"; text:"启动引擎"; enabled:engineController.canStart; onClicked:engineController.start(); Accessible.name:text }
                                SwirlButton { objectName:"engineStopButton"; text:"停止引擎"; enabled:engineController.processAlive||engineController.busy; onClicked:engineController.stop(); Accessible.name:text }
                                SwirlButton { text:"检查状态"; enabled:engineController.processAlive&&!engineController.busy; onClicked:engineController.refresh(); Accessible.name:text }
                            }
                            Text {
                                text:engineController.configPath.length>0?"运行配置："+engineController.configPath:"运行配置在启动时由 Swirl 生成。"
                                color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere; Layout.fillWidth:true
                            }
                            Text {
                                text:engineController.configurationSummary; visible:text.length>0
                                color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere; Layout.fillWidth:true
                            }
                        }
                        ColumnLayout {
                            visible:page.section==="关于 Swirl"; Layout.fillWidth:true; spacing:Theme.dp(18)
                            SwirlBrandIcon { Layout.alignment:Qt.AlignHCenter; Layout.preferredWidth:Theme.dp(76); Layout.preferredHeight:Theme.dp(76) }
                            Text { text:"Swirl"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.text; font.pixelSize:Theme.fontSize(30); font.weight:Font.DemiBold }
                            Text { text:"网络代理工具"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.muted; font.pixelSize:Theme.fontSize(14) }
                            Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                            Repeater {
                                model:[["版本",Qt.application.version.replace("-preview"," · 开发版")],["开发者","SOLHK"],["界面框架","Qt 6 Quick"],["平台","Windows 64 位"]]
                                RowLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(14) }
                                    Item { Layout.fillWidth:true }
                                    Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                }
                            }
                            SwirlButton { text:"项目主页"; Layout.alignment:Qt.AlignHCenter; onClicked:Qt.openUrlExternally("https://github.com/SOLHK/Swirl") }
                            Text { text:"第三方组件：Qt、MinGW 运行库、Mihomo（GPL-3.0）"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                        }
                        Item { Layout.preferredHeight:Theme.dp(25) }
                    }
                }
            }
        }
    }
}

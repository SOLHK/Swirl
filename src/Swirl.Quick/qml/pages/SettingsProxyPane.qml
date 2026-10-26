import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    required property var settingsPage
                             Layout.fillWidth:true; spacing:Theme.dp(17)
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true;
                                SwirlText {Layout.minimumWidth:0; text:engineController.systemProxy.owned?(engineController.systemProxy.enabled?"系统代理已接管":"接管状态未确认 · 快照已保留"):engineController.systemProxy.systemEnabled?"其他应用启用了系统代理":"未接管系统代理"; color:Theme.text; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(14) }
                                SwirlButton { text:"前往活动页管理代理"; onClicked:AppState.navigate("activity") }
                            }
                            SwirlText {Layout.minimumWidth:0; visible:engineController.systemProxy.error.length>0; text:engineController.systemProxy.error; color:Theme.orange; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            SwirlText {Layout.minimumWidth:0; text:"沿用 Swirl 的本地 DPAPI 恢复快照与独立守护进程。其他程序修改代理后让出控制权；控制 API 短时异常不会释放仍在运行的代理。"; color:Theme.muted; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
                            SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:"本地连接诊断"; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true;
                                SwirlTextField { id:diagnosticUrl; objectName:"diagnosticUrlField"; Layout.fillWidth:true; placeholderText:"https://目标地址 或 wss://目标路径"; enabled:!engineController.diagnostics.busy; Accessible.name:"用户指定的连接诊断地址" }
                                SwirlButton { text:engineController.diagnostics.busy?"取消":"开始诊断"; enabled:engineController.diagnostics.busy||engineController.activeProxyPort>0; onClicked:engineController.diagnostics.busy?engineController.diagnostics.cancel():engineController.diagnostics.run(diagnosticUrl.text) }
                            }
                            SwirlText {Layout.minimumWidth:0; text:engineController.diagnostics.stateText; color:Theme.muted; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            SwirlText {Layout.minimumWidth:0; text:"仅点击后向所填目标发送请求：本机端口 → CONNECT → TLS / HTTP 或 WebSocket Upgrade 与随机 Ping/Pong。地址可能需要登录或子协议；诊断失败不等于 Codex 服务故障，10 秒观察不代替长期实测。"; color:Theme.muted; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            SwirlTextArea { readOnly:true; selectByMouse:true; visible:engineController.diagnostics.entries.length>0; text:engineController.diagnostics.report; Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(160); wrapMode:TextEdit.Wrap; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(12); color:Theme.text; background:Rectangle { color:Theme.surface; radius:Theme.dp(14); border.color:Theme.border } }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                SwirlButton { text:"保存诊断报告"; onClicked:{const path=engineController.diagnostics.saveReport();AppState.notice(path.length>0?"诊断报告已保存："+path:"无法保存诊断报告")} }
                                SwirlButton { text:"清空记录"; enabled:!engineController.diagnostics.busy; onClicked:engineController.diagnostics.clear() }
                            }
                            SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:"Codex 与其他应用兼容建议"; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                SwirlText {Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"Rust Core 代理内核"; color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true }
                                SwirlToggle { objectName:"nativeCoreStatus"; checked:true; enabled:false; Accessible.name:"Rust Core 代理内核" }
                            }
                            SwirlText {Layout.minimumWidth:0; text:"Swirl 使用自研 Rust Core 执行节点连接。"; color:Theme.muted; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            SwirlTextArea { readOnly:true; selectByMouse:true; text:engineController.proxyEnvironmentAdvice; Layout.fillWidth:true; wrapMode:TextEdit.Wrap; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(12); color:Theme.text; background:null }
                            SwirlText {Layout.minimumWidth:0; text:"Rust Core 会在连接时校验节点、DNS 和规则能力；不支持的配置会显示阻止原因，原设置保持不变。当前版本尚不支持 TUN 网关转发。"; color:Theme.muted; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                SwirlText {Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"代理引擎"; color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true }
                                SwirlStatusBadge { objectName:"engineStatusBadge"; label:engineController.stateText; tone:engineController.apiHealthy?"success":"accent" }
                            }
                            SwirlText {
                                objectName:"engineErrorText"; visible:engineController.error.length>0
                                text:engineController.error; color:Theme.orange; wrapMode:Text.Wrap; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12)
                            }
                            SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:"内核模块"; color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                            SwirlTextField {
                                objectName:"enginePathField"; Layout.fillWidth:true; text:"swirl_api.dll（随程序交付）"
                                readOnly:true; selectByMouse:true
                                Accessible.name:"Swirl Rust Core 模块"
                            }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                SwirlText {Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"控制接口"; color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true }
                                SwirlTextField {
                                    objectName:"enginePortField"; implicitWidth:Theme.dp(156); text:"进程内（无需端口）"
                                    readOnly:true; selectByMouse:true
                                    Accessible.name:"进程内控制接口"
                                }
                            }
                            SwirlText {
                                text:"当前引擎："+(engineController.engineKind==="rust"?"Rust Core":engineController.engineName)+(engineController.engineReason?"\n"+engineController.engineReason:"")
                                color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap;Layout.fillWidth:true
                            }
                            SwirlText {
                                objectName:"engineProcessText"
                                text:"进程："+(engineController.processAlive?"运行中 · PID "+engineController.processId:"未运行")+"　API："+(engineController.apiHealthy?"健康":"未就绪")
                                color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap; Layout.fillWidth:true
                            }
                            SwirlText {
                                text:"内核模块：swirl_api.dll"+"　运行版本："+(engineController.engineKind==="rust"?(engineController.version||"未读取").replace("Swirl Core Rust","Rust Core"):(engineController.version||"未读取"))+"　运行时间："+engineController.uptimeSeconds+" 秒"
                                color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap; Layout.fillWidth:true
                            }
                            SwirlText {
                                text:"Rust Core 与当前程序配套交付，启动时验证 ABI 和构建标识。"
                                color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere; Layout.fillWidth:true
                            }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                SwirlButton { objectName:"engineStartButton"; text:"启动引擎"; enabled:engineController.canStart; onClicked:engineController.start(); Accessible.name:text }
                                SwirlButton { objectName:"engineStopButton"; text:"停止引擎"; enabled:engineController.processAlive||engineController.busy; onClicked:engineController.stop(); Accessible.name:text }
                                SwirlButton { text:"检查状态"; enabled:engineController.processAlive&&!engineController.busy; onClicked:engineController.refresh(); Accessible.name:text }
                            }
                            SwirlText {
                                text:engineController.configPath.length>0?"运行配置："+engineController.configPath:"运行配置在启动时传入 Swirl Rust Core。"
                                color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere; Layout.fillWidth:true
                            }
                            SwirlText {
                                text:engineController.engineKind==="rust"?engineController.configurationSummary.replace("Swirl Core Rust","Rust Core"):engineController.configurationSummary; visible:text.length>0
                                color:Theme.muted; font.pixelSize:Theme.fontSize(11); wrapMode:Text.WrapAnywhere; Layout.fillWidth:true
                            }
                        }

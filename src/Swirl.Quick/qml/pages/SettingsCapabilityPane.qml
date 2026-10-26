import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    required property var settingsPage
                             Layout.fillWidth:true; spacing:Theme.dp(17)
                            SwirlText {visible:settingsPage.section==="常规";text:"基础设置 · 研发中";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
                            Repeater {
                                model:settingsPage.section==="代理"?["系统代理","默认策略","进程绕过","代理身份验证"]:
                                      settingsPage.section==="DNS"?["解析器选择","加密 DNS","IPv6","虚拟 IP 处理"]:
                                      settingsPage.section==="TUN"?["TUN 入口","网卡选择","路由排除","网关 DNS"]:
                                      settingsPage.section==="端口"?["HTTP 端口","SOCKS 端口","API 端口","端口冲突提醒"]:
                                      settingsPage.section==="隐私与安全"?["敏感数据脱敏","本地加密","证书信任","诊断授权"]:
                                      settingsPage.section==="启动"?["开机启动","启动时最小化","恢复上次窗口"]:
                                      settingsPage.section==="通知"?["连接状态通知","订阅更新通知","错误通知"]:
                                      settingsPage.section==="系统集成"?["显示托盘图标","关闭窗口后保留托盘","桌面通知"]:
                                      settingsPage.section==="数据管理"?["保留连接历史","保留请求日志","自动清理过期记录"]:
                                      settingsPage.section==="快捷键"?["全局搜索快捷键","窗口显示快捷键","页面导航快捷键"]:
                                      ["关闭窗口时保留后台","记住窗口尺寸","显示工具提示"]
                                GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                    Layout.fillWidth:true
                                    ColumnLayout {
                                        Layout.fillWidth:true
                                        SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh(modelData); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                    }
                                    SwirlTextField { enabled:false;
                                        visible:settingsPage.section==="端口"&&modelData.indexOf("端口")>=0&&modelData!=="端口冲突提醒"
                                        implicitWidth:Theme.dp(156); text:modelData==="HTTP 端口"?"7890":modelData==="SOCKS 端口"?"7891":"9090"
                                        validator:IntValidator { bottom:1; top:65535 }
                                        Accessible.name:modelData
                                    }
                                    SwirlComboBox { enabled:false;
                                        visible:modelData==="默认策略"||modelData==="解析器选择"||modelData==="网卡选择"
                                        model:modelData==="默认策略"?["自动选择","直连"]:modelData==="解析器选择"?["系统 DNS","加密 DNS"]:["自动","手动指定"]
                                        Accessible.name:modelData
                                    }
                                    SwirlButton { development:true; enabled:false;
                                        visible:settingsPage.section==="快捷键"
                                        text:modelData==="全局搜索快捷键"?"Ctrl+K":modelData==="页面导航快捷键"?"Alt+← / →":"未设置"
                                        Accessible.name:modelData
                                    }
                                    SwirlToggle { enabled:false;
                                        visible:settingsPage.section!=="快捷键"&&!(settingsPage.section==="端口"&&modelData!=="端口冲突提醒")&&modelData!=="默认策略"&&modelData!=="解析器选择"&&modelData!=="网卡选择"
                                        onToggled:AppState.notice(modelData)
                                        Accessible.name:modelData
                                    }
                                }
                            }
                            Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
                        }

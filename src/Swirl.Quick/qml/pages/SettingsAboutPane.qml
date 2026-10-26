import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    required property var settingsPage
                             Layout.fillWidth:true; spacing:Theme.dp(18)
                            SwirlBrandIcon { Layout.alignment:Qt.AlignHCenter; Layout.preferredWidth:Theme.dp(104); Layout.preferredHeight:Theme.dp(104) }
                            SwirlText {textRole:"largeTitle";Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"Swirl"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.text; font.pixelSize:Theme.fontSize(30); font.weight:Font.DemiBold }
                            SwirlText {Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"网络代理工具"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.muted; font.pixelSize:Theme.fontSize(14) }
                            Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
                            Repeater {
                                model:[["版本",Qt.application.version.replace("-preview"," · 开发版")],["开发者","SOLHK"],["界面框架","Qt 6 Quick"],["平台","Windows 64 位"]]
                                GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                    Layout.fillWidth:true
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(14) }
                                    Item { Layout.fillWidth:true }
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                }
                            }
                            SwirlText {Layout.minimumWidth:0; text:"Swirl 使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.\n完整许可可在字体设置中查看。"; Layout.fillWidth:true; wrapMode:Text.Wrap; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                            SwirlButton { text:"字体与许可"; onClicked:settingsPage.section="字体" }
                            SwirlButton { text:"项目主页"; Layout.alignment:Qt.AlignHCenter; onClicked:Qt.openUrlExternally("https://github.com/SOLHK/Swirl") }
                            GridLayout {
                                Layout.alignment:Qt.AlignHCenter
                                columns:parent.width<Theme.dp(430)?1:2
                                columnSpacing:Theme.compactGap; rowSpacing:Theme.compactGap
                                SwirlButton {
                                    id: officialChannelButton
                                    objectName:"officialChannelButton"; text:"官方频道"
                                    Accessible.description:"通过默认浏览器打开 Swirl官方频道（Telegram）"
                                    SwirlToolTip {parent:officialChannelButton;visible:officialChannelButton.hovered||officialChannelButton.activeFocus;delay:500;text:"Swirl官方频道 · https://t.me/SwirlUpdates"}
                                    onClicked:Qt.openUrlExternally("https://t.me/SwirlUpdates")
                                }
                                SwirlButton {
                                    id: communityGroupButton
                                    objectName:"communityGroupButton"; text:"用户交流群"
                                    Accessible.description:"通过默认浏览器打开 Swirl交流群（Telegram）"
                                    SwirlToolTip {parent:communityGroupButton;visible:communityGroupButton.hovered||communityGroupButton.activeFocus;delay:500;text:"Swirl交流群 · https://t.me/SwirlHQ"}
                                    onClicked:Qt.openUrlExternally("https://t.me/SwirlHQ")
                                }
                            }
                            SwirlText {Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"问题反馈请使用项目主页中的 GitHub Issues。"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                            SwirlText {Layout.minimumWidth:0;wrapMode:Text.Wrap; text:"第三方组件：Qt、Rust 网络与密码库、C++ 运行库、HarmonyOS Sans"; Layout.fillWidth:true; horizontalAlignment:Text.AlignHCenter; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                        }

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    required property var settingsPage
                             spacing:Theme.dp(21); Layout.fillWidth:true
                            SwirlText {text:"外观与主题";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh("Color theme"); color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh("Choose light, dark or follow Windows"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                }
                                SwirlComboBox {
                                    objectName:"themeModePicker"
                                    model:["跟随系统","浅色","深色"]
                                    currentIndex:["System","Light","Dark"].indexOf(Theme.mode)
                                    onActivated:function(index){Theme.mode=["System","Light","Dark"][index]}
                                }
                            }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:"磨砂背景"; color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:"使用 Windows 原生窗口背景材质"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                }
                                SwirlToggle { checked:Theme.transparency; onToggled:Theme.transparency=checked }
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                SwirlText {text:qsTr("增强对比度");color:Theme.text;font.pixelSize:Theme.fontSize(14);Layout.fillWidth:true}
                                SwirlToggle {objectName:"increaseContrastToggle";checked:Theme.increaseContrast;onToggled:Theme.increaseContrast=checked;Accessible.name:qsTr("增强对比度")}
                            }
                            SwirlText {text:"动画与交互";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh("Reduce motion"); color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:AppState.zh("Disable most transition animations"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                                }
                                SwirlToggle { checked:Theme.reduceMotion; onToggled:Theme.reduceMotion=checked }
                            }
                            GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap;text:"跟随系统动态效果";color:Theme.text;font.pixelSize:Theme.fontSize(14)}
                                    SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap;text:"开启后，遵循系统的动画效果设置。";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                                }
                                SwirlToggle {objectName:"followSystemMotionToggle";checked:Theme.followSystemMotion;onToggled:Theme.followSystemMotion=checked}
                            }
                            SwirlText {text:"字体与文字大小";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
                            RowLayout {Layout.fillWidth:true
                                SwirlText {text:"界面缩放会同步调整文字与控件。字体家族和可变轴可单独设置。";color:Theme.muted;wrapMode:Text.WordWrap;Layout.fillWidth:true;font.pixelSize:Theme.fontSize(11)}
                                SwirlButton {text:"选择字体";quiet:true;onClicked:settingsPage.section="字体"}
                            }
                            ColumnLayout {
                                Layout.fillWidth:true; spacing:Theme.dp(10)
                                GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                    Layout.fillWidth:true
                                    ColumnLayout {
                                        Layout.fillWidth:true
                                        SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:"界面缩放"; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                                        SwirlText {Layout.minimumWidth:0;Layout.fillWidth:true;wrapMode:Text.Wrap; text:Theme.followSystemScale?"自动跟随 Windows 显示缩放 · Qt 原生 DPI":"手动缩放 · "+Math.round(Theme.uiScale*100)+"%"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
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
                                GridLayout {columns:width<Theme.dp(430)?1:2;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap;
                                    Layout.fillWidth:true;
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
                                        y: Math.round(scaleSlider.topPadding + scaleSlider.availableHeight / 2 - height / 2)
                                        width: Math.round(scaleSlider.availableWidth)
                                        height:Theme.dp(7)
                                        radius:Theme.roundedRadius(width,height)
                                        color: Theme.material("field")
                                        border.width:Theme.dp(1)
                                        border.color: Theme.glassRim
                                        Rectangle {
                                            height: parent.height
                                            radius:Theme.roundedRadius(width,height)
                                            width: Math.round(scaleSlider.visualPosition * parent.width)
                                            color: Theme.accent
                                        }
                                    }
                                    handle: Rectangle {
                                        x: Math.round(scaleSlider.leftPadding + scaleSlider.visualPosition * (scaleSlider.availableWidth - width))
                                        y: Math.round(scaleSlider.topPadding + scaleSlider.availableHeight / 2 - height / 2)
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
                            SwirlStatusBadge { label:"已实现的设置自动保存"; tone:"accent" }
                        }

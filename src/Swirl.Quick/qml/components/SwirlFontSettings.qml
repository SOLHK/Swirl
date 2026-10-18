import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../controls"
ColumnLayout {
    id: root
    spacing:Theme.dp(14)
    SwirlText { text:"当前字体 · "+fontManager.currentFamily; color:Theme.text; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(15); Layout.fillWidth:true; wrapMode:Text.Wrap }
    RowLayout {
        Layout.fillWidth:true
        SwirlSearchField { id:search; objectName:"fontSearch"; Layout.fillWidth:true; placeholderText:"搜索字体，如 HarmonyOS Sans SC" }
        SwirlButton { objectName:"fontReset"; text:"恢复自动选择"; onClicked:fontManager.reset() }
    }
    SwirlGlassPanel {
        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(240)
        ListView { pixelAligned: true;
            id:fontList; objectName:"fontFamilyList"; anchors.fill:parent; anchors.margins:Theme.dp(6); clip:true
            model:fontManager.families.filter(function(family){return family.toLowerCase().indexOf(search.text.toLowerCase())>=0})
            ScrollBar.vertical:SwirlScrollBar {}
            delegate:SwirlButton {
                id:fontRow
                required property string modelData
                width:ListView.view.width-Theme.dp(12); height:Theme.dp(62)
                text:(fontManager.previewFamily===modelData?"✓  ":"")+modelData+(modelData===fontManager.defaultFamily?" · 默认":"")
                font.family:modelData; onClicked:fontManager.choosePreviewFamily(modelData)
                contentItem:Column {
                    spacing:Theme.dp(3)
                    SwirlText {width:parent.width;text:fontRow.text;font.pixelSize:Theme.fontSize(12);color:Theme.text;elide:Text.ElideRight}
                    SwirlText {width:parent.width;text:"连接让世界更近  Swirl 0123456789";font.family:fontRow.modelData;font.pixelSize:Theme.fontSize(16);color:Theme.text;elide:Text.ElideRight}
                }
                background:SwirlContinuousSurface { radius:Theme.dp(7); color:parent.down?Theme.pressed:fontManager.previewFamily===parent.modelData?Theme.selected:parent.hovered?Theme.hover:"transparent" }
                Accessible.name:modelData
            }
            SwirlText { anchors.centerIn:parent; visible:fontList.count===0; text:"没有匹配的字体，可导入本地字体文件"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
        }
    }
    RowLayout {
        Layout.fillWidth:true
        SwirlText { text:"预览家族 / TTC 家族"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
        SwirlComboBox {
            objectName:"fontCollectionFamily"; Layout.fillWidth:true
            model:fontManager.importedFamilies
            currentIndex:model.indexOf(fontManager.previewFamily)
            enabled:count>0
            onActivated:fontManager.choosePreviewFamily(currentText)
            Accessible.name:"已导入字体的家族"
        }
    }
    SwirlText { text:fontManager.previewFamily; color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true; wrapMode:Text.Wrap }
    Repeater {
        model:fontManager.previewAxes
        delegate:ColumnLayout {
            id:axisRow
            required property var modelData
            readonly property string tag:modelData.tag
            readonly property real axisValue:Number(fontManager.previewValues[tag])
            Layout.fillWidth:true; spacing:Theme.dp(4)
            RowLayout {
                Layout.fillWidth:true
                SwirlText { text:axisRow.tag+" · "+axisRow.modelData.name; color:Theme.text; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(12) }
                SwirlText { text:axisRow.modelData.minimum+" – "+axisRow.modelData.maximum; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                SwirlButton { text:"默认 "+axisRow.modelData.defaultValue; onClicked:fontManager.setPreviewAxis(axisRow.tag,axisRow.modelData.defaultValue); Accessible.name:axisRow.tag+" 恢复默认值" }
            }
            RowLayout {
                Layout.fillWidth:true
                Slider {
                    objectName:"fontAxisSlider_"+axisRow.tag
                    Layout.fillWidth:true
                    from:axisRow.modelData.minimum; to:axisRow.modelData.maximum
                    stepSize:Math.min(1,(to-from)/1000)
                    value:axisRow.axisValue
                    onMoved:fontManager.setPreviewAxis(axisRow.tag,value)
                    Accessible.name:axisRow.tag+" 可变轴"
                }
                SwirlTextField {
                    id:axisInput
                    objectName:"fontAxisInput_"+axisRow.tag
                    Layout.preferredWidth:Theme.dp(108)
                    text:String(Number(axisRow.axisValue.toFixed(4)))
                    selectByMouse:true
                    validator:DoubleValidator { bottom:axisRow.modelData.minimum; top:axisRow.modelData.maximum; decimals:4; notation:DoubleValidator.StandardNotation; locale:"C" }
                    inputMethodHints:Qt.ImhFormattedNumbersOnly
                    onEditingFinished:{
                        if(acceptableInput)fontManager.setPreviewAxis(axisRow.tag,Number(text))
                        text=Qt.binding(function(){return String(Number(axisRow.axisValue.toFixed(4)))})
                    }
                    Accessible.name:axisRow.tag+" 数值"
                }
            }
        }
    }
    SwirlText { visible:fontManager.previewAxes.length===0; text:"此家族没有可用的 OpenType 可变轴。"; color:Theme.muted; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(12) }
    SwirlGlassPanel {
        Layout.fillWidth:true; Layout.preferredHeight:previewColumn.implicitHeight+Theme.dp(32)
        ColumnLayout {
            id:previewColumn
            anchors.left:parent.left; anchors.right:parent.right; anchors.top:parent.top
            anchors.margins:Theme.dp(16); spacing:Theme.dp(8)
            Repeater {
                model:["苹方字体显示效果测试","The quick brown fox jumps over the lazy dog.","0123456789","@ # ¥ % &"]
                delegate:VariableFontPreview {
                    required property string modelData
                    required property int index
                    objectName:"fontPreviewLine_"+index
                    text:modelData; Layout.fillWidth:true
                    Accessible.role:Accessible.StaticText; Accessible.name:text
                    color:Theme.text
                    font.family:fontManager.previewFamily; font.styleName:""
                    font.pixelSize:Theme.fontSize(index===0?21:15)
                    font.hintingPreference:Font.PreferFullHinting
                    font.variableAxes:fontManager.previewValues
                }
            }
        }
    }
    Flow {
        Layout.fillWidth:true; spacing:Theme.dp(8)
        SwirlButton { objectName:"fontApply"; text:"应用到整个界面"; primary:true; onClicked:fontManager.applyPreview() }
        SwirlButton { objectName:"fontAxesReset"; text:"恢复全部轴默认值"; enabled:fontManager.previewAxes.length>0; onClicked:fontManager.resetPreviewAxes() }
        SwirlButton { objectName:"fontPreviewDiscard"; text:"恢复已应用配置"; onClicked:fontManager.discardPreview() }
    }
    SwirlText { text:"预览自动保存并在重启后恢复。确认后应用到整个界面，保留各级字号。"; color:Theme.muted; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(12) }
    RowLayout {
        Layout.fillWidth:true
        SwirlButton { objectName:"fontImport"; text:"导入字体文件…"; onClicked:fontFile.open() }
        SwirlText { text:"支持 TTF、OTF、TTC，最大 128 MiB，仅供 Swirl 使用"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.Wrap }
    }
    SwirlText { text:fontManager.error; visible:text.length>0; color:Theme.red; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(12) }
    SwirlText { text:"Swirl 使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.\n字体按 HarmonyOS Sans Fonts License Agreement 分发，随软件提供的字体文件保持官方原样。"; color:Theme.muted; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(11) }
    SwirlButton { objectName:"fontLicense"; text:"查看鸿蒙字体许可"; onClicked:licenseDialog.open() }
    FileDialog { id:fontFile;parentWindow:root.Window.window;objectName:"settingsFontFileDialog"; title:"选择字体文件"; nameFilters:["字体文件 (*.ttf *.otf *.ttc)"]; onAccepted:fontManager.importFont(selectedFile) }
    SwirlDialog {
        ownerItem:root
        id:licenseDialog; objectName:"fontLicenseDialog"; title:"HarmonyOS Sans 字体许可"; guardChanges:false; implicitWidth:Math.min(Theme.dp(720),parent?parent.width-Theme.dp(40):Theme.dp(720)); implicitHeight:Math.min(Theme.dp(540),parent?parent.height-Theme.dp(40):Theme.dp(540))
        ScrollView { anchors.fill:parent; clip:true; TextArea { renderType: TextEdit.NativeRendering; font.weight: Theme.bodyFontWeight; font.hintingPreference: Font.PreferFullHinting; Binding on font.variableAxes { delayed:true; value:Theme.variableAxesFor(font.family,font.weight) } text:fontManager.licenseText; readOnly:true; selectByMouse:true; textFormat:TextEdit.PlainText; wrapMode:TextEdit.Wrap; color:Theme.text; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(12); background:Item {} } }
    }
}

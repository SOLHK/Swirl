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
        SwirlSearchField { id:search; objectName:"fontSearch"; Layout.fillWidth:true; placeholderText:"搜索字体，如 PingFang、MiSans" }
        SwirlButton { objectName:"fontReset"; text:"恢复自动选择"; onClicked:fontManager.reset() }
    }
    SwirlGlassPanel {
        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(240)
        ListView {
            id:fontList; objectName:"fontFamilyList"; anchors.fill:parent; anchors.margins:Theme.dp(6); clip:true
            model:fontManager.families.filter(function(family){return family.toLowerCase().indexOf(search.text.toLowerCase())>=0})
            ScrollBar.vertical:SwirlScrollBar {}
            delegate:SwirlButton {
                id:fontRow
                required property string modelData
                width:ListView.view.width-Theme.dp(12); height:Theme.dp(62)
                text:(fontManager.currentFamily===modelData?"✓  ":"")+modelData+(modelData===fontManager.defaultFamily?" · 默认":"")
                font.family:modelData; onClicked:fontManager.selectFamily(modelData)
                contentItem:Column {
                    spacing:Theme.dp(3)
                    SwirlText {width:parent.width;text:fontRow.text;font.pixelSize:Theme.fontSize(12);color:Theme.text;elide:Text.ElideRight}
                    SwirlText {width:parent.width;text:"连接让世界更近  Swirl 0123456789";font.family:fontRow.modelData;font.pixelSize:Theme.fontSize(16);color:Theme.text;elide:Text.ElideRight}
                }
                background:SwirlContinuousSurface { radius:Theme.dp(7); color:parent.down?Theme.pressed:fontManager.currentFamily===parent.modelData?Theme.selected:parent.hovered?Theme.hover:"transparent" }
                Accessible.name:modelData
            }
            SwirlText { anchors.centerIn:parent; visible:fontList.count===0; text:"没有匹配的字体，可导入本地字体文件"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
        }
    }
    SwirlGlassPanel {
        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(106)
        Column { anchors.fill:parent; anchors.margins:Theme.dp(16); spacing:Theme.dp(8)
            SwirlText { text:"字形预览 · 连接让世界更近"; font.family:fontManager.currentFamily; font.pixelSize:Theme.fontSize(21); font.weight:Font.DemiBold; color:Theme.text }
            SwirlText { text:"Swirl · 0123456789 · 240 Hz"; font.family:fontManager.currentFamily; font.pixelSize:Theme.fontSize(15); color:Theme.muted }
        }
    }
    RowLayout {
        Layout.fillWidth:true
        SwirlButton { objectName:"fontImport"; text:"导入字体文件…"; onClicked:fontFile.open() }
        SwirlText { text:"支持 TTF、OTF、TTC，仅供 Swirl 使用"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.Wrap }
    }
    SwirlText { text:fontManager.error; visible:text.length>0; color:Theme.red; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(12) }
    SwirlText { text:"自动选择优先使用已安装的 PingFang SC，其次为内置 HarmonyOS Sans SC，最后回退到系统字体。列表按每种字体实际预览，缺失字符由系统补全；手动选择与导入只在本机生效。"; color:Theme.muted; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(12) }
    SwirlText { text:"Swirl 使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.\n字体按 HarmonyOS Sans Fonts License Agreement 分发，随软件提供的字体文件保持官方原样。"; color:Theme.muted; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.fontSize(11) }
    SwirlButton { objectName:"fontLicense"; text:"查看鸿蒙字体许可"; onClicked:licenseDialog.open() }
    FileDialog { id:fontFile; title:"选择字体文件"; nameFilters:["字体文件 (*.ttf *.otf *.ttc)"]; onAccepted:fontManager.importFont(selectedFile) }
    SwirlDialog {
        id:licenseDialog; title:"HarmonyOS Sans 字体许可"; guardChanges:false; implicitWidth:Math.min(Theme.dp(720),parent.width-Theme.dp(40)); implicitHeight:Math.min(Theme.dp(540),parent.height-Theme.dp(40))
        ScrollView { anchors.fill:parent; clip:true; TextArea { text:fontManager.licenseText; readOnly:true; selectByMouse:true; textFormat:TextEdit.PlainText; wrapMode:TextEdit.Wrap; color:Theme.text; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(12); background:Item {} } }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string tab:"Tasks"
    property var selected:null
    property var jobs:[
        {id:"auto1",name:"Refresh profiles",trigger:"Daily · 08:00",action:"Profile refresh",state:"Enabled",last:"Never"},
        {id:"auto2",name:"Wi-Fi route selection",trigger:"Network change",action:"Switch policy",state:"Enabled",last:"Never"},
        {id:"auto3",name:"Log error summary",trigger:"Error event",action:"Create report",state:"Disabled",last:"Never"}
    ]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"SCHEDULER NOT CONNECTED"; tone:"warning" }
            Text { text:"Triggers, cron and actions are UI fixtures only"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"New automation"; primary:true; onClicked:newDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Tasks","History","Conditions"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:"Run all (demo)"; iconName:"play"; onClicked:AppState.notice("Run automation tasks") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Tasks"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.jobs; selectedId:page.selected?page.selected.id:""
                    columns:[{key:"name",label:"TASK",w:225},{key:"trigger",label:"TRIGGER",w:155},
                             {key:"action",label:"ACTION",w:155},{key:"state",label:"STATE",w:96},
                             {key:"last",label:"LAST RUN",w:96}]
                    onRowSelected:function(r){page.selected=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Tasks"
                    anchors.fill:parent; anchors.margins:18; spacing:16
                    Text { text:page.tab==="History"?"Task execution history":"Available trigger conditions"; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="History"?["No scheduled tasks have executed in this preview",
                            "Example: 08:00 · Profile refresh · skipped (no backend)"]:
                            ["Scheduled / Cron","Wi-Fi SSID changes","Network connect or disconnect","DNS query failure",
                             "HTTP response condition","Policy latency threshold"]
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlIcon { name:"clock"; size:17; color:Theme.muted }
                            Text { text:modelData; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:310; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:14
                    Text { text:"Automation editor"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.selected?page.selected.name:"Select a task"; color:Theme.accent; font.pixelSize:14; font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                    Text { text:"TRIGGER TYPE"; color:Theme.muted; font.pixelSize:10 }
                    SwirlComboBox { Layout.fillWidth:true; model:["Schedule","Network change","HTTP event","DNS event","Error event"] }
                    Text { text:"CRON / EVENT FILTER"; color:Theme.muted; font.pixelSize:10 }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"0 8 * * *" }
                    Text { text:"ACTION"; color:Theme.muted; font.pixelSize:10 }
                    SwirlComboBox { Layout.fillWidth:true; model:["Refresh profile","Select proxy","Record log","Run script","Notify"] }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"Enable task"; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                        SwirlToggle { onToggled:AppState.notice("Automation enable switch") }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Validate demo rule"; onClicked:AppState.notice("Validate automation") }
                    SwirlButton { text:"Save preview"; primary:true; onClicked:AppState.notice("Save automation preview") }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"Create automation"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Task name"; color:Theme.text }
            SwirlTextField { id:taskName; Layout.fillWidth:true; placeholderText:"New automation" }
            Text { text:"Trigger type"; color:Theme.text }
            SwirlComboBox { id:triggerInput; Layout.fillWidth:true; model:["Scheduled","Network change","HTTP event","Error event"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:newDialog.close() }
                SwirlButton {
                    text:"Create demo"; primary:true; enabled:taskName.text.trim().length>0
                    onClicked:{
                        page.jobs=page.jobs.concat([{id:"auto"+Date.now(),name:taskName.text.trim(),
                            trigger:triggerInput.currentText,action:"No-op preview",state:"Disabled",last:"Never"}])
                        taskName.text="";newDialog.close()
                    }
                }
            }
        }
    }
}
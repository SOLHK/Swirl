import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property var records:[
        {id:"b1",method:"POST",url:"/api/v1/profile",host:"api.example.test",status:"Paused",time:"14:08:17"},
        {id:"b2",method:"GET",url:"/config.json",host:"cdn.example.test",status:"Paused",time:"14:08:11"},
        {id:"b3",method:"PUT",url:"/account/settings",host:"api.example.test",status:"Continued",time:"14:07:54"}
    ]
    property var selected:null
    property string tab:"Headers"
    property string payload:"Accept: application/json\nContent-Type: application/json\nX-Swirl-Demo: true\n"
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"NO LIVE INTERCEPTION"; tone:"warning" }
            Text { text:"Modify synthetic paused requests without touching the network"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Add breakpoint"; primary:true; onClicked:ruleDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:88
            RowLayout {
                anchors.fill:parent; anchors.margins:18; spacing:15
                ColumnLayout {
                    Layout.fillWidth:true; spacing:5
                    Text { text:"Breakpoint queue"; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Text { text:"Requests are frozen local fixtures. No browser is paused."; color:Theme.muted; font.pixelSize:11 }
                }
                SwirlStatusBadge { label:page.records.filter(function(r){return r.status==="Paused"}).length+" PAUSED"; tone:"accent" }
                SwirlButton { text:"Resume all (demo)"; onClicked:{
                    page.records=page.records.map(function(r){return {id:r.id,method:r.method,url:r.url,host:r.host,status:"Continued",time:r.time}})
                }}
            }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.preferredWidth:380; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.records
                    selectedId:page.selected?page.selected.id:""
                    columns:[{key:"method",label:"METHOD",w:87},{key:"url",label:"REQUEST PATH",w:215},
                             {key:"status",label:"STATE",w:119},{key:"time",label:"TIME",w:98}]
                    onRowSelected:function(r){page.selected=r}
                }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:13
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"Paused request editor"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold; Layout.fillWidth:true }
                        SwirlStatusBadge { label:page.selected?page.selected.status:"NO SELECTION"; tone:"accent" }
                    }
                    Text {
                        Layout.fillWidth:true; elide:Text.ElideMiddle; color:Theme.muted; font.pixelSize:12
                        text:page.selected?("https://"+page.selected.host+page.selected.url):"Select a request to inspect"
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        Repeater {
                            model:["Headers","Body","Query"]
                            SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:8
                            TextArea {
                                id:editor
                                text:page.tab==="Headers"?page.payload:
                                     page.tab==="Body"?"{\n  \"preview\": true\n}":"page=1&mode=demo"
                                color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:12
                                selectByMouse:true; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton {
                            text:"Continue"; primary:true; enabled:page.selected&&page.selected.status==="Paused"
                            onClicked:page.changeStatus("Continued")
                        }
                        SwirlButton {
                            text:"Modify & Continue"; enabled:page.selected&&page.selected.status==="Paused"
                            onClicked:{page.payload=editor.text;page.changeStatus("Modified")}
                        }
                        SwirlButton {
                            text:"Drop"; danger:true; enabled:page.selected&&page.selected.status==="Paused"
                            onClicked:page.changeStatus("Dropped")
                        }
                    }
                }
            }
        }
    }
    function changeStatus(status) {
        if (!selected) return
        var id=selected.id
        records=records.map(function(r){return r.id===id?
            {id:r.id,method:r.method,url:r.url,host:r.host,status:status,time:r.time}:r})
        selected=records.find(function(r){return r.id===id})
        AppState.notice("Breakpoint "+status)
    }
    SwirlDialog {
        id:ruleDialog; title:"Add breakpoint matcher"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"URL match expression"; color:Theme.text }
            SwirlTextField { id:matcher; Layout.fillWidth:true; placeholderText:"/api/*" }
            Text { text:"Request phase"; color:Theme.text }
            SwirlComboBox { model:["Before request","After response"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:ruleDialog.close() }
                SwirlButton { text:"Add demo"; primary:true; enabled:matcher.text.trim().length>0
                    onClicked:{AppState.notice("Add breakpoint matcher");ruleDialog.close();matcher.text=""}
                }
            }
        }
    }
}
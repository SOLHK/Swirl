import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string selectedTab:"Map Local"
    property var selection:null
    property var entries:[
        {id:"m1",name:"User profile fixture",match:"https://api.example.test/user",target:"fixtures/user.json",type:"Map Local",status:"Enabled"},
        {id:"m2",name:"Static assets",match:"https://cdn.example.test/*",target:"C:/fixtures/assets/",type:"Map Local",status:"Enabled"},
        {id:"m3",name:"Legacy API mirror",match:"https://api.example.test/v1/*",target:"https://mirror.example.test/v2/",type:"Map Remote",status:"Disabled"}
    ]
    readonly property var visibleRows:entries.filter(function(r){return r.type===selectedTab &&
        (r.name+" "+r.match+" "+r.target).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"RESPONSE MAPPING · DEMO"; tone:"accent" }
            Text { text:"No files are opened and no requests are redirected"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"New mapping"; primary:true; onClicked:newDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Map Local","Map Remote"]
                SwirlButton { text:modelData; quiet:page.selectedTab!==modelData; onClicked:{page.selectedTab=modelData;page.selection=null} }
            }
            Item { Layout.fillWidth:true }
            SwirlSearchField { id:search; implicitWidth:260; placeholderText:"Filter mapped URLs" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.visibleRows
                    selectedId:page.selection?page.selection.id:""
                    columns:[{key:"name",label:"MAPPING",w:180},{key:"match",label:"REQUEST URL",w:280},
                             {key:"target",label:"REPLACEMENT",w:270},{key:"status",label:"STATE",w:105}]
                    onRowSelected:function(r){page.selection=r;nameField.text=r.name;matchField.text=r.match;targetField.text=r.target}
                }
                SwirlEmptyState { visible:page.visibleRows.length===0; anchors.centerIn:parent; headline:"No mappings" }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:313; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:12
                    Text { text:"Mapping inspector"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.selectedTab; color:Theme.muted; font.pixelSize:11 }
                    Text { text:"Display name"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { id:nameField; Layout.fillWidth:true; placeholderText:"Mapping name" }
                    Text { text:"Match request URL"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { id:matchField; Layout.fillWidth:true; placeholderText:"https://example.test/*" }
                    Text { text:page.selectedTab==="Map Local"?"Replacement file or directory":"Remote replacement URL"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { id:targetField; Layout.fillWidth:true; placeholderText:page.selectedTab==="Map Local"?"fixtures/file.json":"https://mirror.example.test/" }
                    Text { text:"PREVIEW"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        Text {
                            anchors.fill:parent; anchors.margins:12
                            text:(matchField.text||"Original URL")+"\n  ↓\n"+(targetField.text||"Replacement destination")+
                                 "\n\nNo network or filesystem operation is performed."
                            color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:11; wrapMode:Text.WrapAnywhere
                        }
                    }
                    SwirlButton {
                        text:"Save demo mapping"; primary:true
                        enabled:page.selection&&matchField.text.trim().length>0&&targetField.text.trim().length>0
                        onClicked:{
                            var id=page.selection.id
                            page.entries=page.entries.map(function(r){return r.id===id?
                                {id:r.id,name:nameField.text,match:matchField.text,target:targetField.text,type:r.type,status:r.status}:r})
                            AppState.notice("Save mapping")
                        }
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"Create response mapping"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Request URL pattern"; color:Theme.text }
            SwirlTextField { id:urlInput; Layout.fillWidth:true; placeholderText:"https://example.test/api/*" }
            Text { text:page.selectedTab==="Map Local"?"Local fixture path":"Remote replacement URL"; color:Theme.text }
            SwirlTextField { id:destination; Layout.fillWidth:true; placeholderText:page.selectedTab==="Map Local"?"fixtures/response.json":"https://mirror.example.test/" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:newDialog.close() }
                SwirlButton {
                    text:"Add demo"; primary:true
                    enabled:urlInput.text.startsWith("https://")&&destination.text.trim().length>0
                    onClicked:{
                        page.entries=page.entries.concat([{id:"m"+Date.now(),name:"New mapping",
                            match:urlInput.text.trim(),target:destination.text.trim(),type:page.selectedTab,status:"Enabled"}])
                        urlInput.text="";destination.text="";newDialog.close()
                    }
                }
            }
        }
    }
}
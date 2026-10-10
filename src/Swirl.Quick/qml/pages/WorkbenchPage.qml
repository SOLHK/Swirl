import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property string pageId: "dashboard"
    property var features: ({
        dashboard:["Rate History","Connection Trends","Latency","Recent Requests","Domain Ranking","Application Ranking","Policy Usage"],
        profiles:["Local Profiles","Remote Profiles","Editor","Import","Export","Backup","Versions"],
        policies:["Manual Select","Auto Select","Failover","Load Balance","SSID","Policy Details","Relationships"],
        subscriptions:["Providers","Update","Scheduling","Quota","Node Count","History","Errors"],
        rules:["Rule List","Type","Target","Priority","Editor","Hits","Rule Test"],
        dns:["Resolvers","DoH","DoT","DoQ","Query Log","Cache","Hosts","Fake-IP","IPv6","Tests"],
        traffic:["Time Range","Trends","Node Traffic","Domain Traffic","Process Traffic","Protocols","Upload / Download"],
        tls:["TLS Switch","CA Status","Decrypt Hosts","Excluded Hosts","Sessions","Certificates","Trust & Revoke"],
        rewrite:["URL","Headers","Body","Redirect","Reject","Mock Response","Editor","Hit Count"],
        map:["Local Files","Remote URL","Mappings","Editor","Enable","Preview"],
        breakpoint:["Rules","Paused Queue","Headers","Body","Continue","Drop","Modify & Continue"],
        replay:["Request History","Editor","Parameters","Response","Compare","Execution History"],
        modules:["Installed","Marketplace","Import","Remote Modules","Parameters","Versions","Updates"],
        automation:["Scheduled Tasks","Network Trigger","Conditions","Actions","History","Editor"],
        api:["Local API","Permissions","State","CLI","Examples","Access Log"],
        gateway:["Devices","Gateway","DHCP","Port Forwarding","Remote Devices","Interfaces"],
        logs:["Level","Search","Filters","Details","Timeline","Clear","Export"]
    })
    readonly property var featureList:features[pageId]||[]
    property string selected:""
    property var records:[]
    Component.onCompleted:regenerate()
    onPageIdChanged:regenerate()
    function regenerate() {
        var result=[]
        for (var i=0;i<featureList.length;i++) {
            result.push({id:"demo-"+i,name:featureList[i],type:AppState.page(pageId).title,
                status:pageId==="gateway"?"Planned":i%2?"Demo":"Enabled",updated:"Sample"})
        }
        records=result
        selected=featureList.length?featureList[0]:""
    }
    readonly property var filtered:records.filter(function(r){
        return r.name.toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
            (filter.currentText==="All"||r.status===filter.currentText)
    })
    ColumnLayout {
        anchors.fill:parent
        anchors.margins:24
        spacing:15
        SwirlGlassPanel {
            Layout.fillWidth:true
            Layout.preferredHeight:103
            RowLayout {
                anchors.fill:parent; anchors.margins:18
                ColumnLayout {
                    Layout.fillWidth:true; spacing:6
                    Text { text:AppState.page(page.pageId).title+" workspace"; color:Theme.text; font.pixelSize:20; font.weight:Font.DemiBold }
                    Text { text:featureList.length+" interactive feature areas with representative fixtures"; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlStatusBadge { label:page.pageId==="gateway"?"PLANNED":"UI DEMONSTRATION"; tone:page.pageId==="gateway"?"warning":"accent" }
                SwirlButton { text:"Create"; primary:true; onClicked:addDialog.open() }
            }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true
            Layout.preferredHeight:228
            visible:pageId==="dashboard"||pageId==="traffic"
            ColumnLayout {
                anchors.fill:parent; anchors.margins:16
                Text { text:"Traffic data · synthetic sample"; color:Theme.text; font.pixelSize:15; font.weight:Font.DemiBold }
                SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Filter local samples" }
            SwirlComboBox { id:filter; model:["All","Enabled","Demo","Planned"] }
            SwirlButton { text:"Refresh"; onClicked:{page.regenerate();AppState.notice("Refresh "+page.pageId)} }
            SwirlButton { text:"Export"; onClicked:AppState.notice("Export "+page.pageId) }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:15
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.filtered
                    columns:[{key:"name",label:"NAME / ACTION",w:230},{key:"type",label:"MODULE",w:160},
                        {key:"status",label:"STATE",w:105},{key:"updated",label:"TIME",w:100}]
                    onRowSelected:function(record){page.selected=record.name}
                }
                SwirlEmptyState {
                    anchors.centerIn:parent
                    visible:page.filtered.length===0
                    headline:"No matching entries"
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:310; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:11
                    Text { text:"Module inspector"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.selected; color:Theme.accent; font.pixelSize:14; font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                    Text { text:"FEATURES"; font.pixelSize:10; color:Theme.muted }
                    ScrollView {
                        Layout.fillWidth:true
                        Layout.preferredHeight:Math.min(260,page.height*0.34)
                        clip:true
                        ColumnLayout {
                            width:parent.width; spacing:4
                            Repeater {
                                model:page.featureList
                                RowLayout {
                                    Layout.fillWidth:true
                                    Text {
                                        Layout.fillWidth:true
                                        text:modelData; color:Theme.text; font.pixelSize:12; elide:Text.ElideRight
                                        MouseArea { anchors.fill:parent; onClicked:page.selected=modelData }
                                    }
                                    SwirlToggle { onToggled:AppState.notice(modelData) }
                                }
                            }
                        }
                    }
                    Text { text:"EDITOR / OUTPUT"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        color:Theme.field; radius:10; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:8
                            TextArea {
                                text:"# Swirl demonstration\nfeature: "+page.selected+"\nstatus: not connected\n\n# Changes will not affect system settings."
                                color:Theme.text
                                font.family:"Cascadia Code"; font.pixelSize:11
                                selectByMouse:true; wrapMode:Text.Wrap
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { text:page.pageId==="replay"?"Send demo":"Apply demo"; onClicked:AppState.notice(text) }
                        SwirlButton { text:"More"; quiet:true; onClicked:AppState.notice("More options") }
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog
        title:"Create demo entry"
        ColumnLayout {
            width:parent.width; spacing:13
            Text { text:"Entry name"; color:Theme.text }
            SwirlTextField { id:nameField; Layout.fillWidth:true; placeholderText:"Name required" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:addDialog.close() }
                SwirlButton {
                    text:"Add"; primary:true; enabled:nameField.text.trim().length>0
                    onClicked:{
                        page.records=page.records.concat([{id:"local-"+Date.now(),name:nameField.text.trim(),
                            type:AppState.page(page.pageId).title,status:"Demo",updated:"Now"}])
                        nameField.text=""
                        addDialog.close()
                    }
                }
            }
        }
    }
}
import QtQuick
import SwirlQuick
Item {
    id:root
    property string name:"home"
    property int size:Theme.dp(20)
    property color color:Theme.muted
    readonly property var supported:["search", "home", "chart", "activity", "folder", "globe", "wifi", "router", "link", "list", "layers", "grid", "code", "shield", "settings", "server", "inspect", "refresh", "clock", "terminal", "edit", "network", "route", "tool", "plus", "capture", "chevron-right", "chevron-left", "download", "upload", "user", "pin", "document", "file", "gauge", "bars", "bolt", "sliders", "calendar", "help", "pause", "play","appearance","dns","modules","profiles","scripts","subscriptions","proxies","certificate","typography","trash"]
    implicitWidth:size; implicitHeight:size; width:size; height:size
    Image {
        anchors.fill:parent
        source:"image://swirl/"+(root.name.startsWith("nav-")||root.supported.indexOf(root.name)>=0||["add-square","add-circle","chevron-up-down","checkmark","dismiss"].indexOf(root.name)>=0?root.name:"grid")+"/"+root.color.toString().slice(1)
        sourceSize:Qt.size(root.size*Screen.devicePixelRatio,root.size*Screen.devicePixelRatio)
    }
}

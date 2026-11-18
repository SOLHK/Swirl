import QtQuick
Window {
    id: window
    width: 800; height: 600; visible: true
    property int round: 0
    Component {
        id: page
        Item {
            width: 800; height: 600
            Repeater { model: 12; Item { ProbeDialog {} } }
        }
    }
    Loader {
        id: loader
        asynchronous: true
        sourceComponent: page
        onLoaded: advance.start()
    }
    Timer {
        id: advance
        interval: 1
        onTriggered: {
            gcProbe.collect("loaded-page-before-eviction")
            loader.sourceComponent=null
            gcProbe.collect("evicted-page-before-events")
            if(++window.round===8) Qt.quit()
            else loader.sourceComponent=page
        }
    }
}

import QtQuick
QtObject {
    id: helper
    property QtObject target
    property bool initialized: false
    property var payload: ({ value: 3 })
    function scheduleRefresh() { payload = ({ value: 4 }) }
    property Connections changes: Connections {
        target: helper.initialized ? helper.target : null
        function onWidthChanged() { helper.scheduleRefresh() }
    }
    Component.onCompleted: {
        initialized=true
        scheduleRefresh()
        gcProbe.complete()
    }
}

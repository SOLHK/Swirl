pragma Singleton
import QtQuick
import SwirlQuick
QtObject {
    property int serial: 0
    property var active: ({})
    readonly property int activeCount: Object.keys(active).length
    function allocate() { return ++serial }
    function setActive(token, moving) {
        if(token===0)return
        if(Boolean(active[token])===moving)return
        const next = Object.assign({}, active)
        if (moving) next[token] = true
        else delete next[token]
        active = next
    }
}

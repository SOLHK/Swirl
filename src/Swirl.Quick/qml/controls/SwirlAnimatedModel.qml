import QtQuick
ListModel {
    id: model
    dynamicRoles:true
    property var source:[]
    property string keyRole:""
    property QtObject performanceObserver:null
    signal aboutToSync()
    signal synced()
    function sync() {
        const observer=performanceObserver
        if(observer)observer.mark(7,true)
        try {
            let changed=false
            function beginChange() {
                if(changed)return
                changed=true
                aboutToSync()
            }
            // Small editable draft lists use incremental operations so Qt can move
            // existing delegates. Large network tables keep their original model.
            const rows=source || []
            // Prune filtered-out keys first. A country/search subset can start at
            // the end of a large catalog; do not scan the discarded prefix for
            // every retained row. Batch adjacent removals and preserve delegates.
            if(keyRole) {
                const incoming=new Set(rows.map(row=>String(row[keyRole])))
                let last=count-1
                while(last>=0) {
                    if(incoming.has(get(last).motionKey)){--last;continue}
                    const end=last
                    while(last>=0&&!incoming.has(get(last).motionKey))--last
                    beginChange()
                    remove(last+1,end-last)
                }
            }
            let keys=null
            for(let i=0;i<rows.length;i++) {
                const signature=JSON.stringify(rows[i])
                const key=keyRole && rows[i][keyRole]!==undefined?String(rows[i][keyRole]):signature
                // Normal telemetry updates keep the same order: O(n), with one
                // serialization per incoming row and no repeated QObject traversal.
                let found=i<count && (keys?keys[i]:get(i).motionKey)===key?i:-1
                if(found<0) {
                    // Reorders search one plain JS snapshot instead of repeatedly
                    // crossing ListModel.get(). Stable updates never allocate it.
                    if(keys===null){keys=[];for(let j=0;j<count;++j)keys.push(get(j).motionKey)}
                    found=keys.indexOf(key,i+1)
                }
                if(found<0){beginChange();insert(i,{motionKey:key,motionSignature:signature,entry:rows[i]});keys.splice(i,0,key)}
                else {
                    if(found!==i){beginChange();move(found,i,1);keys.splice(i,0,keys.splice(found,1)[0])}
                    if(get(i).motionSignature!==signature){beginChange();setProperty(i,"entry",rows[i]);setProperty(i,"motionSignature",signature)}
                }
            }
            if(count>rows.length){beginChange();remove(rows.length,count-rows.length)}
            if(changed)synced()
        } finally {if(observer)observer.mark(7,false)}
    }
    onSourceChanged:sync()
    Component.onCompleted:sync()
}

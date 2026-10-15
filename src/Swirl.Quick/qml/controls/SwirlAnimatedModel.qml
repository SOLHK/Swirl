import QtQuick
ListModel {
    id: model
    dynamicRoles:true
    property var source:[]
    property string keyRole:""
    function sync() {
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
                remove(last+1,end-last)
            }
        }
        for(let i=0;i<rows.length;i++) {
            const signature=JSON.stringify(rows[i])
            const key=keyRole && rows[i][keyRole]!==undefined?String(rows[i][keyRole]):signature
            // Normal telemetry updates keep the same order: O(n), with one
            // serialization per incoming row and no repeated QObject traversal.
            let found=i<count && get(i).motionKey===key?i:-1
            if(found<0)for(let j=i+1;j<count;j++)if(get(j).motionKey===key){found=j;break}
            if(found<0)insert(i,{motionKey:key,motionSignature:signature,entry:rows[i]})
            else {
                if(found!==i)move(found,i,1)
                if(get(i).motionSignature!==signature){setProperty(i,"entry",rows[i]);setProperty(i,"motionSignature",signature)}
            }
        }
        if(count>rows.length)remove(rows.length,count-rows.length)
    }
    onSourceChanged:sync()
    Component.onCompleted:sync()
}

import QtQuick
ListModel {
    id: model
    dynamicRoles:true
    property var source:[]
    function sync() {
        // Small editable draft lists use incremental operations so Qt can move
        // existing delegates. Large network tables keep their original model.
        const rows=source || []
        for(let i=0;i<rows.length;i++) {
            const key=JSON.stringify(rows[i])
            let found=-1
            for(let j=i;j<count;j++)if(get(j).motionKey===key){found=j;break}
            if(found<0)insert(i,{motionKey:key,entry:rows[i]})
            else if(found!==i)move(found,i,1)
        }
        if(count>rows.length)remove(rows.length,count-rows.length)
    }
    onSourceChanged:sync()
    Component.onCompleted:sync()
}

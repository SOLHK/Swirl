.pragma library

// Original cloud loops, with short tucked ends extended through the crossings.
// Each continuous guide ends in the permanent cloud geometry.
var passages = [
    {
        "key": "warm",
        "tangent": [
            18,
            -10
        ],
        "guide": "M254 558 C272 548 288 561 283 581 C280 613 249 633 219 633 C173 637 144 604 145 560 C144 511 189 470 242 462 C291 454 315 476 355 500 C399 531 440 545 478 513 C514 487 533 447 516 416 C504 393 475 388 456 404 C439 415 436 430 445 432",
        "start": [
            254,
            558
        ],
        "card": "connections",
        "ink": "#E9A54E"
    },
    {
        "key": "return",
        "tangent": [
            -30,
            7
        ],
        "guide": "M490 558 C460 565 430 580 415 587 C370 606 335 644 338 693 C334 752 390 800 453 801 C515 805 566 764 575 713 C579 697 577 685 575 678 C575 655 568 637 559 620",
        "start": [
            490,
            558
        ],
        "card": "traffic",
        "ink": "#DD6A78"
    },
    {
        "key": "crown",
        "tangent": [
            -14,
            -21
        ],
        "guide": "M390 529 C376 508 363 474 352 447 C336 416 343 376 362 349 C391 308 430 287 475 288 C557 278 624 340 625 430 C630 486 600 533 550 568 C532 580 518 594 503 609",
        "start": [
            390,
            529
        ],
        "card": "connection",
        "ink": "#459AB3"
    },
    {
        "key": "forward",
        "tangent": [
            58,
            20
        ],
        "guide": "M450 557 C508 577 558 624 611 651 C661 677 715 679 755 662 C801 644 827 607 828 565 C835 516 793 478 749 479 C708 475 675 499 676 535 C673 554 688 568 701 569 C711 569 711 562 710 559",
        "start": [
            450,
            557
        ],
        "card": "sources",
        "ink": "#8874C2"
    },
    {
        "key": "heart",
        "tangent": [
            -13,
            -1
        ],
        "guide": "M455 664 C442 663 434 677 443 690 C461 719 505 689 530 647 C548 620 563 594 577 574",
        "start": [
            455,
            664
        ],
        "card": "diagnostics",
        "ink": "#59A990"
    }
];

// Four local overpasses alternate depth; no global strand z-order can express this.
// Positions are arc-length fractions on the centre lines above.
var crossings = [
    { passage: 0, start: 0.595, end: 0.677 }, // orange over cyan
    { passage: 1, start: 0.000, end: 0.091 }, // coral over purple
    { passage: 2, start: 0.918, end: 1.000 }, // cyan over purple
    { passage: 3, start: 0.112, end: 0.193 }  // purple over coral
];

// Closed original feather pieces travel as bodies, never as trimmed strokes.
var sourceIndices = [7, 10, 0, 11, 5];
var sourceSides = ["left", "left", "right", "left", "right"];
var arrivals = [0.68, 0.65, 0.69, 0.73, 0.76];
var widths = [74, 86, 80, 86, 54];
var cachedMaterials = null;
function point(x,y) { return {x:x,y:y}; }
function mix(a,b,t) { return point(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t); }
function distance(a,b) { return Math.hypot(a.x-b.x,a.y-b.y); }
function phaseEase(a,b,p) { const t=Math.max(0,Math.min(1,(p-a)/(b-a)));return t*t*(3-2*t); }
function cubic(a,b,c,d,t) { return mix(mix(mix(a,b,t),mix(b,c,t),t),mix(mix(b,c,t),mix(c,d,t),t),t); }
function sample(path) {
    const t=path.match(/[MCZ]|[-+]?\d*\.?\d+/g), result=[point(Number(t[1]),Number(t[2]))];
    for(let i=3;i<t.length && t[i]!=="Z";) {
        ++i; const a=result[result.length-1];
        const b=point(Number(t[i++]),Number(t[i++])),c=point(Number(t[i++]),Number(t[i++])),d=point(Number(t[i++]),Number(t[i++]));
        for(let n=1;n<=32;++n)result.push(cubic(a,b,c,d,n/32));
    }
    return result;
}
function resample(points,count) {
    const lengths=[0];for(let i=1;i<points.length;++i)lengths.push(lengths[i-1]+distance(points[i-1],points[i]));
    const result=[];let next=1;
    for(let i=0;i<=count;++i) { const d=lengths[lengths.length-1]*i/count;while(next<lengths.length-1 && lengths[next]<d)++next;
        result.push(mix(points[next-1],points[next],(d-lengths[next-1])/(lengths[next]-lengths[next-1]||1))); }
    return result;
}
function bounds(points) {
    const xs=points.map(p=>p.x),ys=points.map(p=>p.y);
    const l=Math.min.apply(null,xs),r=Math.max.apply(null,xs),t=Math.min.apply(null,ys),b=Math.max.apply(null,ys);
    return {x:l,y:t,width:r-l,height:b-t,center:point((l+r)/2,(t+b)/2)};
}
function closedPath(points) {
    function xy(p){return p.x.toFixed(3)+" "+p.y.toFixed(3);}
    let path="M"+xy(points[0]);
    for(let i=1;i<points.length;++i)path+=" C"+xy(mix(points[i-1],points[i],1/3))+" "+xy(mix(points[i-1],points[i],2/3))+" "+xy(points[i]);
    return path+" Z";
}
function materials(left,right) {
    if(cachedMaterials)return cachedMaterials;
    cachedMaterials=passages.map(function(p,index){
        const record=(sourceSides[index]==="right"?right:left)[sourceIndices[index]];
        const polygon=sample(record.path),root=point(record.root[0],record.root[1]),tip=point(record.tip[0],record.tip[1]);
        if(distance(polygon[0],polygon[polygon.length-1])<0.001)polygon.pop();
        function nearest(p){let best=0;for(let i=1;i<polygon.length;++i)if(distance(polygon[i],p)<distance(polygon[best],p))best=i;return best;}
        const ri=nearest(root),ti=nearest(tip);
        function side(direction){const part=[polygon[ri]];for(let i=(ri+direction+polygon.length)%polygon.length;i!==ri;i=(i+direction+polygon.length)%polygon.length){part.push(polygon[i]);if(i===ti)break;}return resample(part,96);}
        const a=side(1),b=side(-1),mid=a.map((v,i)=>mix(v,b[i],0.5));
        const profile=a.map(function(v,i){const tangent=point(mid[Math.min(96,i+1)].x-mid[Math.max(0,i-1)].x,mid[Math.min(96,i+1)].y-mid[Math.max(0,i-1)].y);return Math.abs((v.x-b[i].x)*(-tangent.y)+(v.y-b[i].y)*tangent.x)/(Math.hypot(tangent.x,tangent.y)||1);});
        const maximum=Math.max.apply(null,profile),spine=resample(sample(p.guide),96),first=[],second=[];
        for(let i=0;i<=96;++i){const before=spine[Math.max(0,i-1)],after=spine[Math.min(96,i+1)],length=distance(before,after)||1;
            const nx=-(after.y-before.y)/length,ny=(after.x-before.x)/length,w=widths[index]*profile[i]/maximum;
            first.push(point(spine[i].x+nx*w*.52,spine[i].y+ny*w*.52));second.push(point(spine[i].x-nx*w*.48,spine[i].y-ny*w*.48));}
        const contour=first.concat(second.reverse());
        return {key:p.key,card:p.card,ink:p.ink,index:index,side:sourceSides[index],sourceIndex:sourceIndices[index],record:record,
            sourceCenter:bounds(polygon).center,sourceRoot:root,sourceTip:tip,targetPath:closedPath(contour),
            targetRoot:spine[0],targetTip:spine[96],targetCenter:bounds(contour).center,arrival:arrivals[index]};
    });
    return cachedMaterials;
}
function transformPoint(s,p) { return point(s.tx+s.a*p.x+s.c*p.y,s.ty+s.b*p.x+s.d*p.y); }
function flight(material,source,scene,destination,gap) {
    const start=transformPoint(source,material.sourceCenter),sidebar=scene.sidebar;
    const lift=point(start.x+(material.side==="left"?-gap*.45:-gap*.6),start.y+(material.side==="left"?-gap*.6:gap*.45));
    const bottom=scene.viewport.y+scene.viewport.height-gap*2;
    function centre(rect,vertical){return point(rect.x+rect.width*.5,Math.max(scene.viewport.y+gap*2,Math.min(bottom,rect.y+rect.height*vertical)));}
    let way;
    if(material.index===0)way=[lift,point(sidebar.x+sidebar.width*.55,sidebar.y+sidebar.height*.45),point(sidebar.x+sidebar.width*.62,sidebar.y+gap*4),destination];
    else if(material.index===1)way=[lift,centre(scene.sources,.68),centre(scene.sources,.18),destination];
    else if(material.index===3)way=[lift,point(scene.connections.x-gap*3,bottom-gap),centre(scene.connections,.4),destination];
    else if(material.index===2){const buttons=scene.toolbar;way=[lift];for(let i=buttons.length-1;i>=0;--i)way.push(point(buttons[i].x+buttons[i].width*.5,buttons[i].y+buttons[i].height+gap*2));way.push(centre(scene.traffic,.45),destination);}
    else way=[lift,point(scene.traffic.x+scene.traffic.width*.64,scene.traffic.y+scene.traffic.height*.7),centre(scene.connections,.72),destination];
    const points=[way[0]];
    for(let i=0;i<way.length-1;++i){const a=way[i],d=way[i+1],before=way[Math.max(0,i-1)],after=way[Math.min(way.length-1,i+2)];
        const b=point(a.x+(d.x-before.x)*.18,a.y+(d.y-before.y)*.18),c=point(d.x-(after.x-a.x)*.18,d.y-(after.y-a.y)*.18);
        for(let n=1;n<=24;++n)points.push(cubic(a,b,c,d,n/24));}
    return {origin:start,lift:lift,points:resample(points,160),source:source};
}
function pose(material,route,progress,release,origin,scale,gap) {
    const dest=point(origin.x+material.targetCenter.x*scale,origin.y+material.targetCenter.y*scale);
    const localMorph=phaseEase(material.arrival,0.98,progress);
    const morph=localMorph*(1-phaseEase(0.03,0.6,release));
    let center=dest,angle=0,size=scale,fold=1,basis=null;
    if(progress<0.98 && route){
        const travel=phaseEase(.055,material.arrival,progress),i=travel*160,lo=Math.floor(i),hi=Math.min(160,lo+1);
        center=progress<.055?mix(route.origin,route.lift,phaseEase(0,.055,progress)):mix(route.points[lo],route.points[hi],i-lo);
        const breeze=Math.sin(Math.PI*travel);
        center.y+=gap*.55*breeze*Math.sin(travel*Math.PI*2+material.index*.7);
        const sourceScale=Math.sqrt(Math.abs(route.source.a*route.source.d-route.source.b*route.source.c));
        const startAngle=Math.atan2(route.source.b,route.source.a);
        angle=(startAngle+(material.side==="left"?-.09:.09)*phaseEase(0,.055,progress))*(1-travel)
            +breeze*([.36,-.55,.42,.68,-.48][material.index]+.18*Math.sin(travel*Math.PI*3+material.index));
        size=sourceScale+(scale-sourceScale)*localMorph;
        fold=1-.16*breeze*Math.pow(Math.sin(travel*Math.PI*2+material.index),2);
        if(progress<.055)basis=route.source;
    }
    center.x+=gap*(material.side==="left"?-2:2)*phaseEase(0,1,release);
    center.y-=gap*1.4*phaseEase(0,1,release);
    angle+=(material.index-2)*.11*phaseEase(0,1,release);
    const pivot=mix(material.sourceCenter,material.targetCenter,morph),cos=Math.cos(angle),sin=Math.sin(angle);
    let a=size*cos,b=size*sin,c=-size*sin*fold,d=size*cos*fold;
    if(basis){const lift=phaseEase(0,.055,progress);a=basis.a+(a-basis.a)*lift;b=basis.b+(b-basis.b)*lift;c=basis.c+(c-basis.c)*lift;d=basis.d+(d-basis.d)*lift;}
    return {a:a,b:b,c:c,d:d,tx:center.x-a*pivot.x-c*pivot.y,ty:center.y-b*pivot.x-d*pivot.y,morph:morph,
        opacity:phaseEase(0,.035,progress)*(.27+.73*phaseEase(.08,.60,progress))};
}

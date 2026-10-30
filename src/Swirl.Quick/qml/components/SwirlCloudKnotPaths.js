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

// Five feather tips leave together at the peak of their wing's lift.
// The longer destination tours leave about 2.5s of the 6s clock for the weave.
var timing = { connections: [0.055, 0.55, 0.84], connection: [0.055, 0.54, 0.91],
    traffic: [0.055, 0.50, 0.88], sources: [0.055, 0.60, 0.96], diagnostics: [0.055, 0.64, 0.99] };
function phaseEase(start, end, value) {
    const t=Math.max(0,Math.min(1,(value-start)/(end-start)));
    return t*t*(3-2*t);
}
function closePhase(value, card) {
    const delay={diagnostics:0,sources:0.035,connection:0.07,traffic:0.105,connections:0.14}[card];
    return phaseEase(0.04+delay,0.84+delay,value);
}
function point(x, y) { return { x: x, y: y } }
function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }
function mix(a, b, t) { return point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) }
function command(p) { return p.x.toFixed(3) + " " + p.y.toFixed(3) }
function cubicPoint(a, b, c, d, t) {
    const ab = mix(a, b, t), bc = mix(b, c, t), cd = mix(c, d, t);
    return mix(mix(ab, bc, t), mix(bc, cd, t), t);
}

// Tours visit the requested real surfaces: sidebar, sources, connections,
// toolbar->traffic, connections. Narrow/offscreen cards project to the viewport
// edge; their hidden headings are never copied into a fake visible location.
function route(passage, cards, emblem, origin, scale, wide, gap, scene) {
    const card=passage.card, status=cards.connection, wing=scene.wing;
    const entry=point(origin.x+passage.start[0]*scale,origin.y+passage.start[1]*scale);
    const tangent=point(passage.tangent[0],passage.tangent[1]);
    const tangentLength=Math.hypot(tangent.x,tangent.y);
    const approach=point(entry.x-tangent.x/tangentLength*gap,entry.y-tangent.y/tangentLength*gap);
    const rightLimit=scene.viewport.x+scene.viewport.width-gap*0.5;
    const bottomLimit=scene.viewport.y+scene.viewport.height-gap*0.6;
    const rowY=status.y+status.height+gap*0.5;
    const column=Math.min(rightLimit,status.x+status.width+gap*0.5);
    const gate=point(emblem.x+emblem.width*0.78,emblem.y+emblem.height-gap*0.5);
    const start=point(wing[0].x,wing[0].y), curves=[];
    let cursor=start;
    let aperture={x:0,y:0,width:0,height:0};
    function bend(b,c,d) { curves.push([cursor,b,c,d]); cursor=d; }
    function visibleTour(rect) {
        const y=Math.max(scene.viewport.y+gap*0.4,Math.min(rect.y,bottomLimit-gap*3));
        return {x:rect.x,y:y,width:rect.width,height:Math.max(gap*2,Math.min(rect.height,bottomLimit-y))};
    }
    function enterBelow(b) {
        bend(b,point(gate.x+gap,gate.y+gap),gate);
        bend(point(gate.x-gap,gate.y-gap),approach,entry);
    }
    function skimHeading(rect,title,incoming) {
        // A broad feather needs room: skim above the glyphs, never through the
        // five-dp gap between a title and its live values/filters.
        const visible=title.y>=scene.viewport.y && title.y+title.height<=bottomLimit;
        const y=visible?title.y-gap*0.48:rect.y-gap*0.5;
        const left=point(rect.x+gap*1.7,y);
        const end=point(Math.min(rect.x+rect.width-gap*1.7,left.x+Math.max(title.width+gap*2,gap*6)),y);
        bend(incoming,point(left.x-gap,y),left);
        bend(point(left.x+(end.x-left.x)*0.34,y),point(left.x+(end.x-left.x)*0.66,y),end);
        if (visible) {
            const half=gap*0.32;
            aperture={x:rect.x+gap*1.3,y:y-half,width:end.x-rect.x-gap*0.7,height:half*2};
        }
    }
    if (card === "connections") {
        // Gold lifts out along the sidebar's clear outer margin and over its
        // brand heading, then returns down the sidebar/content gutter.
        const left=scene.sidebar.x+gap*0.3, top=scene.sidebar.y+gap*0.35;
        const right=scene.sidebar.x+scene.sidebar.width+gap*0.5;
        const shoulder=point(left,scene.sidebar.y+gap*2.1);
        bend(wing[1],point(left,start.y-gap*3),point(left,start.y-gap*4));
        bend(point(left,cursor.y-gap*6),point(left,shoulder.y+gap*2),shoulder);
        bend(point(left,top),point(left+gap,top),point(left+gap*2.2,top));
        bend(point(left+gap*4,top),point(right,top),point(right,top+gap*2.2));
        const sweep=point(right+gap,rowY);
        bend(point(right,cursor.y+gap*4),point(right-gap,rowY),sweep);
        enterBelow(point(sweep.x+(gate.x-sweep.x)*0.5,rowY));
    } else if (card === "traffic") {
        // Coral visits the sources surface and its heading from the left.
        const target=visibleTour(cards.sources), left=target.x-gap*0.55;
        const side=point(left,target.y+Math.min(target.height*0.45,gap*4));
        bend(point(start.x+gap*2,start.y-gap),point(left,side.y+gap*3),side);
        skimHeading(target,scene.sourcesTitle,point(left,side.y-gap*3));
        const turn=point(Math.min(rightLimit,target.x+target.width+gap*0.45),target.y-gap*0.5);
        bend(point(cursor.x+gap*2,cursor.y),point(turn.x,turn.y+gap*2),turn);
        const back=point(column,rowY);
        bend(point(turn.x,turn.y-gap*2),point(back.x+gap*2,back.y),back);
        enterBelow(point(back.x-gap,rowY));
    } else if (card === "sources") {
        // Purple takes the low arc to the activity-connections card, then
        // rises beside its left shoulder. It does not queue in the left gutter.
        const target=visibleTour(cards.connections);
        const low=Math.min(bottomLimit,target.y+target.height+gap*0.45);
        const left=target.x-gap*0.55;
        const foot=point(left-gap,low);
        bend(point(start.x+gap*2,start.y+gap),point(foot.x-gap*4,low),foot);
        bend(point(left+gap,low),point(left,target.y+gap*4),point(left,target.y+gap*2));
        skimHeading(target,scene.connectionsTitle,point(left,target.y-gap));
        const seam=point(Math.min(rightLimit,target.x-gap*0.55),rowY+gap*0.2);
        bend(point(cursor.x+gap*1.5,cursor.y),point(seam.x,seam.y+gap*4),seam);
        enterBelow(point(seam.x,seam.y-gap*2));
    } else if (card === "connection") {
        // Cyan skims each of the three live toolbar controls from right to
        // left, with a shallow dip under TUN, before visiting the traffic card.
        for (let index=scene.toolbar.length-1;index>=0;--index) {
            const control=scene.toolbar[index];
            const stop=point(control.x+control.width*0.5,control.y+control.height+gap*(index===1?0.95:0.45));
            const reach=Math.max(gap,Math.abs(cursor.x-stop.x)*0.35);
            bend(point(cursor.x-reach,cursor.y),point(stop.x+reach,stop.y),stop);
        }
        const target=visibleTour(cards.traffic);
        skimHeading(target,scene.trafficTitle,point(cursor.x-gap,cursor.y));
        const side=point(column,emblem.y+emblem.height*0.5);
        bend(point(cursor.x+gap*2,cursor.y),point(column,side.y-gap*3),side);
        bend(point(column,side.y+gap*1.4),approach,entry);
    } else {
        // Green reaches the same connections card from the right, curls below
        // it, then climbs the seam between the lower cards back to the knot.
        const target=visibleTour(cards.connections);
        const outer=Math.min(rightLimit,target.x+target.width+gap*0.5);
        const lower=Math.min(bottomLimit,target.y+target.height+gap*0.45);
        const radius=gap*1.2, k=0.55228475;
        bend(point(start.x+gap,start.y),point(outer,start.y+gap),point(outer,start.y+gap*2));
        bend(point(outer,cursor.y+gap*4),point(outer,lower-radius-gap*2),point(outer,lower-radius));
        bend(point(outer,lower-radius+k*radius),point(outer-radius+k*radius,lower),point(outer-radius,lower));
        const left=Math.max(status.x+gap,target.x-gap*0.55), lowerLeft=point(left+radius,lower);
        bend(point(cursor.x-gap*2,lower),point(lowerLeft.x+gap*2,lower),lowerLeft);
        bend(point(left+radius-k*radius,lower),point(left,lower-radius+k*radius),point(left,lower-radius));
        const turn=point(left,rowY+gap);
        bend(point(left,cursor.y-gap*4),point(left,turn.y+gap*4),turn);
        enterBelow(point(left,turn.y-gap*2));
    }
    let guide = "M" + command(start), leadLength = 0;
    for (let j=0; j<curves.length; ++j) {
        const curve = curves[j];
        guide += " C" + command(curve[1]) + " " + command(curve[2]) + " " + command(curve[3]);
        let previous = curve[0];
        for (let n=1; n<=40; ++n) {
            const p=cubicPoint(curve[0],curve[1],curve[2],curve[3],n/40);
            leadLength+=distance(previous,p); previous=p;
        }
    }
    const tokens = passage.guide.match(/[MC]|[-+]?\d*\.?\d+/g);
    let i = 3, previous = entry, knotLength = 0;
    while (i < tokens.length) {
        ++i;
        const b = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        const c = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        const d = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        guide += " C" + command(b) + " " + command(c) + " " + command(d);
        const a = previous;
        for (let n = 1; n <= 40; ++n) { const p = cubicPoint(a, b, c, d, n / 40); knotLength += distance(previous, p); previous = p; }
    }
    const total = leadLength + knotLength;
    const times = timing[card];
    const cues = [[times[0],0], [times[1],leadLength/total], [times[2],1]];
    return {guide:guide, join:leadLength/total, span:110*gap/16/total, aperture:aperture, cues:cues};
}
function hermite(t, a, b, startSlope, endSlope, duration) {
    return (2*t*t*t-3*t*t+1)*a + (t*t*t-2*t*t+t)*startSlope*duration
        + (-2*t*t*t+3*t*t)*b + (t*t*t-t*t)*endSlope*duration;
}
function head(progress, card, route) {
    const cues = route.cues;
    if (progress <= cues[0][0]) return 0;
    if (progress >= cues[cues.length-1][0]) return 1;
    function slope(index) {
        if (index === 0 || index === cues.length-1) return 0;
        const left = (cues[index][1]-cues[index-1][1])/(cues[index][0]-cues[index-1][0]);
        const right = (cues[index+1][1]-cues[index][1])/(cues[index+1][0]-cues[index][0]);
        return Math.min(left,right);
    }
    for (let i=0; i<cues.length-1; ++i) {
        if (progress <= cues[i+1][0]) {
            const duration = cues[i+1][0]-cues[i][0];
            return hermite((progress-cues[i][0])/duration,cues[i][1],cues[i+1][1],slope(i),slope(i+1),duration);
        }
    }
    return 1;
}
function tail(progress, card, route, headPosition) {
    const times = timing[card];
    const t = Math.max(0, Math.min(1, (progress - times[1]) / (times[2] - times[1])));
    const tucked = route.join * t * t * (3 - 2 * t);
    return Math.min(headPosition, route.join, Math.max(0, headPosition - route.span, tucked));
}

.pragma library

// Rope centre lines use the original SVG coordinate system and colour gradients.
// Open round-ended strokes preserve the five passages and their over/under order.
var passages = [
    {
        "key": "warm",
        "index": 0,
        "guide": "M254 558 C272 548 288 561 283 581 C280 613 249 633 219 633 C173 637 144 604 145 560 C144 511 189 470 242 462 C291 454 315 476 355 500 C399 531 440 545 478 513 C514 487 533 447 516 416 C504 393 475 388 456 404 C439 415 436 430 445 432",
        "start": [
            254,
            558
        ],
        "gradient": [
            135.0,
            575.0,
            510.0,
            405.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#F5A04D",
                "dark": "#FFB567"
            },
            {
                "position": 0.38,
                "light": "#F47C51",
                "dark": "#FF9569"
            },
            {
                "position": 0.78,
                "light": "#EC5260",
                "dark": "#FF7685"
            },
            {
                "position": 1.0,
                "light": "#D93962",
                "dark": "#F55F86"
            }
        ]
    },
    {
        "key": "return",
        "index": 1,
        "guide": "M415 587 C370 606 335 644 338 693 C334 752 390 800 453 801 C515 805 566 764 575 713 C579 697 577 685 575 678",
        "start": [
            415,
            587
        ],
        "gradient": [
            342.0,
            636.0,
            546.0,
            775.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#098CAF",
                "dark": "#44B5D1"
            },
            {
                "position": 0.51,
                "light": "#12A39C",
                "dark": "#41C3B9"
            },
            {
                "position": 1.0,
                "light": "#3CAA79",
                "dark": "#6ACA96"
            }
        ]
    },
    {
        "key": "crown",
        "index": 2,
        "guide": "M352 447 C336 416 343 376 362 349 C391 308 430 287 475 288 C557 278 624 340 625 430 C630 486 600 533 550 568",
        "start": [
            352,
            447
        ],
        "gradient": [
            365.0,
            315.0,
            594.0,
            559.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#20B7D0",
                "dark": "#54D0E4"
            },
            {
                "position": 0.42,
                "light": "#188FD2",
                "dark": "#51B1EF"
            },
            {
                "position": 1.0,
                "light": "#285DD3",
                "dark": "#729BF5"
            }
        ]
    },
    {
        "key": "forward",
        "index": 3,
        "guide": "M450 557 C508 577 558 624 611 651 C661 677 715 679 755 662 C801 644 827 607 828 565 C835 516 793 478 749 479 C708 475 675 499 676 535 C673 554 688 568 701 569 C711 569 711 562 710 559",
        "start": [
            450,
            557
        ],
        "gradient": [
            444.0,
            562.0,
            827.0,
            538.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#285DD3",
                "dark": "#729BF5"
            },
            {
                "position": 0.43,
                "light": "#168DCB",
                "dark": "#4DADE4"
            },
            {
                "position": 0.78,
                "light": "#099DC2",
                "dark": "#37BBD8"
            },
            {
                "position": 1.0,
                "light": "#20AE9B",
                "dark": "#55CCB2"
            }
        ]
    },
    {
        "key": "heart",
        "index": 4,
        "guide": "M455 664 C442 663 434 677 443 690 C461 719 505 689 530 647",
        "start": [
            455,
            664
        ],
        "gradient": [
            442.0,
            706.0,
            531.0,
            644.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#1BAA9E",
                "dark": "#51C9B9"
            },
            {
                "position": 0.58,
                "light": "#099DC2",
                "dark": "#37BBD8"
            },
            {
                "position": 1.0,
                "light": "#287CCB",
                "dark": "#66A8E7"
            }
        ]
    }
];

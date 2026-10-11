pragma Singleton
import QtQuick
QtObject {
    readonly property var entries: [
  {
    "id": "feature-system",
    "title": "系统代理",
    "group": "接管与网络",
    "icon": "network",
    "sub": "系统代理接管、绕过地址、监听端口与身份验证。",
    "fields": [
      {
        "key": "f0",
        "label": "启用系统代理",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "HTTP 监听端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "SOCKS5 监听端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "绕过地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "允许局域网访问",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f5",
        "label": "身份验证",
        "options": [
          "关闭",
          "用户名与密码"
        ],
        "kind": "choice"
      }
    ],
    "keywords": " 启用系统代理 HTTP 监听端口 SOCKS5 监听端口 绕过地址 允许局域网访问 身份验证 关闭,用户名与密码",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-enhanced",
    "title": "增强模式 / TUN",
    "group": "接管与网络",
    "icon": "network",
    "sub": "虚拟接口、IPv4/IPv6 路由、包含和排除网段。",
    "fields": [
      {
        "key": "f0",
        "label": "启用增强模式",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "虚拟网卡名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "IPv4 地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "IPv6 地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "路由模式",
        "options": [
          "自动",
          "手动"
        ],
        "kind": "choice"
      },
      {
        "key": "f5",
        "label": "排除网段",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "MTU",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f7",
        "label": "允许 IPv6",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": "Enhanced VIF VPN 启用增强模式 虚拟网卡名称 IPv4 地址 IPv6 地址 路由模式 自动,手动 排除网段 MTU 允许 IPv6",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-networks",
    "title": "按网络设置",
    "group": "接管与网络",
    "icon": "network",
    "sub": "Wi-Fi、以太网、蜂窝网络配置与网络切换行为。",
    "fields": [
      {
        "key": "f0",
        "label": "网络类型",
        "options": [
          "Wi-Fi",
          "以太网",
          "蜂窝网络"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "SSID / BSSID",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "默认策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "DNS 覆盖",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "增强模式",
        "options": [
          "继承",
          "启用",
          "停用"
        ],
        "kind": "choice"
      },
      {
        "key": "f5",
        "label": "低数据模式",
        "options": [
          "继承",
          "启用",
          "停用"
        ],
        "kind": "choice"
      }
    ],
    "keywords": " 网络类型 Wi-Fi,以太网,蜂窝网络 SSID / BSSID 默认策略 DNS 覆盖 增强模式 继承,启用,停用 低数据模式 继承,启用,停用",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-routing",
    "title": "路由与接口",
    "group": "接管与网络",
    "icon": "network",
    "sub": "绑定出站接口、绕过路由与网络栈参数。",
    "fields": [
      {
        "key": "f0",
        "label": "出站接口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "路由网段",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "默认网关",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "IPv6",
        "options": [
          "自动",
          "启用",
          "停用"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "TCP 超时",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "UDP 超时",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "QUIC",
        "options": [
          "允许",
          "阻止",
          "按规则"
        ],
        "kind": "choice"
      }
    ],
    "keywords": " 出站接口 路由网段 默认网关 IPv6 自动,启用,停用 TCP 超时 UDP 超时 QUIC 允许,阻止,按规则",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "proxies",
    "title": "代理节点",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "节点管理、协议、检测与选择。",
    "fields": [],
    "keywords": "HTTP HTTPS SOCKS5 Shadowsocks SS Snell VMess Trojan TUIC Hysteria2 AnyTLS SSH WireGuard Tailscale ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-protocols",
    "title": "代理协议配置",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "完整协议入口与通用 / 专用连接参数。",
    "fields": [
      {
        "key": "f0",
        "label": "协议",
        "options": [
          "HTTP",
          "HTTPS",
          "SOCKS5",
          "Shadowsocks",
          "Snell",
          "VMess",
          "Trojan",
          "TUIC",
          "Hysteria 2",
          "AnyTLS",
          "SSH",
          "WireGuard",
          "Tailscale"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "服务器",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "用户名 / 身份标识",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "加密方式",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "SNI",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "传输",
        "options": [
          "TCP",
          "WebSocket",
          "UDP"
        ],
        "kind": "choice"
      },
      {
        "key": "f7",
        "label": "UDP 转发",
        "options": [
          "启用",
          "停用"
        ],
        "kind": "choice"
      }
    ],
    "keywords": "协议参数 协议 HTTP,HTTPS,SOCKS5,Shadowsocks,Snell,VMess,Trojan,TUIC,Hysteria 2,AnyTLS,SSH,WireGuard,Tailscale 服务器 端口 用户名 / 身份标识 加密方式 SNI 传输 TCP,WebSocket,UDP UDP 转发 启用,停用",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "policies",
    "title": "策略组",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "手动选择、测速、故障转移与负载均衡。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-policyadvanced",
    "title": "高级策略组",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "自动测试、备用策略、子网、智能选择与外部策略来源。",
    "fields": [
      {
        "key": "f0",
        "label": "类型",
        "options": [
          "Select",
          "URL Test",
          "Fallback",
          "Load Balance",
          "Subnet",
          "Smart"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "检测 URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "检测间隔",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "超时",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "容差",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "备用策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "子网匹配",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f7",
        "label": "外部策略来源",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": "smart subnet fallback url-test 类型 Select,URL Test,Fallback,Load Balance,Subnet,Smart 检测 URL 检测间隔 超时 容差 备用策略 子网匹配 外部策略来源",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "rules",
    "title": "分流规则",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "域名、IP、进程、协议与源地址匹配。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-rulesets",
    "title": "规则集与逻辑规则",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "远程规则集、组合条件、规则顺序和匹配测试入口。",
    "fields": [
      {
        "key": "f0",
        "label": "类型",
        "options": [
          "DOMAIN SET",
          "RULE SET",
          "AND",
          "OR",
          "NOT",
          "PROCESS",
          "PROTOCOL",
          "SRC-IP",
          "DEST-PORT",
          "GEOIP",
          "IP-CIDR",
          "FINAL"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "规则来源",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "更新间隔",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "默认策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "匹配表达式",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "启用规则集",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": "逻辑规则 domain-set rule-set 类型 DOMAIN SET,RULE SET,AND,OR,NOT,PROCESS,PROTOCOL,SRC-IP,DEST-PORT,GEOIP,IP-CIDR,FINAL 规则来源 更新间隔 默认策略 匹配表达式 启用规则集",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-udp",
    "title": "UDP 与协议控制",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "UDP 转发、UDP 回退、QUIC 与协议识别。",
    "fields": [
      {
        "key": "f0",
        "label": "启用 UDP",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "UDP 策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "回退策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "QUIC",
        "options": [
          "允许",
          "阻止",
          "按规则"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "协议识别",
        "options": [
          "自动",
          "仅 TCP",
          "仅 UDP"
        ],
        "kind": "choice"
      }
    ],
    "keywords": " 启用 UDP UDP 策略 回退策略 QUIC 允许,阻止,按规则 协议识别 自动,仅 TCP,仅 UDP",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "dns",
    "title": "DNS 解析器",
    "group": "DNS",
    "icon": "globe",
    "sub": "上游、查询、缓存与解析策略。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-encrypteddns",
    "title": "加密 DNS",
    "group": "DNS",
    "icon": "globe",
    "sub": "DoH、DoH3、DoQ、DoT 与引导地址。",
    "fields": [
      {
        "key": "f0",
        "label": "协议",
        "options": [
          "DoH",
          "DoH3",
          "DoQ",
          "DoT"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "服务器 URL / 地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "引导 IP",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "出站策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "证书名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "启用并发查询",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 协议 DoH,DoH3,DoQ,DoT 服务器 URL / 地址 引导 IP 出站策略 证书名称 启用并发查询",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-hosts",
    "title": "Hosts 与本地 DNS",
    "group": "DNS",
    "icon": "globe",
    "sub": "域名映射、别名、通配符与指定解析器。",
    "fields": [
      {
        "key": "f0",
        "label": "域名",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "记录类型",
        "options": [
          "A",
          "AAAA",
          "CNAME",
          "指定解析器"
        ],
        "kind": "choice"
      },
      {
        "key": "f2",
        "label": "目标 / 地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "TTL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "出站策略",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": " 域名 记录类型 A,AAAA,CNAME,指定解析器 目标 / 地址 TTL 出站策略",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-fakeip",
    "title": "Fake-IP 与 DNS 缓存",
    "group": "DNS",
    "icon": "globe",
    "sub": "虚拟 IP 范围、排除域名、缓存和 IPv6 应答。",
    "fields": [
      {
        "key": "f0",
        "label": "启用 Fake-IP",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "IPv4 范围",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "IPv6 范围",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "排除域名",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "缓存策略",
        "options": [
          "乐观缓存",
          "常规缓存",
          "禁用"
        ],
        "kind": "choice"
      },
      {
        "key": "f5",
        "label": "缓存上限",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "允许 AAAA",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 启用 Fake-IP IPv4 范围 IPv6 范围 排除域名 缓存策略 乐观缓存,常规缓存,禁用 缓存上限 允许 AAAA",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-dnspolicy",
    "title": "DNS 分流与应答",
    "group": "DNS",
    "icon": "globe",
    "sub": "按域名指定上游、DNS 劫持、回退与 DNS 脚本入口。",
    "fields": [
      {
        "key": "f0",
        "label": "域名匹配",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "上游服务器",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "回退服务器",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "应答方式",
        "options": [
          "正常",
          "Fake-IP",
          "拒绝"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "劫持端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "脚本名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "允许 mDNS",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 域名匹配 上游服务器 回退服务器 应答方式 正常,Fake-IP,拒绝 劫持端口 脚本名称 允许 mDNS",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "capture",
    "title": "抓包",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "已接入真实 HTTP 会话与 CONNECT 隧道记录。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "inspector",
    "title": "HTTP 检查器",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求、响应、正文、时间线和筛选。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "tls",
    "title": "HTTPS 解密 / MITM",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "解密范围、证书与会话检查界面。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-certificates",
    "title": "证书管理",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "CA 导入 / 导出、密码、信任状态与排除域名。",
    "fields": [
      {
        "key": "f0",
        "label": "证书名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "证书文件路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "私钥文件路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "启用 HTTPS 解密",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f4",
        "label": "域名列表",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "排除域名",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "证书校验",
        "options": [
          "严格",
          "按域名例外"
        ],
        "kind": "choice"
      }
    ],
    "keywords": " 证书名称 证书文件路径 私钥文件路径 启用 HTTPS 解密 域名列表 排除域名 证书校验 严格,按域名例外",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "rewrite",
    "title": "URL / 请求响应重写",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "URL、状态、头部、正文与重定向。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-bodyrewrite",
    "title": "正文与头部处理",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求 / 响应头、正文替换、JSON 与脚本处理。",
    "fields": [
      {
        "key": "f0",
        "label": "阶段",
        "options": [
          "请求头",
          "响应头",
          "请求正文",
          "响应正文"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "匹配 URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "匹配表达式",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "替换内容",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "正文上限",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "处理方式",
        "options": [
          "正则替换",
          "JSON 路径",
          "脚本"
        ],
        "kind": "choice"
      },
      {
        "key": "f6",
        "label": "启用规则",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 阶段 请求头,响应头,请求正文,响应正文 匹配 URL 匹配表达式 替换内容 正文上限 处理方式 正则替换,JSON 路径,脚本 启用规则",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "map",
    "title": "Map Local / Remote",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "本地响应与远程 URL 映射。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "breakpoint",
    "title": "HTTP 断点",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求 / 响应暂停和修改界面。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "replay",
    "title": "HTTP 重放与构造",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求方法、URL、头部、正文与重放。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-mock",
    "title": "本地响应与 Mock",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "响应状态、MIME、头部与文本 / 文件正文。",
    "fields": [
      {
        "key": "f0",
        "label": "匹配 URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "状态码",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "Content-Type",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "正文来源",
        "options": [
          "文本",
          "本地文件"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "正文 / 文件路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "响应头",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "启用 Mock",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 匹配 URL 状态码 Content-Type 正文来源 文本,本地文件 正文 / 文件路径 响应头 启用 Mock",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-websocket",
    "title": "WebSocket 会话",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "消息列表、方向、Opcode 与帧详情模块。",
    "fields": [
      {
        "key": "f0",
        "label": "URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "子协议",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "筛选表达式",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "正文显示",
        "options": [
          "文本",
          "十六进制"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "允许保留历史",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " URL 子协议 筛选表达式 正文显示 文本,十六进制 允许保留历史",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "profiles",
    "title": "配置文件",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "导入、编辑、历史版本与恢复。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-managed",
    "title": "托管配置与外部资源",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "配置 URL、更新间隔、外部规则、策略与资源管理。",
    "fields": [
      {
        "key": "f0",
        "label": "配置 URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "更新间隔",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "更新链路",
        "options": [
          "自动",
          "直连",
          "指定策略"
        ],
        "kind": "choice"
      },
      {
        "key": "f3",
        "label": "失败回退",
        "options": [
          "保留当前",
          "切换备用"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "启用自动更新",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f5",
        "label": "资源类型",
        "options": [
          "完整配置",
          "策略列表",
          "规则集",
          "域名集"
        ],
        "kind": "choice"
      }
    ],
    "keywords": " 配置 URL 更新间隔 更新链路 自动,直连,指定策略 失败回退 保留当前,切换备用 启用自动更新 资源类型 完整配置,策略列表,规则集,域名集",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "subscriptions",
    "title": "订阅管理",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "订阅源、更新、错误与节点预览。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "modules",
    "title": "配置模块",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "模块导入、参数、更新与启停。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-moduleadvanced",
    "title": "模块条件与参数",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "requirement 条件、参数覆盖、模块优先级与冲突。",
    "fields": [
      {
        "key": "f0",
        "label": "模块名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "需求表达式",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "参数声明",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "覆盖值",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "优先级",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "启用模块",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": "requirement expressions arguments override 模块名称 需求表达式 参数声明 覆盖值 优先级 启用模块",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "scripts",
    "title": "JavaScript 脚本",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "脚本编辑、控制台与存储界面。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-scripthooks",
    "title": "脚本触发与 API",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "请求 / 响应、规则、DNS、事件、Cron 和面板脚本。",
    "fields": [
      {
        "key": "f0",
        "label": "类型",
        "options": [
          "http-request",
          "http-response",
          "rule",
          "dns",
          "event",
          "cron",
          "generic",
          "panel"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "匹配表达式",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "脚本路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "参数",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "超时",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "正文上限",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "启用脚本",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": "$request $response $done $httpClient $persistentStore $notification $utils 类型 http-request,http-response,rule,dns,event,cron,generic,panel 匹配表达式 脚本路径 参数 超时 正文上限 启用脚本",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "automation",
    "title": "定时与自动化",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "Cron、网络变化和事件触发任务。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-panels",
    "title": "自定义面板",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "面板标题、图标、刷新间隔、内容与脚本来源。",
    "fields": [
      {
        "key": "f0",
        "label": "标题",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "图标",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "刷新间隔",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "内容",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "脚本路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "启用面板",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 标题 图标 刷新间隔 内容 脚本路径 启用面板",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-sync",
    "title": "配置同步与备份",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "同步来源、配置草稿、版本冲突与恢复入口。",
    "fields": [
      {
        "key": "f0",
        "label": "来源",
        "options": [
          "本地文件夹",
          "WebDAV",
          "iCloud 占位"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "同步路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "冲突策略",
        "options": [
          "询问",
          "保留本机",
          "保留远端"
        ],
        "kind": "choice"
      },
      {
        "key": "f3",
        "label": "启用自动同步",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f4",
        "label": "保留版本数",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": " 来源 本地文件夹,WebDAV,iCloud 占位 同步路径 冲突策略 询问,保留本机,保留远端 启用自动同步 保留版本数",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "gateway",
    "title": "网关与设备",
    "group": "设备与服务",
    "icon": "server",
    "sub": "网关模式、设备列表与接口管理。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-dhcp",
    "title": "DHCP 服务",
    "group": "设备与服务",
    "icon": "server",
    "sub": "地址池、租约、保留地址、网关与 DNS。",
    "fields": [
      {
        "key": "f0",
        "label": "启用 DHCP",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "监听接口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "地址池起点",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "地址池终点",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "子网掩码",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "默认网关",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "DNS 服务器",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f7",
        "label": "租约时长",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": " 启用 DHCP 监听接口 地址池起点 地址池终点 子网掩码 默认网关 DNS 服务器 租约时长",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-forwarding",
    "title": "端口转发",
    "group": "设备与服务",
    "icon": "server",
    "sub": "TCP / UDP 本地监听与目标转发。",
    "fields": [
      {
        "key": "f0",
        "label": "协议",
        "options": [
          "TCP",
          "UDP"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "监听地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "监听端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "目标主机",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "目标端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "出站策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "启用转发",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 协议 TCP,UDP 监听地址 监听端口 目标主机 目标端口 出站策略 启用转发",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-ponte",
    "title": "设备互联 / Ponte",
    "group": "设备与服务",
    "icon": "server",
    "sub": "设备配对、远程服务、授权与连通状态模块。",
    "fields": [
      {
        "key": "f0",
        "label": "设备名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "设备标识",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "远程服务端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "连接方式",
        "options": [
          "自动",
          "局域网",
          "中继"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "允许访问",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f5",
        "label": "授权范围",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": "Surge Ponte remote device 设备名称 设备标识 远程服务端口 连接方式 自动,局域网,中继 允许访问 授权范围",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-snellserver",
    "title": "Snell 服务端",
    "group": "设备与服务",
    "icon": "server",
    "sub": "监听、认证、版本、客户端和访问策略。",
    "fields": [
      {
        "key": "f0",
        "label": "启用服务",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "监听地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "监听端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "协议版本",
        "options": [
          "v4",
          "v5"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "预共享密钥引用",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "访问策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f6",
        "label": "允许 UDP",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 启用服务 监听地址 监听端口 协议版本 v4,v5 预共享密钥引用 访问策略 允许 UDP",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-mtproto",
    "title": "MTProto 服务端",
    "group": "设备与服务",
    "icon": "server",
    "sub": "Telegram 代理监听、密钥引用和客户端记录。",
    "fields": [
      {
        "key": "f0",
        "label": "启用服务",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "监听地址",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "监听端口",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "密钥引用",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "伪装域名",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "连接上限",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": " 启用服务 监听地址 监听端口 密钥引用 伪装域名 连接上限",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-remote",
    "title": "远程控制与设备授权",
    "group": "设备与服务",
    "icon": "server",
    "sub": "远程控制器地址、配对、权限与服务发现。",
    "fields": [
      {
        "key": "f0",
        "label": "设备名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "控制器 URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "认证引用",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "权限",
        "options": [
          "只读",
          "配置管理",
          "完全控制"
        ],
        "kind": "choice"
      },
      {
        "key": "f4",
        "label": "启用服务发现",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 设备名称 控制器 URL 认证引用 权限 只读,配置管理,完全控制 启用服务发现",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "dashboard",
    "title": "Dashboard 仪表盘",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "实时曲线、连接、资源与概览。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "connections",
    "title": "连接记录",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "域名、进程、策略、速度和连接详情。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "traffic",
    "title": "流量分析",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "域名、应用、节点与历史统计。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "toolbox",
    "title": "网络诊断",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "连通性、延迟、DNS、Traceroute 与请求测试。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-benchmark",
    "title": "代理测速与基准测试",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "批量延迟、可用性、带宽、策略对比和报告。",
    "fields": [
      {
        "key": "f0",
        "label": "测试类型",
        "options": [
          "延迟",
          "可用性",
          "下载",
          "上传"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "检测 URL",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "并发数",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "次数",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "超时",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "策略名称",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": " 测试类型 延迟,可用性,下载,上传 检测 URL 并发数 次数 超时 策略名称",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "api",
    "title": "HTTP API / 命令行",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "本地 API、CLI、权限与访问日志。",
    "fields": [],
    "keywords": "surge-cli HTTP API ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-urlscheme",
    "title": "URL Scheme 与快捷指令",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "导入、配置切换、启停与外部自动化入口。",
    "fields": [
      {
        "key": "f0",
        "label": "动作",
        "options": [
          "导入配置",
          "选择配置",
          "连接",
          "断开",
          "运行脚本"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "配置名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "脚本名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "URL Scheme",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "参数",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": "shortcuts siri url scheme 动作 导入配置,选择配置,连接,断开,运行脚本 配置名称 脚本名称 URL Scheme 参数",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "logs",
    "title": "Logbook 日志",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "诊断事件、筛选、详情和导出。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-notifications",
    "title": "通知与事件中心",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "脚本通知、失败提醒、触发来源和记录。",
    "fields": [
      {
        "key": "f0",
        "label": "启用通知",
        "options": [],
        "kind": "toggle"
      },
      {
        "key": "f1",
        "label": "级别",
        "options": [
          "全部",
          "错误",
          "静默"
        ],
        "kind": "choice"
      },
      {
        "key": "f2",
        "label": "来源",
        "options": [
          "网络",
          "规则",
          "脚本",
          "系统"
        ],
        "kind": "choice"
      },
      {
        "key": "f3",
        "label": "保留记录数",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "启用声音",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 启用通知 级别 全部,错误,静默 来源 网络,规则,脚本,系统 保留记录数 启用声音",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-platform",
    "title": "平台与移动设备",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "Always-on、按需连接、Wi-Fi / 蜂窝、低数据、SSID 与平台权限入口。",
    "fields": [
      {
        "key": "f0",
        "label": "平台",
        "options": [
          "Windows",
          "macOS 参考",
          "iOS 参考",
          "tvOS 参考"
        ],
        "kind": "choice"
      },
      {
        "key": "f1",
        "label": "连接方式",
        "options": [
          "手动",
          "按需",
          "Always-on"
        ],
        "kind": "choice"
      },
      {
        "key": "f2",
        "label": "按需匹配",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "蜂窝策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "低数据策略",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f5",
        "label": "权限说明",
        "options": [],
        "kind": "text"
      }
    ],
    "keywords": "on-demand VPN always-on iOS tvOS 平台 Windows,macOS 参考,iOS 参考,tvOS 参考 连接方式 手动,按需,Always-on 按需匹配 蜂窝策略 低数据策略 权限说明",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "settings",
    "title": "设置与偏好",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "外观、监听、安全、通用与版本信息。",
    "fields": [],
    "keywords": " ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  },
  {
    "id": "feature-external",
    "title": "外部工具",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "外部程序路径、启动参数和工具管理草稿。",
    "fields": [
      {
        "key": "f0",
        "label": "工具名称",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f1",
        "label": "程序路径",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f2",
        "label": "启动参数",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f3",
        "label": "工作目录",
        "options": [],
        "kind": "text"
      },
      {
        "key": "f4",
        "label": "启动方式",
        "options": [
          "手动",
          "连接后"
        ],
        "kind": "choice"
      },
      {
        "key": "f5",
        "label": "启用工具",
        "options": [],
        "kind": "toggle"
      }
    ],
    "keywords": " 工具名称 程序路径 启动参数 工作目录 启动方式 手动,连接后 启用工具",
    "sections": [
      "配置",
      "条目",
      "说明"
    ]
  }
]
    readonly property var categories: ["接管与网络", "代理与策略", "DNS", "HTTP 与调试", "配置与自动化", "设备与服务", "工具与系统"]
    function find(id) { for(var i=0;i<entries.length;i++)if(entries[i].id===id)return entries[i];return null }
}

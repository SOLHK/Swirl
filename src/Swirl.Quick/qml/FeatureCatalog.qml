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
    "keywords": " 启用系统代理 HTTP 监听端口 SOCKS5 监听端口 绕过地址 允许局域网访问 身份验证 关闭,用户名与密码 系统代理 · use-local-host-item-for-proxy 系统代理 · System Proxy Bypass 系统代理 · skip-proxy 系统代理 · exclude-simple-hostnames 系统代理 · Proxy Services & Remote Access 系统代理 · proxy-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+ 系统代理 · Sharing Proxy Services over LAN 系统代理 · allow-wifi-access 系统代理 · allow-hotspot-access 系统代理 · wifi-access-http-port 系统代理 · wifi-access-socks5-port 系统代理 · wifi-access-http-auth 系统代理 · http-listen 系统代理 · socks5-listen 系统代理 · set-system-socks-proxy 系统代理开启 系统代理关闭 读取真实 Windows 代理状态 按偏好自动接管 PAC 与绕过列表恢复 GUI 和引擎崩溃恢复 多实例竞争保护 外部代理修改保护 局域网 HTTP / SOCKS5 代理 局域网代理身份验证",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "settings",
    "capabilities": [
      {
        "name": "系统代理 · use-local-host-item-for-proxy",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · System Proxy Bypass",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · skip-proxy",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · exclude-simple-hostnames",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · Proxy Services & Remote Access",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · proxy-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · Sharing Proxy Services over LAN",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · allow-wifi-access",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · allow-hotspot-access",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · wifi-access-http-port",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · wifi-access-socks5-port",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · wifi-access-http-auth",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · http-listen",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · socks5-listen",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理 · set-system-socks-proxy",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "系统代理开启",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "系统代理关闭",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "读取真实 Windows 代理状态",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "按偏好自动接管",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "PAC 与绕过列表恢复",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "GUI 和引擎崩溃恢复",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "多实例竞争保护",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "外部代理修改保护",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "局域网 HTTP / SOCKS5 代理",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "局域网代理身份验证",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": "Enhanced VIF VPN 启用增强模式 虚拟网卡名称 IPv4 地址 IPv6 地址 路由模式 自动,手动 排除网段 MTU 允许 IPv6 增强模式 / TUN · Enhanced Mode 增强模式 / TUN · How the VIF Works 增强模式 / TUN · Related [General] Options 增强模式 / TUN · IPv6 & Virtual Network Interface 增强模式 / TUN · ipv6 增强模式 / TUN · ipv6-vif 增强模式 / TUN · tun-excluded-routes 增强模式 / TUN · tun-included-routes 增强模式 / TUN · icmp-forwarding iOS 5.14.3+ Mac 5.10.0+ TUN 增强模式 IPv4 / IPv6 接管 包含与排除路由 ICMP 转发",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "增强模式 / TUN · Enhanced Mode",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · How the VIF Works",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · Related [General] Options",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · IPv6 & Virtual Network Interface",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · ipv6",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · ipv6-vif",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · tun-excluded-routes",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · tun-included-routes",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "增强模式 / TUN · icmp-forwarding iOS 5.14.3+ Mac 5.10.0+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "TUN 增强模式",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "IPv4 / IPv6 接管",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "包含与排除路由",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "ICMP 转发",
        "source": "https://manual.nssurge.com/features/enhanced-mode.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/enhanced-mode.html",
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": " 网络类型 Wi-Fi,以太网,蜂窝网络 SSID / BSSID 默认策略 DNS 覆盖 增强模式 继承,启用,停用 低数据模式 继承,启用,停用 按网络设置 · Subnet Settings 按网络设置 · suspend 按网络设置 · cellular-fallback iOS Only 按网络设置 · cellular-mode Mac Only 按网络设置 · tfo-behaviour 按网络设置 · dns-server 按网络设置 · encrypted-dns-server 按 Wi-Fi / 网关切换配置 网络变化自动重新检测",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "按网络设置 · Subnet Settings",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按网络设置 · suspend",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按网络设置 · cellular-fallback iOS Only",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按网络设置 · cellular-mode Mac Only",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按网络设置 · tfo-behaviour",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按网络设置 · dns-server",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按网络设置 · encrypted-dns-server",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "按 Wi-Fi / 网关切换配置",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "网络变化自动重新检测",
        "source": "https://manual.nssurge.com/features/subnet-settings.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/subnet-settings.html"
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
    "keywords": " 出站接口 路由网段 默认网关 IPv6 自动,启用,停用 TCP 超时 UDP 超时 QUIC 允许,阻止,按规则 路由与接口 · Common Policy Parameters 路由与接口 · Egress Parameters 路由与接口 · interface 路由与接口 · allow-other-interface 路由与接口 · dns-follow-interface iOS 5.15.2+ Mac 5.2.0+ 路由与接口 · no-error-alert 路由与接口 · ip-version 路由与接口 · tfo 路由与接口 · tos 路由与接口 · ecn iOS 5.8.0+ Mac 5.4.0+ 路由与接口 · block-quic iOS 5.8.0+ Mac 5.4.0+ 网络接口绑定 接口故障回退 IP 版本选择 代理链",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "路由与接口 · Common Policy Parameters",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · Egress Parameters",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · interface",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · allow-other-interface",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · dns-follow-interface iOS 5.15.2+ Mac 5.2.0+",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · no-error-alert",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · ip-version",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · tfo",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · tos",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · ecn iOS 5.8.0+ Mac 5.4.0+",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "路由与接口 · block-quic iOS 5.8.0+ Mac 5.4.0+",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网络接口绑定",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "接口故障回退",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "IP 版本选择",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "代理链",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/parameters.html"
    ]
  },
  {
    "id": "proxies",
    "title": "代理节点",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "节点管理、协议、检测与选择。",
    "fields": [],
    "keywords": "HTTP HTTPS SOCKS5 Shadowsocks SS Snell VMess Trojan TUIC Hysteria2 AnyTLS SSH WireGuard Tailscale  24 种协议导入与凭据保护 全部节点独立测速 单节点独立测试请求 连接 / 断开 / 切换节点 独立超时与取消",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "24 种协议导入与凭据保护",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "全部节点独立测速",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "单节点独立测试请求",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "连接 / 断开 / 切换节点",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "独立超时与取消",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/testing.html"
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
    "keywords": "协议参数 协议 HTTP,HTTPS,SOCKS5,Shadowsocks,Snell,VMess,Trojan,TUIC,Hysteria 2,AnyTLS,SSH,WireGuard,Tailscale 服务器 端口 用户名 / 身份标识 加密方式 SNI 传输 TCP,WebSocket,UDP UDP 转发 启用,停用 代理协议配置 · AnyTLS iOS 5.17.0+ Mac 6.4.3+ 代理协议配置 · password 代理协议配置 · reuse 代理协议配置 · Built-in Policies 代理协议配置 · DIRECT 代理协议配置 · Alias 代理协议配置 · HTTP, HTTPS, and HTTP/2 CONNECT Proxy 代理协议配置 · username / password 代理协议配置 · always-use-connect 代理协议配置 · headers Mac 6.6.0+ 代理协议配置 · max-streams Mac 6.6.0+ 代理协议配置 · udp-relay iOS 5.22.0+ Mac 6.9.0+ 代理协议配置 · Hysteria 2 iOS 5.8.0+ Mac 5.4.0+ 代理协议配置 · password 代理协议配置 · download-bandwidth 代理协议配置 · port-hopping 代理协议配置 · port-hopping-interval 代理协议配置 · salamander-password Mac 6.4.3+ 代理协议配置 · gecko-password iOS 5.20.0+ Mac 6.7.0+ 代理协议配置 · MASQUE iOS 5.22.0+ Mac 6.9.0+ 代理协议配置 · username / password 代理协议配置 · port-hopping 代理协议配置 · port-hopping-interval 代理协议配置 · Policies 代理协议配置 · Referencing Policies 代理协议配置 · Supported Proxy Protocols 代理协议配置 · Shadowsocks 代理协议配置 · encrypt-method 代理协议配置 · password 代理协议配置 · udp-relay 代理协议配置 · udp-port iOS 5.14.0+ Mac 5.9.0+ 代理协议配置 · obfs 代理协议配置 · obfs-host 代理协议配置 · obfs-uri 代理协议配置 · Snell 代理协议配置 · psk 代理协议配置 · version 代理协议配置 · reuse 代理协议配置 · obfs 代理协议配置 · obfs-host 代理协议配置 · obfs-uri 代理协议配置 · udp-port 代理协议配置 · mode 代理协议配置 · UDP Relay 代理协议配置 · Snell v6 iOS 5.20.0+ Mac 6.7.0+ 代理协议配置 · SOCKS5 Proxy 代理协议配置 · username / password 代理协议配置 · udp-relay 代理协议配置 · SSH 代理协议配置 · username 代理协议配置 · password 代理协议配置 · private-key 代理协议配置 · idle-timeout 代理协议配置 · server-fingerprint 代理协议配置 · Algorithm Requirements 代理协议配置 · Pinning the Server Fingerprint 代理协议配置 · Tailscale iOS 5.20.0+ Mac 6.7.0+ 代理协议配置 · section-name 代理协议配置 · underlying-proxy 代理协议配置 · test-url 代理协议配置 · test-timeout 代理协议配置 · Tailscale Section 代理协议配置 · auth-key 代理协议配置 · interactive-login iOS 5.21.0+ Mac 6.8.0+ 代理协议配置 · control-url 代理协议配置 · hostname 代理协议配置 · derp-only 代理协议配置 · auto-add-magic-dns-rule iOS 5.21.0+ Mac 6.8.0+ 代理协议配置 · exit-node 代理协议配置 · idle-keepalive iOS 5.21.0+ Mac 6.8.0+ 代理协议配置 · prefer-ipv6 代理协议配置 · dns-server 代理协议配置 · mtu 代理协议配置 · More Examples 代理协议配置 · Routing and Transport 代理协议配置 · DNS and MagicDNS 代理协议配置 · Policy Testing 代理协议配置 · TLS Parameters 代理协议配置 · skip-cert-verify 代理协议配置 · sni 代理协议配置 · server-cert-verify-name iOS 5.21.0+ Mac 6.8.0+ 代理协议配置 · server-cert-fingerprint-sha256 代理协议配置 · alpn iOS 5.20.0+ Mac 6.7.0+ 代理协议配置 · client-cert 代理协议配置 · Shadow TLS 代理协议配置 · shadow-tls-password 代理协议配置 · shadow-tls-sni 代理协议配置 · shadow-tls-version 代理协议配置 · Trojan 代理协议配置 · password 代理协议配置 · ws 代理协议配置 · ws-path 代理协议配置 · ws-headers 代理协议配置 · Trust Tunnel Mac 6.4.4+ 代理协议配置 · username 代理协议配置 · password 代理协议配置 · headers Mac 6.6.0+ 代理协议配置 · max-streams Mac 6.6.0+ 代理协议配置 · h3 iOS 5.22.0+ Mac 6.9.0+ 代理协议配置 · TUIC 代理协议配置 · token 代理协议配置 · uuid 代理协议配置 · password 代理协议配置 · alpn 代理协议配置 · port-hopping 代理协议配置 · port-hopping-interval 代理协议配置 · VMess 代理协议配置 · username 代理协议配置 · encrypt-method 代理协议配置 · vmess-aead 代理协议配置 · tls 代理协议配置 · ws 代理协议配置 · ws-path 代理协议配置 · ws-headers 代理协议配置 · WireGuard 代理协议配置 · section-name 代理协议配置 · underlying-proxy 代理协议配置 · test-url 代理协议配置 · test-timeout 代理协议配置 · WireGuard Section 代理协议配置 · private-key 代理协议配置 · self-ip 代理协议配置 · self-ip-v6 代理协议配置 · dns-server 代理协议配置 · prefer-ipv6 代理协议配置 · mtu 代理协议配置 · peer 代理协议配置 · Peer Fields 代理协议配置 · public-key 代理协议配置 · allowed-ips 代理协议配置 · endpoint 代理协议配置 · preshared-key 代理协议配置 · keepalive 代理协议配置 · client-id iOS 5.3.1+ Mac 4.10.3+ 代理协议配置 · Policy Testing iOS 5.20.0+ Mac 6.7.0+ 代理协议配置 · ECN and DSCP",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "代理协议配置 · AnyTLS iOS 5.17.0+ Mac 6.4.3+",
        "source": "https://manual.nssurge.com/policies/anytls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/anytls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · reuse",
        "source": "https://manual.nssurge.com/policies/anytls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Built-in Policies",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · DIRECT",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Alias",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · HTTP, HTTPS, and HTTP/2 CONNECT Proxy",
        "source": "https://manual.nssurge.com/policies/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · username / password",
        "source": "https://manual.nssurge.com/policies/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · always-use-connect",
        "source": "https://manual.nssurge.com/policies/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · headers Mac 6.6.0+",
        "source": "https://manual.nssurge.com/policies/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · max-streams Mac 6.6.0+",
        "source": "https://manual.nssurge.com/policies/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · udp-relay iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/policies/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Hysteria 2 iOS 5.8.0+ Mac 5.4.0+",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · download-bandwidth",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · port-hopping",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · port-hopping-interval",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · salamander-password Mac 6.4.3+",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · gecko-password iOS 5.20.0+ Mac 6.7.0+",
        "source": "https://manual.nssurge.com/policies/hysteria2.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · MASQUE iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/policies/masque.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · username / password",
        "source": "https://manual.nssurge.com/policies/masque.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · port-hopping",
        "source": "https://manual.nssurge.com/policies/masque.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · port-hopping-interval",
        "source": "https://manual.nssurge.com/policies/masque.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Policies",
        "source": "https://manual.nssurge.com/policies/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Referencing Policies",
        "source": "https://manual.nssurge.com/policies/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Supported Proxy Protocols",
        "source": "https://manual.nssurge.com/policies/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Shadowsocks",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · encrypt-method",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · udp-relay",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · udp-port iOS 5.14.0+ Mac 5.9.0+",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · obfs",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · obfs-host",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · obfs-uri",
        "source": "https://manual.nssurge.com/policies/shadowsocks.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Snell",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · psk",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · version",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · reuse",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · obfs",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · obfs-host",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · obfs-uri",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · udp-port",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · mode",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · UDP Relay",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Snell v6 iOS 5.20.0+ Mac 6.7.0+",
        "source": "https://manual.nssurge.com/policies/snell.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · SOCKS5 Proxy",
        "source": "https://manual.nssurge.com/policies/socks5.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · username / password",
        "source": "https://manual.nssurge.com/policies/socks5.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · udp-relay",
        "source": "https://manual.nssurge.com/policies/socks5.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · SSH",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · username",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · private-key",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · idle-timeout",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · server-fingerprint",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Algorithm Requirements",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Pinning the Server Fingerprint",
        "source": "https://manual.nssurge.com/policies/ssh.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Tailscale iOS 5.20.0+ Mac 6.7.0+",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · section-name",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · underlying-proxy",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · test-url",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · test-timeout",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Tailscale Section",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · auth-key",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · interactive-login iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · control-url",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · hostname",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · derp-only",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · auto-add-magic-dns-rule iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · exit-node",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · idle-keepalive iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · prefer-ipv6",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · dns-server",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · mtu",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · More Examples",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Routing and Transport",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · DNS and MagicDNS",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Policy Testing",
        "source": "https://manual.nssurge.com/policies/tailscale.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · TLS Parameters",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · skip-cert-verify",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · sni",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · server-cert-verify-name iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · server-cert-fingerprint-sha256",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · alpn iOS 5.20.0+ Mac 6.7.0+",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · client-cert",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Shadow TLS",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · shadow-tls-password",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · shadow-tls-sni",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · shadow-tls-version",
        "source": "https://manual.nssurge.com/policies/tls.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Trojan",
        "source": "https://manual.nssurge.com/policies/trojan.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/trojan.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ws",
        "source": "https://manual.nssurge.com/policies/trojan.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ws-path",
        "source": "https://manual.nssurge.com/policies/trojan.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ws-headers",
        "source": "https://manual.nssurge.com/policies/trojan.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Trust Tunnel Mac 6.4.4+",
        "source": "https://manual.nssurge.com/policies/trust-tunnel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · username",
        "source": "https://manual.nssurge.com/policies/trust-tunnel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/trust-tunnel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · headers Mac 6.6.0+",
        "source": "https://manual.nssurge.com/policies/trust-tunnel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · max-streams Mac 6.6.0+",
        "source": "https://manual.nssurge.com/policies/trust-tunnel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · h3 iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/policies/trust-tunnel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · TUIC",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · token",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · uuid",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · password",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · alpn",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · port-hopping",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · port-hopping-interval",
        "source": "https://manual.nssurge.com/policies/tuic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · VMess",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · username",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · encrypt-method",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · vmess-aead",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · tls",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ws",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ws-path",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ws-headers",
        "source": "https://manual.nssurge.com/policies/vmess.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · WireGuard",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · section-name",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · underlying-proxy",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · test-url",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · test-timeout",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · WireGuard Section",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · private-key",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · self-ip",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · self-ip-v6",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · dns-server",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · prefer-ipv6",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · mtu",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · peer",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Peer Fields",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · public-key",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · allowed-ips",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · endpoint",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · preshared-key",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · keepalive",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · client-id iOS 5.3.1+ Mac 4.10.3+",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · Policy Testing iOS 5.20.0+ Mac 6.7.0+",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理协议配置 · ECN and DSCP",
        "source": "https://manual.nssurge.com/policies/wireguard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/anytls.html",
      "https://manual.nssurge.com/policies/built-in.html",
      "https://manual.nssurge.com/policies/http.html",
      "https://manual.nssurge.com/policies/hysteria2.html",
      "https://manual.nssurge.com/policies/masque.html",
      "https://manual.nssurge.com/policies/overview.html",
      "https://manual.nssurge.com/policies/shadowsocks.html",
      "https://manual.nssurge.com/policies/snell.html",
      "https://manual.nssurge.com/policies/socks5.html",
      "https://manual.nssurge.com/policies/ssh.html",
      "https://manual.nssurge.com/policies/tailscale.html",
      "https://manual.nssurge.com/policies/tls.html",
      "https://manual.nssurge.com/policies/trojan.html",
      "https://manual.nssurge.com/policies/trust-tunnel.html",
      "https://manual.nssurge.com/policies/tuic.html",
      "https://manual.nssurge.com/policies/vmess.html",
      "https://manual.nssurge.com/policies/wireguard.html"
    ]
  },
  {
    "id": "policies",
    "title": "策略组",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "手动选择、测速、故障转移与负载均衡。",
    "fields": [],
    "keywords": "  策略组 · Fallback Group 策略组 · interval 策略组 · timeout 策略组 · evaluate-before-use 策略组 · Load Balance Group 策略组 · persistent 策略组 · Policy Groups 策略组 · Group Types 策略组 · How Testing Works 策略组 · Manual Selection Group 策略组 · Subnet Group 策略组 · Conditions 策略组 · default 策略组 · cellular 策略组 · Automatic Testing Group 策略组 · How Testing Works 策略组 · interval 策略组 · tolerance 策略组 · timeout 策略组 · evaluate-before-use 手动策略组 延迟自动选择 故障转移 负载均衡 策略运行状态 按网络选择 嵌套组循环检测",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "策略组 · Fallback Group",
        "source": "https://manual.nssurge.com/policy-groups/fallback.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · interval",
        "source": "https://manual.nssurge.com/policy-groups/fallback.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · timeout",
        "source": "https://manual.nssurge.com/policy-groups/fallback.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · evaluate-before-use",
        "source": "https://manual.nssurge.com/policy-groups/fallback.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Load Balance Group",
        "source": "https://manual.nssurge.com/policy-groups/load-balance.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · persistent",
        "source": "https://manual.nssurge.com/policy-groups/load-balance.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Policy Groups",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Group Types",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · How Testing Works",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Manual Selection Group",
        "source": "https://manual.nssurge.com/policy-groups/select.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Subnet Group",
        "source": "https://manual.nssurge.com/policy-groups/subnet.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Conditions",
        "source": "https://manual.nssurge.com/policy-groups/subnet.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · default",
        "source": "https://manual.nssurge.com/policy-groups/subnet.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · cellular",
        "source": "https://manual.nssurge.com/policy-groups/subnet.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · Automatic Testing Group",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · How Testing Works",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · interval",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · tolerance",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · timeout",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略组 · evaluate-before-use",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "手动策略组",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "延迟自动选择",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "故障转移",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "负载均衡",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "策略运行状态",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "按网络选择",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "嵌套组循环检测",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policy-groups/fallback.html",
      "https://manual.nssurge.com/policy-groups/load-balance.html",
      "https://manual.nssurge.com/policy-groups/overview.html",
      "https://manual.nssurge.com/policy-groups/select.html",
      "https://manual.nssurge.com/policy-groups/subnet.html",
      "https://manual.nssurge.com/policy-groups/url-test.html"
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
    "keywords": "smart subnet fallback url-test 类型 Select,URL Test,Fallback,Load Balance,Subnet,Smart 检测 URL 检测间隔 超时 容差 备用策略 子网匹配 外部策略来源 高级策略组 · Proxy Chain 高级策略组 · underlying-proxy 高级策略组 · Common Group Parameters 高级策略组 · no-alert 高级策略组 · hidden 高级策略组 · icon-url Mac 6.5.0+ 高级策略组 · category iOS 5.23.0+ Mac 6.10.0+ 高级策略组 · underlying-proxy iOS 5.22.0+ Mac 6.9.0+ 高级策略组 · Testing URL and Timeout 高级策略组 · Policy Including 高级策略组 · Include External Policies 高级策略组 · update-interval 高级策略组 · policy-regex-filter 高级策略组 · external-policy-modifier 高级策略组 · external-policy-name-prefix 高级策略组 · Include Existing Policies iOS 4.12.0+ Mac 4.5.0+ 高级策略组 · include-all-proxies 高级策略组 · include-other-group 高级策略组 · Ordering",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "高级策略组 · Proxy Chain",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · underlying-proxy",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · Common Group Parameters",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · no-alert",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · hidden",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · icon-url Mac 6.5.0+",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · category iOS 5.23.0+ Mac 6.10.0+",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · underlying-proxy iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · Testing URL and Timeout",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · Policy Including",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · Include External Policies",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · update-interval",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · policy-regex-filter",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · external-policy-modifier",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · external-policy-name-prefix",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · Include Existing Policies iOS 4.12.0+ Mac 4.5.0+",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · include-all-proxies",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · include-other-group",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "高级策略组 · Ordering",
        "source": "https://manual.nssurge.com/policy-groups/policy-including.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/parameters.html",
      "https://manual.nssurge.com/policy-groups/parameters.html",
      "https://manual.nssurge.com/policy-groups/policy-including.html"
    ]
  },
  {
    "id": "rules",
    "title": "分流规则",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "域名、IP、进程、协议与源地址匹配。",
    "fields": [],
    "keywords": "  分流规则 · Domain Rules 分流规则 · Matching Semantics 分流规则 · DOMAIN 分流规则 · DOMAIN-SUFFIX 分流规则 · DOMAIN-KEYWORD 分流规则 · DOMAIN-WILDCARD 分流规则 · DOMAIN-SET 分流规则 · DOMAIN-SET File Format 分流规则 · extended-matching iOS 5.8.0+ Mac 5.4.0+ 分流规则 · pre-matching iOS 5.14.0+ Mac 5.9.0+ 分流规则 · Final Rule 分流规则 · dns-failed 分流规则 · Relationship to Outbound Mode 分流规则 · HTTP Rules 分流规则 · When HTTP Rules Apply 分流规则 · USER-AGENT 分流规则 · URL-REGEX 分流规则 · IP Rules 分流规则 · IP Rules and DNS 分流规则 · IP-CIDR 分流规则 · IP-CIDR6 分流规则 · Unknown Database Results iOS 5.102.0+ Mac 6.9.1+ 分流规则 · no-resolve 分流规则 · pre-matching iOS 5.14.0+ Mac 5.9.0+ 分流规则 · Rules Overview 分流规则 · Composition 分流规则 · Evaluation Order 分流规则 · Rules and DNS 分流规则 · Rule Parameters 分流规则 · notification-text and notification-interval 分流规则 · Rule Type Index 分流规则 · Process Rules 分流规则 · PROCESS-NAME Mac Only 分流规则 · Protocol and Network Rules 分流规则 · PROTOCOL 分流规则 · HOSTNAME-TYPE Mac 5.7.3+ 分流规则 · CELLULAR-RADIO iOS Only 分流规则 · CELLULAR-CARRIER iOS Only 分流规则 · SUBNET 分流规则 · Subnet Expressions 分流规则 · SSID:<value> 分流规则 · BSSID:<value> 分流规则 · ROUTER:<ip> 分流规则 · TYPE:WIFI / TYPE:WIRED / TYPE:CELLULAR 分流规则 · MCCMNC:<digits> 分流规则 · Bare value (legacy) 分流规则 · Source and Port Rules 分流规则 · When Source-Based Rules Make Sense 分流规则 · Port Expressions 分流规则 · DEST-PORT 分流规则 · SRC-PORT iOS 5.8.4+ Mac 5.4.4+ 分流规则 · IN-PORT 分流规则 · SRC-IP 分流规则 · DEVICE-NAME 分流规则 · MAC-ADDRESS Mac 6.1.0+ 规则 / 全局 / 直连真实模式 局域网与本机直连 中国域名与 IP 直连 国外目标代理 规则顺序查看 连接匹配规则查看 缺少规则数据明确报错 精确域名规则 域名后缀规则 域名关键词规则 通配域名规则 IPv4 / IPv6 CIDR 进程规则 目标 / 来源 / 监听端口规则 来源 IP 规则 设备名称和 MAC 规则 协议规则 主机类型规则 网络环境规则",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "分流规则 · Domain Rules",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Matching Semantics",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DOMAIN",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DOMAIN-SUFFIX",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DOMAIN-KEYWORD",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DOMAIN-WILDCARD",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DOMAIN-SET",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DOMAIN-SET File Format",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · extended-matching iOS 5.8.0+ Mac 5.4.0+",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · pre-matching iOS 5.14.0+ Mac 5.9.0+",
        "source": "https://manual.nssurge.com/rules/domain.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Final Rule",
        "source": "https://manual.nssurge.com/rules/final.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · dns-failed",
        "source": "https://manual.nssurge.com/rules/final.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Relationship to Outbound Mode",
        "source": "https://manual.nssurge.com/rules/final.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · HTTP Rules",
        "source": "https://manual.nssurge.com/rules/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · When HTTP Rules Apply",
        "source": "https://manual.nssurge.com/rules/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · USER-AGENT",
        "source": "https://manual.nssurge.com/rules/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · URL-REGEX",
        "source": "https://manual.nssurge.com/rules/http.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · IP Rules",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · IP Rules and DNS",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · IP-CIDR",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · IP-CIDR6",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Unknown Database Results iOS 5.102.0+ Mac 6.9.1+",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · no-resolve",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · pre-matching iOS 5.14.0+ Mac 5.9.0+",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Rules Overview",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Composition",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Evaluation Order",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Rules and DNS",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Rule Parameters",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · notification-text and notification-interval",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Rule Type Index",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Process Rules",
        "source": "https://manual.nssurge.com/rules/process.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · PROCESS-NAME Mac Only",
        "source": "https://manual.nssurge.com/rules/process.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Protocol and Network Rules",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · PROTOCOL",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · HOSTNAME-TYPE Mac 5.7.3+",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · CELLULAR-RADIO iOS Only",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · CELLULAR-CARRIER iOS Only",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · SUBNET",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Subnet Expressions",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · SSID:<value>",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · BSSID:<value>",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · ROUTER:<ip>",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · TYPE:WIFI / TYPE:WIRED / TYPE:CELLULAR",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · MCCMNC:<digits>",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Bare value (legacy)",
        "source": "https://manual.nssurge.com/rules/protocol-and-network.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Source and Port Rules",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · When Source-Based Rules Make Sense",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · Port Expressions",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DEST-PORT",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · SRC-PORT iOS 5.8.4+ Mac 5.4.4+",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · IN-PORT",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · SRC-IP",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · DEVICE-NAME",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分流规则 · MAC-ADDRESS Mac 6.1.0+",
        "source": "https://manual.nssurge.com/rules/source-and-port.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则 / 全局 / 直连真实模式",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "局域网与本机直连",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "中国域名与 IP 直连",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "国外目标代理",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则顺序查看",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "连接匹配规则查看",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "缺少规则数据明确报错",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "精确域名规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "域名后缀规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "域名关键词规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "通配域名规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "IPv4 / IPv6 CIDR",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "进程规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "目标 / 来源 / 监听端口规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "来源 IP 规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "设备名称和 MAC 规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "协议规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "主机类型规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "网络环境规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/rules/domain.html",
      "https://manual.nssurge.com/rules/final.html",
      "https://manual.nssurge.com/rules/http.html",
      "https://manual.nssurge.com/rules/ip.html",
      "https://manual.nssurge.com/rules/overview.html",
      "https://manual.nssurge.com/rules/process.html",
      "https://manual.nssurge.com/rules/protocol-and-network.html",
      "https://manual.nssurge.com/rules/source-and-port.html"
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
    "keywords": "逻辑规则 domain-set rule-set 类型 DOMAIN SET,RULE SET,AND,OR,NOT,PROCESS,PROTOCOL,SRC-IP,DEST-PORT,GEOIP,IP-CIDR,FINAL 规则来源 更新间隔 默认策略 匹配表达式 启用规则集 规则集与逻辑规则 · REJECT Policy 规则集与逻辑规则 · REJECT 规则集与逻辑规则 · REJECT-TINYGIF 规则集与逻辑规则 · REJECT-DROP 规则集与逻辑规则 · REJECT-NO-DROP 规则集与逻辑规则 · Pre-matching Reject iOS 5.14.0+ Mac 5.9.0+ 规则集与逻辑规则 · Pre-matching Technical Details 规则集与逻辑规则 · For DNS queries 规则集与逻辑规则 · For TCP requests using IP 规则集与逻辑规则 · For UDP packets 规则集与逻辑规则 · Logical Rules 规则集与逻辑规则 · Nesting 规则集与逻辑规则 · Flags on logical rules 规则集与逻辑规则 · Rule Set 规则集与逻辑规则 · Internal Rule Sets 规则集与逻辑规则 · SYSTEM 规则集与逻辑规则 · LAN 规则集与逻辑规则 · Inline Rule Sets Mac 5.3.1+ 规则集与逻辑规则 · External Rule Sets 规则集与逻辑规则 · Nested Rule Sets iOS 5.22.0+ Mac 6.9.0+ 规则集与逻辑规则 · Options on the RULE-SET Line 规则集与逻辑规则 · no-resolve 规则集与逻辑规则 · extended-matching 规则集与逻辑规则 · update-interval 规则集与逻辑规则 · pre-matching 规则集与逻辑规则 · Performance 规则集与逻辑规则 · RULE-SET vs. DOMAIN-SET AND / OR / NOT 逻辑规则 外部规则集 域名集合 内联规则集 拒绝策略及预匹配 最终兜底规则",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "规则集与逻辑规则 · REJECT Policy",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · REJECT",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · REJECT-TINYGIF",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · REJECT-DROP",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · REJECT-NO-DROP",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Pre-matching Reject iOS 5.14.0+ Mac 5.9.0+",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Pre-matching Technical Details",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · For DNS queries",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · For TCP requests using IP",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · For UDP packets",
        "source": "https://manual.nssurge.com/policies/reject.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Logical Rules",
        "source": "https://manual.nssurge.com/rules/logical.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Nesting",
        "source": "https://manual.nssurge.com/rules/logical.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Flags on logical rules",
        "source": "https://manual.nssurge.com/rules/logical.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Rule Set",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Internal Rule Sets",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · SYSTEM",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · LAN",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Inline Rule Sets Mac 5.3.1+",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · External Rule Sets",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Nested Rule Sets iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Options on the RULE-SET Line",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · no-resolve",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · extended-matching",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · update-interval",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · pre-matching",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · Performance",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "规则集与逻辑规则 · RULE-SET vs. DOMAIN-SET",
        "source": "https://manual.nssurge.com/rules/ruleset.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "AND / OR / NOT 逻辑规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "外部规则集",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "域名集合",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "内联规则集",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "拒绝策略及预匹配",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "最终兜底规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/reject.html",
      "https://manual.nssurge.com/rules/logical.html",
      "https://manual.nssurge.com/rules/overview.html",
      "https://manual.nssurge.com/rules/ruleset.html"
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
    "keywords": " 启用 UDP UDP 策略 回退策略 QUIC 允许,阻止,按规则 协议识别 自动,仅 TCP,仅 UDP UDP 与协议控制 · UDP Relay UDP 与协议控制 · Protocol Support UDP 与协议控制 · udp-relay UDP 与协议控制 · udp-port iOS 5.14.0+ Mac 5.9.0+ UDP 与协议控制 · Behavior for Unsupported Policies UDP 与协议控制 · UDP Testing UDP 与协议控制 · udp-policy-not-supported-behaviour UDP 与协议控制 · udp-priority UDP 与协议控制 · block-quic iOS 5.14.6+ Mac 5.10.3+ UDP 转发 QUIC 策略 UDP 性能优先级 UDP 测试 不支持 UDP 时拒绝或直连",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "UDP 与协议控制 · UDP Relay",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · Protocol Support",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · udp-relay",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · udp-port iOS 5.14.0+ Mac 5.9.0+",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · Behavior for Unsupported Policies",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · UDP Testing",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · udp-policy-not-supported-behaviour",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · udp-priority",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 与协议控制 · block-quic iOS 5.14.6+ Mac 5.10.3+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "UDP 转发",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "QUIC 策略",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "UDP 性能优先级",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "UDP 测试",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "不支持 UDP 时拒绝或直连",
        "source": "https://manual.nssurge.com/policies/udp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/udp.html",
      "https://manual.nssurge.com/profile/general.html"
    ]
  },
  {
    "id": "dns",
    "title": "DNS 解析器",
    "group": "DNS",
    "icon": "globe",
    "sub": "上游、查询、缓存与解析策略。",
    "fields": [],
    "keywords": "  DNS 解析器 · DNS Servers DNS 解析器 · DNS over TCP iOS 5.21.0+ Mac 6.8.0+ DNS 解析器 · Per-Network Overrides DNS 解析器 · DNS DNS 解析器 · dns-server DNS 解析器 · read-etc-hosts 常规 DNS 系统解析器 DNS over TCP 并发 DNS 查询 A / AAAA 并发与回退",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "DNS 解析器 · DNS Servers",
        "source": "https://manual.nssurge.com/dns/dns-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 解析器 · DNS over TCP iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/dns/dns-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 解析器 · Per-Network Overrides",
        "source": "https://manual.nssurge.com/dns/dns-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 解析器 · DNS",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 解析器 · dns-server",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 解析器 · read-etc-hosts",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "常规 DNS",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "系统解析器",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS over TCP",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "并发 DNS 查询",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "A / AAAA 并发与回退",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/dns/dns-server.html",
      "https://manual.nssurge.com/dns/overview.html",
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": " 协议 DoH,DoH3,DoQ,DoT 服务器 URL / 地址 引导 IP 出站策略 证书名称 启用并发查询 加密 DNS · Encrypted DNS 加密 DNS · Supported Protocols 加密 DNS · Use Encrypted DNS for Specified Domains 加密 DNS · encrypted-dns-skip-cert-verification 加密 DNS · encrypted-dns-follow-outbound-mode 加密 DNS · encrypted-dns-server 加密 DNS · encrypted-dns-follow-outbound-mode 加密 DNS · encrypted-dns-skip-cert-verification DoH DoH3 DoT DoQ 加密 DNS 跟随出站策略 加密 DNS 证书验证",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "加密 DNS · Encrypted DNS",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · Supported Protocols",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · Use Encrypted DNS for Specified Domains",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · encrypted-dns-skip-cert-verification",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · encrypted-dns-follow-outbound-mode",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · encrypted-dns-server",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · encrypted-dns-follow-outbound-mode",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "加密 DNS · encrypted-dns-skip-cert-verification",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DoH",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DoH3",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DoT",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DoQ",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "加密 DNS 跟随出站策略",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "加密 DNS 证书验证",
        "source": "https://manual.nssurge.com/dns/encrypted-dns.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/dns/encrypted-dns.html",
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": " 域名 记录类型 A,AAAA,CNAME,指定解析器 目标 / 地址 TTL 出站策略 Hosts 与本地 DNS · Local DNS Mapping Hosts 与本地 DNS · IP Address Mapping Hosts 与本地 DNS · Wildcards Hosts 与本地 DNS · Alias Hosts 与本地 DNS · Assigning DNS Servers Hosts 与本地 DNS · System Resolution Hosts 与本地 DNS · Script-Based Resolution Hosts 与本地 DNS · Referencing Rule Sets Mac 5.10.0+ Hosts 与本地 DNS · /etc/hosts (macOS) Hosts 与本地 DNS · Use Local DNS Items for Proxied Requests Hosts 与本地 DNS · Host List Parameter Type Hosts 本地域名映射 域名别名 指定 DNS 服务器 系统解析与 mDNS",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Hosts 与本地 DNS · Local DNS Mapping",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · IP Address Mapping",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Wildcards",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Alias",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Assigning DNS Servers",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · System Resolution",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Script-Based Resolution",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Referencing Rule Sets Mac 5.10.0+",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · /etc/hosts (macOS)",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Use Local DNS Items for Proxied Requests",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts 与本地 DNS · Host List Parameter Type",
        "source": "https://manual.nssurge.com/profile/host-list.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Hosts",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "本地域名映射",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "域名别名",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "指定 DNS 服务器",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "系统解析与 mDNS",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/dns/local-dns-mapping.html",
      "https://manual.nssurge.com/profile/host-list.html"
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
    "keywords": " 启用 Fake-IP IPv4 范围 IPv6 范围 排除域名 缓存策略 乐观缓存,常规缓存,禁用 缓存上限 允许 AAAA Fake-IP 与 DNS 缓存 · Advanced DNS Topics Fake-IP 与 DNS 缓存 · The Fake-IP DNS Responder Fake-IP 与 DNS 缓存 · hijack-dns Fake-IP 与 DNS 缓存 · always-real-ip Fake-IP 与 DNS 缓存 · allow-dns-svcb Fake-IP 与 DNS 缓存 · REJECT at DNS Time Fake-IP 与 DNS 缓存 · allow-dns-svcb Fake-IP 与 DNS 缓存 · hijack-dns Fake-IP 与 DNS 缓存 · always-real-ip Fake-IP DNS 劫持 真实 IP 例外 SVCB 控制",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Fake-IP 与 DNS 缓存 · Advanced DNS Topics",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · The Fake-IP DNS Responder",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · hijack-dns",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · always-real-ip",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · allow-dns-svcb",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · REJECT at DNS Time",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · allow-dns-svcb",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · hijack-dns",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP 与 DNS 缓存 · always-real-ip",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Fake-IP",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS 劫持",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "真实 IP 例外",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "SVCB 控制",
        "source": "https://manual.nssurge.com/dns/advanced.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/dns/advanced.html",
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": " 域名匹配 上游服务器 回退服务器 应答方式 正常,Fake-IP,拒绝 劫持端口 脚本名称 允许 mDNS DNS 分流 指定应答 规则集关联 DNS",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "DNS 分流",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "指定应答",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则集关联 DNS",
        "source": "https://manual.nssurge.com/dns/local-dns-mapping.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/dns/local-dns-mapping.html"
    ]
  },
  {
    "id": "capture",
    "title": "抓包",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "已接入真实 HTTP 会话与 CONNECT 隧道记录。",
    "fields": [],
    "keywords": "  抓包 · HTTP Processing 抓包 · Which traffic can be processed 抓包 · Processing pipeline 抓包 · Inspecting the results 抓包 · force-http-engine-hosts 抓包 · always-raw-tcp-hosts iOS 5.8.0+ Mac 5.4.0+ 抓包 · always-raw-tcp-keywords Mac 5.5.0+ 抓包 · show-error-page Mac 5.8.0+ 抓包 · show-error-page-for-reject 真实明文 HTTP 抓包 请求 / 响应头与正文检查",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "抓包 · HTTP Processing",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · Which traffic can be processed",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · Processing pipeline",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · Inspecting the results",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · force-http-engine-hosts",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · always-raw-tcp-hosts iOS 5.8.0+ Mac 5.4.0+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · always-raw-tcp-keywords Mac 5.5.0+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · show-error-page Mac 5.8.0+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "抓包 · show-error-page-for-reject",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "真实明文 HTTP 抓包",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "请求 / 响应头与正文检查",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/overview.html",
      "https://manual.nssurge.com/profile/general.html"
    ]
  },
  {
    "id": "inspector",
    "title": "HTTP 检查器",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求、响应、正文、时间线和筛选。",
    "fields": [],
    "keywords": "  ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "请求、响应、正文、时间线和筛选。",
        "status": "部分实现",
        "source": "https://manual.nssurge.com/",
        "note": "Swirl 扩展入口；不宣称 Surge 格式兼容。"
      }
    ],
    "sources": []
  },
  {
    "id": "tls",
    "title": "HTTPS 解密 / MITM",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "解密范围、证书与会话检查界面。",
    "fields": [],
    "keywords": "  HTTPS 解密 / MITM · HTTPS Decryption (MITM) HTTPS 解密 / MITM · CA certificate HTTPS 解密 / MITM · hostname: Host List HTTPS 解密 / MITM · hostname-disabled: Optional, Host List HTTPS 解密 / MITM · ca-p12: Optional, string HTTPS 解密 / MITM · ca-passphrase: Optional, string HTTPS 解密 / MITM · ca-keystore-name: Optional, string HTTPS 解密 / MITM · skip-server-cert-verify: Optional, Boolean, default: false HTTPS 解密 / MITM · h2: Optional, Boolean, default: false HTTPS 解密 / MITM · client-source-address: Optional, list HTTPS 解密 / MITM · auto-quic-block: Optional, Boolean, default: true iOS 5.8.0+ Mac 5.4.0+ HTTPS 解密 按域名启用 MITM HTTP/2 解密 QUIC 自动阻止",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "HTTPS 解密 / MITM · HTTPS Decryption (MITM)",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · CA certificate",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · hostname: Host List",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · hostname-disabled: Optional, Host List",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · ca-p12: Optional, string",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · ca-passphrase: Optional, string",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · ca-keystore-name: Optional, string",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · skip-server-cert-verify: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · h2: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · client-source-address: Optional, list",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密 / MITM · auto-quic-block: Optional, Boolean, default: true iOS 5.8.0+ Mac 5.4.0+",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTPS 解密",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "按域名启用 MITM",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "HTTP/2 解密",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "QUIC 自动阻止",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/mitm.html"
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
    "keywords": " 证书名称 证书文件路径 私钥文件路径 启用 HTTPS 解密 域名列表 排除域名 证书校验 严格,按域名例外 CA 证书导入 证书生成与信任 客户端证书 证书指纹",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "CA 证书导入",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "证书生成与信任",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "客户端证书",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "证书指纹",
        "source": "https://manual.nssurge.com/http/mitm.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/mitm.html"
    ]
  },
  {
    "id": "rewrite",
    "title": "URL / 请求响应重写",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "URL、状态、头部、正文与重定向。",
    "fields": [],
    "keywords": "  URL / 请求响应重写 · URL Rewrite URL / 请求响应重写 · Header Mode URL / 请求响应重写 · 302 Mode URL / 请求响应重写 · 307 Mode URL / 请求响应重写 · Reject Mode URL / 请求响应重写 · Matching details URL 重写 302 / 307 重定向 拒绝重写",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "URL / 请求响应重写 · URL Rewrite",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL / 请求响应重写 · Header Mode",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL / 请求响应重写 · 302 Mode",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL / 请求响应重写 · 307 Mode",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL / 请求响应重写 · Reject Mode",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL / 请求响应重写 · Matching details",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL 重写",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "302 / 307 重定向",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "拒绝重写",
        "source": "https://manual.nssurge.com/http/url-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/url-rewrite.html"
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
    "keywords": " 阶段 请求头,响应头,请求正文,响应正文 匹配 URL 匹配表达式 替换内容 正文上限 处理方式 正则替换,JSON 路径,脚本 启用规则 正文与头部处理 · Body Rewrite iOS 5.10.0+ Mac 5.6.0+ 正文与头部处理 · JQ Body Rewrite iOS 5.14.0+ Mac 5.9.0+ 正文与头部处理 · Interaction with scripts 正文与头部处理 · Header Rewrite 正文与头部处理 · header-add 正文与头部处理 · header-del 正文与头部处理 · header-replace 正文与头部处理 · header-replace-regex 请求 / 响应 Header 重写 Header 增删与正则 请求 / 响应 Body 重写 JQ 正文重写",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "正文与头部处理 · Body Rewrite iOS 5.10.0+ Mac 5.6.0+",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · JQ Body Rewrite iOS 5.14.0+ Mac 5.9.0+",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · Interaction with scripts",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · Header Rewrite",
        "source": "https://manual.nssurge.com/http/header-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · header-add",
        "source": "https://manual.nssurge.com/http/header-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · header-del",
        "source": "https://manual.nssurge.com/http/header-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · header-replace",
        "source": "https://manual.nssurge.com/http/header-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "正文与头部处理 · header-replace-regex",
        "source": "https://manual.nssurge.com/http/header-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "请求 / 响应 Header 重写",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "Header 增删与正则",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "请求 / 响应 Body 重写",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "JQ 正文重写",
        "source": "https://manual.nssurge.com/http/body-rewrite.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/body-rewrite.html",
      "https://manual.nssurge.com/http/header-rewrite.html"
    ]
  },
  {
    "id": "map",
    "title": "Map Local / Remote",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "本地响应与远程 URL 映射。",
    "fields": [],
    "keywords": "  Map Local / Remote · Map Local Map Local / Remote · URL Pattern Map Local / Remote · data-type: Optional, default: file Map Local / Remote · data Map Local / Remote · header: Optional Map Local / Remote · status-code: Optional, 200–999, default: 200 Map Local / Remote · About Content-Type Map Remote 本地资源映射",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Map Local / Remote · Map Local",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Local / Remote · URL Pattern",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Local / Remote · data-type: Optional, default: file",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Local / Remote · data",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Local / Remote · header: Optional",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Local / Remote · status-code: Optional, 200–999, default: 200",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Local / Remote · About Content-Type",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Map Remote",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "本地资源映射",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/map-local.html"
    ]
  },
  {
    "id": "breakpoint",
    "title": "HTTP 断点",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求 / 响应暂停和修改界面。",
    "fields": [],
    "keywords": "  HTTP 请求断点 HTTP 响应断点",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "HTTP 请求断点",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "HTTP 响应断点",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/overview.html"
    ]
  },
  {
    "id": "replay",
    "title": "HTTP 重放与构造",
    "group": "HTTP 与调试",
    "icon": "code",
    "sub": "请求方法、URL、头部、正文与重放。",
    "fields": [],
    "keywords": "  请求重放 网络请求构造 HTTP 测试",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "请求重放",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "网络请求构造",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "HTTP 测试",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/overview.html"
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
    "keywords": " 匹配 URL 状态码 Content-Type 正文来源 文本,本地文件 正文 / 文件路径 响应头 启用 Mock API Mock 自定义状态码 自定义响应头与正文",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "API Mock",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "自定义状态码",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "自定义响应头与正文",
        "source": "https://manual.nssurge.com/http/map-local.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/map-local.html"
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
    "keywords": " URL 子协议 筛选表达式 正文显示 文本,十六进制 允许保留历史 WebSocket 会话检查",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "WebSocket 会话检查",
        "source": "https://manual.nssurge.com/http/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/http/overview.html"
    ]
  },
  {
    "id": "profiles",
    "title": "配置文件",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "导入、编辑、历史版本与恢复。",
    "fields": [],
    "keywords": "  配置文件 · Profile Format 配置文件 · Comments 配置文件 · Quoted Values iOS 5.21.0+ Mac 6.8.0+ 配置文件 · Detached Profile Section 配置文件 · Include Patterns 配置文件 · Dedicated Include 配置文件 · Multiple Includes iOS 4.12.0+ Mac 4.5.0+ 配置文件 · Mixed Content and Includes iOS 5.22.0+ Mac 6.9.0+ 配置文件 · Wildcard Named Sections iOS 5.22.0+ Mac 6.9.0+ 配置文件 · Linked Profiles Mac 6.0.0+ 配置文件 · Modules 配置文件 · Line Requirement 本地配置 配置编辑与错误提示 配置导入导出 分离和关联配置 多个包含资源 通配命名配置段",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "配置文件 · Profile Format",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Comments",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Quoted Values iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Detached Profile Section",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Include Patterns",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Dedicated Include",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Multiple Includes iOS 4.12.0+ Mac 4.5.0+",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Mixed Content and Includes iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Wildcard Named Sections iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Linked Profiles Mac 6.0.0+",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Modules",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置文件 · Line Requirement",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "本地配置",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "配置编辑与错误提示",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "配置导入导出",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "分离和关联配置",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "多个包含资源",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "通配命名配置段",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/format.html"
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
    "keywords": " 配置 URL 更新间隔 更新链路 自动,直连,指定策略 失败回退 保留当前,切换备用 启用自动更新 资源类型 完整配置,策略列表,规则集,域名集 托管配置与外部资源 · Managed Profile 托管配置与外部资源 · interval 托管配置与外部资源 · strict 托管配置与外部资源 · REQUIREMENT Statement 托管配置与外部资源 · FORBIDDEN-AUTO-UPGRADE Statement 托管配置 严格更新模式 托管配置条件 规则资源自动更新",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "托管配置与外部资源 · Managed Profile",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "托管配置与外部资源 · interval",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "托管配置与外部资源 · strict",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "托管配置与外部资源 · REQUIREMENT Statement",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "托管配置与外部资源 · FORBIDDEN-AUTO-UPGRADE Statement",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "托管配置",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "严格更新模式",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "托管配置条件",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则资源自动更新",
        "source": "https://manual.nssurge.com/profile/managed-profile.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/managed-profile.html"
    ]
  },
  {
    "id": "subscriptions",
    "title": "订阅管理",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "订阅源、更新、错误与节点预览。",
    "fields": [],
    "keywords": "  ",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "订阅源、更新、错误与节点预览。",
        "status": "部分实现",
        "source": "https://manual.nssurge.com/",
        "note": "Swirl 扩展入口；不宣称 Surge 格式兼容。"
      }
    ],
    "sources": []
  },
  {
    "id": "modules",
    "title": "配置模块",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "模块导入、参数、更新与启停。",
    "fields": [],
    "keywords": "  配置模块 · Module 配置模块 · Parameter Tables Mac 5.5.0+ 配置模块 · Requirements iOS 5.10.0+ Mac 5.6.0+ 配置模块 模块参数 模块优先级",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "配置模块 · Module",
        "source": "https://manual.nssurge.com/profile/module.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置模块 · Parameter Tables Mac 5.5.0+",
        "source": "https://manual.nssurge.com/profile/module.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置模块 · Requirements iOS 5.10.0+ Mac 5.6.0+",
        "source": "https://manual.nssurge.com/profile/module.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "配置模块",
        "source": "https://manual.nssurge.com/profile/module.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "模块参数",
        "source": "https://manual.nssurge.com/profile/module.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "模块优先级",
        "source": "https://manual.nssurge.com/profile/module.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/module.html"
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
    "keywords": "requirement expressions arguments override 模块名称 需求表达式 参数声明 覆盖值 优先级 启用模块 模块条件与参数 · Line Requirement iOS 5.11.0+ Mac 5.7.0+ 模块条件与参数 · Start-of-Line and End-of-Line Forms 模块条件与参数 · REQUIREMENT Expression 模块条件与参数 · Core Version 模块条件与参数 · Simplified Notation iOS 5.14.3+ Mac 5.10.0+ 模块条件与参数 · Usage in Managed Profiles 条件配置 平台条件 版本条件 行条件表达式",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "模块条件与参数 · Line Requirement iOS 5.11.0+ Mac 5.7.0+",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "模块条件与参数 · Start-of-Line and End-of-Line Forms",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "模块条件与参数 · REQUIREMENT Expression",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "模块条件与参数 · Core Version",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "模块条件与参数 · Simplified Notation iOS 5.14.3+ Mac 5.10.0+",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "模块条件与参数 · Usage in Managed Profiles",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "条件配置",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "平台条件",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "版本条件",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "行条件表达式",
        "source": "https://manual.nssurge.com/profile/requirement.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/requirement.html"
    ]
  },
  {
    "id": "scripts",
    "title": "JavaScript 脚本",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "脚本编辑、控制台与存储界面。",
    "fields": [],
    "keywords": "  JavaScript 脚本 · cron Script JavaScript 脚本 · cronexp JavaScript 脚本 · wake-system iOS Only JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本 · Manual Triggering JavaScript 脚本 · Constraints JavaScript 脚本 · Trigger JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本 · Constraints JavaScript 脚本 · generic Script JavaScript 脚本 · Trigger JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本 · http-request Script JavaScript 脚本 · Trigger JavaScript 脚本 · pattern JavaScript 脚本 · requires-body JavaScript 脚本 · max-size JavaScript 脚本 · binary-body-mode JavaScript 脚本 · full-header-mode JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本 · http-response Script JavaScript 脚本 · Trigger JavaScript 脚本 · pattern JavaScript 脚本 · requires-body JavaScript 脚本 · max-size JavaScript 脚本 · binary-body-mode JavaScript 脚本 · full-header-mode JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本 · Scripting JavaScript 脚本 · Declaration JavaScript 脚本 · type: Optional, default: generic JavaScript 脚本 · script-path: Required JavaScript 脚本 · script-update-interval: Optional, in seconds, default: 86400 JavaScript 脚本 · timeout: Optional, in seconds, default: 5 JavaScript 脚本 · argument: Optional JavaScript 脚本 · engine: Optional, auto/jsc/webview, default: auto JavaScript 脚本 · debug: Optional, Boolean, default: false JavaScript 脚本 · pattern: Required for http-request and http-response, regex JavaScript 脚本 · requires-body: Optional, Boolean, default: false JavaScript 脚本 · max-size: Optional, in bytes, default: 1 MB (iOS) / 10 MB (Mac) JavaScript 脚本 · binary-body-mode: Optional, Boolean, default: false JavaScript 脚本 · full-header-mode: Optional, Boolean, default: false JavaScript 脚本 · cronexp: Required for cron JavaScript 脚本 · wake-system: Optional, Boolean, default: false iOS Only JavaScript 脚本 · Script Engine iOS 5.9.0+ Mac 5.5.0+ JavaScript 脚本 · JavaScriptCore (engine=jsc) JavaScript 脚本 · WebView (engine=webview) JavaScript 脚本 · Usage Recommendations JavaScript 脚本 · Engine Availability JavaScript 脚本 · Performance Constraints JavaScript 脚本 · Debugging JavaScript 脚本 · Trigger JavaScript 脚本 · Input JavaScript 脚本 · Result JavaScript 脚本管理 脚本运行日志",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "JavaScript 脚本 · cron Script",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · cronexp",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · wake-system iOS Only",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Manual Triggering",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Constraints",
        "source": "https://manual.nssurge.com/scripting/cron.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Trigger",
        "source": "https://manual.nssurge.com/scripting/dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/event.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/event.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Constraints",
        "source": "https://manual.nssurge.com/scripting/event.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · generic Script",
        "source": "https://manual.nssurge.com/scripting/generic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Trigger",
        "source": "https://manual.nssurge.com/scripting/generic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/generic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/generic.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · http-request Script",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Trigger",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · pattern",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · requires-body",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · max-size",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · binary-body-mode",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · full-header-mode",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/http-request.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · http-response Script",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Trigger",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · pattern",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · requires-body",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · max-size",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · binary-body-mode",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · full-header-mode",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/http-response.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Scripting",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Declaration",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · type: Optional, default: generic",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · script-path: Required",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · script-update-interval: Optional, in seconds, default: 86400",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · timeout: Optional, in seconds, default: 5",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · argument: Optional",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · engine: Optional, auto/jsc/webview, default: auto",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · debug: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · pattern: Required for http-request and http-response, regex",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · requires-body: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · max-size: Optional, in bytes, default: 1 MB (iOS) / 10 MB (Mac)",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · binary-body-mode: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · full-header-mode: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · cronexp: Required for cron",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · wake-system: Optional, Boolean, default: false iOS Only",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Script Engine iOS 5.9.0+ Mac 5.5.0+",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · JavaScriptCore (engine=jsc)",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · WebView (engine=webview)",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Usage Recommendations",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Engine Availability",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Performance Constraints",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Debugging",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Trigger",
        "source": "https://manual.nssurge.com/scripting/rule.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Input",
        "source": "https://manual.nssurge.com/scripting/rule.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本 · Result",
        "source": "https://manual.nssurge.com/scripting/rule.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "JavaScript 脚本管理",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "脚本运行日志",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/scripting/cron.html",
      "https://manual.nssurge.com/scripting/dns.html",
      "https://manual.nssurge.com/scripting/event.html",
      "https://manual.nssurge.com/scripting/generic.html",
      "https://manual.nssurge.com/scripting/http-request.html",
      "https://manual.nssurge.com/scripting/http-response.html",
      "https://manual.nssurge.com/scripting/overview.html",
      "https://manual.nssurge.com/scripting/rule.html"
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
    "keywords": "$request $response $done $httpClient $persistentStore $notification $utils 类型 http-request,http-response,rule,dns,event,cron,generic,panel 匹配表达式 脚本路径 参数 超时 正文上限 启用脚本 脚本触发与 API · Script Rule 脚本触发与 API · requires-resolve 脚本触发与 API · JavaScript API 脚本触发与 API · Globals 脚本触发与 API · $environment 脚本触发与 API · $script 脚本触发与 API · $network 脚本触发与 API · $argument 脚本触发与 API · $trigger 脚本触发与 API · $intent 脚本触发与 API · $input 脚本触发与 API · $done 脚本触发与 API · $httpClient 脚本触发与 API · $httpClient.get(options<String|Object>, callback<Function>) 脚本触发与 API · $httpAPI 脚本触发与 API · $httpAPI(method<String>, path<String>, body<Object>, callback<Function>(result<Object>)) 脚本触发与 API · $persistentStore 脚本触发与 API · $persistentStore.write(data<String>, [key<String>]) 脚本触发与 API · $persistentStore.read([key<String>]) 脚本触发与 API · $notification 脚本触发与 API · $notification.post(title<String>, subtitle<String>, body<String>[, options<Object>]) 脚本触发与 API · $utils 脚本触发与 API · $utils.geoip(ip<String>) 脚本触发与 API · $utils.ipasn(ip<String>) 脚本触发与 API · $utils.ipaso(ip<String>) 脚本触发与 API · $utils.ungzip(binary<Uint8Array>) 脚本触发与 API · $surge 脚本触发与 API · $surge.setSelectGroupPolicy(groupName<String>, policyName<String>) 脚本触发与 API · $surge.selectGroupDetails() 脚本触发与 API · $surge.retestGroup(groupName<String>, callback<Function>(result<Object>)) 脚本触发与 API · $surge.setOutboundMode(mode<String>) 脚本触发与 API · $surge.setHTTPCaptureEnabled(enabled<Boolean>) 脚本触发与 API · $surge.setRewriteEnabled(enabled<Boolean>) 脚本触发与 API · $surge.setEnhancedModeEnabled(enabled<Boolean>) Mac Only 脚本触发与 API · $surge.setCellularModeEnabled(enabled<Boolean>) Mac Only 脚本触发与 API · $surge.logbook(content<String>) 脚本触发与 API · Miscellaneous 脚本触发与 API · console.log(message) 脚本触发与 API · setTimeout(function[, delay]) 脚本触发与 API · dns Script 脚本触发与 API · event Script 脚本触发与 API · event-name 脚本触发与 API · event-name: Required for event 脚本触发与 API · rule Script 脚本触发与 API · DNS Resolution 请求事件 响应事件 DNS 脚本 规则脚本 系统事件触发 手动脚本 脚本持久化与通知 API",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "脚本触发与 API · Script Rule",
        "source": "https://manual.nssurge.com/rules/script.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · requires-resolve",
        "source": "https://manual.nssurge.com/rules/script.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · JavaScript API",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · Globals",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $environment",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $script",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $network",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $argument",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $trigger",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $intent",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $input",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $done",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $httpClient",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $httpClient.get(options<String|Object>, callback<Function>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $httpAPI",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $httpAPI(method<String>, path<String>, body<Object>, callback<Function>(result<Object>))",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $persistentStore",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $persistentStore.write(data<String>, [key<String>])",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $persistentStore.read([key<String>])",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $notification",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $notification.post(title<String>, subtitle<String>, body<String>[, options<Object>])",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $utils",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $utils.geoip(ip<String>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $utils.ipasn(ip<String>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $utils.ipaso(ip<String>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $utils.ungzip(binary<Uint8Array>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.setSelectGroupPolicy(groupName<String>, policyName<String>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.selectGroupDetails()",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.retestGroup(groupName<String>, callback<Function>(result<Object>))",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.setOutboundMode(mode<String>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.setHTTPCaptureEnabled(enabled<Boolean>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.setRewriteEnabled(enabled<Boolean>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.setEnhancedModeEnabled(enabled<Boolean>) Mac Only",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.setCellularModeEnabled(enabled<Boolean>) Mac Only",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · $surge.logbook(content<String>)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · Miscellaneous",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · console.log(message)",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · setTimeout(function[, delay])",
        "source": "https://manual.nssurge.com/scripting/api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · dns Script",
        "source": "https://manual.nssurge.com/scripting/dns.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · event Script",
        "source": "https://manual.nssurge.com/scripting/event.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · event-name",
        "source": "https://manual.nssurge.com/scripting/event.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · event-name: Required for event",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · rule Script",
        "source": "https://manual.nssurge.com/scripting/rule.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "脚本触发与 API · DNS Resolution",
        "source": "https://manual.nssurge.com/scripting/rule.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "请求事件",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "响应事件",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS 脚本",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则脚本",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "系统事件触发",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "手动脚本",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "脚本持久化与通知 API",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/rules/script.html",
      "https://manual.nssurge.com/scripting/api.html",
      "https://manual.nssurge.com/scripting/dns.html",
      "https://manual.nssurge.com/scripting/event.html",
      "https://manual.nssurge.com/scripting/overview.html",
      "https://manual.nssurge.com/scripting/rule.html"
    ]
  },
  {
    "id": "automation",
    "title": "定时与自动化",
    "group": "配置与自动化",
    "icon": "terminal",
    "sub": "Cron、网络变化和事件触发任务。",
    "fields": [],
    "keywords": "  定时任务 自动化面板 自动化事件",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "定时任务",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "自动化面板",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "自动化事件",
        "source": "https://manual.nssurge.com/scripting/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/scripting/overview.html"
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
    "keywords": " 标题 图标 刷新间隔 内容 脚本路径 启用面板 自定义面板 · Information Panel iOS 4.9.3+ Mac 5.7.5+ 自定义面板 · Static Mode 自定义面板 · Dynamic Mode 自定义面板 · More Customization 静态信息面板 动态脚本面板",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "自定义面板 · Information Panel iOS 4.9.3+ Mac 5.7.5+",
        "source": "https://manual.nssurge.com/tools/panel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "自定义面板 · Static Mode",
        "source": "https://manual.nssurge.com/tools/panel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "自定义面板 · Dynamic Mode",
        "source": "https://manual.nssurge.com/tools/panel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "自定义面板 · More Customization",
        "source": "https://manual.nssurge.com/tools/panel.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "静态信息面板",
        "source": "https://manual.nssurge.com/tools/panel.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "动态脚本面板",
        "source": "https://manual.nssurge.com/tools/panel.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/panel.html"
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
    "keywords": " 来源 本地文件夹,WebDAV,iCloud 占位 同步路径 冲突策略 询问,保留本机,保留远端 启用自动同步 保留版本数 配置同步 配置备份 配置恢复",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "配置同步",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "配置备份",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "配置恢复",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/format.html"
    ]
  },
  {
    "id": "gateway",
    "title": "网关与设备",
    "group": "设备与服务",
    "icon": "server",
    "sub": "网关模式、设备列表与接口管理。",
    "fields": [],
    "keywords": "  网关与设备 · Gateway Mode Mac Only 网关与设备 · Device Management 网关与设备 · Per-Device Policies 网关与设备 · Access Restriction 网关与设备 · UDP Fast Path Mac 6.4.0+ 网关与设备 · gateway-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+ 网关模式 设备管理 设备独立分流 设备访问限制 UDP Fast Path",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "网关与设备 · Gateway Mode Mac Only",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网关与设备 · Device Management",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网关与设备 · Per-Device Policies",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网关与设备 · Access Restriction",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网关与设备 · UDP Fast Path Mac 6.4.0+",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网关与设备 · gateway-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "网关模式",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "设备管理",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "设备独立分流",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "设备访问限制",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "UDP Fast Path",
        "source": "https://manual.nssurge.com/features/gateway.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/gateway.html",
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": " 启用 DHCP 监听接口 地址池起点 地址池终点 子网掩码 默认网关 DNS 服务器 租约时长 DHCP 服务 · DHCP Mac Only DHCP 服务 · DHCP Section Mac 6.5.0+ DHCP 服务 · max-lease-time DHCP 服务 · default-lease-time DHCP 服务 · min-lease-time DHCP 服务 · one-lease-per-client DHCP 服务 · ping-check DHCP 服务 租约管理 冲突探测 单客户端租约",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "DHCP 服务 · DHCP Mac Only",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务 · DHCP Section Mac 6.5.0+",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务 · max-lease-time",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务 · default-lease-time",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务 · min-lease-time",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务 · one-lease-per-client",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务 · ping-check",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DHCP 服务",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "租约管理",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "冲突探测",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "单客户端租约",
        "source": "https://manual.nssurge.com/features/dhcp.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/dhcp.html"
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
    "keywords": " 协议 TCP,UDP 监听地址 监听端口 目标主机 目标端口 出站策略 启用转发 端口转发 · Port Forwarding iOS 5.14.3+ Mac 5.10.0+ 端口转发 · policy 端口转发 · Use Cases TCP / UDP 端口转发 指定出站策略",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "端口转发 · Port Forwarding iOS 5.14.3+ Mac 5.10.0+",
        "source": "https://manual.nssurge.com/features/port-forwarding.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "端口转发 · policy",
        "source": "https://manual.nssurge.com/features/port-forwarding.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "端口转发 · Use Cases",
        "source": "https://manual.nssurge.com/features/port-forwarding.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "TCP / UDP 端口转发",
        "source": "https://manual.nssurge.com/features/port-forwarding.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "指定出站策略",
        "source": "https://manual.nssurge.com/features/port-forwarding.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/port-forwarding.html"
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
    "keywords": "Surge Ponte remote device 设备名称 设备标识 远程服务端口 连接方式 自动,局域网,中继 允许访问 授权范围 设备互联 / Ponte · Surge Ponte 设备互联 / Ponte · How It Works 设备互联 / Ponte · client-proxy-name: Optional, policy name 设备互联 / Ponte · server-proxy-name: Optional, comma-separated policy names 远程设备互联 家庭网络访问 设备客户端与服务端角色",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "设备互联 / Ponte · Surge Ponte",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设备互联 / Ponte · How It Works",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设备互联 / Ponte · client-proxy-name: Optional, policy name",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设备互联 / Ponte · server-proxy-name: Optional, comma-separated policy names",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "远程设备互联",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "家庭网络访问",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "设备客户端与服务端角色",
        "source": "https://manual.nssurge.com/features/ponte.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/ponte.html"
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
    "keywords": " 启用服务 监听地址 监听端口 协议版本 v4,v5 预共享密钥引用 访问策略 允许 UDP Snell 服务端 · Built-in Snell Server Snell 服务端 · interface Snell 服务端 · port Snell 服务端 · psk Snell 服务端 · version Snell 服务端 · mode Snell 服务端 · Snell v6 Mac 6.8.0+ Snell 服务端 · Client Configuration Snell 服务端 · Using a Module iOS 5.23.0+ Mac 6.10.0+ Snell 服务端 Snell v6 模块配置服务端",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Snell 服务端 · Built-in Snell Server",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · interface",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · port",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · psk",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · version",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · mode",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · Snell v6 Mac 6.8.0+",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · Client Configuration",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端 · Using a Module iOS 5.23.0+ Mac 6.10.0+",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Snell 服务端",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "Snell v6",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "模块配置服务端",
        "source": "https://manual.nssurge.com/features/snell-server.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/snell-server.html"
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
    "keywords": " 启用服务 监听地址 监听端口 密钥引用 伪装域名 连接上限 MTProto 服务端 · MTProto Proxy Server iOS 5.21.0+ Mac 6.8.0+ MTProto 服务端 · Why MTProto Instead of SOCKS5 MTProto 服务端 · interface: Required, IPv4 or IPv6 address MTProto 服务端 · port: Required, 1–65535 MTProto 服务端 · secret: Required, 32 hexadecimal characters MTProto 服务端 · ipv6: Optional, Boolean, default: false MTProto 服务端 · dc-config-url: Optional, HTTP or HTTPS URL MTProto 服务端 · Rule Evaluation and Outbound Policies MTProto 服务端 · Telegram DC Resolution MTProto 服务端 · DC Configuration, Cache, and Updates MTProto 服务端 · Hosting a Custom DC Configuration MTProto 服务端 · Request Records and Traffic Statistics MTProto 服务端 · Connection Lifecycle and Performance MTProto 服务端 DC 配置与缓存 Telegram 分流",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "MTProto 服务端 · MTProto Proxy Server iOS 5.21.0+ Mac 6.8.0+",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · Why MTProto Instead of SOCKS5",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · interface: Required, IPv4 or IPv6 address",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · port: Required, 1–65535",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · secret: Required, 32 hexadecimal characters",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · ipv6: Optional, Boolean, default: false",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · dc-config-url: Optional, HTTP or HTTPS URL",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · Rule Evaluation and Outbound Policies",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · Telegram DC Resolution",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · DC Configuration, Cache, and Updates",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · Hosting a Custom DC Configuration",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · Request Records and Traffic Statistics",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端 · Connection Lifecycle and Performance",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "MTProto 服务端",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DC 配置与缓存",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "Telegram 分流",
        "source": "https://manual.nssurge.com/features/mtproto.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/mtproto.html"
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
    "keywords": " 设备名称 控制器 URL 认证引用 权限 只读,配置管理,完全控制 启用服务发现 远程控制与设备授权 · external-controller-access 远程控制 远程设备授权 远程日志查看",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "远程控制与设备授权 · external-controller-access",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "远程控制",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "远程设备授权",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "远程日志查看",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/general.html",
      "https://manual.nssurge.com/tools/dashboard.html"
    ]
  },
  {
    "id": "dashboard",
    "title": "Dashboard 仪表盘",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "实时曲线、连接、资源与概览。",
    "fields": [],
    "keywords": "  Dashboard 仪表盘 · Surge Dashboard Dashboard 仪表盘 · Local and Remote Connections Dashboard 仪表盘 · external-controller-access Dashboard 仪表盘 · Web Dashboard",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Dashboard 仪表盘 · Surge Dashboard",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Dashboard 仪表盘 · Local and Remote Connections",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Dashboard 仪表盘 · external-controller-access",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Dashboard 仪表盘 · Web Dashboard",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/dashboard.html"
    ]
  },
  {
    "id": "connections",
    "title": "连接记录",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "域名、进程、策略、速度和连接详情。",
    "fields": [],
    "keywords": "  连接访问时间 目标域名与协议 实际进程 匹配规则 实际出站节点 上传 / 下载字节 终止实际连接",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "连接访问时间",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "目标域名与协议",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "实际进程",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "匹配规则",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "实际出站节点",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "上传 / 下载字节",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "终止实际连接",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/dashboard.html"
    ]
  },
  {
    "id": "traffic",
    "title": "流量分析",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "域名、应用、节点与历史统计。",
    "fields": [],
    "keywords": "  有界历史流量 防重复累计 采集失败状态 重启后旧采样隔离",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "有界历史流量",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "防重复累计",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "采集失败状态",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "重启后旧采样隔离",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/dashboard.html"
    ]
  },
  {
    "id": "toolbox",
    "title": "网络诊断",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "连通性、延迟、DNS、Traceroute 与请求测试。",
    "fields": [],
    "keywords": "  互联网 TCP 延迟 路由器 ICMP 延迟 DNS 解析延迟 当前代理 HTTP 延迟 网络环境摘要 实际出口 IP",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "互联网 TCP 延迟",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "路由器 ICMP 延迟",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS 解析延迟",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "当前代理 HTTP 延迟",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "网络环境摘要",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "实际出口 IP",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/testing.html"
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
    "keywords": " 测试类型 延迟,可用性,下载,上传 检测 URL 并发数 次数 超时 策略名称 代理测速与基准测试 · Testing Parameters 代理测速与基准测试 · test-url 代理测速与基准测试 · test-timeout 代理测速与基准测试 · test-udp 代理测速与基准测试 · Connectivity Testing 代理测速与基准测试 · internet-test-url 代理测速与基准测试 · proxy-test-url 代理测速与基准测试 · test-timeout 代理测速与基准测试 · proxy-test-udp 代理测速与基准测试 · Testing 代理测速与基准测试 · Connectivity and Latency Testing 代理测速与基准测试 · Throughput Test Parameters Mac 6.4.4+ 代理测速与基准测试 · download-url 代理测速与基准测试 · upload-url 代理测速与基准测试 · download-url-proxy 代理测速与基准测试 · upload-url-proxy 代理测速与基准测试 · download-concurrency 代理测速与基准测试 · upload-concurrency 代理测速与基准测试 · download-duration-limit 代理测速与基准测试 · upload-size-limit 代理测速与基准测试 · upload-duration-limit 吞吐量基准测试 上传 / 下载并发和时限",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "proxies",
    "capabilities": [
      {
        "name": "代理测速与基准测试 · Testing Parameters",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · test-url",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · test-timeout",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · test-udp",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · Connectivity Testing",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · internet-test-url",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · proxy-test-url",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · test-timeout",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · proxy-test-udp",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · Testing",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · Connectivity and Latency Testing",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · Throughput Test Parameters Mac 6.4.4+",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · download-url",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · upload-url",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · download-url-proxy",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · upload-url-proxy",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · download-concurrency",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · upload-concurrency",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · download-duration-limit",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · upload-size-limit",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "代理测速与基准测试 · upload-duration-limit",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "吞吐量基准测试",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "上传 / 下载并发和时限",
        "source": "https://manual.nssurge.com/tools/testing.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/parameters.html",
      "https://manual.nssurge.com/profile/general.html",
      "https://manual.nssurge.com/tools/testing.html"
    ]
  },
  {
    "id": "api",
    "title": "HTTP API / 命令行",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "本地 API、CLI、权限与访问日志。",
    "fields": [],
    "keywords": "surge-cli HTTP API  HTTP API / 命令行 · http-api HTTP API / 命令行 · http-api-tls HTTP API / 命令行 · http-api-web-dashboard HTTP API / 命令行 · Surge CLI HTTP API / 命令行 · Editor Language Server Mac 6.10.0+ HTTP API / 命令行 · Expanded Management and Diagnostics Mac 6.8.0+ HTTP API / 命令行 · Routing and Network Diagnostics Mac 6.9.0+ HTTP API / 命令行 · Agent Skill Mac 6.5.0+ HTTP API / 命令行 · HTTP API iOS 4.4.0+ Mac 4.0.0+ HTTP API / 命令行 · HTTPS (TLS) HTTP API / 命令行 · Basic Constraints HTTP API / 命令行 · Toggle Capabilities HTTP API / 命令行 · Outbound Mode HTTP API / 命令行 · Proxy Policy HTTP API / 命令行 · Requests HTTP API / 命令行 · Profiles HTTP API / 命令行 · External Resources iOS 5.23.0+ Mac 6.10.0+ HTTP API / 命令行 · DNS HTTP API / 命令行 · Modules HTTP API / 命令行 · Scripting HTTP API / 命令行 · Device Management Mac Only 4.0.6+ 本地 HTTP API 命令行工具 远程 CLI API 认证与 TLS",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "HTTP API / 命令行 · http-api",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · http-api-tls",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · http-api-web-dashboard",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Surge CLI",
        "source": "https://manual.nssurge.com/tools/cli.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Editor Language Server Mac 6.10.0+",
        "source": "https://manual.nssurge.com/tools/cli.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Expanded Management and Diagnostics Mac 6.8.0+",
        "source": "https://manual.nssurge.com/tools/cli.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Routing and Network Diagnostics Mac 6.9.0+",
        "source": "https://manual.nssurge.com/tools/cli.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Agent Skill Mac 6.5.0+",
        "source": "https://manual.nssurge.com/tools/cli.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · HTTP API iOS 4.4.0+ Mac 4.0.0+",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · HTTPS (TLS)",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Basic Constraints",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Toggle Capabilities",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Outbound Mode",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Proxy Policy",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Requests",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Profiles",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · External Resources iOS 5.23.0+ Mac 6.10.0+",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · DNS",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Modules",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Scripting",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "HTTP API / 命令行 · Device Management Mac Only 4.0.6+",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "本地 HTTP API",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "命令行工具",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "远程 CLI",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "API 认证与 TLS",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/general.html",
      "https://manual.nssurge.com/tools/cli.html",
      "https://manual.nssurge.com/tools/http-api.html"
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
    "keywords": "shortcuts siri url scheme 动作 导入配置,选择配置,连接,断开,运行脚本 配置名称 脚本名称 URL Scheme 参数 URL Scheme 与快捷指令 · URL Scheme URL Scheme 与快捷指令 · x-callback-url 快捷指令",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "URL Scheme 与快捷指令 · URL Scheme",
        "source": "https://manual.nssurge.com/tools/url-scheme.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "URL Scheme 与快捷指令 · x-callback-url",
        "source": "https://manual.nssurge.com/tools/url-scheme.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "快捷指令",
        "source": "https://manual.nssurge.com/tools/url-scheme.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/url-scheme.html"
    ]
  },
  {
    "id": "logs",
    "title": "Logbook 日志",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "诊断事件、筛选、详情和导出。",
    "fields": [],
    "keywords": "  Logbook 日志 · Logbook Mac 6.6.0+ Logbook 日志 · Remote Viewing 分级运行日志 事件时间与组件 错误码搜索 错误详情 脱敏诊断 ZIP 日志轮转 崩溃线索",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Logbook 日志 · Logbook Mac 6.6.0+",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Logbook 日志 · Remote Viewing",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "分级运行日志",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "事件时间与组件",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "错误码搜索",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "错误详情",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "脱敏诊断 ZIP",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "日志轮转",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "崩溃线索",
        "source": "https://manual.nssurge.com/tools/logbook.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/logbook.html"
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
    "keywords": " 启用通知 级别 全部,错误,静默 来源 网络,规则,脚本,系统 保留记录数 启用声音 通知中心 事件确认 规则命中通知",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "logs",
    "capabilities": [
      {
        "name": "通知中心",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "事件确认",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则命中通知",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/rules/overview.html"
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
    "keywords": "on-demand VPN always-on iOS tvOS 平台 Windows,macOS 参考,iOS 参考,tvOS 参考 连接方式 手动,按需,Always-on 按需匹配 蜂窝策略 低数据策略 权限说明 平台与移动设备 · Platform Differences 平台与移动设备 · Surge Mac Only 平台与移动设备 · Surge iOS Only",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "平台受限",
    "platform": "Apple 平台专用接口，Windows 无同名系统能力",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "平台与移动设备 · Platform Differences",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "平台与移动设备 · Surge Mac Only",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "平台与移动设备 · Surge iOS Only",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/getting-started/platform-differences.html"
    ]
  },
  {
    "id": "settings",
    "title": "设置与偏好",
    "group": "工具与系统",
    "icon": "grid",
    "sub": "外观、监听、安全、通用与版本信息。",
    "fields": [],
    "keywords": "  设置与偏好 · The [General] Section 设置与偏好 · Logging & Debugging 设置与偏好 · loglevel 设置与偏好 · debug-cpu-usage 设置与偏好 · debug-memory-usage 设置与偏好 · Traffic Processing 设置与偏好 · Error Pages 设置与偏好 · Surge iOS Only Parameters 设置与偏好 · Working Mode 设置与偏好 · Network Behavior 设置与偏好 · wifi-assist 设置与偏好 · VPN Tunnel Scope 设置与偏好 · Surge Mac Only Parameters 设置与偏好 · subnet-exp-wifi-always-match",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "设置与偏好 · The [General] Section",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Logging & Debugging",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · loglevel",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · debug-cpu-usage",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · debug-memory-usage",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Traffic Processing",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Error Pages",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Surge iOS Only Parameters",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Working Mode",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Network Behavior",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · wifi-assist",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · VPN Tunnel Scope",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · Surge Mac Only Parameters",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "设置与偏好 · subnet-exp-wifi-always-match",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/general.html"
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
    "keywords": " 工具名称 程序路径 启动参数 工作目录 启动方式 手动,连接后 启用工具 外部工具 · External Proxy Program Mac Only 外部工具 · exec 外部工具 · local-port 外部工具 · args 外部工具 · addresses 外部工具 · udp-relay",
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "外部工具 · External Proxy Program Mac Only",
        "source": "https://manual.nssurge.com/policies/external.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "外部工具 · exec",
        "source": "https://manual.nssurge.com/policies/external.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "外部工具 · local-port",
        "source": "https://manual.nssurge.com/policies/external.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "外部工具 · args",
        "source": "https://manual.nssurge.com/policies/external.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "外部工具 · addresses",
        "source": "https://manual.nssurge.com/policies/external.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "外部工具 · udp-relay",
        "source": "https://manual.nssurge.com/policies/external.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policies/external.html"
    ]
  },
  {
    "id": "activity",
    "title": "活动",
    "group": "工具与系统",
    "icon": "activity",
    "sub": "真实速度、连接、延迟及流量统计。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "活动 真实速度、连接、延迟及流量统计。 真实上传 / 下载速度 1 分钟 / 5 分钟 / 1 小时曲线 今日 / 本月流量 代理 / 直连分类 应用 / 域名 / 节点排行 客户端来源 真实活跃连接",
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "真实上传 / 下载速度",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "1 分钟 / 5 分钟 / 1 小时曲线",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "今日 / 本月流量",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "代理 / 直连分类",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "应用 / 域名 / 节点排行",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "客户端来源",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "真实活跃连接",
        "source": "https://manual.nssurge.com/tools/dashboard.html",
        "status": "部分实现",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/dashboard.html"
    ]
  },
  {
    "id": "processes",
    "title": "进程与客户端",
    "group": "工具与系统",
    "icon": "settings",
    "sub": "共享真实连接采样，识别实际进程与来源。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "进程与客户端 共享真实连接采样，识别实际进程与来源。 ",
    "status": "部分实现",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "共享真实连接采样，识别实际进程与来源。",
        "status": "部分实现",
        "source": "https://manual.nssurge.com/",
        "note": "Swirl 扩展入口；不宣称 Surge 格式兼容。"
      }
    ],
    "sources": []
  },
  {
    "id": "feature-iprewrite",
    "title": "IP 重写",
    "group": "接管与网络",
    "icon": "route",
    "sub": "预留 IP reflect、reject 和 drop 处理规则。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "IP 重写 预留 IP reflect、reject 和 drop 处理规则。 IP 重写 · IP Rewrite iOS 5.23.0+ Mac 6.10.0+ IP 重写 · reflect IP 重写 · reject IP 重写 · drop IP 重写 · Example: On-Device Developer Services",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "IP 重写 · IP Rewrite iOS 5.23.0+ Mac 6.10.0+",
        "source": "https://manual.nssurge.com/features/ip-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "IP 重写 · reflect",
        "source": "https://manual.nssurge.com/features/ip-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "IP 重写 · reject",
        "source": "https://manual.nssurge.com/features/ip-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "IP 重写 · drop",
        "source": "https://manual.nssurge.com/features/ip-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "IP 重写 · Example: On-Device Developer Services",
        "source": "https://manual.nssurge.com/features/ip-rewrite.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/features/ip-rewrite.html"
    ]
  },
  {
    "id": "feature-smart",
    "title": "智能策略与站点记忆",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "按连接质量和目标站点选择策略；独立架构待开发。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "智能策略与站点记忆 按连接质量和目标站点选择策略；独立架构待开发。 智能策略与站点记忆 · Smart Group iOS 5.11.0+ Mac 5.7.0+ 智能策略与站点记忆 · How Selection Works 智能策略与站点记忆 · Per-site Memory 智能策略与站点记忆 · Testing 智能策略与站点记忆 · Temporary Override 智能策略与站点记忆 · policy-priority 连接质量智能选路 按站点策略记忆",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "智能策略与站点记忆 · Smart Group iOS 5.11.0+ Mac 5.7.0+",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "智能策略与站点记忆 · How Selection Works",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "智能策略与站点记忆 · Per-site Memory",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "智能策略与站点记忆 · Testing",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "智能策略与站点记忆 · Temporary Override",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "智能策略与站点记忆 · policy-priority",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "连接质量智能选路",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "按站点策略记忆",
        "source": "https://manual.nssurge.com/policy-groups/smart.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policy-groups/smart.html"
    ]
  },
  {
    "id": "feature-policyoverride",
    "title": "策略临时覆盖",
    "group": "代理与策略",
    "icon": "layers",
    "sub": "预留手动覆盖、覆盖时限、恢复及组嵌套。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "策略临时覆盖 预留手动覆盖、覆盖时限、恢复及组嵌套。 策略临时覆盖 · Temporary Override 策略临时覆盖 · Temporary Override 策略临时覆盖 · Nesting Groups 策略临时覆盖 · Temporary Override 策略临时覆盖 · Temporary Override",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "策略临时覆盖 · Temporary Override",
        "source": "https://manual.nssurge.com/policy-groups/fallback.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略临时覆盖 · Temporary Override",
        "source": "https://manual.nssurge.com/policy-groups/load-balance.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略临时覆盖 · Nesting Groups",
        "source": "https://manual.nssurge.com/policy-groups/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略临时覆盖 · Temporary Override",
        "source": "https://manual.nssurge.com/policy-groups/parameters.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "策略临时覆盖 · Temporary Override",
        "source": "https://manual.nssurge.com/policy-groups/url-test.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/policy-groups/fallback.html",
      "https://manual.nssurge.com/policy-groups/load-balance.html",
      "https://manual.nssurge.com/policy-groups/overview.html",
      "https://manual.nssurge.com/policy-groups/parameters.html",
      "https://manual.nssurge.com/policy-groups/url-test.html"
    ]
  },
  {
    "id": "feature-geodb",
    "title": "GeoIP / ASN 数据库",
    "group": "代理与策略",
    "icon": "globe",
    "sub": "地理和自治系统规则、数据库更新及缺失诊断。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "GeoIP / ASN 数据库 地理和自治系统规则、数据库更新及缺失诊断。 GeoIP / ASN 数据库 · GeoIP Database GeoIP / ASN 数据库 · geoip-maxmind-url GeoIP / ASN 数据库 · disable-geoip-db-auto-update GeoIP / ASN 数据库 · GEOIP GeoIP / ASN 数据库 · IP-ASN GeoIP / ASN 数据库 · GeoIP and ASN Databases GeoIP / ASN 数据库 · GeoIP country database GeoIP / ASN 数据库 · ASN database GeoIP 规则 ASN 规则 数据库更新与校验",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "GeoIP / ASN 数据库 · GeoIP Database",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · geoip-maxmind-url",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · disable-geoip-db-auto-update",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · GEOIP",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · IP-ASN",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · GeoIP and ASN Databases",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · GeoIP country database",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP / ASN 数据库 · ASN database",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "GeoIP 规则",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "ASN 规则",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "数据库更新与校验",
        "source": "https://manual.nssurge.com/rules/ip.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/general.html",
      "https://manual.nssurge.com/rules/ip.html"
    ]
  },
  {
    "id": "feature-ruleinspection",
    "title": "规则测试与命中解释",
    "group": "代理与策略",
    "icon": "list",
    "sub": "预留临时规则、匹配测试、命中解释与统计。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "规则测试与命中解释 预留临时规则、匹配测试、命中解释与统计。 规则测试与命中解释 · Pre-matching 临时规则 规则匹配测试 规则命中解释 规则命中统计",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "规则测试与命中解释 · Pre-matching",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "临时规则",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则匹配测试",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则命中解释",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "规则命中统计",
        "source": "https://manual.nssurge.com/rules/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/rules/overview.html"
    ]
  },
  {
    "id": "feature-dnstrace",
    "title": "DNS 查询追踪",
    "group": "DNS",
    "icon": "search",
    "sub": "预留查询记录、缓存查看与清理、故障诊断。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "DNS 查询追踪 预留查询记录、缓存查看与清理、故障诊断。 DNS 查询追踪 · DNS Overview DNS 查询追踪 · Concurrent Querying DNS 查询追踪 · A and AAAA Queries DNS 查询追踪 · Empty Answers DNS 查询追踪 · Caching DNS 查询追踪 · Special Hostnames DNS 缓存查看 DNS 缓存清理 DNS 查询追踪 DNS 故障诊断",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "DNS 查询追踪 · DNS Overview",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 查询追踪 · Concurrent Querying",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 查询追踪 · A and AAAA Queries",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 查询追踪 · Empty Answers",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 查询追踪 · Caching",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 查询追踪 · Special Hostnames",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "DNS 缓存查看",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS 缓存清理",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS 查询追踪",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "DNS 故障诊断",
        "source": "https://manual.nssurge.com/dns/overview.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/dns/overview.html"
    ]
  },
  {
    "id": "feature-keystore",
    "title": "密钥库与证书引用",
    "group": "配置与自动化",
    "icon": "shield",
    "sub": "预留受保护密钥引用；草稿禁止保存实际密钥。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "密钥库与证书引用 预留受保护密钥引用；草稿禁止保存实际密钥。 密钥库与证书引用 · Keystore 密钥库与证书引用 · type 密钥库与证书引用 · base64 密钥库与证书引用 · password 密钥库与证书引用 · Client Certificate for TLS Proxy 密钥库与证书引用 · MITM CA Certificate 密钥库与证书引用 · SSH Private Key",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "密钥库与证书引用 · Keystore",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "密钥库与证书引用 · type",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "密钥库与证书引用 · base64",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "密钥库与证书引用 · password",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "密钥库与证书引用 · Client Certificate for TLS Proxy",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "密钥库与证书引用 · MITM CA Certificate",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "密钥库与证书引用 · SSH Private Key",
        "source": "https://manual.nssurge.com/profile/keystore.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/keystore.html"
    ]
  },
  {
    "id": "feature-configvalidation",
    "title": "配置验证与差异检查",
    "group": "配置与自动化",
    "icon": "document",
    "sub": "预留配置校验、错误定位和版本差异。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "配置验证与差异检查 预留配置校验、错误定位和版本差异。 配置验证 配置差异检查",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "配置验证",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "配置差异检查",
        "source": "https://manual.nssurge.com/profile/format.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/profile/format.html"
    ]
  },
  {
    "id": "feature-prometheus",
    "title": "Prometheus 指标",
    "group": "工具与系统",
    "icon": "chart",
    "sub": "预留受控指标导出与访问认证。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "Prometheus 指标 预留受控指标导出与访问认证。 Prometheus 指标 · Prometheus Metrics iOS 5.22.0+ Mac 6.9.0+ Prometheus 指标导出",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "Prometheus 指标 · Prometheus Metrics iOS 5.22.0+ Mac 6.9.0+",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "Prometheus 指标导出",
        "source": "https://manual.nssurge.com/tools/http-api.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/tools/http-api.html"
    ]
  },
  {
    "id": "feature-metered",
    "title": "计费网络应用限制",
    "group": "接管与网络",
    "icon": "network",
    "sub": "预留按网络环境限制应用访问和计费流量。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "计费网络应用限制 预留按网络环境限制应用访问和计费流量。 计费网络应用限制 · Metered Network Mode 计费网络应用白名单 按网络启用计费模式",
    "status": "待开发",
    "platform": "Windows 具备相关网络或应用能力；Swirl 接入程度见细项",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "计费网络应用限制 · Metered Network Mode",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "待开发",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "计费网络应用白名单",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "按网络启用计费模式",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "待开发",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/getting-started/platform-differences.html"
    ]
  },
  {
    "id": "feature-mobileinterfaces",
    "title": "蜂窝与 Apple 网络扩展",
    "group": "接管与网络",
    "icon": "network",
    "sub": "蜂窝混合链路、Apple VPN 扩展及系统图标属于平台参考能力。",
    "fields": [
      {
        "key": "plan",
        "label": "配置规划",
        "kind": "text",
        "options": []
      }
    ],
    "sections": [
      "配置",
      "条目",
      "说明"
    ],
    "keywords": "蜂窝与 Apple 网络扩展 蜂窝混合链路、Apple VPN 扩展及系统图标属于平台参考能力。 蜂窝与 Apple 网络扩展 · CELLULAR iOS Only 蜂窝与 Apple 网络扩展 · CELLULAR-ONLY iOS Only 蜂窝与 Apple 网络扩展 · HYBRID iOS Only 蜂窝与 Apple 网络扩展 · NO-HYBRID iOS Only 蜂窝与 Apple 网络扩展 · hybrid iOS Only 蜂窝与 Apple 网络扩展 · compatibility-mode 蜂窝与 Apple 网络扩展 · auto-suspend iOS 5.11.0+ 蜂窝与 Apple 网络扩展 · all-hybrid 蜂窝与 Apple 网络扩展 · hide-vpn-icon 蜂窝与 Apple 网络扩展 · include-all-networks 蜂窝与 Apple 网络扩展 · include-local-networks 蜂窝与 Apple 网络扩展 · include-apns 蜂窝与 Apple 网络扩展 · include-cellular-services 蜂窝与 Apple 网络扩展 · include-device-communication iOS 5.23.0+ iOS 蜂窝策略 Wi-Fi 与蜂窝混合链路 Apple Network Extension tvOS VPN 状态图标 兼容接管模式",
    "platformLimited": true,
    "status": "平台受限",
    "platform": "Apple 平台专用接口，Windows 无同名系统能力",
    "future": true,
    "liveRoute": "",
    "capabilities": [
      {
        "name": "蜂窝与 Apple 网络扩展 · CELLULAR iOS Only",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · CELLULAR-ONLY iOS Only",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · HYBRID iOS Only",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · NO-HYBRID iOS Only",
        "source": "https://manual.nssurge.com/policies/built-in.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · hybrid iOS Only",
        "source": "https://manual.nssurge.com/policies/parameters.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · compatibility-mode",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · auto-suspend iOS 5.11.0+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · all-hybrid",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · hide-vpn-icon",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · include-all-networks",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · include-local-networks",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · include-apns",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · include-cellular-services",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "蜂窝与 Apple 网络扩展 · include-device-communication iOS 5.23.0+",
        "source": "https://manual.nssurge.com/profile/general.html",
        "status": "平台受限",
        "note": "模块入口已规划；此细项未宣称生效，Surge 格式及 API 兼容不在本阶段范围。"
      },
      {
        "name": "iOS 蜂窝策略",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "Wi-Fi 与蜂窝混合链路",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "Apple Network Extension",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "tvOS",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "VPN 状态图标",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      },
      {
        "name": "兼容接管模式",
        "source": "https://manual.nssurge.com/getting-started/platform-differences.html",
        "status": "平台受限",
        "note": "Swirl 对应能力；状态描述不代表 Surge 格式兼容。"
      }
    ],
    "sources": [
      "https://manual.nssurge.com/getting-started/platform-differences.html",
      "https://manual.nssurge.com/policies/built-in.html",
      "https://manual.nssurge.com/policies/parameters.html",
      "https://manual.nssurge.com/profile/general.html"
    ]
  }
]
    readonly property var categories: ["接管与网络", "代理与策略", "DNS", "HTTP 与调试", "配置与自动化", "设备与服务", "工具与系统"]
    function find(id) { for(var i=0;i<entries.length;i++)if(entries[i].id===id)return entries[i];return null }
}

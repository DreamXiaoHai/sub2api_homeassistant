[English](README.md)

# sub2API Subscription for Home Assistant

将 [sub2API](https://github.com/Wei-Shaw/sub2api) 账号中的订阅额度同步到
Home Assistant，并以传感器、Lovelace 卡片和自动化通知的方式使用这些数据。

本项目适合希望在 Home Assistant 中查看以下信息的用户：

- 每日已用金额和每日总额度
- 每周已用金额和每周总额度
- 每日、每周额度的下一次重置时间
- 剩余额度和使用百分比
- 多个有效订阅的独立状态

> [!IMPORTANT]
> 本集成使用 sub2API 网页登录会话的 `auth_token` 和 `refresh_token`。
> 模型调用使用的 API Key 无法访问订阅接口。不要把令牌提交到 GitHub、
> 发送到聊天或写入公开日志。

## 目录

- [工作原理](#工作原理)
- [安装前准备](#安装前准备)
- [安装集成](#安装集成)
- [获取 sub2API 令牌](#获取-sub2api-令牌)
- [在 Home Assistant 中添加集成](#在-home-assistant-中添加集成)
- [认识生成的实体](#认识生成的实体)
- [创建 Lovelace 仪表盘](#创建-lovelace-仪表盘)
- [配置额度重置通知](#配置额度重置通知)
- [令牌刷新与重新认证](#令牌刷新与重新认证)
- [更新和卸载](#更新和卸载)
- [常见问题](#常见问题)
- [仓库结构](#仓库结构)
- [开发与验证](#开发与验证)

## 工作原理

集成每 5 分钟调用一次 sub2API 的用户订阅接口：

```text
GET /api/v1/subscriptions/progress
```

Home Assistant 中的数据流如下：

```text
sub2API 订阅接口
        ↓
sub2API Subscription 集成
        ↓
每日/每周传感器
        ↓
Lovelace 卡片、历史记录和自动化
```

集成会自动发现当前账号下的全部有效订阅。每个订阅对应一个 Home
Assistant 设备，并根据该订阅配置的额度窗口创建传感器。新增订阅会自动
出现；失效或被移除的订阅实体会保留在实体注册表中，但状态会变成不可用。

## 安装前准备

请先确认以下条件：

- Home Assistant 版本为 **2025.1.0 或更新版本**
- Home Assistant 所在机器可以通过 HTTPS 访问 sub2API 站点
- 可以在浏览器中正常登录目标 sub2API 账号
- 可以访问 Home Assistant 的 `/config` 配置目录，或者已经安装 HACS

如果 Home Assistant 和 sub2API 不在同一台机器上，请从 Home Assistant
机器测试域名是否可以正常解析和访问。反向代理、防火墙和 DNS 配置都可能
导致浏览器可以访问、Home Assistant 却无法访问。

## 安装集成

选择 HACS 或手动安装其中一种方式即可。

### 方法一：通过 HACS 安装

仓库发布到 GitHub 后，可以把它作为 HACS 自定义仓库使用：

1. 打开 Home Assistant 中的 **HACS**。
2. 进入 **集成**。
3. 点击右上角菜单，选择 **自定义仓库**。
4. 填写本项目的 GitHub 仓库地址。
5. 类别选择 **集成**，然后添加仓库。
6. 搜索并下载 **sub2API Subscription**。
7. 完全重启 Home Assistant。

HACS 只能从 GitHub 仓库安装，不能直接读取另一台电脑上的本地目录。

### 方法二：手动安装

把仓库中的整个 `custom_components/sub2api` 文件夹复制到 Home
Assistant 配置目录。最终目录必须是：

```text
/config/
└── custom_components/
    └── sub2api/
        ├── __init__.py
        ├── api.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── manifest.json
        ├── models.py
        ├── sensor.py
        ├── strings.json
        └── translations/
```

常见部署方式对应的操作如下：

#### Home Assistant OS / Supervised

可以使用 Samba share、Studio Code Server 或 Terminal & SSH 加载项，把
文件复制到：

```text
/config/custom_components/sub2api
```

#### Home Assistant Container（Docker）

找到容器映射的宿主机配置目录。例如启动参数包含：

```text
-v /opt/homeassistant/config:/config
```

则应复制到：

```text
/opt/homeassistant/config/custom_components/sub2api
```

不要只复制进容器临时文件系统，否则重新创建容器后文件会消失。

#### Home Assistant Core

将组件复制到 `configuration.yaml` 所在目录下的：

```text
custom_components/sub2api
```

复制完成后，必须完全重启 Home Assistant。仅重新加载 YAML 不会加载新的
自定义集成。

> [!WARNING]
> 常见错误是多复制了一层目录。正确路径是
> `/config/custom_components/sub2api/manifest.json`，而不是
> `/config/custom_components/sub2api/custom_components/sub2api/manifest.json`。

## 获取 sub2API 令牌

推荐从已经登录的 sub2API 网页读取令牌，这种方式兼容第三方站点的验证码、
Turnstile 和双因素认证。

以 Chrome 或 Edge 为例：

1. 在浏览器中登录目标 sub2API 站点。
2. 按 `F12` 打开开发者工具。
3. 进入 **Application（应用）**。
4. 展开 **Local Storage（本地存储）**。
5. 选择当前 sub2API 站点。
6. 找到并复制 `auth_token` 的值。
7. 找到并复制 `refresh_token` 的值。

Firefox 中对应的位置是 **Storage（存储）** > **Local Storage**。

请注意：

- 复制的是字段的值，不要把字段名一起复制。
- 不要使用以模型调用为目的的 API Key。
- 两个令牌必须来自同一个 sub2API 站点和同一个账号。
- 建议使用专门的无痕窗口获取令牌。Home Assistant 配置完成后直接关闭窗口，
  但不要在该窗口中点击退出登录。
- 不要让浏览器和 Home Assistant 长期共用同一个 refresh token。sub2API 会
  轮换 refresh token，先执行刷新的客户端会使另一个客户端保存的旧令牌失效。

> [!WARNING]
> 当前版本的 sub2API 默认启用会话 IP 和 User-Agent 绑定。从浏览器取得的
> 令牌，可能在另一台机器上的 Home Assistant 尝试刷新时被拒绝。如果你是
> sub2API 站点管理员，需要为这种用法关闭会话 IP/UA 绑定，或者为 Home
> Assistant 提供在兼容环境中签发的独立会话。

## 在 Home Assistant 中添加集成

安装并重启 Home Assistant 后：

1. 打开 **设置** > **设备与服务**。
2. 点击 **添加集成**。
3. 搜索 **sub2API Subscription**。
4. 填写 sub2API 站点地址。
5. 粘贴 access token，即网页中的 `auth_token`。
6. 粘贴 refresh token。
7. 提交配置。

站点地址推荐填写根地址：

```text
https://sub2api.example.com
```

以下形式也可以，集成会自动移除末尾的 `/api/v1`：

```text
https://sub2api.example.com/api/v1
```

出于令牌安全考虑，集成只接受 HTTPS 地址，不支持普通公网 HTTP 地址。

配置成功后，可以在集成页面看到账号和自动发现的订阅设备。同一个站点的
不同用户可以分别添加；同一站点的同一用户不能重复添加。

## 认识生成的实体

每个订阅最多创建 6 个传感器。没有配置相应额度的订阅不会创建该组实体。

| 传感器 | 内容 | 单位 | 主要属性 |
|---|---|---|---|
| 每日已用 | 当前每日窗口已使用金额 | USD | `remaining_usd`、`percentage`、`window_start` |
| 每日总额 | 每日额度上限 | USD | 订阅和分组信息 |
| 每日重置 | 每日窗口下一次重置时间 | 时间戳 | `resets_in_seconds` |
| 每周已用 | 当前每周窗口已使用金额 | USD | `remaining_usd`、`percentage`、`window_start` |
| 每周总额 | 每周额度上限 | USD | 订阅和分组信息 |
| 每周重置 | 每周窗口下一次重置时间 | 时间戳 | `resets_in_seconds` |

实体 ID 由 Home Assistant 根据订阅名称生成，因此不同用户的实体 ID 不一定
相同。仓库示例使用的 `sensor.codex_subscription_*` 只是占位符。

查找实际实体 ID：

1. 打开 **开发者工具** > **状态**。
2. 搜索 `daily_used`、`daily_limit`、`daily_reset`、`weekly_used`、
   `weekly_limit` 或 `weekly_reset`。
3. 也可以在 **设置** > **设备与服务** > **sub2API Subscription** 中打开
   对应订阅设备，查看它的全部实体。

如果额度已经配置但窗口尚未激活，已用和总额仍可显示，重置时间会暂时显示
为不可用。

## 创建 Lovelace 仪表盘

Lovelace 是 Home Assistant 仪表盘系统的传统名称。集成负责产生实体，
Lovelace 卡片负责把实体展示出来。

### 原生实体卡片

不安装任何前端插件也可以使用原生实体卡片。打开仪表盘编辑模式，添加
**手动卡片**，把下面的占位符替换成实际实体 ID：

```yaml
type: entities
title: sub2API 订阅额度
entities:
  - entity: sensor.codex_subscription_daily_used
    name: 每日已用
  - entity: sensor.codex_subscription_daily_limit
    name: 每日总额
  - entity: sensor.codex_subscription_daily_reset
    name: 每日重置
  - entity: sensor.codex_subscription_weekly_used
    name: 每周已用
  - entity: sensor.codex_subscription_weekly_limit
    name: 每周总额
  - entity: sensor.codex_subscription_weekly_reset
    name: 每周重置
```

### 仿 sub2API 进度卡片

仓库提供了更接近 sub2API 网页效果的进度卡片：

[`lovelace/sub2api-quota-card.yaml`](lovelace/sub2api-quota-card.yaml)

该卡片显示：

- 订阅名称、平台和有效状态
- 每日及每周的已用金额和总额度
- 根据使用百分比变化的进度条颜色
- 距离下一次重置的动态倒计时
- Home Assistant 浅色和深色主题适配

这张卡片依赖 HACS 前端插件 `button-card`：

1. 打开 **HACS** > **前端**。
2. 搜索并安装 **button-card**。
3. 根据 HACS 提示重新加载浏览器或重启 Home Assistant。
4. 打开 `lovelace/sub2api-quota-card.yaml`。
5. 修改文件顶部 `variables` 中的 6 个实体 ID。
6. 可选：修改 `fallback_title`。
7. 在仪表盘中添加 **手动卡片**，粘贴整个 YAML 文件内容。

需要替换的部分集中在文件开头：

```yaml
variables:
  daily_used: sensor.codex_subscription_daily_used
  daily_limit: sensor.codex_subscription_daily_limit
  daily_reset: sensor.codex_subscription_daily_reset
  weekly_used: sensor.codex_subscription_weekly_used
  weekly_limit: sensor.codex_subscription_weekly_limit
  weekly_reset: sensor.codex_subscription_weekly_reset
  fallback_title: Codex Subscription
```

如果一个账号有多个订阅，请为每个订阅复制一张卡片，并分别填写对应实体。

如果页面显示 `Custom element doesn't exist: button-card`，说明 `button-card`
没有正确安装或浏览器仍在使用旧缓存。确认 HACS 资源已经加载后，强制刷新
浏览器页面。

## 配置额度重置通知

仓库提供了手机通知自动化：

[`automations/sub2api-quota-reset-notification.yaml`](automations/sub2api-quota-reset-notification.yaml)

它会同时监听每日和每周已用额度。当状态从大于 0 突然变为 0，并且当前记录
的重置时间仍在未来或暂不可用时，向手机发送消息。它会忽略
`unknown`、`unavailable` 以及 Home Assistant 启动期间的无效状态变化。

### 准备手机通知服务

1. 在手机上安装 Home Assistant Companion App。
2. 使用该 App 登录当前 Home Assistant。
3. 打开 **开发者工具** > **操作**。
4. 搜索 `notify.mobile_app_`。
5. 记录对应手机的完整操作名称，例如：

```text
notify.mobile_app_your_phone
```

### 添加自动化

1. 打开 **设置** > **自动化与场景**。
2. 新建一个空白自动化。
3. 点击右上角菜单，选择 **以 YAML 编辑**。
4. 粘贴通知 YAML 文件的完整内容。
5. 替换文件中的 6 个 `sensor.codex_subscription_*` 实体 ID。
6. 把 `notify.mobile_app_your_phone` 替换成实际手机通知操作。
7. 保存并启用自动化。

自动化使用 `queued` 模式。如果每日和每周额度在同一次同步中同时归零，两条
通知都会进入队列，不会因为前一条通知尚未完成而丢失后一条。

不要直接使用“运行动作”测试这条自动化，因为通知内容依赖触发器提供的
`trigger.from_state` 和 `trigger.to_state`。手动运行动作时没有这些数据。

## 令牌刷新与重新认证

sub2API 默认配置通常是：

- access token 约 24 小时有效
- refresh token 约 30 天有效

第三方站点可以修改这些期限，因此实际时间以站点配置为准。
例如，站点把 access token 设置为 2 小时有效也是正常的服务端配置。

access token 请求收到 HTTP 401 后，集成会自动使用 refresh token 获取并
保存一对轮换后的新令牌，然后重试原请求。

以下情况可能触发 Home Assistant 的“需要重新认证”：

- refresh token 已过期或被撤销
- 浏览器已经使用并轮换了同一个 refresh token
- sub2API 的会话 IP/User-Agent 绑定拒绝了 Home Assistant 的刷新请求
- 用户修改了密码或站点撤销了会话
- Home Assistant 长时间离线
- 站点启用了后端模式，并禁止非管理员用户刷新令牌
- sub2API 服务重启时清空了 refresh token 缓存
- 站点修改了登录或安全策略

看到重新认证提示后，重新登录 sub2API 网页，获取新的 `auth_token` 和
`refresh_token`，然后在 Home Assistant 提示中粘贴即可。集成不会要求保存
sub2API 邮箱或密码。

## 更新和卸载

### HACS 更新

在 HACS 中更新集成，然后根据提示重启 Home Assistant。

### 手动更新

使用新版本完整替换 `/config/custom_components/sub2api`，不要只替换其中一个
Python 文件。替换后重启 Home Assistant。

### 卸载

1. 在 **设置** > **设备与服务** 中删除 `sub2API Subscription` 配置项。
2. 通过 HACS 卸载，或删除 `/config/custom_components/sub2api`。
3. 重启 Home Assistant。
4. 如有需要，手动删除不再使用的 Lovelace 卡片和自动化。

## 常见问题

### 添加集成时搜索不到 sub2API Subscription

- 检查 `manifest.json` 是否位于
  `/config/custom_components/sub2api/manifest.json`。
- 确认没有多套一层目录。
- 完全重启 Home Assistant。
- 查看 **设置** > **系统** > **日志** 中是否有自定义集成加载错误。

### 提示“无法连接 sub2API 站点”

- 确认填写的是 HTTPS 地址。
- 确认 Home Assistant 机器可以访问该域名，而不只是电脑浏览器可以访问。
- 检查 DNS、防火墙、反向代理和 TLS 证书。
- 不要把登录页面的其他路径附加到站点地址。

### 提示“访问令牌或刷新令牌无效”

- 重新登录网页并获取一对新令牌。
- 确认没有复制引号、空格或字段名称。
- 确认两个令牌来自同一站点、同一账号。
- 不要填写模型 API Key。
- 检查 sub2API 站点是否启用了会话 IP/User-Agent 绑定。
- 不要让浏览器和 Home Assistant 共用同一个轮换中的 refresh token。

### 集成一直正常，但 access token 到期后就报错

这通常表示普通 API 请求成功，但刷新令牌被服务器拒绝。可以在 sub2API
服务端日志中搜索：

```text
SESSION_BINDING_MISMATCH
REFRESH_TOKEN_INVALID
Refresh token not found
possible reuse attack
```

如果启用了会话绑定，从浏览器复制的令牌可能无法由另一台机器上的 Home
Assistant 刷新。如果原浏览器页面一直保持运行，它也可能在 Home Assistant
之前轮换 refresh token，导致 Home Assistant 保存的副本失效。

### 集成添加成功但没有订阅设备

- 确认该账号在 sub2API 中存在有效订阅。
- 确认订阅状态为 active 且尚未到期。
- 打开 sub2API 网页，确认订阅页面本身可以显示额度。

### 只有每日实体或只有每周实体

这是正常情况。集成只为订阅实际配置的额度窗口创建实体。

### 重置时间显示不可用

订阅额度窗口可能尚未激活。通常在该订阅第一次产生用量后，sub2API 才会
设置窗口起点和重置时间。

### Lovelace 卡片没有更新

- 检查文件顶部的 6 个实体 ID。
- 在开发者工具中确认实体本身正在更新。
- 确认 `button-card` 已正确安装。
- 强制刷新浏览器或清除 Home Assistant 前端缓存。

### 手机收不到通知

- 确认 Companion App 已登录并允许通知权限。
- 在开发者工具中单独测试手机的 `notify.mobile_app_*` 操作。
- 检查自动化是否启用，以及跟踪记录中的条件判断结果。
- 确认用量确实从大于 0 直接变成 0。

### 是否支持月额度或订阅到期时间实体

当前 `0.1.0` 版本只创建每日和每周额度实体，暂不创建月额度、订阅状态或
到期时间的独立实体。

### 是否可以添加多个账号或多个站点

可以。同一个站点的不同用户、不同 sub2API 站点都可以分别添加。集成会把
站点、用户和订阅 ID 组合成唯一标识，避免实体冲突。

## 数据与安全

- 访问令牌和刷新令牌保存在 Home Assistant 配置项存储中。
- 令牌输入框使用密码类型，集成不会把令牌写入日志。
- 集成不保存 sub2API 邮箱或密码。
- 只接受 HTTPS 地址，避免通过明文 HTTP 传输令牌。
- 金额单位保持为 sub2API 返回的 USD。
- 仓库中的 URL、实体 ID、用户名和通知服务均为示例值。
- YAML 示例不包含任何真实令牌。

## 仓库结构

```text
.
├── custom_components/
│   └── sub2api/                       # Home Assistant 自定义集成
├── lovelace/
│   └── sub2api-quota-card.yaml        # 可选的额度进度卡片
├── automations/
│   └── sub2api-quota-reset-notification.yaml
│                                       # 可选的额度重置通知
├── tests/                              # 自动化测试
├── hacs.json                           # HACS 元数据
├── pyproject.toml                      # 开发和测试配置
├── README.md                            # 英文文档（默认）
└── README.zh-CN.md                      # 简体中文文档
```

安装集成时只需要 `custom_components/sub2api`。`lovelace` 和 `automations`
目录是可选示例，不需要复制到 Home Assistant 配置目录，也不会被自动加载。

## 开发与验证

创建 Python 3.12 虚拟环境后：

```bash
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

当前测试覆盖：

- API 响应解析和异常响应
- access token 过期与 refresh token 轮换
- 配置、重复账号和重新认证流程
- 每日及每周传感器创建
- 新订阅和新额度窗口的动态发现
- 订阅消失后的实体不可用状态
- 认证失败后启动 Home Assistant 重新认证流程

GitHub Actions 会继续运行单元测试、`ruff`、HACS validation 和 hassfest。

## 上游项目

本项目依赖 sub2API 提供的用户订阅接口。sub2API 服务端和网页项目请参考：

- [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api)

本仓库不是 sub2API 官方 Home Assistant 集成。

---

[Buy me a coffee](https://www.buymeacoffee.com/dreamxiaohai)

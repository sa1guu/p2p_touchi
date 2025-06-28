# IPv6 P2P 游戏网络实现

本项目已完全实现基于IPv6的P2P游戏网络功能，移除了IPv4支持，专门为公网IPv6环境设计。

## 🌟 主要特性

### IPv6专用设计
- **纯IPv6实现**：完全移除IPv4支持，专为IPv6网络优化
- **公网连接**：支持跨公网的IPv6节点发现和连接
- **自动地址获取**：自动检测本机公网IPv6地址
- **协议版本控制**：确保节点间协议兼容性

### P2P网络功能
- **去中心化架构**：无需中央服务器的完全分布式网络
- **节点自动发现**：支持本地和公网节点发现
- **种子节点支持**：可配置种子节点加速网络引导
- **心跳机制**：自动维护节点连接状态
- **速率限制**：防止网络滥用和攻击

### 游戏匹配系统
- **自动匹配**：支持多人游戏自动匹配
- **游戏会话管理**：完整的游戏生命周期管理
- **结果同步**：游戏结果在网络中自动同步

## 🔧 系统要求

### 网络环境
- **IPv6连接**：设备必须具有公网IPv6地址
- **防火墙配置**：允许TCP连接到配置的端口范围
- **路由器支持**：确保IPv6流量可以正常路由

### 软件依赖
- Python 3.7+
- asyncio（Python标准库）
- socket（Python标准库）
- json（Python标准库）

## 📋 配置说明

### P2P网络配置

在 `core/p2p_config.py` 中可以配置以下参数：

```python
class P2PConfig:
    # 网络配置
    DEFAULT_PORT_RANGE = (8000, 8100)  # 端口范围
    MAX_PEERS = 50                      # 最大连接节点数
    DISCOVERY_INTERVAL = 30             # 节点发现间隔（秒）
    HEARTBEAT_INTERVAL = 10             # 心跳间隔（秒）
    CONNECTION_TIMEOUT = 15             # 连接超时（秒）
    
    # IPv6种子节点配置
    SEED_NODES = [
        # 添加已知的公网IPv6节点
        # ("2001:db8::1", 8000),
    ]
```

### 种子节点配置

为了加速网络引导，可以在 `SEED_NODES` 中配置已知的公网IPv6节点：

```python
SEED_NODES = [
    ("2001:db8:1234::1", 8000),
    ("2001:db8:5678::2", 8001),
]
```

## 🚀 使用方法

### 基本使用

```python
from core.p2p_network import P2PNetworkManager

# 创建P2P网络管理器
p2p_manager = P2PNetworkManager()

# 设置回调函数
p2p_manager.on_match_found = lambda match_info: print(f"找到匹配: {match_info}")
p2p_manager.on_game_result = lambda result: print(f"游戏结果: {result}")

# 启动网络
port = await p2p_manager.start()
print(f"P2P网络启动，监听端口: {port}")
print(f"IPv6地址: {p2p_manager.local_ipv6}")

# 请求匹配
await p2p_manager.request_match("user123")

# 获取网络状态
status = p2p_manager.get_network_status()
print(f"网络状态: {status}")
```

### 测试网络

运行测试脚本验证IPv6 P2P功能：

```bash
python test_p2p.py
```

测试包括：
- IPv6连接性测试
- 单节点功能测试
- 多节点发现测试
- 游戏匹配测试

## 🔍 故障排除

### 常见问题

1. **无法获取公网IPv6地址**
   - 检查设备是否配置了IPv6
   - 确认ISP提供IPv6服务
   - 验证路由器IPv6设置

2. **节点发现失败**
   - 检查防火墙设置
   - 确认端口范围未被占用
   - 验证IPv6路由配置

3. **连接超时**
   - 增加 `CONNECTION_TIMEOUT` 值
   - 检查网络延迟
   - 验证目标节点可达性

### 调试方法

启用详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

检查网络状态：

```python
status = p2p_manager.get_network_status()
print(f"节点ID: {status['node_id']}")
print(f"端口: {status['port']}")
print(f"对等节点数: {status['peers_count']}")
print(f"待处理匹配: {status['pending_matches']}")
print(f"活跃会话: {status['active_sessions']}")
```

## 🔒 安全考虑

### 网络安全
- **速率限制**：防止消息洪泛攻击
- **协议版本验证**：确保节点兼容性
- **连接超时**：防止资源耗尽
- **消息大小限制**：防止大消息攻击

### 隐私保护
- 节点ID使用UUID生成，不包含个人信息
- 仅传输必要的游戏相关数据
- 支持临时连接，游戏结束后自动断开

## 📈 性能优化

### 网络优化
- 使用异步I/O提高并发性能
- 实现连接池复用TCP连接
- 优化消息序列化格式

### 扩展性
- 支持动态调整最大连接数
- 可配置发现和心跳间隔
- 支持自定义消息处理器

## 🔄 版本兼容性

当前协议版本：`1.0`

节点间会自动检查协议版本兼容性，不兼容的节点将被拒绝连接。

## 📞 技术支持

如遇到问题，请检查：
1. IPv6网络连接状态
2. 防火墙和路由器配置
3. 应用程序日志输出
4. 运行测试脚本验证功能

---

**注意**：此实现专为IPv6环境设计，不支持IPv4网络。确保您的网络环境支持IPv6后再使用。
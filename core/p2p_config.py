# P2P网络配置文件

class P2PConfig:
    """P2P网络配置类"""
    
    # 网络配置
    DEFAULT_PORT_RANGE = (8000, 8100)  # 默认端口范围
    MAX_PEERS = 50  # 最大连接节点数
    DISCOVERY_INTERVAL = 30  # 节点发现间隔（秒）
    HEARTBEAT_INTERVAL = 10  # 心跳间隔（秒）
    CONNECTION_TIMEOUT = 15  # 连接超时（秒）
    
    # 匹配配置
    MATCH_TIMEOUT = 300  # 匹配超时时间（5分钟）
    PLAYERS_PER_MATCH = 3  # 每场游戏玩家数
    MATCH_COST = 2000000  # 匹配费用（哈夫币）
    
    # 游戏配置
    GAME_DURATION = 60  # 游戏时长（1分钟）
    WINNER_REWARD = 3300  # 获胜者奖励（三角币）
    
    # 网络发现配置
    BROADCAST_PORT = 8888  # 广播端口
    DISCOVERY_MESSAGE = "MANDEL_P2P_DISCOVERY"
    RESPONSE_MESSAGE = "MANDEL_P2P_RESPONSE"
    
    # 协议版本
    PROTOCOL_VERSION = "1.0"
    
    # IPv6种子节点配置（公网节点发现）
    SEED_NODES = [
        # 可以添加已知的公网IPv6节点地址
        # 格式: ("ipv6_address", port)
        # 例如: ("2001:db8::1", 8000),
    ]
    
    # 安全配置
    MAX_MESSAGE_SIZE = 1024 * 1024  # 最大消息大小（1MB）
    RATE_LIMIT_MESSAGES = 100  # 每分钟最大消息数
    RATE_LIMIT_WINDOW = 60  # 速率限制窗口（秒）
    
    @classmethod
    def get_available_port(cls, start_port=None, end_port=None):
        """获取可用端口"""
        import socket
        
        if start_port is None:
            start_port = cls.DEFAULT_PORT_RANGE[0]
        if end_port is None:
            end_port = cls.DEFAULT_PORT_RANGE[1]
            
        for port in range(start_port, end_port + 1):
            try:
                with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    # 绑定到IPv6通配符地址，支持IPv6-only
                    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                    s.bind(('::', port))
                    return port
            except OSError:
                continue
        
        raise RuntimeError(f"No available port in range {start_port}-{end_port}")
    
    @classmethod
    def validate_config(cls):
        """验证配置有效性"""
        assert cls.MAX_PEERS > 0, "MAX_PEERS must be positive"
        assert cls.DISCOVERY_INTERVAL > 0, "DISCOVERY_INTERVAL must be positive"
        assert cls.HEARTBEAT_INTERVAL > 0, "HEARTBEAT_INTERVAL must be positive"
        assert cls.CONNECTION_TIMEOUT > 0, "CONNECTION_TIMEOUT must be positive"
        assert cls.MATCH_TIMEOUT > 0, "MATCH_TIMEOUT must be positive"
        assert cls.PLAYERS_PER_MATCH > 1, "PLAYERS_PER_MATCH must be greater than 1"
        assert cls.MATCH_COST > 0, "MATCH_COST must be positive"
        assert cls.GAME_DURATION > 0, "GAME_DURATION must be positive"
        assert cls.WINNER_REWARD > 0, "WINNER_REWARD must be positive"
        assert cls.MAX_MESSAGE_SIZE > 0, "MAX_MESSAGE_SIZE must be positive"
        assert cls.RATE_LIMIT_MESSAGES > 0, "RATE_LIMIT_MESSAGES must be positive"
        assert cls.RATE_LIMIT_WINDOW > 0, "RATE_LIMIT_WINDOW must be positive"
        
        return True
import asyncio
import json
import socket
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Callable
import logging
from .p2p_config import P2PConfig

@dataclass
class P2PNode:
    """P2P节点信息"""
    node_id: str
    host: str
    port: int
    last_seen: float
    capabilities: List[str]

@dataclass
class MatchRequest:
    """匹配请求"""
    request_id: str
    user_id: str
    node_id: str
    timestamp: float
    game_type: str = "mandel_online"

@dataclass
class GameSession:
    """游戏会话"""
    session_id: str
    players: List[str]
    coordinator_node: str
    status: str  # waiting, playing, finished
    start_time: Optional[float] = None
    end_time: Optional[float] = None

class P2PProtocol(asyncio.Protocol):
    """P2P通信协议"""
    
    def __init__(self, network_manager):
        self.network_manager = network_manager
        self.transport = None
        self.buffer = b""
        
    def connection_made(self, transport):
        self.transport = transport
        peer_addr = transport.get_extra_info('peername')
        logger.info(f"P2P连接建立: {peer_addr}")
        
    def data_received(self, data):
        self.buffer += data
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                message = json.loads(line.decode('utf-8'))
                asyncio.create_task(self.network_manager.handle_message(message, self))
            except Exception as e:
                logger.error(f"P2P消息解析错误: {e}")
                
    def connection_lost(self, exc):
        peer_addr = self.transport.get_extra_info('peername') if self.transport else "unknown"
        logger.info(f"P2P连接断开: {peer_addr}")
        
    def send_message(self, message: dict):
        if self.transport:
            data = json.dumps(message).encode('utf-8') + b'\n'
            self.transport.write(data)

class P2PNetworkManager:
    """P2P网络管理器"""
    
    def __init__(self, port: int = None):
        # 验证配置
        P2PConfig.validate_config()
        
        # 获取可用端口
        if port is None:
            port = P2PConfig.get_available_port()
        self.port = port
        
        self.node_id = str(uuid.uuid4())
        self.peers: Dict[str, P2PNode] = {}
        self.pending_matches: Dict[str, MatchRequest] = {}
        self.active_sessions: Dict[str, GameSession] = {}
        self.server = None
        self.protocol = None
        self.discovery_task = None
        self.heartbeat_task = None
        
        # 全局队列状态管理
        self.global_queue_state: Dict[str, int] = {}  # {node_id: pending_count}
        self.is_coordinator = False
        self.coordinator_node_id = None
        
        # 回调函数
        self.on_match_found: Optional[Callable] = None
        self.on_game_result: Optional[Callable] = None
        
        # 速率限制
        self.message_counts: Dict[str, List[float]] = {}
        
        # 获取本机IPv6地址
        self.local_ipv6 = self._get_local_ipv6_address()
        
        logging.info(f"P2P网络管理器初始化完成，节点ID: {self.node_id[:8]}..., 端口: {self.port}, IPv6: {self.local_ipv6}")
    
    def _get_local_ipv6_address(self) -> str:
        """获取本机IPv6地址"""
        try:
            # 创建一个IPv6 socket连接到公网地址来获取本机IPv6地址
            with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s:
                # 连接到Google的IPv6 DNS服务器
                s.connect(("2001:4860:4860::8888", 80))
                local_ipv6 = s.getsockname()[0]
                return local_ipv6
        except Exception:
            # 如果无法获取公网IPv6地址，返回回环地址
            return "::1"
    
    def _is_public_ipv6(self, ipv6_addr: str) -> bool:
        """检查是否为公网IPv6地址"""
        import ipaddress
        try:
            addr = ipaddress.IPv6Address(ipv6_addr)
            return not (addr.is_loopback or addr.is_link_local or addr.is_private)
        except:
            return False
    
    def _get_coordinator_node(self) -> str:
        """选择协调节点（最小节点ID）"""
        all_nodes = [self.node_id] + list(self.peers.keys())
        return min(all_nodes)
    
    async def _update_coordinator_status(self):
        """更新协调节点状态"""
        coordinator_id = self._get_coordinator_node()
        old_coordinator = self.coordinator_node_id
        self.coordinator_node_id = coordinator_id
        self.is_coordinator = (coordinator_id == self.node_id)
        
        # 如果协调节点发生变化，同步队列状态
        if old_coordinator != coordinator_id and self.is_coordinator:
            await self._sync_queue_state()
        
    async def _sync_queue_state(self):
        """同步队列状态到所有节点"""
        if not self.is_coordinator:
            return
            
        # 计算全局队列总数
        total_pending = sum(self.global_queue_state.values())
        
        queue_sync_msg = {
            'type': 'queue_sync',
            'coordinator_id': self.node_id,
            'global_queue_state': self.global_queue_state,
            'total_pending': total_pending
        }
        
        for peer in self.peers.values():
            try:
                await self._send_message(peer.host, peer.port, queue_sync_msg)
            except:
                pass
        
    def _check_rate_limit(self, peer_id: str) -> bool:
        """检查速率限制"""
        current_time = time.time()
        
        if peer_id not in self.message_counts:
            self.message_counts[peer_id] = []
        
        # 清理过期的消息记录
        self.message_counts[peer_id] = [
            msg_time for msg_time in self.message_counts[peer_id]
            if current_time - msg_time < P2PConfig.RATE_LIMIT_WINDOW
        ]
        
        # 检查是否超过限制
        if len(self.message_counts[peer_id]) >= P2PConfig.RATE_LIMIT_MESSAGES:
            return False
        
        # 记录新消息
        self.message_counts[peer_id].append(current_time)
        return True
        
    async def start(self) -> int:
        """启动P2P网络服务"""
        max_retries = 10
        current_port = self.port
        
        for attempt in range(max_retries):
            try:
                # 创建IPv6服务器
                self.server = await asyncio.start_server(
                    self._handle_client,
                    '::',
                    current_port,
                    family=socket.AF_INET6
                )
                
                # 更新实际使用的端口
                self.port = current_port
                logging.info(f"P2P服务器启动成功，监听端口 {self.port}")
                
                # 初始化协调节点状态
                await self._update_coordinator_status()
                
                # 启动节点发现任务
                self.discovery_task = asyncio.create_task(self._discover_peers())
                
                # 启动心跳任务
                self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                return self.port
                
            except OSError as e:
                if e.errno == 10048:  # 端口被占用
                    logging.warning(f"端口 {current_port} 被占用，尝试下一个端口")
                    current_port = P2PConfig.get_available_port(current_port + 1, P2PConfig.DEFAULT_PORT_RANGE[1])
                    continue
                else:
                    logging.error(f"P2P服务器启动失败: {e}")
                    raise
            except Exception as e:
                logging.error(f"P2P服务器启动失败: {e}")
                raise
        
        raise RuntimeError(f"无法在 {max_retries} 次尝试后启动P2P服务器")
    
    async def _handle_client(self, reader, writer):
        """处理客户端连接"""
        peer_addr = writer.get_extra_info('peername')
        logging.info(f"新的P2P连接: {peer_addr}")
        
        try:
            while True:
                # 读取消息长度
                length_data = await reader.readexactly(4)
                if not length_data:
                    break
                
                message_length = int.from_bytes(length_data, 'big')
                if message_length > P2PConfig.MAX_MESSAGE_SIZE:
                    logging.warning(f"消息过大，断开连接: {peer_addr}")
                    break
                
                # 读取消息内容
                message_data = await reader.readexactly(message_length)
                message = json.loads(message_data.decode('utf-8'))
                
                # 处理消息
                await self._handle_message(message, writer)
                
        except Exception as e:
            logging.error(f"处理客户端连接出错: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def _handle_message(self, message: dict, writer):
        """处理收到的消息"""
        msg_type = message.get('type')
        sender_id = message.get('sender_id')
        
        # 检查速率限制
        if sender_id and not self._check_rate_limit(sender_id):
            logging.warning(f"节点 {sender_id} 触发速率限制")
            return
        
        if msg_type == 'discovery':
            await self._handle_discovery(message, writer)
        elif msg_type == 'match_request':
            await self._handle_match_request(message)
        elif msg_type == 'game_result':
            await self._handle_game_result(message)
        elif msg_type == 'heartbeat':
            await self._handle_heartbeat(message, writer)
        elif msg_type == 'queue_sync':
            await self._handle_queue_sync(message)
        elif msg_type == 'global_match_request':
            await self._handle_global_match_request(message)
    
    async def _discover_peers(self):
        """节点发现循环"""
        while True:
            try:
                # 广播发现消息
                discovery_msg = {
                    'type': 'discovery',
                    'sender_id': self.node_id,
                    'host': self.local_ipv6,
                    'port': self.port,
                    'timestamp': time.time(),
                    'protocol_version': P2PConfig.PROTOCOL_VERSION
                }
                
                # 向本地网络广播
                await self._broadcast_discovery(discovery_msg)
                
                await asyncio.sleep(P2PConfig.DISCOVERY_INTERVAL)
                
            except Exception as e:
                logging.error(f"节点发现出错: {e}")
                await asyncio.sleep(5)
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while True:
            try:
                current_time = time.time()
                
                # 清理超时的节点
                timeout_peers = []
                for peer_id, peer in self.peers.items():
                    if current_time - peer.last_seen > P2PConfig.CONNECTION_TIMEOUT:
                        timeout_peers.append(peer_id)
                
                for peer_id in timeout_peers:
                    logging.info(f"移除超时节点: {peer_id[:8]}...")
                    del self.peers[peer_id]
                
                # 发送心跳给所有连接的节点
                heartbeat_msg = {
                    'type': 'heartbeat',
                    'sender_id': self.node_id,
                    'host': self.local_ipv6,
                    'port': self.port,
                    'timestamp': current_time,
                    'protocol_version': P2PConfig.PROTOCOL_VERSION
                }
                
                for peer in self.peers.values():
                    try:
                        await self._send_message(peer.host, peer.port, heartbeat_msg)
                    except:
                        pass
                
                await asyncio.sleep(P2PConfig.HEARTBEAT_INTERVAL)
                
            except Exception as e:
                logging.error(f"心跳循环出错: {e}")
                await asyncio.sleep(5)
             
    async def _send_message(self, host: str, port: int, message: dict):
        """发送消息到指定节点"""
        try:
            # 强制使用IPv6连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, port,
                    family=socket.AF_INET6
                ),
                timeout=P2PConfig.CONNECTION_TIMEOUT
            )
            
            # 序列化消息
            message_data = json.dumps(message).encode('utf-8')
            message_length = len(message_data)
            
            # 发送消息长度和内容
            writer.write(message_length.to_bytes(4, 'big'))
            writer.write(message_data)
            await writer.drain()
            
            writer.close()
            await writer.wait_closed()
            
        except Exception as e:
            logging.debug(f"发送消息失败 {host}:{port} - {e}")
    
    async def _broadcast_discovery(self, message: dict):
        """广播发现消息"""
        # 向本地IPv6网络的常见端口发送发现消息
        for port in range(P2PConfig.DEFAULT_PORT_RANGE[0], P2PConfig.DEFAULT_PORT_RANGE[1]):
            if port != self.port:  # 不向自己发送
                try:
                    # 使用IPv6回环地址进行本地发现
                    await self._send_message('::1', port, message)
                except:
                    pass  # 忽略连接失败
        
        # 尝试向已知的公网IPv6节点发送发现消息
        await self._discover_public_nodes(message)
    
    async def _discover_public_nodes(self, message: dict):
        """发现公网IPv6节点"""
        # 从已知节点列表中选择活跃节点进行发现
        active_peers = [
            peer for peer in self.peers.values() 
            if time.time() - peer.last_seen < P2PConfig.CONNECTION_TIMEOUT
        ]
        
        # 向活跃节点发送发现消息
        for peer in active_peers:
            try:
                await self._send_message(peer.host, peer.port, message)
            except:
                pass  # 忽略连接失败
        
        # 如果没有已知节点，可以尝试连接到种子节点（如果有配置的话）
        if not active_peers and hasattr(P2PConfig, 'SEED_NODES'):
            for seed_host, seed_port in P2PConfig.SEED_NODES:
                try:
                    await self._send_message(seed_host, seed_port, message)
                except:
                    pass
    
    async def _handle_discovery(self, message: dict, writer):
        """处理发现消息"""
        sender_id = message.get('sender_id')
        sender_host = message.get('host')
        sender_port = message.get('port')
        protocol_version = message.get('protocol_version', '1.0')
        
        if sender_id == self.node_id:
            return  # 忽略自己的消息
        
        # 检查协议版本兼容性
        if protocol_version != P2PConfig.PROTOCOL_VERSION:
            logging.warning(f"协议版本不匹配: {protocol_version} vs {P2PConfig.PROTOCOL_VERSION}")
            return
        
        # 优先使用消息中的host信息，否则使用连接地址
        host = sender_host
        if not host:
            peer_addr = writer.get_extra_info('peername')
            if peer_addr:
                host = peer_addr[0]
            else:
                return  # 无法获取地址信息
        
        # 添加或更新节点信息
        self.peers[sender_id] = P2PNode(
            node_id=sender_id,
            host=host,
            port=sender_port,
            last_seen=time.time(),
            capabilities=[]
        )
        
        logging.info(f"发现新节点: {sender_id[:8]}... at {host}:{sender_port}")
        
        # 更新协调节点状态
        await self._update_coordinator_status()
        
        # 回复发现响应
        response = {
            'type': 'discovery_response',
            'sender_id': self.node_id,
            'host': self.local_ipv6,
            'port': self.port,
            'timestamp': time.time(),
            'protocol_version': P2PConfig.PROTOCOL_VERSION
        }
         
        try:
             await self._send_message(host, sender_port, response)
        except:
             pass
    
    async def _handle_heartbeat(self, message: dict, writer):
        """处理心跳消息"""
        sender_id = message.get('sender_id')
        
        if sender_id in self.peers:
            self.peers[sender_id].last_seen = time.time()
    
    async def _handle_match_request(self, message: dict):
        """处理匹配请求"""
        request_id = message.get('request_id')
        user_id = message.get('user_id')
        
        if not request_id or not user_id:
            return
        
        # 创建匹配请求
        match_request = MatchRequest(
            request_id=request_id,
            user_id=user_id,
            node_id=message.get('node_id', ''),
            timestamp=time.time()
        )
        
        self.pending_matches[request_id] = match_request
        
        # 检查是否可以组成游戏
        await self._try_create_match()
    
    async def _handle_game_result(self, message: dict):
        """处理游戏结果"""
        session_id = message.get('session_id')
        winner_id = message.get('winner_id')
        
        if session_id in self.active_sessions and self.on_game_result:
            await self.on_game_result(winner_id)
    
    async def _handle_queue_sync(self, message: dict):
        """处理队列状态同步"""
        coordinator_id = message.get('coordinator_id')
        global_queue_state = message.get('global_queue_state', {})
        
        # 更新全局队列状态
        self.global_queue_state = global_queue_state
        self.coordinator_node_id = coordinator_id
        self.is_coordinator = (coordinator_id == self.node_id)
        
        logging.info(f"收到队列同步: 协调节点={coordinator_id}, 全局队列状态={global_queue_state}")
    
    async def _handle_global_match_request(self, message: dict):
        """处理全局匹配请求（仅协调节点处理）"""
        if not self.is_coordinator:
            return
            
        request_id = message.get('request_id')
        user_id = message.get('user_id')
        source_node = message.get('source_node')
        
        if not request_id or not user_id or not source_node:
            return
        
        # 创建匹配请求
        match_request = MatchRequest(
            request_id=request_id,
            user_id=user_id,
            node_id=source_node,
            timestamp=time.time()
        )
        
        self.pending_matches[request_id] = match_request
        
        # 更新全局队列状态
        self.global_queue_state[source_node] = self.global_queue_state.get(source_node, 0) + 1
        
        # 同步队列状态
        await self._sync_queue_state()
        
        # 尝试创建匹配
        await self._try_create_match()
        
        logging.info(f"协调节点处理匹配请求: {user_id} from {source_node}")
    
    async def _try_create_match(self):
        """尝试创建匹配"""
        if len(self.pending_matches) >= P2PConfig.PLAYERS_PER_MATCH:
            # 选择最早的3个请求
            requests = sorted(self.pending_matches.values(), key=lambda x: x.timestamp)
            selected_requests = requests[:P2PConfig.PLAYERS_PER_MATCH]
            
            # 创建游戏会话
            session_id = str(uuid.uuid4())
            players = [req.user_id for req in selected_requests]
            
            game_session = GameSession(
                session_id=session_id,
                players=players,
                coordinator_node=self.node_id,
                status="playing",
                start_time=time.time()
            )
            
            self.active_sessions[session_id] = game_session
            
            # 更新全局队列状态（减少对应节点的队列数量）
            if self.is_coordinator:
                for req in selected_requests:
                    node_id = req.node_id
                    if node_id in self.global_queue_state:
                        self.global_queue_state[node_id] = max(0, self.global_queue_state[node_id] - 1)
            
            # 移除已匹配的请求
            for req in selected_requests:
                if req.request_id in self.pending_matches:
                    del self.pending_matches[req.request_id]
            
            # 同步更新后的队列状态
            if self.is_coordinator:
                await self._sync_queue_state()
            
            # 通知匹配成功
            if self.on_match_found:
                await self.on_match_found(session_id, players)
            
            # 启动游戏计时器
            asyncio.create_task(self._game_timer(session_id, players))
            
            logging.info(f"匹配成功: 会话={session_id}, 玩家={players}")
    
    async def _game_timer(self, session_id: str, players: List[str]):
        """游戏计时器"""
        await asyncio.sleep(P2PConfig.GAME_DURATION)
        
        if session_id in self.active_sessions:
            # 随机选择获胜者
            import random
            winner_id = random.choice(players)
            
            # 广播游戏结果
            result_msg = {
                'type': 'game_result',
                'session_id': session_id,
                'winner_id': winner_id,
                'timestamp': time.time()
            }
            
            for peer in self.peers.values():
                try:
                    await self._send_message(peer.host, peer.port, result_msg)
                except:
                    pass
            
            # 处理本地结果
            if self.on_game_result:
                await self.on_game_result(winner_id)
            
            # 清理会话
            del self.active_sessions[session_id]
     
    async def stop(self):
        """停止P2P网络节点"""
        if self.discovery_task:
            self.discovery_task.cancel()
        
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logging.info("P2P节点已停止")
     
    async def request_match(self, user_id: str) -> str:
        """请求匹配"""
        request_id = str(uuid.uuid4())
        
        # 更新协调节点状态
        self._update_coordinator_status()
        
        if self.is_coordinator:
            # 协调节点直接处理本地请求
            match_request = MatchRequest(
                request_id=request_id,
                user_id=user_id,
                node_id=self.node_id,
                timestamp=time.time()
            )
            
            self.pending_matches[request_id] = match_request
            
            # 更新全局队列状态
            self.global_queue_state[self.node_id] = self.global_queue_state.get(self.node_id, 0) + 1
            
            # 同步队列状态
            await self._sync_queue_state()
            
            # 检查匹配
            await self._try_create_match()
        else:
            # 非协调节点发送请求给协调节点
            if self.coordinator_node_id:
                coordinator_peer = None
                for peer in self.peers.values():
                    if peer.node_id == self.coordinator_node_id:
                        coordinator_peer = peer
                        break
                
                if coordinator_peer:
                    message = {
                        'type': 'global_match_request',
                        'request_id': request_id,
                        'user_id': user_id,
                        'source_node': self.node_id
                    }
                    
                    try:
                        await self._send_message(coordinator_peer.host, coordinator_peer.port, message)
                        logging.info(f"向协调节点发送匹配请求: {user_id}")
                    except Exception as e:
                        logging.error(f"发送匹配请求到协调节点失败: {e}")
                        # 回退到本地处理
                        await self._fallback_local_match(user_id, request_id)
                else:
                    # 找不到协调节点，回退到本地处理
                    await self._fallback_local_match(user_id, request_id)
            else:
                # 没有协调节点，回退到本地处理
                await self._fallback_local_match(user_id, request_id)
        
        logging.info(f"用户 {user_id} 请求匹配: {request_id}")
        return request_id
    
    async def _fallback_local_match(self, user_id: str, request_id: str):
        """回退到本地匹配处理"""
        match_request = MatchRequest(
            request_id=request_id,
            user_id=user_id,
            node_id=self.node_id,
            timestamp=time.time()
        )
        
        self.pending_matches[request_id] = match_request
        
        # 广播匹配请求给所有对等节点
        message = {
            'type': 'match_request',
            'request_id': request_id,
            'user_id': user_id,
            'node_id': self.node_id,
            'timestamp': time.time()
        }
        
        for peer in self.peers.values():
            try:
                await self._send_message(peer.host, peer.port, message)
            except Exception as e:
                logging.error(f"发送匹配请求失败: {e}")
        
        # 检查本地匹配
        await self._try_create_match()
        
        logging.info(f"回退到本地匹配处理: {user_id}")
     
    def get_network_status(self) -> dict:
        """获取网络状态"""
        return {
            'node_id': self.node_id,
            'host': self.local_ipv6,
            'port': self.port,
            'is_coordinator': self.is_coordinator,
            'coordinator_node_id': self.coordinator_node_id,
            'global_queue_state': self.global_queue_state,
            'peers_count': len(self.peers),
            'pending_matches': len(self.pending_matches),
            'active_sessions': len(self.active_sessions),
            'peers': [
                {
                    'node_id': peer.node_id[:8] + '...',
                    'host': peer.host,
                    'port': peer.port,
                    'last_seen': peer.last_seen
                }
                for peer in self.peers.values()
            ]
        }
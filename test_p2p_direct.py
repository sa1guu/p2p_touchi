#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
曼德尔P2P直连功能测试脚本

测试新增的曼德尔P2P直连匹配功能，验证：
1. P2P直连匹配流程
2. 本地队列兼容性
3. 混合匹配机制
4. 错误处理和回退
"""

import asyncio
import logging
import time
from unittest.mock import Mock, AsyncMock
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.touchi_tools import TouchiTools
from core.p2p_network import P2PNetwork

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockEvent:
    """模拟事件对象"""
    def __init__(self, user_id, group_id):
        self.user_id = user_id
        self.group_id = group_id
        self.results = []
    
    def get_sender_id(self):
        return self.user_id
    
    def get_group_id(self):
        return self.group_id
    
    def plain_result(self, text):
        self.results.append(text)
        print(f"[Event Result] {text}")
        return text
    
    def image_result(self, path):
        result = f"[Image: {path}]"
        self.results.append(result)
        print(f"[Event Result] {result}")
        return result

class P2PDirectTester:
    """P2P直连功能测试器"""
    
    def __init__(self):
        self.test_results = []
        self.touchi_tools = None
        self.p2p_networks = []
    
    async def setup_test_environment(self):
        """设置测试环境"""
        logger.info("设置测试环境...")
        
        # 创建测试用的TouchiTools实例
        self.touchi_tools = TouchiTools()
        
        # 模拟数据库路径
        self.touchi_tools.db_path = ":memory:"
        
        # 模拟P2P管理器
        self.touchi_tools.p2p_manager = Mock()
        self.touchi_tools.p2p_port = 8000
        
        # 模拟用户经济数据获取
        async def mock_get_user_economy_data(user_id):
            return {
                "warehouse_value": 5000000,  # 500万哈夫币
                "user_id": user_id
            }
        
        self.touchi_tools.get_user_economy_data = mock_get_user_economy_data
        
        # 模拟数据库操作
        import aiosqlite
        original_connect = aiosqlite.connect
        
        async def mock_connect(db_path):
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            mock_db.execute = AsyncMock(return_value=mock_cursor)
            mock_db.commit = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            return mock_db
        
        aiosqlite.connect = mock_connect
        
        logger.info("测试环境设置完成")
    
    async def test_p2p_direct_basic(self):
        """测试基本P2P直连功能"""
        logger.info("\n=== 测试基本P2P直连功能 ===")
        
        try:
            # 模拟P2P网络状态
            self.touchi_tools.p2p_manager.get_network_status.return_value = {
                'node_id': 'test_node_12345678',
                'peers_count': 2,
                'pending_matches': 1,
                'active_sessions': 0
            }
            
            # 模拟P2P匹配请求
            self.touchi_tools.p2p_manager.request_match = AsyncMock(return_value="match_request_123")
            
            # 创建测试事件
            event = MockEvent(user_id="user_001", group_id="group_001")
            
            # 执行P2P直连匹配
            results = []
            async for result in self.touchi_tools.mandel_p2p_direct(event):
                results.append(result)
            
            # 验证结果
            assert len(results) > 0, "应该有返回结果"
            assert "P2P直连匹配已启动" in results[0], "应该显示P2P匹配启动信息"
            assert "已扣除200万哈夫币" in results[0], "应该显示扣费信息"
            assert "同时兼容本地和P2P玩家匹配" in results[0], "应该显示兼容性信息"
            
            self.test_results.append(("基本P2P直连功能", "通过", "P2P直连匹配正常启动"))
            logger.info("✅ 基本P2P直连功能测试通过")
            
        except Exception as e:
            self.test_results.append(("基本P2P直连功能", "失败", str(e)))
            logger.error(f"❌ 基本P2P直连功能测试失败: {e}")
    
    async def test_local_queue_compatibility(self):
        """测试本地队列兼容性"""
        logger.info("\n=== 测试本地队列兼容性 ===")
        
        try:
            # 模拟P2P网络状态
            self.touchi_tools.p2p_manager.get_network_status.return_value = {
                'node_id': 'test_node_12345678',
                'peers_count': 2,
                'pending_matches': 0,
                'active_sessions': 0
            }
            
            # 模拟P2P匹配请求
            self.touchi_tools.p2p_manager.request_match = AsyncMock(return_value="match_request_123")
            
            # 模拟本地游戏启动
            self.touchi_tools._start_local_mandel_game = AsyncMock()
            
            # 创建测试事件
            events = [
                MockEvent(user_id="user_001", group_id="group_001"),
                MockEvent(user_id="user_002", group_id="group_001"),
                MockEvent(user_id="user_003", group_id="group_001")
            ]
            
            # 依次执行P2P直连匹配
            for i, event in enumerate(events):
                results = []
                async for result in self.touchi_tools.mandel_p2p_direct(event):
                    results.append(result)
                
                if i < 2:
                    # 前两个玩家应该进入队列
                    assert "P2P直连匹配已启动" in results[0], f"玩家{i+1}应该进入P2P匹配"
                else:
                    # 第三个玩家应该触发本地游戏
                    assert "本地队列已满3人" in results[0], "第三个玩家应该触发本地游戏"
            
            # 验证本地游戏是否被调用
            self.touchi_tools._start_local_mandel_game.assert_called_once()
            
            self.test_results.append(("本地队列兼容性", "通过", "本地队列满员时正确触发本地游戏"))
            logger.info("✅ 本地队列兼容性测试通过")
            
        except Exception as e:
            self.test_results.append(("本地队列兼容性", "失败", str(e)))
            logger.error(f"❌ 本地队列兼容性测试失败: {e}")
    
    async def test_insufficient_funds(self):
        """测试哈夫币不足的情况"""
        logger.info("\n=== 测试哈夫币不足情况 ===")
        
        try:
            # 模拟哈夫币不足的用户
            async def mock_get_user_economy_data_poor(user_id):
                return {
                    "warehouse_value": 1000000,  # 只有100万哈夫币
                    "user_id": user_id
                }
            
            self.touchi_tools.get_user_economy_data = mock_get_user_economy_data_poor
            
            # 创建测试事件
            event = MockEvent(user_id="poor_user", group_id="group_001")
            
            # 执行P2P直连匹配
            results = []
            async for result in self.touchi_tools.mandel_p2p_direct(event):
                results.append(result)
            
            # 验证结果
            assert len(results) > 0, "应该有返回结果"
            assert "哈夫币不足" in results[0], "应该显示哈夫币不足信息"
            
            self.test_results.append(("哈夫币不足处理", "通过", "正确拒绝哈夫币不足的用户"))
            logger.info("✅ 哈夫币不足处理测试通过")
            
        except Exception as e:
            self.test_results.append(("哈夫币不足处理", "失败", str(e)))
            logger.error(f"❌ 哈夫币不足处理测试失败: {e}")
    
    async def test_p2p_network_unavailable(self):
        """测试P2P网络不可用的情况"""
        logger.info("\n=== 测试P2P网络不可用情况 ===")
        
        try:
            # 恢复正常的经济数据获取
            async def mock_get_user_economy_data(user_id):
                return {
                    "warehouse_value": 5000000,  # 500万哈夫币
                    "user_id": user_id
                }
            
            self.touchi_tools.get_user_economy_data = mock_get_user_economy_data
            
            # 模拟P2P网络不可用
            self.touchi_tools.p2p_manager = None
            
            # 创建测试事件
            event = MockEvent(user_id="user_001", group_id="group_001")
            
            # 执行P2P直连匹配
            results = []
            async for result in self.touchi_tools.mandel_p2p_direct(event):
                results.append(result)
            
            # 验证结果
            assert len(results) > 0, "应该有返回结果"
            assert "P2P网络未启动" in results[0], "应该显示P2P网络未启动信息"
            
            self.test_results.append(("P2P网络不可用处理", "通过", "正确处理P2P网络不可用情况"))
            logger.info("✅ P2P网络不可用处理测试通过")
            
        except Exception as e:
            self.test_results.append(("P2P网络不可用处理", "失败", str(e)))
            logger.error(f"❌ P2P网络不可用处理测试失败: {e}")
    
    async def test_private_chat_restriction(self):
        """测试私聊限制"""
        logger.info("\n=== 测试私聊限制 ===")
        
        try:
            # 恢复P2P管理器
            self.touchi_tools.p2p_manager = Mock()
            
            # 创建私聊事件（group_id为None）
            event = MockEvent(user_id="user_001", group_id=None)
            
            # 执行P2P直连匹配
            results = []
            async for result in self.touchi_tools.mandel_p2p_direct(event):
                results.append(result)
            
            # 验证结果
            assert len(results) > 0, "应该有返回结果"
            assert "此功能仅支持群聊使用" in results[0], "应该显示群聊限制信息"
            
            self.test_results.append(("私聊限制", "通过", "正确限制私聊使用"))
            logger.info("✅ 私聊限制测试通过")
            
        except Exception as e:
            self.test_results.append(("私聊限制", "失败", str(e)))
            logger.error(f"❌ 私聊限制测试失败: {e}")
    
    def print_test_results(self):
        """打印测试结果"""
        logger.info("\n" + "="*60)
        logger.info("曼德尔P2P直连功能测试结果")
        logger.info("="*60)
        
        passed = 0
        failed = 0
        
        for test_name, status, description in self.test_results:
            status_icon = "✅" if status == "通过" else "❌"
            logger.info(f"{status_icon} {test_name}: {status} - {description}")
            
            if status == "通过":
                passed += 1
            else:
                failed += 1
        
        logger.info("-" * 60)
        logger.info(f"总计: {len(self.test_results)} 项测试")
        logger.info(f"通过: {passed} 项")
        logger.info(f"失败: {failed} 项")
        logger.info(f"成功率: {passed/len(self.test_results)*100:.1f}%" if self.test_results else "0%")
        logger.info("="*60)
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("开始曼德尔P2P直连功能测试...")
        
        await self.setup_test_environment()
        
        # 运行各项测试
        await self.test_p2p_direct_basic()
        await self.test_local_queue_compatibility()
        await self.test_insufficient_funds()
        await self.test_p2p_network_unavailable()
        await self.test_private_chat_restriction()
        
        # 打印测试结果
        self.print_test_results()
        
        return len([r for r in self.test_results if r[1] == "通过"]) == len(self.test_results)

async def main():
    """主函数"""
    tester = P2PDirectTester()
    
    try:
        success = await tester.run_all_tests()
        
        if success:
            logger.info("\n🎉 所有测试通过！曼德尔P2P直连功能正常工作。")
            return 0
        else:
            logger.error("\n❌ 部分测试失败，请检查代码。")
            return 1
            
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
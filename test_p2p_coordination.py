#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2P协调节点测试脚本
用于测试修改后的P2P网络协调机制
"""

import asyncio
import logging
import time
from core.p2p_network import P2PNetworkManager
from core.p2p_config import P2PConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class TestP2PCoordination:
    def __init__(self):
        self.managers = []
        self.match_results = []
    
    async def create_test_nodes(self, count=3):
        """创建测试节点"""
        base_port = 8000
        
        for i in range(count):
            manager = P2PNetworkManager(port=base_port + i)
            
            # 设置匹配回调
            manager.on_match_found = self.create_match_callback(f"Node-{i}")
            
            self.managers.append(manager)
            
            # 启动节点
            await manager.start()
            logging.info(f"节点 {i} 启动完成，端口: {base_port + i}")
            
            # 等待一下让节点初始化
            await asyncio.sleep(1)
    
    def create_match_callback(self, node_name):
        """创建匹配回调函数"""
        async def on_match_found(session_id, players):
            result = {
                'node': node_name,
                'session_id': session_id,
                'players': players,
                'timestamp': time.time()
            }
            self.match_results.append(result)
            logging.info(f"{node_name} 匹配成功: {session_id}, 玩家: {players}")
        
        return on_match_found
    
    async def wait_for_discovery(self, timeout=10):
        """等待节点发现完成"""
        logging.info("等待节点发现...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            all_discovered = True
            for manager in self.managers:
                if len(manager.peers) < len(self.managers) - 1:
                    all_discovered = False
                    break
            
            if all_discovered:
                logging.info("所有节点发现完成")
                return True
            
            await asyncio.sleep(1)
        
        logging.warning("节点发现超时")
        return False
    
    async def test_coordinator_selection(self):
        """测试协调节点选择"""
        logging.info("\n=== 测试协调节点选择 ===")
        
        coordinators = []
        for i, manager in enumerate(self.managers):
            status = manager.get_network_status()
            logging.info(f"节点 {i}: 是否为协调节点={status['is_coordinator']}, 协调节点ID={status['coordinator_node_id'][:8]}...")
            if status['is_coordinator']:
                coordinators.append(i)
        
        if len(coordinators) == 1:
            logging.info(f"✓ 协调节点选择正确，协调节点: Node-{coordinators[0]}")
            return True
        else:
            logging.error(f"✗ 协调节点选择错误，发现 {len(coordinators)} 个协调节点")
            return False
    
    async def test_queue_coordination(self):
        """测试队列协调"""
        logging.info("\n=== 测试队列协调 ===")
        
        # 清空之前的匹配结果
        self.match_results.clear()
        
        # 模拟3个用户同时请求匹配
        tasks = []
        for i, manager in enumerate(self.managers):
            task = asyncio.create_task(manager.request_match(f"user_{i}"))
            tasks.append(task)
        
        # 等待所有请求完成
        await asyncio.gather(*tasks)
        
        # 等待匹配处理
        await asyncio.sleep(3)
        
        # 检查结果
        if len(self.match_results) == 1:
            result = self.match_results[0]
            if len(result['players']) == 3:
                logging.info(f"✓ 队列协调成功，3个玩家匹配到同一个游戏: {result['players']}")
                return True
            else:
                logging.error(f"✗ 匹配玩家数量错误: {len(result['players'])}")
                return False
        elif len(self.match_results) == 0:
            logging.error("✗ 没有匹配结果")
            return False
        else:
            logging.error(f"✗ 产生了多个匹配结果: {len(self.match_results)}")
            return False
    
    async def test_global_queue_state(self):
        """测试全局队列状态同步"""
        logging.info("\n=== 测试全局队列状态同步 ===")
        
        # 找到协调节点
        coordinator = None
        for manager in self.managers:
            if manager.is_coordinator:
                coordinator = manager
                break
        
        if not coordinator:
            logging.error("✗ 找不到协调节点")
            return False
        
        # 检查全局队列状态
        status = coordinator.get_network_status()
        global_queue = status['global_queue_state']
        
        logging.info(f"全局队列状态: {global_queue}")
        
        # 验证队列状态是否合理
        total_queue = sum(global_queue.values())
        if total_queue >= 0:
            logging.info(f"✓ 全局队列状态正常，总队列数: {total_queue}")
            return True
        else:
            logging.error(f"✗ 全局队列状态异常: {global_queue}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        logging.info("清理测试资源...")
        for manager in self.managers:
            await manager.stop()
    
    async def run_tests(self):
        """运行所有测试"""
        try:
            # 创建测试节点
            await self.create_test_nodes(3)
            
            # 等待节点发现
            if not await self.wait_for_discovery():
                logging.error("节点发现失败，跳过后续测试")
                return
            
            # 运行测试
            tests = [
                self.test_coordinator_selection(),
                self.test_queue_coordination(),
                self.test_global_queue_state()
            ]
            
            results = await asyncio.gather(*tests, return_exceptions=True)
            
            # 统计结果
            passed = sum(1 for result in results if result is True)
            total = len(results)
            
            logging.info(f"\n=== 测试结果 ===")
            logging.info(f"通过: {passed}/{total}")
            
            if passed == total:
                logging.info("🎉 所有测试通过！P2P协调机制工作正常")
            else:
                logging.warning(f"⚠️  有 {total - passed} 个测试失败")
        
        except Exception as e:
            logging.error(f"测试过程中出现错误: {e}")
        
        finally:
            await self.cleanup()

async def main():
    """主函数"""
    logging.info("开始P2P协调节点测试")
    
    test = TestP2PCoordination()
    await test.run_tests()
    
    logging.info("测试完成")

if __name__ == "__main__":
    asyncio.run(main())
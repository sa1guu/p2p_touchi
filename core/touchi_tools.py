import httpx
import asyncio
import json
import random
import os
import time
import httpx
import aiosqlite  # Import the standard SQLite library
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import At, Plain, Image
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .touchi import generate_safe_image, get_item_value
from .p2p_network import P2PNetworkManager

class TouchiTools:
    def __init__(self, enable_touchi=True, enable_beauty_pic=True, cd=5, db_path=None):
        self.enable_touchi = enable_touchi
        self.enable_beauty_pic = enable_beauty_pic
        self.cd = cd
        self.db_path = db_path # Path to the database file
        self.last_usage = {}
        self.waiting_users = {}  # 记录正在等待的用户及其结束时间
        self.semaphore = asyncio.Semaphore(10)
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.biaoqing_dir = os.path.join(current_dir, "biaoqing")
        os.makedirs(self.biaoqing_dir, exist_ok=True)
        
        self.output_dir = os.path.join(current_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.multiplier = 1.0
        
        self.safe_box_messages = [
            ("鼠鼠偷吃中...(预计{}min)", "touchi.png", 120),
            ("鼠鼠猛攻中...(预计{}min)", "menggong.png", 60)
        ]
        
        self.character_names = ["威龙", "老黑", "蜂医", "红狼", "乌鲁鲁", "深蓝", "无名"]
        
        # 自动偷吃相关
        self.auto_touchi_tasks = {}  # 存储用户的自动偷吃任务
        self.auto_touchi_data = {}   # 存储自动偷吃期间的数据
        self.nickname_cache = {}     # 缓存群成员昵称，格式: {group_id: {user_id: nickname}}
        self.cache_expire_time = {}  # 缓存过期时间
        
        # 初始化P2P网络管理器
        self.p2p_manager = None
        self.p2p_port = None
        self._init_p2p_network()
        
        # 启动P2P网络
        asyncio.create_task(self._start_p2p_network())
    
    def _init_p2p_network(self):
        """初始化P2P网络"""
        try:
            self.p2p_manager = P2PNetworkManager()
            # 设置回调函数
            self.p2p_manager.on_match_found = self._on_match_found
            self.p2p_manager.on_game_result = self._on_game_result
            
            # 启动P2P网络（异步）
            asyncio.create_task(self._start_p2p_network())
            logger.info("P2P网络管理器初始化完成")
        except Exception as e:
            logger.error(f"P2P网络初始化失败: {e}")
            
    async def _start_p2p_network(self):
        """启动P2P网络"""
        try:
            self.p2p_port = await self.p2p_manager.start()
            logger.info(f"P2P网络已启动，端口: {self.p2p_port}")
        except Exception as e:
            logger.error(f"P2P网络启动失败: {e}")
            
    async def _on_match_found(self, session_id: str, players: list):
        """匹配成功回调"""
        try:
            logger.info(f"P2P匹配成功: 会话 {session_id}, 玩家: {players}")
        except Exception as e:
            logger.error(f"处理匹配成功回调错误: {e}")
            
    async def _on_game_result(self, message: dict):
        """游戏结果回调"""
        try:
            session_id = message["session_id"]
            winners = message["winners"]
            losers = message["losers"]
            rewards = message["rewards"]
            
            # 更新本地数据库中获胜者的三角币
            async with aiosqlite.connect(self.db_path) as db:
                for winner_id, reward in rewards.items():
                    await db.execute(
                        "UPDATE user_economy SET triangle_coins = triangle_coins + ? WHERE user_id = ?",
                        (reward, winner_id)
                    )
                await db.commit()
                
            logger.info(f"P2P游戏结束: 会话 {session_id}, 获胜者: {winners}, 失败者: {losers}")
        except Exception as e:
            logger.error(f"处理游戏结果回调错误: {e}")

    def set_multiplier(self, multiplier: float):
        if multiplier < 0.01 or multiplier > 100:
            return "倍率必须在0.01到100之间"
        self.multiplier = multiplier
        return f"鼠鼠冷却倍率已设置为 {multiplier} 倍！"
    
    async def clear_user_data(self, user_id=None):
        """清除用户数据（管理员功能）"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                if user_id:
                    # 清除指定用户数据
                    await db.execute("DELETE FROM user_touchi_collection WHERE user_id = ?", (user_id,))
                    await db.execute("DELETE FROM user_economy WHERE user_id = ?", (user_id,))
                    await db.commit()
                    return f"已清除用户 {user_id} 的所有数据"
                else:
                    # 清除所有用户数据
                    await db.execute("DELETE FROM user_touchi_collection")
                    await db.execute("DELETE FROM user_economy")
                    await db.commit()
                    return "已清除所有用户数据"
        except Exception as e:
            logger.error(f"清除用户数据时出错: {e}")
            return "清除数据失败，请重试"
    
    async def add_hafubi_all_users(self):
        """给所有用户增加200万哈夫币（管理员功能）"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 获取所有用户
                async with db.execute("SELECT DISTINCT user_id FROM user_economy") as cursor:
                    users = await cursor.fetchall()
                
                if not users:
                    return "❌ 数据库中没有找到任何用户"
                
                # 给所有用户增加200万哈夫币
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value + 2000000"
                )
                await db.commit()
                
                user_count = len(users)
                return f"✅ 成功给 {user_count} 名用户增加了200万哈夫币！"
                
        except Exception as e:
            logger.error(f"给所有用户增加哈夫币时出错: {e}")
            return "❌ 操作失败，请重试"
    
    async def _get_group_member_nicknames(self, event: AstrMessageEvent, group_id: str):
        """获取群成员昵称映射，带缓存机制"""
        current_time = time.time()
        
        # 检查缓存是否有效（10分钟过期）
        if (group_id in self.nickname_cache and 
            group_id in self.cache_expire_time and 
            current_time < self.cache_expire_time[group_id]):
            return self.nickname_cache[group_id]
        
        nickname_map = {}
        
        try:
            # 直接使用event.bot获取群成员列表
            members = await event.bot.get_group_member_list(group_id=int(group_id))
            
            # 创建昵称映射字典
            for member in members:
                user_id = str(member['user_id'])
                nickname = member.get('card') or member.get('nickname') or f"用户{user_id[:6]}"
                nickname_map[user_id] = nickname
            
            # 更新缓存
            self.nickname_cache[group_id] = nickname_map
            self.cache_expire_time[group_id] = current_time + 600  # 10分钟后过期
            
            logger.info(f"成功获取群{group_id}的{len(nickname_map)}个成员昵称")
            
        except Exception as e:
            logger.error(f"获取群成员信息失败: {str(e)}")
        
        return nickname_map
        
    async def fetch_touchi(self):
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get("https://api.lolicon.app/setu/v2?r18=0")
            resp.raise_for_status()
            return resp.json()

    async def add_items_to_collection(self, user_id, placed_items):
        """将获得的物品添加到用户收藏中并更新仓库价值"""
        if not self.db_path or not placed_items:
            return
        
        try:
            total_value = 0
            async with aiosqlite.connect(self.db_path) as db:
                # 添加物品到收藏
                for placed in placed_items:
                    item = placed["item"]
                    item_name = os.path.splitext(os.path.basename(item["path"]))[0]
                    item_level = item["level"]
                    item_value = item.get("value", get_item_value(item_name))
                    total_value += item_value
                    
                    await db.execute(
                        "INSERT OR IGNORE INTO user_touchi_collection (user_id, item_name, item_level) VALUES (?, ?, ?)",
                        (user_id, item_name, item_level)
                    )
                
                # 更新用户经济数据
                await db.execute(
                    "INSERT OR IGNORE INTO user_economy (user_id) VALUES (?)",
                    (user_id,)
                )
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value + ? WHERE user_id = ?",
                    (total_value, user_id)
                )
                await db.commit()
            logger.info(f"用户 {user_id} 成功记录了 {len(placed_items)} 个物品到[collection.db]，总价值: {total_value}。")
        except Exception as e:
            logger.error(f"为用户 {user_id} 添加物品到数据库[collection.db]时出错: {e}")

    async def get_user_economy_data(self, user_id):
        """获取用户经济数据"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT warehouse_value, teqin_level, grid_size, menggong_active, menggong_end_time, auto_touchi_active, auto_touchi_start_time, triangle_coins FROM user_economy WHERE user_id = ?",
                    (user_id,)
                )
                result = await cursor.fetchone()
                if result:
                    return {
                        "warehouse_value": result[0],
                        "teqin_level": result[1],
                        "grid_size": result[2],
                        "menggong_active": result[3],
                        "menggong_end_time": result[4],
                        "auto_touchi_active": result[5],
                        "auto_touchi_start_time": result[6],
                        "triangle_coins": result[7] if len(result) > 7 else 0
                    }
                else:
                    # 获取系统配置的基础等级
                    config_cursor = await db.execute(
                        "SELECT config_value FROM system_config WHERE config_key = 'base_teqin_level'"
                    )
                    config_result = await config_cursor.fetchone()
                    base_level = int(config_result[0]) if config_result else 0
                    
                    # 计算对应的grid_size
                    if base_level == 0:
                        base_grid_size = 2
                    else:
                        base_grid_size = 2 + base_level
                    
                    # 创建新用户记录
                    await db.execute(
                        "INSERT INTO user_economy (user_id, teqin_level, grid_size, triangle_coins) VALUES (?, ?, ?, ?)",
                        (user_id, base_level, base_grid_size, 0)
                    )
                    await db.commit()
                    return {
                        "warehouse_value": 0,
                        "teqin_level": base_level,
                        "grid_size": base_grid_size,
                        "menggong_active": 0,
                        "menggong_end_time": 0,
                        "auto_touchi_active": 0,
                        "auto_touchi_start_time": 0,
                        "triangle_coins": 0
                    }
        except Exception as e:
            logger.error(f"获取用户经济数据时出错: {e}")
            return None

    async def get_touchi(self, event):
        if not self.enable_touchi:
            yield event.plain_result("盲盒功能已关闭")
            return
            
        user_id = event.get_sender_id()
        now = asyncio.get_event_loop().time()
        
        # 检查用户是否在自动偷吃状态，如果是则不允许手动偷吃
        economy_data = await self.get_user_economy_data(user_id)
        if economy_data and economy_data["auto_touchi_active"]:
            yield event.plain_result("自动偷吃进行中，无法手动偷吃。请先关闭自动偷吃。")
            return
        
        # 检查用户是否在等待状态
        if user_id in self.waiting_users:
            end_time = self.waiting_users[user_id]
            remaining_time = end_time - now
            if remaining_time > 0:
                minutes = int(remaining_time // 60)
                seconds = int(remaining_time % 60)
                if minutes > 0:
                    yield event.plain_result(f"鼠鼠还在偷吃中，请等待 {minutes}分{seconds}秒")
                else:
                    yield event.plain_result(f"鼠鼠还在偷吃中，请等待 {seconds}秒")
                return
            else:
                # 等待时间已过，清除等待状态
                del self.waiting_users[user_id]
        
        rand_num = random.random()
        
        if self.enable_beauty_pic and rand_num < 0.3: 
            async with self.semaphore:
                try:
                    data = await self.fetch_touchi()
                    if data['data']:
                        image_url = data['data'][0]['urls']['original']
                        character = random.choice(self.character_names)
                        
                        chain = [
                            At(qq=event.get_sender_id()),
                            Plain(f"🎉 恭喜开到{character}珍藏美图："),
                            Image.fromURL(image_url, size='small'),
                        ]
                        yield event.chain_result(chain)
                    else:
                        yield event.plain_result("没有找到图。")
                except Exception as e:
                    yield event.plain_result(f"获取美图时发生错误: {e}")
        else:
            message_template, image_name, original_wait_time = random.choice(self.safe_box_messages)
            actual_wait_time = original_wait_time / self.multiplier
            minutes = round(actual_wait_time / 60)
            message = message_template.format(minutes)
            image_path = os.path.join(self.biaoqing_dir, image_name)
            
            if not os.path.exists(image_path):
                logger.warning(f"表情图片不存在: {image_path}")
                yield event.plain_result(message)
            else:
                chain = [Plain(message), Image.fromFileSystem(image_path)]
                yield event.chain_result(chain)
            
            # 记录用户等待结束时间
            self.waiting_users[user_id] = now + actual_wait_time
            asyncio.create_task(self.send_delayed_safe_box(event, actual_wait_time, user_id))

    async def send_delayed_safe_box(self, event, wait_time, user_id=None, menggong_mode=False):
        """异步生成保险箱图片，发送并记录到数据库"""
        try:
            await asyncio.sleep(wait_time)
            
            if user_id is None:
                user_id = event.get_sender_id()
            
            # 清除等待状态
            if user_id in self.waiting_users:
                del self.waiting_users[user_id]
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                await event.send(MessageChain([Plain("🎁获取用户数据失败！")]))
                return
            
            # 检查猛攻状态
            current_time = int(time.time())
            if economy_data["menggong_active"] and current_time < economy_data["menggong_end_time"]:
                menggong_mode = True
            
            loop = asyncio.get_running_loop()
            safe_image_path, placed_items = await loop.run_in_executor(
                None, generate_safe_image, menggong_mode, economy_data["grid_size"]
            )
            
            if safe_image_path and os.path.exists(safe_image_path):
                await self.add_items_to_collection(user_id, placed_items)
                
                # 计算总价值
                total_value = sum(item["item"].get("value", get_item_value(
                    os.path.splitext(os.path.basename(item["item"]["path"]))[0]
                )) for item in placed_items)
                
                message = "鼠鼠偷吃到了" if not menggong_mode else "鼠鼠猛攻获得了"
                chain = MessageChain([
                    At(qq=event.get_sender_id()),
                    Plain(f"{message}\n总价值: {total_value:,}"),
                    Image.fromFileSystem(safe_image_path),
                ])
                await event.send(chain)
            else:
                await event.send(MessageChain([Plain("🎁 图片生成失败！")]))
                
        except Exception as e:
            logger.error(f"执行偷吃代码或发送结果时出错: {e}")
            await event.send(MessageChain([Plain("🎁打开时出了点问题！")]))

    async def menggong_attack(self, event):
        """六套猛攻功能"""
        user_id = event.get_sender_id()
        
        try:
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("获取用户数据失败！")
                return
            
            # 检查仓库价值是否足够
            if economy_data["warehouse_value"] < 3000000:
                yield event.plain_result(f"哈夫币不足！当前: {economy_data['warehouse_value']:,}，需要: 3,000,000")
                return
            
            # 检查是否已经在猛攻状态
            current_time = int(time.time())
            if economy_data["menggong_active"] and current_time < economy_data["menggong_end_time"]:
                remaining_time = economy_data["menggong_end_time"] - current_time
                yield event.plain_result(f"刘涛状态进行中，剩余时间: {remaining_time // 60}分{remaining_time % 60}秒")
                return
            
            # 扣除仓库价值并激活猛攻状态
            menggong_end_time = current_time + 120  # 2分钟
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value - 3000000, menggong_active = 1, menggong_end_time = ? WHERE user_id = ?",
                    (menggong_end_time, user_id)
                )
                await db.commit()
            
            # 发送猛攻图片
            menggong_image_path = os.path.join(self.biaoqing_dir, "menggong.png")
            if os.path.exists(menggong_image_path):
                chain = [
                    At(qq=event.get_sender_id()),
                    Plain("🔥 六套猛攻激活！2分钟内提高红色和金色物品概率，不出现蓝色物品！\n消耗哈夫币: 3,000,000"),
                    Image.fromFileSystem(menggong_image_path)
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result("🔥 六套猛攻激活！2分钟内提高红色和金色物品概率，不出现蓝色物品！\n消耗哈夫币: 3,000,000")
            
            # 2分钟后自动关闭猛攻状态
            asyncio.create_task(self._disable_menggong_after_delay(user_id, 120))
            
        except Exception as e:
            logger.error(f"六套猛攻功能出错: {e}")
            yield event.plain_result("六套猛攻功能出错，请重试")

    async def _disable_menggong_after_delay(self, user_id, delay):
        """延迟关闭猛攻状态"""
        try:
            await asyncio.sleep(delay)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET menggong_active = 0, menggong_end_time = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            logger.info(f"用户 {user_id} 的猛攻状态已自动关闭")
        except Exception as e:
            logger.error(f"关闭猛攻状态时出错: {e}")

    async def upgrade_teqin(self, event):
        """特勤处升级功能"""
        user_id = event.get_sender_id()
        
        try:
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("获取用户数据失败！")
                return
            
            current_level = economy_data["teqin_level"]
            
            # 升级费用（对应0->1, 1->2, 2->3, 3->4, 4->5级的升级）
            upgrade_costs = [640000, 3200000, 25600000, 64800000, 102400000]
            
            # 等级限制检查
            if current_level >= 5:
                yield event.plain_result("特勤处已达到最高等级（5级）！")
                return
            
            # 获取升级费用
            if current_level < len(upgrade_costs):
                upgrade_cost = upgrade_costs[current_level]
            else:
                yield event.plain_result("升级费用配置错误！")
                return
            
            # 检查仓库价值是否足够
            if economy_data["warehouse_value"] < upgrade_cost:
                yield event.plain_result(f"哈夫币不足！当前价值: {economy_data['warehouse_value']:,}，升级到{current_level + 1}级需要: {upgrade_cost:,}")
                return
            
            # 执行升级
            new_level = current_level + 1
            # 计算新的格子大小：0级=2x2, 1级=3x3, 2级=4x4, 3级=5x5, 4级=6x6, 5级=7x7
            if new_level == 0:
                new_grid_size = 2
            else:
                new_grid_size = 2 + new_level
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value - ?, teqin_level = ?, grid_size = ? WHERE user_id = ?",
                    (upgrade_cost, new_level, new_grid_size, user_id)
                )
                await db.commit()
            
            yield event.plain_result(
                f"🎉 特勤处升级成功！\n"
                f"等级: {current_level} → {new_level}\n"
                f"格子大小: {economy_data['grid_size']}x{economy_data['grid_size']} → {new_grid_size}x{new_grid_size}\n"
                f"消耗价值: {upgrade_cost:,}\n"
                f"剩余价值: {economy_data['warehouse_value'] - upgrade_cost:,}"
            )
            
        except Exception as e:
            logger.error(f"特勤处升级功能出错: {e}")
            yield event.plain_result("特勤处升级功能出错，请重试")

    async def get_warehouse_info(self, event):
        """查看仓库价值和特勤处信息"""
        user_id = event.get_sender_id()
        
        try:
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("获取用户数据失败！")
                return
            
            # 检查猛攻状态
            current_time = int(time.time())
            menggong_status = ""
            if economy_data["menggong_active"] and current_time < economy_data["menggong_end_time"]:
                remaining_time = economy_data["menggong_end_time"] - current_time
                menggong_status = f"\n🔥 刘涛状态: 激活中 (剩余 {remaining_time // 60}分{remaining_time % 60}秒)"
            else:
                menggong_status = "\n🔥 刘涛状态: 未激活"
            
            # 下一级升级费用
            upgrade_costs = [640000, 3200000, 25600000, 64800000, 102400000]
            
            next_upgrade_info = ""
            if economy_data["teqin_level"] < 5:
                if economy_data["teqin_level"] < len(upgrade_costs):
                    next_cost = upgrade_costs[economy_data["teqin_level"]]
                    next_upgrade_info = f"\n📈 下级升级费用: {next_cost:,}"
                else:
                    next_upgrade_info = "\n📈 升级费用配置错误"
            else:
                next_upgrade_info = "\n📈 已达最高等级"
            
            info_text = (
                f"💰 哈夫币: {economy_data['warehouse_value']:,}\n"
                f"🔺 三角币: {economy_data.get('triangle_coins', 0)}\n"
                f"🏢 特勤处等级: {economy_data['teqin_level']}级\n"
                f"📦 格子大小: {economy_data['grid_size']}x{economy_data['grid_size']}"
                f"{next_upgrade_info}"
                f"{menggong_status}"
            )
            
            yield event.plain_result(info_text)
            
        except Exception as e:
            logger.error(f"查看仓库信息功能出错: {e}")
            yield event.plain_result("查看仓库信息功能出错，请重试")

    async def get_leaderboard(self, event):
        """获取图鉴数量榜和仓库价值榜前五位"""
        try:
            # 获取群ID
            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result("此功能仅支持群聊使用")
                return
            
            # 获取群成员昵称映射
            nickname_map = await self._get_group_member_nicknames(event, group_id)
            
            async with aiosqlite.connect(self.db_path) as db:
                # 图鉴数量榜
                cursor = await db.execute("""
                    SELECT user_id, COUNT(*) as item_count
                    FROM user_touchi_collection
                    GROUP BY user_id
                    ORDER BY item_count DESC
                    LIMIT 5
                """)
                collection_top = await cursor.fetchall()
                
                # 仓库价值榜
                cursor = await db.execute("""
                    SELECT user_id, warehouse_value
                    FROM user_economy
                    WHERE warehouse_value > 0
                    ORDER BY warehouse_value DESC
                    LIMIT 5
                """)
                warehouse_top = await cursor.fetchall()
                
                # 构建排行榜消息
                message = "🏆 鼠鼠榜 🏆\n\n"
                
                # 图鉴数量榜
                message += "📚 图鉴数量榜 TOP5:\n"
                for i, (user_id, count) in enumerate(collection_top, 1):
                    nickname = nickname_map.get(user_id, f"用户{user_id[:6]}")
                    message += f"{i}. {nickname} - {count}个物品\n"
                
                message += "\n💰 仓库价值榜 TOP5:\n"
                for i, (user_id, value) in enumerate(warehouse_top, 1):
                    nickname = nickname_map.get(user_id, f"用户{user_id[:6]}")
                    message += f"{i}. {nickname} - {value}哈夫币\n"
                
                yield event.plain_result(message)
                
        except Exception as e:
            logger.error(f"获取排行榜时出错: {str(e)}")
            yield event.plain_result("获取排行榜失败，请稍后再试")

    async def start_auto_touchi(self, event):
        """开启自动偷吃功能"""
        user_id = event.get_sender_id()
        
        try:
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("获取用户数据失败！")
                return
            
            # 检查是否已经在自动偷吃状态
            if economy_data["auto_touchi_active"]:
                start_time = economy_data["auto_touchi_start_time"]
                elapsed_time = int(time.time()) - start_time
                yield event.plain_result(f"自动偷吃已经在进行中，已运行 {elapsed_time // 60}分{elapsed_time % 60}秒")
                return
            
            # 开启自动偷吃
            current_time = int(time.time())
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET auto_touchi_active = 1, auto_touchi_start_time = ? WHERE user_id = ?",
                    (current_time, user_id)
                )
                await db.commit()
            
            # 初始化自动偷吃数据
            self.auto_touchi_data[user_id] = {
                "red_items_count": 0,
                "start_time": current_time
            }
            
            # 启动自动偷吃任务
            task = asyncio.create_task(self._auto_touchi_loop(user_id, event))
            self.auto_touchi_tasks[user_id] = task
            
            # 计算实际间隔时间
            actual_interval = 600 / self.multiplier  # 基础10分钟除以倍率
            interval_minutes = round(actual_interval / 60, 1)
            
            yield event.plain_result(f"🤖 自动偷吃已开启！\n⏰ 每{interval_minutes}分钟自动偷吃\n🎯 金红概率降低\n📊 只记录数据，不输出图片\n⏱️ 4小时后自动停止")
            
        except Exception as e:
            logger.error(f"开启自动偷吃时出错: {e}")
            yield event.plain_result("开启自动偷吃失败，请重试")

    async def stop_auto_touchi(self, event):
        """关闭自动偷吃功能"""
        user_id = event.get_sender_id()
        
        try:
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("获取用户数据失败！")
                return
            
            # 检查是否在自动偷吃状态
            if not economy_data["auto_touchi_active"]:
                yield event.plain_result("自动偷吃未开启")
                return
            
            result_text = await self._stop_auto_touchi_internal(user_id)
            yield event.plain_result(result_text)
            
        except Exception as e:
            logger.error(f"关闭自动偷吃时出错: {e}")
            yield event.plain_result("关闭自动偷吃失败，请重试")
    
    async def _stop_auto_touchi_internal(self, user_id):
        """内部停止自动偷吃方法"""
        try:
            # 停止自动偷吃任务
            if user_id in self.auto_touchi_tasks:
                self.auto_touchi_tasks[user_id].cancel()
                del self.auto_touchi_tasks[user_id]
            
            # 更新数据库状态
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET auto_touchi_active = 0, auto_touchi_start_time = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            
            # 统计结果
            auto_data = self.auto_touchi_data.get(user_id, {})
            red_count = auto_data.get("red_items_count", 0)
            start_time = auto_data.get("start_time", int(time.time()))
            duration = int(time.time()) - start_time
            
            # 清理数据
            if user_id in self.auto_touchi_data:
                del self.auto_touchi_data[user_id]
            
            result_text = (
                f"🛑 自动偷吃已关闭\n"
                f"⏱️ 运行时长: {duration // 60}分{duration % 60}秒\n"
                f"🔴 获得红色物品数量: {red_count}个"
            )
            
            return result_text
            
        except Exception as e:
            logger.error(f"内部停止自动偷吃时出错: {e}")
            return "关闭自动偷吃失败，请重试"

    async def _auto_touchi_loop(self, user_id, event):
        """自动偷吃循环任务"""
        try:
            start_time = time.time()
            max_duration = 4 * 3600  # 4小时 = 14400秒
            base_interval = 600  # 基础间隔10分钟 = 600秒
            interval = base_interval / self.multiplier  # 应用冷却倍率
            
            while True:
                # 检查是否超过4小时
                if time.time() - start_time >= max_duration:
                    logger.info(f"用户 {user_id} 的自动偷吃已运行4小时，自动停止")
                    await self._stop_auto_touchi_internal(user_id)
                    try:
                        await event.send(MessageChain([Plain("🛑 自动偷吃已运行4小时，自动停止")]))
                    except:
                        pass  # 发送失败不影响停止逻辑
                    break
                
                await asyncio.sleep(interval)
                
                # 检查用户是否还在自动偷吃状态
                economy_data = await self.get_user_economy_data(user_id)
                if not economy_data or not economy_data["auto_touchi_active"]:
                    break
                
                # 执行自动偷吃
                await self._perform_auto_touchi(user_id, economy_data)
                
        except asyncio.CancelledError:
            logger.info(f"用户 {user_id} 的自动偷吃任务被取消")
        except Exception as e:
            logger.error(f"自动偷吃循环出错: {e}")

    async def _perform_auto_touchi(self, user_id, economy_data):
        """执行一次自动偷吃"""
        try:
            from .touchi import load_items, create_safe_layout
            
            # 加载物品
            items = load_items()
            if not items:
                return
            
            # 检查猛攻状态
            current_time = int(time.time())
            menggong_mode = economy_data["menggong_active"] and current_time < economy_data["menggong_end_time"]
            
            # 创建保险箱布局（自动模式下概率调整）
            placed_items, _, _, _, _ = create_safe_layout(items, menggong_mode, economy_data["grid_size"], auto_mode=True)
            
            if placed_items:
                # 记录到数据库
                await self.add_items_to_collection(user_id, placed_items)
                
                # 统计红色物品
                red_items = [item for item in placed_items if item["item"]["level"] == "red"]
                if user_id in self.auto_touchi_data:
                    self.auto_touchi_data[user_id]["red_items_count"] += len(red_items)
                
                logger.info(f"用户 {user_id} 自动偷吃获得 {len(placed_items)} 个物品，其中红色 {len(red_items)} 个")
                
        except Exception as e:
            logger.error(f"执行自动偷吃时出错: {e}")
    
    async def set_base_teqin_level(self, level: int):
        """设置特勤处基础等级"""
        try:
            # 计算对应的grid_size
            if level == 0:
                grid_size = 2  # 0级对应2x2
            else:
                grid_size = 2 + level  # 1级=3x3, 2级=4x4, 3级=5x5, 4级=6x6, 5级=7x7
            
            async with aiosqlite.connect(self.db_path) as db:
                # 更新系统配置
                await db.execute(
                    "UPDATE system_config SET config_value = ? WHERE config_key = 'base_teqin_level'",
                    (str(level),)
                )
                
                await db.commit()
                
                # 获取当前用户数量
                cursor = await db.execute("SELECT COUNT(*) FROM user_economy")
                user_count = (await cursor.fetchone())[0]
            
            return (
                f"✅ 特勤处基础等级设置成功！\n"
                f"基础等级: {level}级\n"
                f"对应格子大小: {grid_size}x{grid_size}\n"
                f"此设置将影响新注册的用户\n"
                f"当前已有 {user_count} 个用户（不受影响）"
            )
            
        except Exception as e:
            logger.error(f"设置特勤处基础等级时出错: {e}")
            return "设置特勤处基础等级失败，请重试"
    
    async def mandel_online_match(self, event):
        """曼德尔online匹配功能（本地优先，2分钟后P2P）"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        
        if not group_id:
            yield event.plain_result("❌ 此功能仅支持群聊使用")
            return
        
        try:
            # 检查用户经济数据
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("❌ 获取用户数据失败")
                return
            
            # 检查哈夫币是否足够
            if economy_data["warehouse_value"] < 2000000:
                yield event.plain_result(f"❌ 哈夫币不足！需要200万，当前：{economy_data['warehouse_value']:,}")
                return
            
            # 首先尝试本地匹配
            try:
                async for result in self._try_local_match(user_id, group_id, event):
                    yield result
                # 如果本地匹配成功完成，直接返回
                return
            except Exception as e:
                if str(e) == "SWITCH_TO_P2P":
                    # 本地匹配失败，继续P2P匹配
                    pass
                else:
                    # 其他错误，重新抛出
                    raise
            
            # 本地匹配失败，尝试P2P匹配
            if not self.p2p_manager or not self.p2p_port:
                yield event.plain_result("❌ 本地玩家不足且P2P网络未启动，无法进行匹配")
                return
            
            # 扣除哈夫币
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value - 2000000 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            
            # 发送P2P匹配请求
            request_id = await self.p2p_manager.request_match(user_id)
            
            # 获取网络状态
            network_status = self.p2p_manager.get_network_status()
            
            yield event.plain_result(
                f"🌐 P2P匹配请求已发送\n"
                f"🔗 节点ID: {network_status['node_id'][:8]}...\n"
                f"🌍 连接节点: {network_status['peers_count']}个\n"
                f"⏳ 队列中: {network_status['pending_matches']}/3人\n"
                f"🎮 活跃游戏: {network_status['active_sessions']}场\n\n"
                f"💰 已扣除200万哈夫币\n"
                f"⏰ 等待其他玩家加入P2P网络..."
            )
            
        except Exception as e:
            logger.error(f"曼德尔online匹配出错: {e}")
            # 如果出错，退还哈夫币
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE user_economy SET warehouse_value = warehouse_value + 2000000 WHERE user_id = ?",
                        (user_id,)
                    )
                    await db.commit()
            except:
                pass
            yield event.plain_result("❌ 匹配失败，已退还哈夫币")
    
    async def _try_local_match(self, user_id, group_id, event):
        """尝试本地匹配，2分钟超时"""
        try:
            # 初始化本地匹配队列
            if not hasattr(self, 'local_match_queue'):
                self.local_match_queue = {}
            
            if group_id not in self.local_match_queue:
                self.local_match_queue[group_id] = []
            
            queue = self.local_match_queue[group_id]
            
            # 检查用户是否已在队列中
            if user_id in [player['user_id'] for player in queue]:
                yield event.plain_result("❌ 您已在本地匹配队列中，请等待其他玩家")
                return
            
            # 扣除哈夫币
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value - 2000000 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            
            # 添加玩家到队列
            queue.append({
                'user_id': user_id,
                'join_time': time.time(),
                'event': event
            })
            
            yield event.plain_result(
                f"🏠 已加入本地匹配队列\n"
                f"👥 当前队列: {len(queue)}/3人\n"
                f"💰 已扣除200万哈夫币\n"
                f"⏰ 等待其他本地玩家加入...\n"
                f"⌛ 2分钟后自动切换P2P匹配"
            )
            
            # 检查是否有足够玩家开始游戏
            if len(queue) >= 3:
                players = queue[:3]
                self.local_match_queue[group_id] = queue[3:]
                
                # 通知玩家游戏开始
                yield event.plain_result(
                    f"🎮 本地匹配成功！\n"
                    f"👥 玩家: {len(players)}人\n"
                    f"⏰ 游戏时长: 1分钟\n"
                    f"🏆 获胜者将获得3300三角币\n\n"
                    f"游戏即将开始..."
                )
                
                # 启动本地游戏
                asyncio.create_task(self._start_local_mandel_game(players, group_id, event))
                return
            
            # 等待2分钟
            await asyncio.sleep(120)
            
            # 检查用户是否还在队列中
            current_queue = self.local_match_queue.get(group_id, [])
            user_in_queue = any(p['user_id'] == user_id for p in current_queue)
            
            if user_in_queue:
                # 从队列中移除用户
                self.local_match_queue[group_id] = [p for p in current_queue if p['user_id'] != user_id]
                yield event.plain_result("⏰ 本地匹配超时，正在切换到P2P匹配...")
                # 这里需要特殊处理，因为需要告诉调用者切换到P2P匹配
                # 我们通过抛出一个特殊异常来处理
                raise Exception("SWITCH_TO_P2P")
            
            # 用户已经匹配成功或离开队列
            return
            
        except Exception as e:
            if str(e) == "SWITCH_TO_P2P":
                # 这是切换到P2P匹配的信号，重新抛出
                raise
            logger.error(f"本地匹配出错: {e}")
            # 退还哈夫币
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE user_economy SET warehouse_value = warehouse_value + 2000000 WHERE user_id = ?",
                        (user_id,)
                    )
                    await db.commit()
            except:
                pass
            return
    
    async def _start_local_mandel_game(self, players, group_id, event):
        """开始本地曼德尔游戏"""
        try:
            # 等待1分钟
            await asyncio.sleep(60)
            
            # 随机选择2个获胜者和1个失败者
            winners = random.sample(players, 2)
            loser = [p for p in players if p not in winners][0]
            
            # 更新获胜者的三角币
            async with aiosqlite.connect(self.db_path) as db:
                for winner in winners:
                    await db.execute(
                        "UPDATE user_economy SET triangle_coins = triangle_coins + 3300 WHERE user_id = ?",
                        (winner['user_id'],)
                    )
                await db.commit()
            
            # 构建游戏结果消息
            result_message = (
                f"🎮 本地曼德尔游戏结束！\n\n"
                f"🏆 获胜者:\n"
            )
            
            for winner in winners:
                result_message += f"👤 {winner['user_id']} (+3300三角币)\n"
            
            result_message += f"\n💀 失败者:\n👤 {loser['user_id']}\n\n🎊 恭喜获胜者！"
            
            # 发送游戏结果到群聊
            await event.send(MessageChain([Plain(result_message)]))
            
            logger.info(f"本地曼德尔游戏结束: {result_message}")
                    
        except Exception as e:
             logger.error(f"本地曼德尔游戏出错: {e}")
     
    
    async def _start_mandel_game(self, match_id, players, event):
        """开始曼德尔游戏"""
        try:
            # 等待1分钟
            await asyncio.sleep(60)
            
            # 随机选择2个获胜者和1个失败者
            winners = random.sample(players, 2)
            losers = [p for p in players if p not in winners]
            
            async with aiosqlite.connect(self.db_path) as db:
                # 给获胜者发放三角币
                for winner_id in winners:
                    await db.execute(
                        "UPDATE user_economy SET triangle_coins = triangle_coins + 3300 WHERE user_id = ?",
                        (winner_id,)
                    )
                
                # 更新匹配状态
                await db.execute(
                    "UPDATE mandel_matches SET status = 'finished', end_time = ? WHERE match_id = ?",
                    (time.time(), match_id)
                )
                await db.commit()
            
            # 获取群成员昵称
            group_id = event.get_group_id()
            nickname_map = await self._get_group_member_nicknames(event, group_id)
            
            # 构建结果消息
            result_msg = "🎮 曼德尔online游戏结束！\n\n🏆 获胜者：\n"
            for winner_id in winners:
                nickname = nickname_map.get(winner_id, f"用户{winner_id[:6]}")
                reward = random.randint(300, 500)  # 重新生成用于显示
                result_msg += f"• {nickname} (+{reward}三角币)\n"
            
            result_msg += "\n💀 失败者：\n"
            for loser_id in losers:
                nickname = nickname_map.get(loser_id, f"用户{loser_id[:6]}")
                result_msg += f"• {nickname} (无奖励)\n"
            
            # 发送结果（这里需要通过bot发送到群聊）
            logger.info(f"曼德尔游戏 {match_id} 结束: {result_msg}")
            
        except Exception as e:
            logger.error(f"曼德尔游戏执行出错: {e}")
    
    async def draw_red_card(self, event):
        """抽卡功能"""
        user_id = event.get_sender_id()
        
        try:
            # 检查用户经济数据
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("❌ 获取用户数据失败")
                return
            
            # 检查三角币是否足够
            if economy_data["triangle_coins"] < 1100:
                yield event.plain_result(f"❌ 三角币不足！需要1100，当前：{economy_data['triangle_coins']}")
                return
            
            # 扣除三角币
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET triangle_coins = triangle_coins - 1100 WHERE user_id = ?",
                    (user_id,)
                )
                
                # 抽卡逻辑（6%概率）
                if random.random() < 0.06:  # 6%概率
                    # 抽中红皮
                    await db.execute(
                        "INSERT OR IGNORE INTO user_touchi_collection (user_id, item_name, item_level) VALUES (?, ?, ?)",
                        (user_id, "hongpi_mai1", "hongpi")
                    )
                    await db.commit()
                    
                    # 返回红皮图片
                    hongpi_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hongpi", "hongpi_mai1.jpg")
                    if os.path.exists(hongpi_path):
                        yield event.image_result(hongpi_path)
                        yield event.plain_result("🎉 恭喜！抽中红皮！")
                    else:
                        yield event.plain_result("🎉 恭喜！抽中红皮！（图片文件缺失）")
                else:
                    # 没抽中
                    await db.commit()
                    yield event.plain_result("💔 很遗憾，没有抽中红皮，再试试吧！")
                
        except Exception as e:
             logger.error(f"抽卡功能出错: {e}")
             yield event.plain_result("❌ 抽卡失败，请重试")
    
    async def mandel_p2p_direct(self, event):
        """曼德尔P2P直连匹配（跳过本地匹配，直接P2P，但兼容本地玩家）"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        
        if not group_id:
            yield event.plain_result("❌ 此功能仅支持群聊使用")
            return
        
        try:
            # 检查用户经济数据
            economy_data = await self.get_user_economy_data(user_id)
            if not economy_data:
                yield event.plain_result("❌ 获取用户数据失败")
                return
            
            # 检查哈夫币是否足够
            if economy_data["warehouse_value"] < 2000000:
                yield event.plain_result(f"❌ 哈夫币不足！需要200万，当前：{economy_data['warehouse_value']:,}")
                return
            
            # 检查P2P网络状态
            if not self.p2p_manager or not self.p2p_port:
                yield event.plain_result("❌ P2P网络未启动，无法进行P2P匹配")
                return
            
            # 扣除哈夫币
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE user_economy SET warehouse_value = warehouse_value - 2000000 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            
            # 同时将用户加入本地队列（兼容本地玩家）
            if not hasattr(self, 'local_match_queue'):
                self.local_match_queue = {}
            
            if group_id not in self.local_match_queue:
                self.local_match_queue[group_id] = []
            
            queue = self.local_match_queue[group_id]
            
            # 检查用户是否已在队列中
            if user_id not in [player['user_id'] for player in queue]:
                queue.append({
                    'user_id': user_id,
                    'join_time': time.time(),
                    'event': event
                })
            
            # 检查本地队列是否已满3人
            if len(queue) >= 3:
                # 本地队列满员，直接开始本地游戏
                players = queue[:3]
                self.local_match_queue[group_id] = queue[3:]  # 移除已匹配的玩家
                
                yield event.plain_result(
                    f"🎮 本地队列已满3人，直接开始本地游戏！\n"
                    f"👥 参与玩家: {len(players)}人\n"
                    f"🎯 游戏即将开始..."
                )
                
                # 启动本地游戏
                asyncio.create_task(self._start_local_mandel_game(players, group_id, event))
                return
            
            # 发送P2P匹配请求
            request_id = await self.p2p_manager.request_match(user_id)
            
            # 获取网络状态
            network_status = self.p2p_manager.get_network_status()
            
            yield event.plain_result(
                f"🌐 P2P直连匹配已启动\n"
                f"🔗 节点ID: {network_status['node_id'][:8]}...\n"
                f"🌍 连接节点: {network_status['peers_count']}个\n"
                f"⏳ P2P队列: {network_status['pending_matches']}/3人\n"
                f"👥 本地队列: {len(queue)}/3人\n"
                f"🎮 活跃游戏: {network_status['active_sessions']}场\n\n"
                f"💰 已扣除200万哈夫币\n"
                f"🔄 同时兼容本地和P2P玩家匹配\n"
                f"⏰ 等待其他玩家加入..."
            )
            
        except Exception as e:
            logger.error(f"曼德尔P2P直连匹配出错: {e}")
            # 如果出错，退还哈夫币
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE user_economy SET warehouse_value = warehouse_value + 2000000 WHERE user_id = ?",
                        (user_id,)
                    )
                    await db.commit()
            except:
                pass
            yield event.plain_result("❌ P2P匹配失败，已退还哈夫币")

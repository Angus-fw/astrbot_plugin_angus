import psutil
import time
import asyncio
import platform
import datetime

class ServerStatusTools:
    def __init__(self, enable_server_status=True):
        self.enable_server_status = enable_server_status

    async def get_zt(self):
        if not self.enable_server_status:
            return "服务器状态功能已关闭"
        cpu_usage = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        sys_info = (f"CPU使用: {cpu_usage}%\n"
                    f"内存使用: {memory_info.percent}%")
        return sys_info

    async def get_status(self):
        if not self.enable_server_status:
            return "服务器状态功能已关闭"
        cpu_usage_str = self._get_average_cpu_usage(samples=3, interval=0.2)
        memory_usage_str = await self._get_memory_usage()
        disk_usage_str = self._get_disk_usage("/")
        net_info = psutil.net_io_counters()
        process_count = len(psutil.pids())
        net_connections = len(psutil.net_connections())
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        now = datetime.datetime.now()
        uptime = now - boot_time
        sys_info = (
            f"系统状态：\n"
            f"CPU占用: {cpu_usage_str}\n"
            f"内存占用: {memory_usage_str}\n"
            f"磁盘占用: {disk_usage_str}\n"
            f"系统运行时间: {str(uptime).split('.')[0]}\n"
            f"网络发送: {self._convert_to_readable(net_info.bytes_sent)}\n"
            f"网络接收: {self._convert_to_readable(net_info.bytes_recv)}\n"
            f"进程数量: {process_count}\n"
            f"连接数量: {net_connections}"
        )
        return sys_info

    def _convert_to_readable(self, value):
        units = ["B", "KB", "MB", "GB"]
        unit_index = min(len(units) - 1, int(value > 0 and (value.bit_length() - 1) / 10))
        return f"{value / (1024**unit_index):.2f} {units[unit_index]}"

    async def _get_memory_usage(self):
        memory_info = psutil.virtual_memory()
        used_memory_gb = memory_info.used / (1024**3)
        total_memory_gb = memory_info.total / (1024**3)
        return f"{used_memory_gb:.2f}G/{total_memory_gb:.1f}G"

    def _get_average_cpu_usage(self, samples=5, interval=0.5):
        total_usage = 0
        for _ in range(samples):
            cpu_usage = psutil.cpu_percent(interval=interval)
            total_usage += cpu_usage
            time.sleep(interval)
        average_usage = total_usage / samples
        return f"{average_usage:.2f}%"

    def _get_disk_usage(self, path="/"):
        disk_info = psutil.disk_usage(path)
        used_disk_gb = disk_info.used / (1024**3)
        total_disk_gb = disk_info.total / (1024**3)
        return f"{used_disk_gb:.2f}G/{total_disk_gb:.1f}G" 
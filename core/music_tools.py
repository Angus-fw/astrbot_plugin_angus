import urllib.parse
import httpx


class MusicTools:
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    async def _fetch_json(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=False) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return {}

    async def search_songs(self, keyword: str, page: int = 1, pagesize: int = 10) -> list:
        encoded = urllib.parse.quote(keyword)
        url = (
            f"https://mobiles.kugou.com/api/v3/search/song?format=json&keyword={encoded}"
            f"&page={page}&pagesize={pagesize}&showtype=1"
        )
        data = await self._fetch_json(url)
        return (data.get("data", {}) or {}).get("info", []) or []

    async def get_song_info_by_hash(self, song_hash: str) -> dict:
        url = f"https://m.kugou.com/app/i/getSongInfo.php?hash={song_hash}&cmd=playInfo"
        return await self._fetch_json(url)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        seconds = seconds or 0
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    async def build_song_selection_text(self, keyword: str, songs: list) -> str:
        if not songs:
            return f"未找到与“{keyword}”相关的歌曲。"
        lines = [f"为“{keyword}”找到以下结果（回复 /si 音乐 {keyword} 序号 选择）："]
        for i, s in enumerate(songs, start=1):
            duration = self._format_duration(s.get("duration", 0))
            filename = s.get("filename", "")
            lines.append(f"{i}. {filename} | 时长 {duration}")
        return "\n".join(lines)

    async def get_song_result_text(self, keyword: str, index: int) -> str:
        songs = await self.search_songs(keyword, page=1, pagesize=10)
        if not songs:
            return f"未找到与“{keyword}”相关的歌曲。"
        if index < 1 or index > len(songs):
            return f"序号超出范围（1-{len(songs)}）。可先不带序号查询以查看列表。"

        chosen = songs[index - 1]
        song_hash = chosen.get("hash", "")
        filename = chosen.get("filename", "")
        singername = chosen.get("singername", "")
        duration = self._format_duration(chosen.get("duration", 0))

        link = ""
        size_mb = ""
        cover = ""
        if song_hash:
            info = await self.get_song_info_by_hash(song_hash)
            link = info.get("url", "") or "（可能为付费或暂不可获取）"
            file_size = (info or {}).get("fileSize", 0)
            size_mb = f"{round((file_size or 0)/(1024*1024), 2)} MB" if file_size else ""
            cover = (info or {}).get("album_img", "").replace("/{size}", "")

        parts = [
            f"已为你选中第{index}首：{filename}",
            f"歌手：{singername}",
            f"时长：{duration}",
        ]
        if size_mb:
            parts.append(f"大小：{size_mb}")
        if cover:
            parts.append(f"封面：{cover}")
        parts.append(f"直链：{link}")
        return "\n".join(parts)



import sqlite3
from PySide6.QtCore import QThread, Signal
from src.core.steam_integration import SteamIntegration

class DataLoader(QThread):
    """Background thread to load games, platforms, and categories/tags.

    Emits: data_loaded(games: list, platforms: list[str], categories: list[str])
    """
    data_loaded = Signal(list, list, list)

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path

    def run(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                """
                SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
                FROM games g
                LEFT JOIN game_tags gt ON g.id = gt.game_id
                LEFT JOIN tags t ON gt.tag_id = t.id
                GROUP BY g.id
                ORDER BY g.date_added DESC
                """
            )
            games = [dict(row) for row in cur.fetchall()]

            plats = ['All Platforms']
            cur.execute("SELECT DISTINCT platform_type FROM games ORDER BY platform_type")
            plats.extend([row[0] for row in cur.fetchall()])

            cats = ['All Categories']
            # Only get tags that are actually in use (assigned to at least one game)
            cur.execute("""
                SELECT DISTINCT t.* FROM tags t
                INNER JOIN game_tags gt ON t.id = gt.tag_id
                ORDER BY t.name
            """)
            tags = [dict(row) for row in cur.fetchall()]
            platform_names = [p for p in plats if p != 'All Platforms']
            
            # Get ignored tags set (Steam platform features)
            ignored_tags = SteamIntegration.IGNORED_TAGS
            
            # Filter out platform names and ignored Steam feature tags
            cats.extend([
                tag['name'] for tag in tags 
                if tag['name'] not in platform_names 
                and tag['name'].lower() not in ignored_tags
            ])
        except Exception:
            games, plats, cats = [], ['All Platforms'], ['All Categories']
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        self.data_loaded.emit(games, plats, cats)

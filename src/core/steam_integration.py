"""
Steam Integration Module for SteamKM2

Provides functionality to:
- Search for Steam games by title
- Fetch AppID, tags, and cover images
- Cache fetched data to reduce API calls
- Background threaded fetching for non-blocking UI
"""

from __future__ import annotations

import os
import json
import re
import time
import threading
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote

# Optional Qt imports for threaded operations
try:
    from PySide6.QtCore import QThread, Signal, QObject
    HAS_QT = True
except ImportError:
    HAS_QT = False

# Debug mode - set to True for verbose logging
DEBUG = True

def _log(msg: str):
    """Print debug message if DEBUG is enabled."""
    if DEBUG:
        print(f"[Steam] {msg}")


def _parse_tags_string(tags_str: Optional[str]) -> List[str]:
    """Parse comma-separated tags string into a list."""
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(',') if t.strip()]


# Base worker class to reduce duplication
class _BaseWorker(QObject if HAS_QT else object):
    """Base class for Steam background workers with common signal patterns."""
    if HAS_QT:
        finished = Signal(dict)
        error = Signal(str)
        progress = Signal(str)
    
    def __init__(self, steam_integration):
        if HAS_QT:
            super().__init__()
        self.steam = steam_integration
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the operation."""
        self._cancelled = True
    
    def _emit(self, signal_name: str, *args):
        """Emit a signal if Qt is available."""
        if HAS_QT and hasattr(self, signal_name):
            getattr(self, signal_name).emit(*args)
    
    def _run_safe(self, operation):
        """Run an operation with error handling."""
        try:
            self._emit('finished', operation())
        except Exception as e:
            _log(f"Worker error: {e}")
            self._emit('error', str(e))


class SteamFetchWorker(_BaseWorker):
    """Worker for background Steam data fetching (single game)."""
    
    def __init__(self, steam_integration, title: str, **kwargs):
        super().__init__(steam_integration)
        self.title = title
        self.opts = kwargs  # current_app_id, current_tags, current_image_path, fetch_*, force_tags, custom_tags
    
    def run(self):
        """Execute the fetch operation."""
        self._emit('progress', f"Fetching Steam data for '{self.title}'...")
        self._run_safe(lambda: self.steam.fetch_missing_data(title=self.title, **self.opts))


class SteamBatchFetchWorker(_BaseWorker):
    """Worker for background Steam data fetching (multiple games)."""
    
    if HAS_QT:
        progress = Signal(str, int, int)  # Override with counts
        games_updated = Signal(list)      # Batch update signal
    
    def __init__(self, steam_integration, games: List[dict], reviews_only: bool = False, **kwargs):
        super().__init__(steam_integration)
        self.games = games
        self.reviews_only = reviews_only
        self.opts = kwargs  # fetch_appid, fetch_tags, fetch_image, fetch_reviews, force_tags, custom_tags
    
    def run(self):
        """Execute batch fetch: cached first, then network (single thread)."""
        try:
            total = len(self.games)
            to_fetch = []
            processed_count = 0
            fetched_count = 0
            failed_count = 0
            failed_titles = []
            
            batch_buffer = []
            BATCH_SIZE = 20  # Update UI every 20 cached games
            
            # 1. Process cached games immediately
            for i, game in enumerate(self.games):
                if self._cancelled:
                    break
                
                title = game.get('title', 'Unknown')
                
                try:
                    # Check if needs fetch
                    if self.opts.get('force_fresh_search') or self.opts.get('force_image'):
                        needs_fetch = True
                    else:
                        needs_fetch = self.steam.check_needs_fetch(
                            title=title, current_app_id=game.get('steam_app_id'),
                            current_tags=_parse_tags_string(game.get('tags')),
                            current_image_path=game.get('image_path'),
                            reviews_only=self.reviews_only, **{k: v for k, v in self.opts.items() if k.startswith('fetch_') or k == 'force_tags'}
                        )
                    
                    if not needs_fetch:
                        # It is cached, process
                        processed_count += 1
                        self._emit('progress', title, processed_count, total)
                        
                        result = self._process_game(game, title, True) # from_cache=True
                        result.update({'game': game, 'success': any(result.get('fetched', {}).values()), 'from_cache': True})
                        
                        if result['success']:
                            batch_buffer.append(result)
                            if len(batch_buffer) >= BATCH_SIZE:
                                self._emit('games_updated', list(batch_buffer))
                                batch_buffer.clear()
                    else:
                        # Needs network, save for later (preserve order)
                        to_fetch.append(game)
                        
                except Exception as e:
                    _log(f"Error checking/processing {title}: {e}")
                    to_fetch.append(game)

            # Flush remaining cached updates
            if batch_buffer:
                self._emit('games_updated', list(batch_buffer))
                batch_buffer.clear()

            # 2. Process network games one by one
            for game in to_fetch:
                if self._cancelled:
                    break
                    
                title = game.get('title', 'Unknown')
                processed_count += 1
                self._emit('progress', title, processed_count, total)
                
                try:
                    result = self._process_game(game, title, False) # from_cache=False
                    result.update({'game': game, 'success': any(result.get('fetched', {}).values()), 'from_cache': False})
                    
                    if result['success']:
                        fetched_count += 1
                        # Emit immediately for network fetches (they are slow enough)
                        self._emit('games_updated', [result])
                except Exception as e:
                    _log(f"Failed to fetch {title}: {e}")
                    failed_count += 1
                    failed_titles.append(title)
            
            self._emit('finished', {
                'results': [], 
                'fetched_count': fetched_count, 
                'failed_count': failed_count,
                'failed_titles': failed_titles, 
                'total': total, 
                'cancelled': self._cancelled,
                'cached_count': total - len(to_fetch), 
                'network_count': len(to_fetch)
            })

        except Exception as e:
            _log(f"Batch worker error: {e}")
            self._emit('error', str(e))

    def _process_batch_queue(self, games_with_indices: List[tuple], is_cached_batch: bool, total_games: int, q: Any) -> dict:
        """Deprecated."""
        return {}

    def _process_batch(self, games_with_indices: List[tuple], is_cached_batch: bool, total_games: int) -> dict:
        """Deprecated."""
        return {}

    
    def _process_game(self, game: dict, title: str, from_cache: bool) -> dict:
        """Process a single game."""
        app_id = game.get('steam_app_id')
        tags = _parse_tags_string(game.get('tags'))
        image = game.get('image_path')
        is_dlc = game.get('dlc_enabled', False)
        
        if from_cache:
            # Filter out arguments not supported by fetch_from_cache_only
            # fetch_from_cache_only does not support force_fresh_search or force_image
            cache_opts = {k: v for k, v in self.opts.items() 
                         if k in ('fetch_appid', 'fetch_tags', 'fetch_image', 'fetch_reviews', 'force_tags', 'custom_tags')}
            return self.steam.fetch_from_cache_only(title=title, current_app_id=app_id, current_tags=tags, current_image_path=image, current_is_dlc=is_dlc, **cache_opts)
        
        if self.reviews_only:
            if not app_id:
                app_id = self.steam.search_app_id(title)
                if not app_id:
                    raise ValueError(f"Could not find AppID for {title}")
            return self.steam.fetch_missing_data(title=title, current_app_id=app_id, current_is_dlc=is_dlc, fetch_appid=False, fetch_tags=False, fetch_image=False, fetch_reviews=True)
        
        return self.steam.fetch_missing_data(
            title=title, current_app_id=app_id, current_tags=tags, current_image_path=image, current_is_dlc=is_dlc,
            fetch_appid=self.opts.get('fetch_appid', True) and not app_id,
            fetch_tags=self.opts.get('fetch_tags', True), 
            fetch_image=self.opts.get('fetch_image', True) and not (image and os.path.exists(image)),
            fetch_reviews=self.opts.get('fetch_reviews', True), 
            force_tags=self.opts.get('force_tags', False), 
            custom_tags=self.opts.get('custom_tags'),
            force_fresh_search=self.opts.get('force_fresh_search', False),
            force_image=self.opts.get('force_image', False)
        )


class SteamCacheRefreshWorker(_BaseWorker):
    """Worker for background Steam cache refresh (force fetch fresh data)."""
    
    def __init__(self, steam_integration, app_id: str, title: Optional[str] = None, custom_tags: Optional[List[str]] = None):
        super().__init__(steam_integration)
        self.app_id, self.title, self.custom_tags = app_id, title, custom_tags
    
    def run(self):
        self._emit('progress', f"Refreshing cache for AppID {self.app_id}...")
        self._run_safe(lambda: self.steam.force_refresh_cache(app_id=self.app_id, title=self.title, custom_tags=self.custom_tags))


class SteamBatchCacheRefreshWorker(_BaseWorker):
    """Worker for background Steam cache refresh for multiple games (deduplicates by AppID)."""
    
    if HAS_QT:
        progress = Signal(str, int, int)
        game_refreshed = Signal(dict)
    
    def __init__(self, steam_integration, games: List[dict], custom_tags: Optional[List[str]] = None):
        super().__init__(steam_integration)
        self.games, self.custom_tags = games, custom_tags
    
    def run(self):
        try:
            # Deduplicate by AppID
            appid_map = {}
            for g in self.games:
                if app_id := g.get('steam_app_id'):
                    appid_map.setdefault(app_id, []).append(g)
            
            unique, total = list(appid_map.keys()), len(appid_map)
            _log(f"Batch cache refresh: {total} unique AppIDs from {len(self.games)} games")
            
            if not unique:
                self._emit('finished', {'refreshed_count': 0, 'failed_count': 0, 'total_games': len(self.games), 'cancelled': False, 'results': {}})
                return
            
            results, refreshed, failed, failed_ids = {}, 0, 0, []
            for i, app_id in enumerate(unique):
                if self._cancelled:
                    break
                games = appid_map[app_id]
                self._emit('progress', games[0].get('title', f'AppID {app_id}'), i + 1, total)
                try:
                    result = self.steam.force_refresh_cache(app_id=app_id, title=games[0].get('title'), custom_tags=self.custom_tags)
                    result.update({'app_id': app_id, 'affected_games': games})
                    results[app_id] = result
                    refreshed += 1
                    self._emit('game_refreshed', result)
                except Exception as e:
                    _log(f"Failed to refresh cache for AppID {app_id}: {e}")
                    failed += 1
                    failed_ids.append(app_id)
            
            self._emit('finished', {
                'refreshed_count': refreshed, 'failed_count': failed, 'failed_appids': failed_ids,
                'total_appids': total, 'total_games': len(self.games), 'cancelled': self._cancelled, 'results': results
            })
        except Exception as e:
            _log(f"Batch cache refresh worker error: {e}")
            self._emit('error', str(e))


class SteamBatchReviewsWorker(_BaseWorker):
    """Worker for fetching fresh review data for multiple games (deduplicates by AppID).
    
    Always fetches fresh data from Steam API (no cache check). Updates all games
    sharing the same AppID after each fetch.
    """
    
    if HAS_QT:
        progress = Signal(str, int, int)
        game_refreshed = Signal(dict)  # Emitted after each AppID's reviews are fetched
    
    def __init__(self, steam_integration, games: List[dict]):
        super().__init__(steam_integration)
        self.games = games
    
    def run(self):
        try:
            # Deduplicate by AppID - games without AppID need search first
            appid_map = {}  # app_id -> [games]
            no_appid = []   # games that need AppID lookup
            
            for g in self.games:
                if app_id := g.get('steam_app_id'):
                    appid_map.setdefault(app_id, []).append(g)
                else:
                    no_appid.append(g)
            
            # Try to find AppIDs for games without them
            for g in no_appid:
                title = g.get('title', 'Unknown')
                if app_id := self.steam.search_app_id(title):
                    appid_map.setdefault(app_id, []).append(g)
                    _log(f"Found AppID {app_id} for '{title}'")
                else:
                    _log(f"Could not find AppID for '{title}'")
            
            unique, total = list(appid_map.keys()), len(appid_map)
            _log(f"Batch reviews refresh: {total} unique AppIDs from {len(self.games)} games")
            
            if not unique:
                self._emit('finished', {'refreshed_count': 0, 'failed_count': 0, 'total_games': len(self.games), 'cancelled': False, 'results': {}})
                return
            
            results, refreshed, failed, failed_ids = {}, 0, 0, []
            for i, app_id in enumerate(unique):
                if self._cancelled:
                    break
                games = appid_map[app_id]
                first_title = games[0].get('title', f'AppID {app_id}')
                self._emit('progress', first_title, i + 1, total)
                try:
                    # Always fetch fresh review data
                    review_data = self.steam.fetch_review_data(app_id)
                    if review_data:
                        result = {
                            'app_id': app_id,
                            'review_score': review_data.get('review_score'),
                            'review_count': review_data.get('review_count'),
                            'affected_games': games,
                            'fetched': {'reviews': True}
                        }
                        # Update cache with fresh review data
                        self.steam._update_cache_with_reviews(first_title, app_id, review_data)
                        results[app_id] = result
                        refreshed += 1
                        self._emit('game_refreshed', result)
                    else:
                        _log(f"No review data returned for AppID {app_id}")
                        failed += 1
                        failed_ids.append(app_id)
                except Exception as e:
                    _log(f"Failed to fetch reviews for AppID {app_id}: {e}")
                    failed += 1
                    failed_ids.append(app_id)
            
            self._emit('finished', {
                'refreshed_count': refreshed, 'failed_count': failed, 'failed_appids': failed_ids,
                'total_appids': total, 'total_games': len(self.games), 'cancelled': self._cancelled, 'results': results
            })
        except Exception as e:
            _log(f"Batch reviews worker error: {e}")
            self._emit('error', str(e))


class DatabaseSaveWorker(_BaseWorker):
    """Worker for background database save operations."""
    
    if HAS_QT:
        finished = Signal(object)  # Override for flexible result type
    
    def __init__(self, db_manager, operation: str, **kwargs):
        if HAS_QT:
            super(QObject, self).__init__()
        self.steam = None
        self.db_manager, self.operation, self.kwargs = db_manager, operation, kwargs
    
    def run(self):
        self._emit('progress', "Saving game to database...")
        try:
            if not (op_func := getattr(self.db_manager, f"{self.operation}_game", None)):
                raise ValueError(f"Unknown operation: {self.operation}")
            result = op_func(**self.kwargs)
            _log(f"{self.operation.title()}d game: {result}")
            self._emit('finished', result)
        except Exception as e:
            _log(f"Database worker error: {e}")
            self._emit('error', str(e))


class SteamCache:
    """Cache for Steam game data to avoid repeated API calls."""
    
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "steam_cache.json")
        self.images_dir = os.path.join(cache_dir, "Images")
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self._load_cache()
        
        # Ensure directories exist
        os.makedirs(self.images_dir, exist_ok=True)
        
    def get_platform_images_dir(self, platform: str = "Steam") -> str:
        """Get the images directory for a specific platform."""
        platform_dir = os.path.join(self.images_dir, platform)
        os.makedirs(platform_dir, exist_ok=True)
        return platform_dir
    
    def _load_cache(self):
        """Load cache from disk."""
        with self._lock:
            try:
                if os.path.exists(self.cache_file):
                    with open(self.cache_file, 'r', encoding='utf-8') as f:
                        self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {}
    
    def _save_cache(self):
        """Save cache to disk."""
        with self._lock:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self._cache, f, indent=2)
            except IOError as e:
                print(f"Failed to save Steam cache: {e}")
    
    def clear_by_appid(self, app_id: str) -> List[str]:
        """Clear all cache entries with the given AppID. Returns list of cleared titles."""
        if not app_id:
            return []
        
        app_id_str = str(app_id)
        with self._lock:
            keys_to_remove = [key for key, data in self._cache.items() 
                              if str(data.get('app_id')) == app_id_str]
            
            for key in keys_to_remove:
                del self._cache[key]
            
            if keys_to_remove:
                self._save_cache()
                _log(f"Cleared cache for AppID {app_id}: {keys_to_remove}")
        
        return keys_to_remove
    
    def clear_by_title(self, title: str) -> bool:
        """Clear cache entry for a specific title. Returns True if cleared."""
        key = self._normalize_title(title)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._save_cache()
                _log(f"Cleared cache for title: {title}")
                return True
        return False
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for cache key lookup."""
        # Remove special characters, lowercase, strip whitespace
        normalized = re.sub(r'[^\w\s]', '', title.lower()).strip()
        # Collapse multiple whitespaces
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized
    
    def get(self, title: str) -> Optional[Dict]:
        """Get cached data for a game title."""
        key = self._normalize_title(title)
        with self._lock:
            # Return a copy to avoid modification issues if caller mutates it
            data = self._cache.get(key)
            return data.copy() if data else None
    
    def get_by_appid(self, app_id: str) -> Optional[Dict]:
        """Get cached data by Steam AppID."""
        app_id_str = str(app_id)
        with self._lock:
            data = next((data for data in self._cache.values() 
                         if str(data.get('app_id')) == app_id_str), None)
            return data.copy() if data else None
    
    def get_cache_timestamp(self, app_id: str) -> Optional[float]:
        """Get the cache timestamp for a specific AppID. Returns None if not cached."""
        if not app_id:
            return None
        cached_data = self.get_by_appid(app_id)
        return cached_data.get('cached_at') if cached_data else None
    
    def set(self, title: str, data: Dict):
        """Cache data for a game title."""
        key = self._normalize_title(title)
        data['cached_at'] = time.time()
        with self._lock:
            self._cache[key] = data
            self._save_cache()
    
    def get_image_path(self, app_id: str, platform: str = "Steam") -> Optional[str]:
        """Get the local path for a cached game image."""
        platform_dir = self.get_platform_images_dir(platform)
        return next(
            (path for ext in ('jpg', 'png', 'webp')
             for path in [os.path.join(platform_dir, f"{app_id}.{ext}")]
             if os.path.exists(path)),
            None
        )
    
    def save_image(self, app_id: str, image_data: bytes, extension: str = 'jpg', platform: str = "Steam") -> str:
        """Save game image to cache and return the path."""
        platform_dir = self.get_platform_images_dir(platform)
        path = os.path.join(platform_dir, f"{app_id}.{extension}")
        with open(path, 'wb') as f:
            f.write(image_data)
        return path
    
    def clear_old_entries(self, max_age_days: int = 30):
        """Remove cache entries older than max_age_days."""
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        with self._lock:
            keys_to_remove = []
            for key, data in self._cache.items():
                cached_at = data.get('cached_at', 0)
                if current_time - cached_at > max_age_seconds:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._cache[key]
            
            if keys_to_remove:
                self._save_cache()


class SteamIntegration:
    """Handles Steam API interactions for game data fetching."""
    
    # Steam CDN URL for game header images (460x215)
    STEAM_IMAGE_URL = "https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg"
    # Alternative: Library capsule (600x900)
    STEAM_LIBRARY_IMAGE_URL = "https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/library_600x900.jpg"
    # Steam store page for parsing (fallback)
    STEAM_STORE_URL = "https://store.steampowered.com/app/{app_id}"
    # Steam search API
    STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=us"
    # Community search API (fallback for missing base games)
    COMMUNITY_SEARCH_URL = "https://steamcommunity.com/actions/SearchApps/{term}"
    # Steam app details API
    STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids={app_id}"
    
    # Tags to ignore - Steam platform features, not gameplay descriptors
    # These are filtered out during tag fetching to keep the tag list clean
    IGNORED_TAGS = frozenset({
        # Steam features & platform capabilities
        'steam achievements', 'achievements',
        'steam trading cards', 'trading cards',
        'steam cloud', 'cloud saves',
        'steam workshop', 'workshop',
        'steam leaderboards', 'leaderboards',
        'full controller support', 'controller support', 'partial controller support',
        'controller', 'gamepad', 'mouse only option', 'keyboard only option',
        'remote play', 'remote play on phone', 'remote play on tablet', 'remote play on tv',
        'remote play together',
        'steam input api',
        'in-app purchases', 'microtransactions',
        'downloadable content',
        'family sharing', 'family share', 'steam family sharing',
        'valve anti-cheat enabled', 'anti-cheat', 'vac',
        'steam turn notifications',
        'stats', 'steam stats',
        
        # Accessibility/technical features (not gameplay tags)
        'captions available', 'subtitles', 'closed captions',
        'includes level editor', 'level editor',
        'commentary available',
        'includes source sdk',
        
        # OS/Platform compatibility
        'windows', 'macos', 'mac os x', 'linux', 'steamos',
        'steamdeck verified', 'steam deck verified', 'steam deck playable',
        'steamvr', 'oculus', 'htc vive', 'valve index',
        'tracked motion controller support', 'tracked controller support',
        'seated', 'standing', 'room-scale',
        
        # Purchasing/Distribution status
        'free to play', 'free', 'free-to-play', 'f2p',
        'demo available', 'demo',
        'early access',
        
        # Software categories (not games)
        'software', 'utilities', 'video production', 'audio production',
        'game development', 'animation & modeling', 'design & illustration',
        'photo editing', 'web publishing',
    })
    
    # Tag normalization mapping (Steam tag -> our preferred format)
    # All fetched tags are considered Steam-provided tags by the app
    TAG_MAPPING = {
        'fps': 'First-Person Shooter',
        'tps': 'Third-Person Shooter',
        'role-playing': 'RPG',
        'action rpg': 'RPG',
        'jrpg': 'RPG',
        'crpg': 'RPG',
        'single-player': 'Singleplayer',
        'multi-player': 'Multiplayer',
        'co-op': 'Co-op',
        'cooperative': 'Co-op',
        'virtual reality': 'VR',
        'vr supported': 'VR',
        'indie': 'Indie',
        'open world': 'Open World',
        'sandbox': 'Sandbox',
        'survival horror': 'Horror',
        'psychological horror': 'Horror',
        'action-adventure': 'Adventure',
        'hack & slash': 'Hack and Slash',
        'hack-and-slash': 'Hack and Slash',
    }
    
    def __init__(self, app_data_dir: str):
        self.cache = SteamCache(app_data_dir)
        self._request_timeout = 10
        self._rate_limit_delay = 0.5  # Seconds between requests
        self._last_request_time = 0
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    # Shared request headers
    _REQUEST_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json,text/html,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    def _make_request(self, url: str) -> Optional[bytes]:
        """Make an HTTP request with rate limiting and error handling."""
        self._rate_limit()
        
        try:
            request = Request(url, headers=self._REQUEST_HEADERS)
            _log(f"Fetching: {url}")
            with urlopen(request, timeout=self._request_timeout) as response:
                data = response.read()
                _log(f"Success: received {len(data)} bytes")
                return data
        except (URLError, HTTPError) as e:
            _log(f"Request failed for {url}: {e}")
            return None
        except Exception as e:
            _log(f"Unexpected error for {url}: {e}")
            return None
    
    # Common edition suffixes to strip from titles for better search results
    _EDITION_PATTERNS = [
        r'\s*[-:]?\s*Deluxe\s*(Edition)?$',
        r'\s*[-:]?\s*(GOTY|Game of the Year)\s*(Edition)?$',
        r'\s*[-:]?\s*Definitive\s*(Edition)?$',
        r'\s*[-:]?\s*Ultimate\s*(Edition)?$',
        r'\s*[-:]?\s*Gold\s*(Edition)?$',
        r'\s*[-:]?\s*Complete\s*(Edition)?$',
        r'\s*[-:]?\s*Launch$',
        r'\s*[-:]?\s*Anniversary\s*(Edition)?$',
        r'\s*[-:]?\s*Remastered$',
        r'\s*[-:]?\s*Enhanced\s*(Edition)?$',
        r'\s*[-:]?\s*Special\s*(Edition)?$',
        r'\s*[-:]?\s*Steam\s*Special\s*(Edition)?$',
        r'\s*[-:]?\s*Collector\'?s?\s*(Edition)?$',
        r'\s*[-:]?\s*Premium\s*(Edition)?$',
        r'\s*[-:]?\s*Standard\s*(Edition)?$',
        r'\s*[-:]?\s*Digital\s*(Deluxe)?\s*(Edition)?$',
        r'\s*[-:]?\s*Legacy\s*(Edition)?$',
        r'\s*[-:]?\s*Extended\s*(Edition)?$',
    ]
    
    def _clean_title_for_search(self, title: str) -> str:
        """Clean a game title for Steam search.
        
        Removes special characters and common edition suffixes that might
        interfere with Steam's search API finding results.
        """
        clean = title.strip()
        
        # Remove common edition suffixes (case insensitive)
        for pattern in self._EDITION_PATTERNS:
            clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)
        
        # Remove special characters but keep alphanumeric, numbers and spaces
        clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean)
        # Collapse multiple spaces
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
    
    def _generate_search_variants(self, title: str) -> List[str]:
        """Generate search term variants for a title, from most specific to least.
        
        This helps find games with special characters, edition names, or subtitles.
        """
        variants = []
        original = title.strip()
        
        # 1. Original title (unchanged)
        variants.append(original)
        
        # 2. Cleaned title (special chars removed, edition suffixes stripped)
        cleaned = self._clean_title_for_search(original)
        if cleaned and cleaned != original:
            variants.append(cleaned)
        
        # 3. Remove content in parentheses (e.g. "Game (Note)")
        no_parens = re.sub(r'\s*\([^)]*\)', '', original).strip()
        if no_parens and no_parens != original and no_parens not in variants:
            variants.append(no_parens)
            
        # 3b. Cleaned version of no_parens
        cleaned_no_parens = self._clean_title_for_search(no_parens)
        if cleaned_no_parens and cleaned_no_parens != no_parens and cleaned_no_parens not in variants:
            variants.append(cleaned_no_parens)
        
        # 4. Just remove special characters (keep edition names)
        no_special = re.sub(r'[^a-zA-Z0-9\s]', ' ', original)
        no_special = re.sub(r'\s+', ' ', no_special).strip()
        if no_special and no_special not in variants:
            variants.append(no_special)
        
        # 5. First part before colon (for games with subtitles like "Game: Subtitle")
        if ':' in original:
            base_title = original.split(':')[0].strip()
            base_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', base_title)
            base_clean = re.sub(r'\s+', ' ', base_clean).strip()
            if base_clean and base_clean not in variants and len(base_clean.split()) >= 2:
                variants.append(base_clean)
            elif base_clean and base_clean not in variants and len(base_clean) >= 5:
                variants.append(base_clean)
        
        # 6. First part before " - "
        if ' - ' in original:
            base_title = original.split(' - ')[0].strip()
            base_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', base_title)
            base_clean = re.sub(r'\s+', ' ', base_clean).strip()
            if base_clean and base_clean not in variants and len(base_clean.split()) >= 2:
                variants.append(base_clean)

        # 7. First two words of the cleaned title (if long enough)
        # This helps when the user has a very long note or subtitle that isn't caught by other rules
        words = cleaned.split()
        if len(words) > 2:
            two_words = ' '.join(words[:2])
            if two_words not in variants and len(two_words) >= 4: # Avoid very short abbreviations
                variants.append(two_words)
        
        # 8. First word of the cleaned title (if distinctive enough)
        if len(words) > 1:
            first_word = words[0]
            if first_word not in variants and len(first_word) >= 5: # Only if word is substantial
                variants.append(first_word)
        
        return variants
    
    def search_game(self, title: str) -> Optional[Dict]:
        """Search for a game by title on Steam.
        
        Uses multiple search strategies with progressively cleaned titles
        to maximize chances of finding the game. Returns a dict with 
        app_id, name, tags, and image_url.
        """
        if not title or not title.strip():
            return None
        
        _log(f"Searching for game: '{title}'")
        
        # Check cache first
        if cached := self.cache.get(title):
            _log(f"Cache hit for '{title}': AppID={cached.get('app_id')}")
            return cached
        
        _log("Cache miss, querying Steam Store API...")
        
        # Generate search variants from most specific to least
        search_variants = self._generate_search_variants(title)
        _log(f"Search variants: {search_variants}")
        
        for variant in search_variants:
            # Strategy 1: Try Store API first (better details/DLC support)
            items = self._search_steam_api(variant)
            if items:
                best_match = self._find_best_match(title, items, variant)
                if best_match:
                    self._cache_and_return_match(title, best_match, variant)
                    return self.cache.get(title)

            # Strategy 2: If no strict match, try Community API (better for missing base games)
            # Only strictly necessary if the first search yielded nothing or only rejected sequels
            community_items = self._search_community_api(variant)
            if community_items:
                best_match = self._find_best_match(title, community_items, variant)
                if best_match:
                    self._cache_and_return_match(title, best_match, variant)
                    return self.cache.get(title)
        
        _log(f"No results found for '{title}' after trying all variants")
        return None

    def _cache_and_return_match(self, title: str, match: Dict, variant: str):
        """Helper to cache the found match."""
        app_id = str(match.get('id'))
        name = match.get('name', title)
        _log(f"Best match: '{name}' (AppID: {app_id}) using variant: '{variant}'")
        
        # Fetch detailed info including SteamSpy tags
        game_info = self._fetch_app_details(app_id) or {'app_id': app_id, 'tags': []}
        game_info.update({'name': name, 'image_url': self.STEAM_IMAGE_URL.format(app_id=app_id)})
        self.cache.set(title, game_info)
        _log(f"Cached game info for '{title}'")
    
    def _search_steam_api(self, search_term: str) -> List[Dict]:
        """Perform a single search against Steam's store search API."""
        response = self._make_request(self.STEAM_SEARCH_URL.format(term=quote(search_term)))
        if not response:
            return []
        
        try:
            items = json.loads(response.decode('utf-8')).get('items', [])
            _log(f"Store Search '{search_term}': found {len(items)} results")
            return items
        except (json.JSONDecodeError, KeyError) as e:
            _log(f"Failed to parse store search response for '{search_term}': {e}")
            return []

    def _search_community_api(self, search_term: str) -> List[Dict]:
        """Perform a single search against Steam's community search API."""
        url = self.COMMUNITY_SEARCH_URL.format(term=quote(search_term))
        response = self._make_request(url)
        if not response:
            return []
        
        try:
            # Community API returns a direct list of dicts: [{"appid": 123, "name": "Game", ...}, ...]
            items = json.loads(response.decode('utf-8'))
            if not isinstance(items, list):
                _log(f"Community Search '{search_term}': unexpected response format")
                return []
                
            # Convert to internal format (id -> appid) for compatibility
            results = []
            for item in items:
                if 'appid' in item and 'name' in item:
                    item['id'] = item['appid']
                    results.append(item)
                    
            _log(f"Community Search '{search_term}': found {len(results)} results")
            return results
        except (json.JSONDecodeError, KeyError) as e:
            _log(f"Failed to parse community search response for '{search_term}': {e}")
            return []
    
    def _find_best_match(self, original_title: str, items: List[Dict], search_variant: str = None) -> Optional[Dict]:
        """Find the best matching game from search results.
        
        Uses multiple matching strategies to handle edition names, subtitles, etc.
        Avoids matching sequels when searching for the base game (e.g., won't match
        "Psychonauts 2" when searching for "Psychonauts").
        """
        if not items:
            return None
        
        search_title = original_title.lower().strip()
        clean_search = self._clean_title_for_search(original_title).lower()
        variant_lower = (search_variant or original_title).lower().strip()
        
        # Check if search title already contains a number suffix (e.g., "Psychonauts 2")
        search_has_number = bool(re.search(r'\s\d+([: -]|$)', search_title)) or bool(re.search(r'\s[ivxlcdm]+([: -]|$)', search_title.lower()))
        
        def _is_sequel_mismatch(item_name: str) -> bool:
            """Check if item is a sequel but search is for base game."""
            if search_has_number:
                return False  # User is searching for a specific numbered title
            # Reject if item has a number suffix that search doesn't have
            item_lower = item_name.lower()
            if re.search(r'\s\d+([: -]|$)', item_lower):
                return True  # Item is a sequel like "Game 2"
            if re.search(r'\s[ivxlcdm]+([: -]|$)', item_lower):
                return True  # Item uses roman numerals like "Game III"
            return False
        
        # Exact match first (case-insensitive)
        for item in items:
            item_name = item.get('name', '').lower()
            if item_name == search_title:
                return item
        
        # Exact match with cleaned title
        for item in items:
            item_name = item.get('name', '')
            item_clean = self._clean_title_for_search(item_name).lower()
            if item_clean == clean_search:
                return item
        
        # Check if search variant matches item name exactly
        if search_variant:
            for item in items:
                item_clean = self._clean_title_for_search(item.get('name', '')).lower()
                if item_clean == variant_lower:
                    return item
        
        # Contains match (original in item OR item in original) - but avoid sequels
        for item in items:
            item_name = item.get('name', '')
            item_lower = item_name.lower()
            if search_title in item_lower or item_lower in search_title:
                if not _is_sequel_mismatch(item_name):
                    return item
        
        # Contains match with cleaned versions - but avoid sequels
        for item in items:
            item_name = item.get('name', '')
            item_clean = self._clean_title_for_search(item_name).lower()
            if clean_search in item_clean or item_clean in clean_search:
                if not _is_sequel_mismatch(item_name):
                    return item
        
        # Second pass: allow contains matches even for sequels if nothing else matched
        # BUT still reject if it's a clear sequel mismatch (e.g. searching for "Game" finding "Game 2")
        for item in items:
            item_name = item.get('name', '')
            item_lower = item_name.lower()
            if search_title in item_lower or item_lower in search_title:
                if not _is_sequel_mismatch(item_name):
                    return item
        
        # Fallback: return first result ONLY if it's not a sequel mismatch AND has reasonable similarity
        first_item = items[0]
        first_name = first_item.get('name', '')
        if not _is_sequel_mismatch(first_name):
            # Calculate similarity ratio
            # Use cleaned titles for better comparison
            first_clean = self._clean_title_for_search(first_name).lower()
            ratio = SequenceMatcher(None, clean_search, first_clean).ratio()
            
            # If ratio is decent, accept it. 0.4 is low but allows for significant differences 
            # (e.g. "Tropico 3" vs "Tropico 3 - Steam Special Edition" is high, 
            # but "Tropico 3" vs "Disciples III" should be low)
            # "tropico 3" vs "disciples iii renaissance" -> ratio ~0.2
            # "tropico 3" vs "tropico 3 steam special edition" -> ratio ~0.45 (if cleaned properly)
            
            # If we cleaned "Steam Special Edition" from search, clean_search is "tropico 3"
            # If result is "Tropico 3", first_clean is "tropico 3", ratio 1.0
            
            if ratio > 0.4: 
                return first_item
            
            _log(f"Rejected fallback '{first_name}' due to low similarity ({ratio:.2f}) with '{clean_search}'")
            
        _log(f"Rejected all {len(items)} items due to sequel mismatch or low similarity")
        return None
    
    def _fetch_app_details(self, app_id: str) -> Optional[Dict]:
        """Fetch detailed game info from Steam API and SteamSpy for user tags."""
        _log(f"Fetching app details for AppID: {app_id}")
        
        tags = []
        seen = set()
        review_count = None
        is_dlc = False
        
        # First, try to get user-defined tags from SteamSpy (more comprehensive)
        steamspy_tags = self._fetch_steamspy_tags(app_id)
        if steamspy_tags:
            for tag_name in steamspy_tags:
                if normalized := self._normalize_tag(tag_name):
                    if normalized not in seen:
                        tags.append(normalized)
                        seen.add(normalized)
            _log(f"SteamSpy tags for {app_id}: {tags[:30]}")
        
        # Also get official Steam genres/categories as fallback
        response = self._make_request(self.STEAM_APP_DETAILS_URL.format(app_id=app_id))
        
        if response:
            try:
                app_data = json.loads(response.decode('utf-8')).get(str(app_id), {})
                if app_data.get('success'):
                    details = app_data.get('data', {})
                    review_count = details.get('recommendations', {}).get('total')
                    
                    # Check if this is a DLC (type field is 'dlc' for DLC content)
                    app_type = details.get('type', '').lower()
                    is_dlc = app_type == 'dlc'
                    if is_dlc:
                        _log(f"AppID {app_id} is a DLC")
                    
                    # Add genres and categories as additional tags
                    for item in details.get('genres', []) + details.get('categories', []):
                        if tag_name := item.get('description', ''):
                            if normalized := self._normalize_tag(tag_name):
                                if normalized not in seen:
                                    tags.append(normalized)
                                    seen.add(normalized)
            except (json.JSONDecodeError, KeyError) as e:
                _log(f"Failed to parse app details for {app_id}: {e}")
        
        if not tags:
            _log(f"No tags found for AppID: {app_id}")
            return None
        
        _log(f"Final tags for AppID {app_id}: {tags[:30]}")
        
        return {
            'app_id': app_id,
            'tags': tags[:30],  # Increased limit to capture more tags
            'review_count': review_count,
            'review_score': None,  # Fetched from reviews API
            'is_dlc': is_dlc,
        }
    
    # SteamSpy API for user-defined tags
    STEAMSPY_URL = "https://steamspy.com/api.php?request=appdetails&appid={app_id}"
    
    def _fetch_steamspy_tags(self, app_id: str) -> List[str]:
        """Fetch user-defined tags from SteamSpy API.
        
        SteamSpy provides actual Steam user tags which are more comprehensive
        than the official genres/categories from Steam's appdetails API.
        """
        try:
            response = self._make_request(self.STEAMSPY_URL.format(app_id=app_id))
            if not response:
                return []
            
            data = json.loads(response.decode('utf-8'))
            tags_dict = data.get('tags', {})
            
            if not tags_dict:
                return []
            
            # Tags are returned as {tag_name: vote_count}, sorted by votes
            # Sort by vote count descending and return tag names
            sorted_tags = sorted(tags_dict.items(), key=lambda x: x[1], reverse=True)
            tags = [tag_name for tag_name, _ in sorted_tags[:30]]
            
            _log(f"SteamSpy returned {len(tags)} tags for AppID {app_id}")
            return tags
            
        except (json.JSONDecodeError, KeyError) as e:
            _log(f"Failed to fetch SteamSpy tags for {app_id}: {e}")
            return []
        except Exception as e:
            _log(f"Unexpected error fetching SteamSpy tags for {app_id}: {e}")
            return []
    
    # Steam Reviews API URL template
    STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}?json=1&language=all&purchase_type=all"
    
    def fetch_review_data(self, app_id: str) -> Optional[Dict]:
        """Fetch review score and count for a game from Steam Reviews API."""
        if not app_id:
            return None
        
        _log(f"Fetching review data for AppID: {app_id}")
        response = self._make_request(self.STEAM_REVIEWS_URL.format(app_id=app_id))
        
        if not response:
            _log(f"No response for reviews (AppID: {app_id})")
            return None
        
        try:
            data = json.loads(response.decode('utf-8'))
            if not data.get('success'):
                _log(f"Reviews API returned unsuccessful for AppID: {app_id}")
                return None
            
            qs = data.get('query_summary', {})
            total_positive = qs.get('total_positive', 0)
            total_reviews = qs.get('total_reviews', 0)
            review_percentage = round((total_positive / total_reviews) * 100) if total_reviews > 0 else None
            
            _log(f"Reviews for {app_id}: {review_percentage}% positive ({total_reviews} reviews)")
            
            return {
                'review_score': review_percentage,
                'review_count': total_reviews,
                'review_score_desc': qs.get('review_score_desc', ''),
                'total_positive': total_positive,
                'total_negative': qs.get('total_negative', 0),
            }
        except (json.JSONDecodeError, KeyError) as e:
            _log(f"Failed to parse reviews for {app_id}: {e}")
            return None
    
    def _update_cache_with_reviews(self, title: str, app_id: str, review_data: Dict):
        """Update the cache with review data for a game."""
        # Update existing cache entry if it exists
        cached = self.cache.get(title)
        if cached:
            cached['review_score'] = review_data.get('review_score')
            cached['review_count'] = review_data.get('review_count')
            self.cache.set(title, cached)
            _log(f"Updated cache with reviews for '{title}'")
        elif app_id:
            # Create new cache entry with review data
            self.cache.set(title, {
                'app_id': app_id,
                'review_score': review_data.get('review_score'),
                'review_count': review_data.get('review_count'),
            })
            _log(f"Created cache entry with reviews for '{title}'")
    
    def _normalize_tag(self, tag: str) -> Optional[str]:
        """Normalize a tag name to our standard format.
        
        Returns None for ignored tags (Steam platform features).
        All other tags from Steam sources are accepted and will be
        automatically marked as Steam-provided when stored in the database.
        """
        if not tag:
            return None
        
        tag_lower = tag.lower().strip()
        
        # Filter out ignored tags (Steam platform features, not gameplay descriptors)
        if tag_lower in self.IGNORED_TAGS:
            return None
        
        # Check mapping first for known normalizations, otherwise preserve original case
        # This ensures tags like "PvP" stay as "PvP" instead of becoming "Pvp"
        return self.TAG_MAPPING.get(tag_lower) or tag.strip()
    
    def fetch_game_image(self, app_id: str, force_download: bool = False) -> Optional[str]:
        """Download and cache a game's header image. Returns local path or None."""
        if not app_id:
            return None
        
        _log(f"Fetching image for AppID: {app_id}")
        
        # Check cache first
        if not force_download:
            if cached_path := self.cache.get_image_path(app_id, platform="Steam"):
                _log(f"Image cache hit: {cached_path}")
                return cached_path
        
        _log("Downloading image from Steam CDN...")
        
        # Try header image first, then library image
        for url_template in (self.STEAM_IMAGE_URL, self.STEAM_LIBRARY_IMAGE_URL):
            url = url_template.format(app_id=app_id)
            if image_data := self._make_request(url):
                ext = 'png' if '.png' in url else ('webp' if '.webp' in url else 'jpg')
                try:
                    path = self.cache.save_image(app_id, image_data, ext, platform="Steam")
                    _log(f"Image saved to: {path}")
                    return path
                except IOError as e:
                    _log(f"Failed to save image for {app_id}: {e}")
        
        _log(f"Failed to download image for AppID: {app_id}")
        return None
    
    def get_game_info_by_appid(self, app_id: str) -> Optional[Dict]:
        """Get game info by Steam AppID."""
        if not app_id:
            return None
        
        # Check cache first
        if cached := self.cache.get_by_appid(app_id):
            return cached
        
        # Fetch details
        return self._fetch_app_details(app_id)
    
    def search_app_id(self, title: str) -> Optional[str]:
        """Search for a game's AppID by title. Returns AppID string or None."""
        if game_info := self.search_game(title):
            return game_info.get('app_id')
        return None
    
    def fetch_missing_data(
        self,
        title: str,
        current_app_id: Optional[str] = None,
        current_tags: Optional[List[str]] = None,
        current_image_path: Optional[str] = None,
        current_is_dlc: bool = False,
        fetch_appid: bool = True,
        fetch_tags: bool = True,
        fetch_image: bool = True,
        fetch_reviews: bool = True,
        force_tags: bool = False,
        custom_tags: Optional[List[str]] = None,
        force_fresh_search: bool = False,
        force_image: bool = False
    ) -> Dict[str, Any]:
        """Fetch missing data for a game.
        
        Args:
            force_fresh_search: If True, clears the cache for this title before searching.
                               Use when the title has changed since the last fetch.
            force_image: If True, re-downloads the image even if one exists.
                        Use when explicitly refetching.
        
        Returns dict with app_id, tags, image_path, review_score, review_count, is_dlc, and fetched flags.
        """
        _log(f"fetch_missing_data called for '{title}'")
        
        # Clear cache if force_fresh_search is requested (e.g., title changed)
        if force_fresh_search:
            self.cache.clear_by_title(title)
            _log(f"Cleared cache for '{title}' (force_fresh_search)")
        
        result = self._create_result_dict(current_app_id, current_tags, current_image_path, current_is_dlc)
        
        # Determine what needs fetching
        has_valid_image = current_image_path and os.path.exists(current_image_path)
        needs = {
            'appid': fetch_appid and not current_app_id,
            'tags': fetch_tags and (not current_tags or force_tags),
            'image': fetch_image and (not has_valid_image or force_image),
            'reviews': fetch_reviews
        }
        
        if not any(needs.values()):
            _log(f"Nothing to fetch for '{title}'")
            return result
        
        # Get AppID if needed
        app_id, game_info = self._resolve_app_id(
            title, current_app_id, 
            needs['appid'] or needs['tags'] or needs['reviews']
        )
        
        if needs['appid'] and app_id and not current_app_id:
            result['app_id'] = app_id
            result['fetched']['app_id'] = True
        
        # If we needed to search but couldn't find anything, mark as not_found
        if needs['appid'] and not app_id and not current_app_id:
            result['not_found'] = True
            _log(f"Could not find game '{title}' on Steam")
        
        # Fetch remaining data
        if app_id:
            self._fetch_tags_if_needed(result, app_id, game_info, current_tags, 
                                       needs['tags'], force_tags, custom_tags)
            self._fetch_image_if_needed(result, app_id, needs['image'], force_image)
            self._fetch_reviews_if_needed(result, title, app_id, needs['reviews'])
            self._fetch_dlc_status_if_needed(result, app_id, game_info)
        
        _log(f"fetch_missing_data complete for '{title}'")
        return result
    
    def _create_result_dict(self, app_id: Optional[str], tags: Optional[List[str]], 
                            image_path: Optional[str], is_dlc: bool = False) -> Dict[str, Any]:
        """Create the standard result dictionary structure."""
        return {
            'app_id': app_id,
            'tags': tags or [],
            'image_path': image_path,
            'review_score': None,
            'review_count': None,
            'is_dlc': is_dlc,
            'fetched': {'app_id': False, 'tags': False, 'image': False, 'reviews': False, 'is_dlc': False}
        }
    
    def _resolve_app_id(self, title: str, current_app_id: Optional[str], 
                        needs_search: bool) -> tuple:
        """Resolve AppID from current value or by searching."""
        if current_app_id:
            return current_app_id, None
        if needs_search:
            _log("Searching by title to get AppID...")
            if game_info := self.search_game(title):
                app_id = game_info.get('app_id')
                if app_id:
                    _log(f"Found AppID: {app_id}")
                    return app_id, game_info
        return None, None
    
    def _fetch_tags_if_needed(self, result: Dict, app_id: str, game_info: Optional[Dict],
                              current_tags: Optional[List[str]], needs_tags: bool,
                              force_tags: bool, custom_tags: Optional[List[str]]):
        """Fetch and update tags in result if needed."""
        if not needs_tags:
            return
        
        fetched_tags = (
            (game_info or {}).get('tags') or 
            (self.get_game_info_by_appid(app_id) or {}).get('tags')
        )
        
        if fetched_tags:
            if force_tags:
                custom_set = set(custom_tags or [])
                preserved = [t for t in (current_tags or []) 
                            if t in custom_set and t not in fetched_tags]
                result['tags'] = fetched_tags + preserved
            else:
                result['tags'] = fetched_tags
            result['fetched']['tags'] = True
            _log(f"Fetched tags: {result['tags']}")
    
    def _fetch_image_if_needed(self, result: Dict, app_id: str, needs_image: bool, 
                                force_download: bool = False):
        """Fetch and update image path in result if needed."""
        if needs_image:
            if image_path := self.fetch_game_image(app_id, force_download=force_download):
                result['image_path'] = image_path
                result['fetched']['image'] = True
    
    def _fetch_reviews_if_needed(self, result: Dict, title: str, app_id: str, 
                                  needs_reviews: bool):
        """Fetch and update review data in result if needed."""
        if needs_reviews:
            if review_data := self.fetch_review_data(app_id):
                result['review_score'] = review_data.get('review_score')
                result['review_count'] = review_data.get('review_count')
                result['fetched']['reviews'] = True
                self._update_cache_with_reviews(title, app_id, review_data)
    
    def _fetch_dlc_status_if_needed(self, result: Dict, app_id: str, game_info: Optional[Dict]):
        """Fetch and update DLC status in result.
        
        Extracts is_dlc from game_info (if available from search) or from cache.
        Always sets the is_dlc flag since this information is needed for proper categorization.
        """
        # Try to get is_dlc from game_info first (from search result)
        is_dlc = (game_info or {}).get('is_dlc')
        
        # If not in game_info, try to get from cache
        if is_dlc is None:
            cached = self.cache.get_by_appid(app_id)
            is_dlc = (cached or {}).get('is_dlc')
        
        # If we found DLC status, update the result
        if is_dlc is not None:
            result['is_dlc'] = is_dlc
            result['fetched']['is_dlc'] = True
            if is_dlc:
                _log(f"AppID {app_id} identified as DLC")
    
    def _get_cached_data(self, title: str, current_app_id: Optional[str] = None) -> tuple:
        """Get cached data and resolved app_id. Returns (cached_dict, app_id)."""
        cached = self.cache.get(title)
        app_id = current_app_id or (cached.get('app_id') if cached else None)
        if app_id and not cached:
            cached = self.cache.get_by_appid(app_id)
        return cached, app_id
    
    def check_needs_fetch(
        self,
        title: str,
        current_app_id: Optional[str] = None,
        current_tags: Optional[List[str]] = None,
        current_image_path: Optional[str] = None,
        fetch_appid: bool = True,
        fetch_tags: bool = True,
        fetch_image: bool = True,
        fetch_reviews: bool = True,
        force_tags: bool = False,
        reviews_only: bool = False
    ) -> bool:
        """Check if a game needs any network requests or if all data is cached.
        
        Returns True if network requests are needed, False if everything is cached.
        """
        cached, app_id = self._get_cached_data(title, current_app_id)
        
        # For reviews_only mode, just check review cache
        if reviews_only:
            if not app_id:
                return True  # Need to search for AppID
            return cached is None or cached.get('review_score') is None
        
        # Determine what would need fetching
        needs_appid = fetch_appid and not current_app_id
        needs_tags = fetch_tags and (not current_tags or force_tags)
        needs_image = fetch_image and not (current_image_path and os.path.exists(current_image_path))
        needs_reviews = fetch_reviews
        
        if not any([needs_appid, needs_tags, needs_image, needs_reviews]):
            return False  # Nothing to fetch at all
        
        # Check each need against cache
        if needs_appid and not app_id:
            return True
        
        if needs_tags and app_id and (not cached or not cached.get('tags')):
            return True
        
        if needs_image and app_id and not self.cache.get_image_path(app_id, platform="Steam"):
            return True
        
        if needs_reviews and app_id and (not cached or cached.get('review_score') is None):
            return True
        
        return False  # All needed data is in cache
    
    def fetch_from_cache_only(
        self,
        title: str,
        current_app_id: Optional[str] = None,
        current_tags: Optional[List[str]] = None,
        current_image_path: Optional[str] = None,
        current_is_dlc: bool = False,
        fetch_appid: bool = True,
        fetch_tags: bool = True,
        fetch_image: bool = True,
        fetch_reviews: bool = True,
        force_tags: bool = False,
        custom_tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Fetch data from cache only, no network requests.
        
        This is used for games that have been pre-checked to have all needed data cached.
        Returns same structure as fetch_missing_data but skips rate limiting.
        """
        _log(f"fetch_from_cache_only called for '{title}'")
        
        result = self._create_result_dict(current_app_id, current_tags, current_image_path, current_is_dlc)
        cached, app_id = self._get_cached_data(title, current_app_id)
        
        # Get AppID from cache
        if fetch_appid and not current_app_id and app_id:
            result['app_id'] = app_id
            result['fetched']['app_id'] = True
        
        # Get tags from cache
        if fetch_tags and app_id and cached:
            if fetched_tags := cached.get('tags'):
                if force_tags:
                    custom_set = set(custom_tags or [])
                    preserved = [t for t in (current_tags or []) if t in custom_set and t not in fetched_tags]
                    result['tags'] = fetched_tags + preserved
                else:
                    result['tags'] = fetched_tags
                result['fetched']['tags'] = True
        
        # Get image from cache
        if fetch_image and app_id:
            if cached_path := self.cache.get_image_path(app_id, platform="Steam"):
                result['image_path'] = cached_path
                result['fetched']['image'] = True
        
        # Get reviews from cache
        if fetch_reviews and app_id and cached:
            if (review_score := cached.get('review_score')) is not None:
                result['review_score'] = review_score
                result['review_count'] = cached.get('review_count')
                result['fetched']['reviews'] = True
        
        # Get DLC status from cache
        if app_id and cached:
            if (is_dlc := cached.get('is_dlc')) is not None:
                result['is_dlc'] = is_dlc
                result['fetched']['is_dlc'] = True
        
        _log(f"fetch_from_cache_only complete for '{title}'")
        return result
    
    def clear_cache(self):
        """Clear all cached data."""
        self.cache._cache = {}
        self.cache._save_cache()
    
    def get_cache_stats(self) -> Dict:
        """Get statistics about the cache."""
        return {
            'entries': len(self.cache._cache),
            'cache_file': self.cache.cache_file,
            'images_dir': self.cache.images_dir,
        }
    
    def create_fetch_worker(self, title: str, **kwargs) -> 'SteamFetchWorker':
        """Create a worker for background Steam data fetching (single game)."""
        return SteamFetchWorker(self, title, **kwargs)
    
    def create_batch_fetch_worker(self, games: List[dict], reviews_only: bool = False, **kwargs) -> 'SteamBatchFetchWorker':
        """Create a worker for background Steam data fetching (multiple games)."""
        return SteamBatchFetchWorker(self, games, reviews_only=reviews_only, **kwargs)
    
    def get_steam_store_url(self, app_id: Optional[str] = None, title: Optional[str] = None) -> Optional[str]:
        """
        Get the Steam store URL for a game.
        
        Args:
            app_id: Steam AppID (preferred)
            title: Game title (fallback for search)
        
        Returns the Steam store URL or None if not available.
        """
        if app_id:
            return f"https://store.steampowered.com/app/{app_id}"
        elif title:
            # Search URL as fallback
            return f"https://store.steampowered.com/search/?term={quote(title)}"
        return None
    
    def force_refresh_cache(
        self,
        app_id: str,
        title: Optional[str] = None,
        custom_tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Force refresh cache for a Steam AppID by clearing cache and fetching fresh data.
        
        Args:
            app_id: Steam AppID to refresh
            title: Optional title for cache key (if not provided, uses AppID lookup)
            custom_tags: List of custom tag names to preserve
        
        Returns dict with fresh app_id, tags, image_path, review_score, review_count, is_dlc.
        """
        if not app_id:
            return {'error': 'No AppID provided'}
        
        _log(f"Force refreshing cache for AppID: {app_id}")
        
        # Clear existing cache entries for this AppID
        self.cache.clear_by_appid(app_id)
        
        # Fetch fresh data from Steam
        result = {
            'app_id': app_id,
            'tags': [],
            'image_path': None,
            'review_score': None,
            'review_count': None,
            'is_dlc': False,
            'fetched': {'app_id': True, 'tags': False, 'image': False, 'reviews': False, 'is_dlc': False}
        }
        
        # Fetch app details (tags and DLC status)
        if details := self._fetch_app_details(app_id):
            result['tags'] = details.get('tags', [])
            result['fetched']['tags'] = True
            # Get DLC status from app details
            if (is_dlc := details.get('is_dlc')) is not None:
                result['is_dlc'] = is_dlc
                result['fetched']['is_dlc'] = True
                if is_dlc:
                    _log(f"AppID {app_id} identified as DLC during cache refresh")
        
        # Fetch image
        if image_path := self.fetch_game_image(app_id, force_download=True):
            result['image_path'] = image_path
            result['fetched']['image'] = True
        
        # Fetch reviews
        if review_data := self.fetch_review_data(app_id):
            result['review_score'] = review_data.get('review_score')
            result['review_count'] = review_data.get('review_count')
            result['fetched']['reviews'] = True
        
        # Cache the fresh data
        cache_title = title or f"appid_{app_id}"
        self.cache.set(cache_title, {
            'app_id': app_id,
            'tags': result['tags'],
            'review_score': result['review_score'],
            'review_count': result['review_count'],
            'is_dlc': result['is_dlc'],
        })
        
        _log(f"Force refresh complete for AppID: {app_id}")
        return result
    
    def create_cache_refresh_worker(self, app_id: str, title: Optional[str] = None, custom_tags: Optional[List[str]] = None) -> 'SteamCacheRefreshWorker':
        """Create a worker for background cache refresh."""
        return SteamCacheRefreshWorker(self, app_id, title, custom_tags)
    
    def create_batch_cache_refresh_worker(self, games: List[dict], custom_tags: Optional[List[str]] = None) -> 'SteamBatchCacheRefreshWorker':
        """Create a worker for batch cache refresh (deduplicates by AppID)."""
        return SteamBatchCacheRefreshWorker(self, games, custom_tags)
    
    def create_batch_reviews_worker(self, games: List[dict]) -> 'SteamBatchReviewsWorker':
        """Create a worker for batch reviews refresh (always fetches fresh, deduplicates by AppID)."""
        return SteamBatchReviewsWorker(self, games)

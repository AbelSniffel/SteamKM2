"""
Game list filter proxy model for efficient filtering without model resets.
"""

from datetime import datetime, date
from enum import Enum
from PySide6.QtCore import QSortFilterProxyModel, Qt


class SortMode(Enum):
    """Available sorting modes for the game list."""
    DEADLINE_FIRST = "deadline_first"     # Urgent deadlines first, then by title
    TITLE_ASC = "title_asc"               # Title A-Z
    TITLE_DESC = "title_desc"             # Title Z-A
    PLATFORM_ASC = "platform_asc"         # Platform A-Z, then title
    PLATFORM_DESC = "platform_desc"       # Platform Z-A, then title
    DATE_ADDED_NEWEST = "date_newest"     # Newest first
    DATE_ADDED_OLDEST = "date_oldest"     # Oldest first
    RATING_HIGH = "rating_high"           # Highest Steam rating first
    RATING_LOW = "rating_low"             # Lowest Steam rating first


class GameListFilterProxy(QSortFilterProxyModel):
    """Proxy model that filters games without modifying the source model.
    
    This allows for instant filtering by hiding/showing rows rather than
    adding/removing them from the model, which is much more efficient.
    
    Also provides custom sorting with multiple sort modes.
    """
    
    # Number of days before deadline to consider "urgent" and push to top
    URGENT_DEADLINE_DAYS = 14
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Filter state - default to no filtering
        self._search_term = ""
        self._platform_filter = ""  # Empty = no filter (show all)
        self._active_tags = set()
        self._deadline_only = False
        self._dlc_only = False
        self._used_only = False
        self._no_pictures_only = False
        
        # Sort mode - default to deadline first
        self._sort_mode = SortMode.DEADLINE_FIRST
        
        # Cache for parsed tags (game_id -> set of tags)
        self._tag_cache = {}
        
        # Enable dynamic sorting
        self.setDynamicSortFilter(True)
    
    def set_sort_mode(self, mode: SortMode):
        """Set the sorting mode."""
        if self._sort_mode != mode:
            self._sort_mode = mode
            self.invalidate()  # Re-sort the entire model
    
    def get_sort_mode(self) -> SortMode:
        """Get the current sorting mode."""
        return self._sort_mode
    
    def set_search_term(self, term: str):
        """Set the search term for filtering."""
        self._search_term = term.lower().strip()
        self.invalidateFilter()
    
    def set_platform_filter(self, platform: str):
        """Set the platform filter."""
        self._platform_filter = platform
        self.invalidateFilter()
    
    def set_tag_filter(self, tags: set):
        """Set active tags for filtering."""
        self._active_tags = set(tags)
        self.invalidateFilter()
    
    def set_deadline_filter(self, enabled: bool):
        """Set deadline-only filter."""
        self._deadline_only = enabled
        self.invalidateFilter()
    
    def set_dlc_filter(self, enabled: bool):
        """Set DLC-only filter."""
        self._dlc_only = enabled
        self.invalidateFilter()
    
    def set_used_filter(self, enabled: bool):
        """Set used-only filter."""
        self._used_only = enabled
        self.invalidateFilter()

    def set_no_pictures_filter(self, enabled: bool):
        """Filter to show only games without an image path (no pictures)."""
        self._no_pictures_only = bool(enabled)
        self.invalidateFilter()
    
    def filterAcceptsRow(self, source_row: int, source_parent):
        """Determine if a row should be visible based on current filters."""
        # Get the source model
        source_model = self.sourceModel()
        if not source_model:
            return True
        
        # Get game data from source model
        index = source_model.index(source_row, 0, source_parent)
        
        # Get game dict (assuming the model has a game_at method)
        try:
            game = source_model.game_at(source_row)
            if not game:
                return False
        except Exception:
            return False
        
        # Apply search term filter
        if self._search_term:
            title = (game.get('title') or '').lower()
            key = (game.get('game_key') or '').lower()
            if self._search_term not in title and self._search_term not in key:
                return False
        
        # Apply platform filter
        if self._platform_filter and self._platform_filter != "All Platforms":
            game_platform = game.get('platform_type', '')
            if game_platform != self._platform_filter:
                return False
        
        # Apply tag filter (game must have ALL active tags)
        if self._active_tags:
            game_id = game.get('id')
            
            # Check cache first
            if game_id not in self._tag_cache:
                tags_str = game.get('tags') or ''
                self._tag_cache[game_id] = {t.strip() for t in tags_str.split(',') if t.strip()}
            
            game_tags = self._tag_cache[game_id]
            
            # Game must have all active tags
            if not self._active_tags.issubset(game_tags):
                return False
        
        # Apply deadline filter
        if self._deadline_only:
            if not game.get('deadline_enabled', False):
                return False
        
        # Apply DLC filter
        if self._dlc_only:
            if not game.get('dlc_enabled', False):
                return False
        
        # Apply used filter
        if self._used_only:
            if not game.get('is_used', False):
                return False

        # Apply 'no pictures' filter
        if self._no_pictures_only:
            # If the game has an image_path defined (truthy), then exclude it
            if game.get('image_path'):
                return False
        
        # All filters passed
        return True
    
    def lessThan(self, left_index, right_index) -> bool:
        """Custom sorting based on the current sort mode.
        
        Sort modes:
        - DEADLINE_FIRST: Urgent deadlines (≤14 days) first, then by title
        - TITLE_ASC/DESC: Alphabetical by title
        - PLATFORM_ASC/DESC: By platform, then title
        - DATE_ADDED_NEWEST/OLDEST: By date added
        - RATING_HIGH/LOW: By Steam review score
        """
        source_model = self.sourceModel()
        if not source_model:
            return False
        
        try:
            left_game = source_model.game_at(left_index.row())
            right_game = source_model.game_at(right_index.row())
        except Exception:
            return False
        
        if not left_game or not right_game:
            return False
        
        mode = self._sort_mode
        
        # Handle each sort mode
        if mode == SortMode.DEADLINE_FIRST:
            return self._compare_deadline_first(left_game, right_game)
        elif mode == SortMode.TITLE_ASC:
            return self._compare_title(left_game, right_game, ascending=True)
        elif mode == SortMode.TITLE_DESC:
            return self._compare_title(left_game, right_game, ascending=False)
        elif mode == SortMode.PLATFORM_ASC:
            return self._compare_platform(left_game, right_game, ascending=True)
        elif mode == SortMode.PLATFORM_DESC:
            return self._compare_platform(left_game, right_game, ascending=False)
        elif mode == SortMode.DATE_ADDED_NEWEST:
            return self._compare_date_added(left_game, right_game, newest_first=True)
        elif mode == SortMode.DATE_ADDED_OLDEST:
            return self._compare_date_added(left_game, right_game, newest_first=False)
        elif mode == SortMode.RATING_HIGH:
            return self._compare_rating(left_game, right_game, high_first=True)
        elif mode == SortMode.RATING_LOW:
            return self._compare_rating(left_game, right_game, high_first=False)
        
        # Default fallback: title ascending
        return self._compare_title(left_game, right_game, ascending=True)
    
    def _compare_deadline_first(self, left_game: dict, right_game: dict) -> bool:
        """Sort urgent deadlines first, then by title."""
        left_urgent = self._is_deadline_urgent(left_game)
        right_urgent = self._is_deadline_urgent(right_game)
        
        # Urgent deadlines come first
        if left_urgent and not right_urgent:
            return True
        if right_urgent and not left_urgent:
            return False
        
        # Both urgent: sort by deadline (soonest first)
        if left_urgent and right_urgent:
            left_date = self._parse_deadline(left_game)
            right_date = self._parse_deadline(right_game)
            if left_date and right_date:
                return left_date < right_date
        
        # Default: sort by title alphabetically
        return self._compare_title(left_game, right_game, ascending=True)
    
    def _compare_title(self, left_game: dict, right_game: dict, ascending: bool = True) -> bool:
        """Compare games by title."""
        left_title = (left_game.get('title') or '').lower()
        right_title = (right_game.get('title') or '').lower()
        if ascending:
            return left_title < right_title
        else:
            return left_title > right_title
    
    def _compare_platform(self, left_game: dict, right_game: dict, ascending: bool = True) -> bool:
        """Compare games by platform, then by title."""
        left_platform = (left_game.get('platform_type') or '').lower()
        right_platform = (right_game.get('platform_type') or '').lower()
        
        if left_platform != right_platform:
            if ascending:
                return left_platform < right_platform
            else:
                return left_platform > right_platform
        
        # Same platform: sort by title
        return self._compare_title(left_game, right_game, ascending=True)
    
    def _compare_date_added(self, left_game: dict, right_game: dict, newest_first: bool = True) -> bool:
        """Compare games by date added."""
        left_date = left_game.get('date_added') or ''
        right_date = right_game.get('date_added') or ''
        
        # Handle empty dates (put them at the end)
        if not left_date and right_date:
            return False
        if left_date and not right_date:
            return True
        if not left_date and not right_date:
            return self._compare_title(left_game, right_game, ascending=True)
        
        if newest_first:
            return str(left_date) > str(right_date)
        else:
            return str(left_date) < str(right_date)
    
    def _compare_rating(self, left_game: dict, right_game: dict, high_first: bool = True) -> bool:
        """Compare games by Steam review score."""
        left_rating = left_game.get('steam_review_score')
        right_rating = right_game.get('steam_review_score')
        
        # Handle None ratings (put them at the end)
        if left_rating is None and right_rating is not None:
            return False
        if left_rating is not None and right_rating is None:
            return True
        if left_rating is None and right_rating is None:
            return self._compare_title(left_game, right_game, ascending=True)
        
        if left_rating != right_rating:
            if high_first:
                return left_rating > right_rating
            else:
                return left_rating < right_rating
        
        # Same rating: sort by title
        return self._compare_title(left_game, right_game, ascending=True)
    
    def _is_deadline_urgent(self, game: dict) -> bool:
        """Check if game has a deadline within the urgent threshold (default 14 days)."""
        if not game.get('deadline_enabled'):
            return False
        deadline = self._parse_deadline(game)
        if not deadline:
            return False
        days_left = (deadline - date.today()).days
        return days_left <= self.URGENT_DEADLINE_DAYS
    
    def _parse_deadline(self, game: dict):
        """Parse deadline string to date object. Returns None if invalid."""
        deadline_str = game.get('deadline_at')
        if not deadline_str:
            return None
        try:
            # Handle various date formats (including ISO with T)
            clean_str = str(deadline_str).replace('T', ' ').strip()
            date_str = clean_str.split()[0]
            
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, AttributeError):
            try:
                # Try alternative format (DD/MM/YYYY)
                return datetime.strptime(str(deadline_str).split()[0], '%d/%m/%Y').date()
            except (ValueError, AttributeError):
                return None

    
    def clear_tag_cache(self):
        """Clear the tag cache (call when games are modified)."""
        self._tag_cache.clear()
    
    def invalidate_tag_cache_for_game(self, game_id: int):
        """Invalidate tag cache for a specific game."""
        self._tag_cache.pop(game_id, None)


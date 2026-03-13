from dataclasses import dataclass, field
from datetime import datetime, date as _date
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGradient, QLinearGradient, QPainter, QPainterPath, QPixmap, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from src.ui.config import WIDGET_SPACING, GRID_CARD_WIDTH, GRID_CARD_HEIGHT, LIST_CARD_HEIGHT, LIST_CARD_IMAGE_WIDTH, GRID_CARD_SPACING, LIST_CARD_SPACING
from .game_list import GameListModel
from src.core.theme import get_contrasting_text_color, mix_colors
from src.core.steam_integration import SteamIntegration

# Unified cache with size limits
_cache: Dict[str, Dict] = {'pixmap': {}, 'pattern': {}, 'tag': {}}
_CACHE_LIMITS = {'pixmap': 500, 'pattern': 32, 'tag': 500}


def _cache_get(cache_type: str, key, create_fn):
    """Get from cache or create with auto-eviction."""
    cache = _cache[cache_type]
    if key in cache:
        return cache[key]
    value = create_fn()
    if len(cache) >= _CACHE_LIMITS[cache_type]:
        for k in list(cache.keys())[:len(cache)//2]:
            del cache[k]
    cache[key] = value
    return value


def clear_caches():
    """Clear all caches."""
    for c in _cache.values():
        c.clear()


@dataclass(frozen=True)
class GameCardData:
    title: str = ""
    platform: str = ""
    tags: List[str] = field(default_factory=list)
    deadline_enabled: bool = False
    deadline_text: str = ""
    dlc_enabled: bool = False
    is_used: bool = False
    steam_review_score: int = None


class GameCard(QStyledItemDelegate):
    """Adaptive game card delegate for grid (vertical) and list (horizontal) layouts."""

    # Dimensions
    GRID_WIDTH, GRID_HEIGHT = GRID_CARD_WIDTH, GRID_CARD_HEIGHT
    LIST_HEIGHT, LIST_IMAGE_WIDTH = LIST_CARD_HEIGHT, LIST_CARD_IMAGE_WIDTH
    CORNER_RADIUS, BADGE_SIZE, TAG_HEIGHT = 6, 28, 18
    PADDING, SPACING = 6, WIDGET_SPACING
    
    # Animation
    HOVER_ZOOM_SCALE, ZOOM_STEP = 1.08, 0.0125
    HOVER_ALPHA, SELECT_ALPHA = 80, 140
    
    # Chip visibility (updatable from settings)
    _chip_visibility = {'title': True, 'platform': True, 'tags': True, 'deadline': True}
    
    PLATFORM_ICONS = {"Steam": "🎮", "Epic": "🎮", "GOG": "🎮", "Origin/EA": "🎮", 
                      "Uplay": "🎮", "Xbox": "🎮", "PlayStation": "🎮", "Nintendo": "🎮"}
    RATING_LABELS = [(95, "Overwhelmingly +"), (80, "Very Positive"), (70, "Positive"), 
                     (40, "Mixed"), (20, "Negative"), (0, "Very Negative")]

    def __init__(self, theme_manager=None, parent=None, settings_manager=None):
        super().__init__(parent)
        self.theme_manager, self.settings_manager = theme_manager, settings_manager
        self._active_tag_filter = set()
        self._anim_state = {'zoom': {}, 'zoom_target': {}, 'overlay': {}, 'overlay_target': {}}
        self._parent_view = None
        
        self._zoom_timer = QTimer()
        self._zoom_timer.setInterval(16)
        self._zoom_timer.timeout.connect(self._animate)
        
        self._init_fonts()
        self._load_theme()
        self._load_chip_visibility()
        
        if hasattr(self.theme_manager, 'theme_changed'):
            try:
                self.theme_manager.theme_changed.connect(self._load_theme, Qt.ConnectionType.UniqueConnection)
            except Exception:
                pass
    
    def _animate(self):
        """Animate zoom and overlay values towards targets."""
        if not self._parent_view:
            return
        
        s = self._anim_state
        model = self._parent_view.model()
        needs_update, items = False, []
        
        for key in set(s['zoom_target']) | set(s['overlay_target']):
            # Zoom animation
            z_cur, z_tgt = s['zoom'].get(key, 1.0), s['zoom_target'].get(key, 1.0)
            if abs(z_cur - z_tgt) >= 0.001:
                s['zoom'][key] = z_cur + (self.ZOOM_STEP if z_cur < z_tgt else -self.ZOOM_STEP)
                s['zoom'][key] = max(1.0, min(self.HOVER_ZOOM_SCALE, s['zoom'][key]))
                needs_update = True
                items.append(key)
            else:
                s['zoom'][key] = z_tgt
            
            # Overlay animation
            o_cur, o_tgt = s['overlay'].get(key, 0.0), s['overlay_target'].get(key, 0.0)
            if abs(o_cur - o_tgt) >= 0.5:
                s['overlay'][key] = o_cur + (o_tgt - o_cur) * 0.22
                needs_update = True
                if key not in items:
                    items.append(key)
            else:
                s['overlay'][key] = o_tgt
            
            # Cleanup completed animations
            if z_tgt == 1.0 and o_tgt == 0.0 and s['zoom'].get(key, 1.0) == 1.0 and s['overlay'].get(key, 0.0) == 0.0:
                for d in s.values():
                    d.pop(key, None)
        
        if needs_update and model:
            for row, col in items:
                if 0 <= row < model.rowCount():
                    self._parent_view.update(model.index(row, col))
        
        if not needs_update:
            self._zoom_timer.stop()

    def _get_anim_value(self, index, is_hovered: bool, is_selected: bool) -> Tuple[float, float]:
        """Get current zoom and overlay values, updating targets as needed."""
        key = (index.row(), index.column())
        s = self._anim_state
        
        z_target = self.HOVER_ZOOM_SCALE if is_hovered else 1.0
        o_target = self.SELECT_ALPHA if is_selected else (self.HOVER_ALPHA if is_hovered else 0)
        
        if s['zoom_target'].get(key) != z_target or s['overlay_target'].get(key) != o_target:
            s['zoom_target'][key], s['overlay_target'][key] = z_target, o_target
            if not self._zoom_timer.isActive():
                self._zoom_timer.start()
        
        return s['zoom'].get(key, 1.0), s['overlay'].get(key, 0.0)

    def set_active_tag_filter(self, tags):
        self._active_tag_filter = set(tags) if tags else set()

    def _load_chip_visibility(self):
        if self.settings_manager:
            for k in self._chip_visibility:
                self._chip_visibility[k] = self.settings_manager.get_bool(f'show_{k}_chip', True)

    def update_chip_visibility(self, **kwargs):
        for k, v in kwargs.items():
            if k.startswith('show_') and k.endswith('_chip'):
                self._chip_visibility[k[5:-5]] = v

    def _init_fonts(self):
        """Initialize fonts and metrics."""
        base = QFont()
        bs = base.pointSize()
        configs = [('title_v', 3, True), ('title_h', 2, True), ('meta', max(-bs + 7, -3), False),
                   ('tag', 0, True), ('deadline', max(-bs + 7, -3), True)]
        
        self._fonts, self._metrics = {}, {}
        for key, delta, bold in configs:
            f = QFont(base)
            f.setPointSize(bs + delta)
            f.setBold(bold)
            self._fonts[key], self._metrics[key] = f, QFontMetrics(f)
        
        self._tag_sep, self._tag_pad, self._tag_space = " • ", 12, 4
        self._tag_sep_w = self._metrics['tag'].horizontalAdvance(self._tag_sep)
        
        self._used_font = QFont()
        self._used_font.setBold(True)
        self._used_font.setPointSize(12)
        m = QFontMetrics(self._used_font)
        self._used_size = (m.horizontalAdvance("USED"), m.height())

    def _load_theme(self):
        """Load theme colors."""
        theme = getattr(self.theme_manager, 'current_theme', {}) or {}
        accent, primary = theme.get('base_accent', '#1db954'), theme.get('base_primary', '#0078d4')
        bg_base = theme.get('base_background', '#252524')
        
        palette = getattr(self.theme_manager, 'get_palette', lambda: None)() if self.theme_manager else None
        
        if palette:
            self.accent_color = QColor(palette.get('accent_color', accent))
            self.primary_color = QColor(palette.get('primary_color', primary))
            self.bg_color = QColor(palette.get('bg_color', bg_base))
            self.text_color = QColor(palette.get('text_color', get_contrasting_text_color(bg_base)))
            self.badge_platform_color = QColor(palette.get('badge_platform_color', self.bg_color.name()))
            self.badge_deadline_color = QColor(palette.get('badge_deadline_color', self.accent_color.name()))
            self.badge_rating_color = QColor(palette.get('badge_rating_color', mix_colors(primary, accent, 0.5)))
        else:
            self.accent_color, self.primary_color, self.bg_color = QColor(accent), QColor(primary), QColor(bg_base)
            self.text_color = QColor(get_contrasting_text_color(bg_base))
            self.badge_platform_color = QColor(theme.get('badge_platform_color', accent))
            self.badge_deadline_color = QColor(theme.get('badge_deadline_color', primary))
            self.badge_rating_color = QColor(mix_colors(primary, accent, 0.5))

        self.glass_bg = QColor(self.bg_color)
        self.glass_bg.setAlpha(150)
        self._hover_color = QColor(self.primary_color)
        self._hover_color.setAlpha(200)
        self._text_shadow_color = QColor(0, 0, 0, 180)
        self._tag_text_color = Qt.white if self._is_dark(self.accent_color) else Qt.black
        
        # Gradients
        p, a = QColor(self.primary_color), QColor(self.accent_color)
        p.setAlpha(60)
        a.setAlpha(185)
        self._placeholder_gradient = QLinearGradient(0.0, 0.0, 0.0, 1.0)
        self._placeholder_gradient.setCoordinateMode(QGradient.ObjectBoundingMode)
        self._placeholder_gradient.setColorAt(0.0, p)
        self._placeholder_gradient.setColorAt(1.0, a)
        
        self._subtle_colors = (QColor(self.primary_color), QColor(self.accent_color))
        self._subtle_colors[0].setAlpha(35)
        self._subtle_colors[1].setAlpha(55)
        
        _cache['tag'].clear()  # Clear tag cache on theme change

    def _view_spacing(self, option) -> int:
        from PySide6.QtWidgets import QListView
        view = getattr(option, 'widget', None)
        if view and hasattr(view, 'viewMode'):
            try:
                return LIST_CARD_SPACING if view.viewMode() == QListView.ListMode else GRID_CARD_SPACING
            except Exception:
                pass
        return GRID_CARD_SPACING

    def _card_rect(self, rect: QRect, spacing: int) -> QRect:
        return rect.adjusted(2, 2, -(spacing + 2), -(spacing + 2)) if spacing > 0 else QRect(rect)

    def _is_horizontal(self, rect: QRect) -> bool:
        return rect.width() > rect.height() * 2

    def sizeHint(self, option, index):
        from PySide6.QtWidgets import QListView
        view = option.widget
        if view and hasattr(view, 'viewMode') and view.viewMode() == QListView.ListMode:
            return QSize(-1, self.LIST_HEIGHT)
        return QSize(self.GRID_WIDTH, self.GRID_HEIGHT)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        spacing = self._view_spacing(option)
        card_rect = self._card_rect(option.rect, spacing)
        
        path = QPainterPath()
        path.addRoundedRect(card_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.setClipPath(path)

        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        
        if option.widget and not self._parent_view:
            self._parent_view = option.widget

        zoom, overlay = self._get_anim_value(index, is_hovered, is_selected)
        data = self._extract_game_data(index)
        pixmap = index.data(GameListModel.PixmapRole)

        if self._is_horizontal(card_rect):
            self._paint_list(painter, card_rect, pixmap, data, zoom, overlay)
        else:
            self._paint_grid(painter, card_rect, pixmap, data, zoom)

        painter.setClipping(False)
        self._draw_selection(painter, card_rect, option.state)
        painter.restore()

    # ========================================================================
    # LAYOUTS
    # ========================================================================
    
    def _paint_grid(self, painter: QPainter, rect: QRect, pixmap, data: GameCardData, zoom: float = 1.0):
        """Paint grid (vertical) card layout."""
        self._draw_bg_image(painter, rect, pixmap, zoom)
        
        show_title, show_tags = self._chip_visibility['title'], data.tags and self._chip_visibility['tags']
        if show_title or show_tags:
            title_w = rect.width() - (self.PADDING * 2 + 4)
            title_h = self._measure_text(self._metrics['title_v'], title_w, data.title) if show_title else 0
            panel_h = self.PADDING + (title_h + self.SPACING if show_title else 0)
            panel_h += (self.SPACING if show_title else 0) + self.TAG_HEIGHT if show_tags else 0
            panel_h += self.PADDING
            
            panel = QRect(rect.left(), rect.bottom() - panel_h + 1, rect.width(), panel_h)
            painter.fillRect(panel, self.glass_bg)
            
            if show_title and title_h > 0:
                painter.setFont(self._fonts['title_v'])
                painter.setPen(self.text_color)
                painter.drawText(QRect(panel.left() + self.PADDING + 2, panel.top() + self.PADDING, title_w, title_h + 4), Qt.TextWordWrap, data.title)
            
            if show_tags:
                self._draw_tags(painter, panel, data.tags, True)
        
        self._draw_badges(painter, rect, data)
        if data.is_used:
            self._draw_used_overlay(painter, rect)

    def _paint_list(self, painter: QPainter, rect: QRect, pixmap, data: GameCardData, zoom: float = 1.0, overlay: float = 0.0):
        """Paint list (horizontal) card layout."""
        img_rect = QRect(rect.left(), rect.top(), self.LIST_IMAGE_WIDTH, rect.height())
        content = QRect(rect.left() + self.LIST_IMAGE_WIDTH, rect.top(), rect.width() - self.LIST_IMAGE_WIDTH, rect.height())

        self._draw_bg_image(painter, img_rect, pixmap, zoom)
        painter.fillRect(content, self.glass_bg)
        
        # Always draw subtle gradient overlay, with extra alpha boost on hover/select
        grad = QLinearGradient(0.0, 1.0, 1.0, 0.5)
        grad.setCoordinateMode(QGradient.ObjectBoundingMode)
        c1, c2 = QColor(self._subtle_colors[0]), QColor(self._subtle_colors[1])
        if overlay > 0.5:
            b = int(max(0, min(255, overlay)))
            c1.setAlpha(min(255, c1.alpha() + b))
            c2.setAlpha(min(255, c2.alpha() + b))
        grad.setColorAt(0.0, c1)
        grad.setColorAt(0.5, c1)
        grad.setColorAt(1.0, c2)
        painter.fillRect(content, grad)
        
        if self._chip_visibility['title']:
            painter.setFont(self._fonts['title_h'])
            painter.setPen(self.text_color)
            title_rect = QRect(content.left() + self.PADDING, content.top() + self.PADDING, 
                               content.width() - self.PADDING * 2, self._metrics['title_h'].height())
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, data.title)
        
        if data.tags and self._chip_visibility['tags']:
            tag_rect = QRect(content.left(), content.bottom() - self.PADDING - self.TAG_HEIGHT, content.width(), self.TAG_HEIGHT)
            self._draw_tags(painter, tag_rect, data.tags, False)
        
        self._draw_badges(painter, content, data)
        if data.is_used:
            self._draw_used_overlay(painter, rect)

    def _draw_badges(self, painter, rect, data: GameCardData):
        """Draw platform/rating/deadline badges at top-right, flush with no gaps."""
        cv = self._chip_visibility
        show_platform = cv['platform']
        show_deadline = cv['deadline'] and data.deadline_enabled
        show_rating = cv['platform'] and data.platform == "Steam" and data.steam_review_score is not None

        if not (show_platform or show_deadline or show_rating):
            return

        H, PX, ICON_GAP = 24, 8, 6
        painter.setFont(self._fonts['tag'])
        metrics = self._metrics['tag']
        painter.setPen(Qt.white)

        # Build badge list (right-to-left order: platform first, then rating, then deadline)
        badges = []
        if show_platform:
            icon = "📦" if data.dlc_enabled else ""
            badges.append(('platform', (data.platform or "UNKNOWN").upper(), self.badge_platform_color, icon))
        if show_rating:
            label = next((l for t, l in self.RATING_LABELS if data.steam_review_score >= t), "N/A")
            badges.append(('rating', label, self.badge_rating_color, ""))
        if show_deadline:
            badges.append(('deadline', f"⌛ {data.deadline_text}", self.badge_deadline_color, ""))

        # Calculate total width first to position from right edge
        widths = []
        for kind, text, bg, icon in badges:
            text_w = metrics.horizontalAdvance(text)
            icon_w = metrics.horizontalAdvance(icon) if icon else 0
            w = PX * 2 + text_w + (ICON_GAP + icon_w if icon else 0)
            widths.append(w)
        
        # Start from right edge of rect (use right() + 1 since right() is inclusive)
        x = rect.right() + 1
        y = rect.top()
        r = self.CORNER_RADIUS
        last_idx = len(badges) - 1

        for i, ((kind, text, bg, icon), w) in enumerate(zip(badges, widths)):
            x -= w  # Move left by badge width
            # Use explicit coordinates to avoid Qt's inclusive right()/bottom() issue
            bx, by, bw, bh = x, y, w, H
            br = QRect(bx, by, bw, bh)
            round_bl = (i == last_idx)
            
            # Draw badge shape using explicit math (bx+bw and by+bh for true edges)
            path = QPainterPath()
            path.moveTo(bx, by)
            path.lineTo(bx + bw, by)
            path.lineTo(bx + bw, by + bh)
            if round_bl:
                path.lineTo(bx + r, by + bh)
                path.arcTo(bx, by + bh - 2*r, 2*r, 2*r, 270, -90)
            else:
                path.lineTo(bx, by + bh)
            path.closeSubpath()
            painter.fillPath(path, bg)
            # Prevent 1px hairline gaps on fractional DPI (e.g. 150% scaling)
            x += 1
            
            # Draw text/icon
            icon_w = metrics.horizontalAdvance(icon) if icon else 0
            if icon:
                cr = br.adjusted(PX, 0, -PX, 0)
                painter.drawText(cr.left(), cr.top(), icon_w, cr.height(), Qt.AlignVCenter, icon)
                painter.drawText(cr.adjusted(icon_w + ICON_GAP, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
            else:
                painter.drawText(br, Qt.AlignCenter, text)

    # ========================================================================
    # HELPERS
    # ========================================================================
    
    def _extract_game_data(self, index) -> GameCardData:
        """Extract game data from model index."""
        ignored = SteamIntegration.IGNORED_TAGS
        tags_text = index.data(GameListModel.TagsRole) or ""
        tags = [t.strip() for t in tags_text.split(',') if t.strip() and t.strip().lower() not in ignored]
        
        deadline_enabled = bool(index.data(GameListModel.DeadlineEnabledRole))
        deadline_text = self._format_deadline(index.data(GameListModel.DeadlineAtRole)) if deadline_enabled else ""
        
        return GameCardData(
            title=index.data(GameListModel.TitleRole) or "",
            platform=index.data(GameListModel.PlatformRole) or "",
            tags=tags,
            deadline_enabled=deadline_enabled,
            deadline_text=deadline_text,
            dlc_enabled=bool(index.data(GameListModel.DlcEnabledRole)),
            is_used=bool(index.data(GameListModel.IsUsedRole)),
            steam_review_score=index.data(GameListModel.SteamReviewScoreRole),
        )

    def _draw_bg_image(self, painter, rect, pixmap, zoom: float = 1.0):
        """Draw background image with zoom effect."""
        if not pixmap or pixmap.isNull():
            painter.fillRect(rect, self._placeholder_gradient)
            return
        
        key = (pixmap.cacheKey(), rect.width(), rect.height())
        scaled = _cache_get('pixmap', key, lambda: pixmap.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.FastTransformation))
        
        x_off, y_off = (scaled.width() - rect.width()) // 2, (scaled.height() - rect.height()) // 2
        src = QRect(x_off, y_off, rect.width(), rect.height())
        
        if zoom > 1.0:
            z = int(rect.width() * (zoom - 1) / 2), int(rect.height() * (zoom - 1) / 2)
            src = src.adjusted(z[0], z[1], -z[0], -z[1])
        
        painter.drawPixmap(rect, scaled, src)

    def _draw_used_overlay(self, painter, rect):
        """Draw 'USED' pattern overlay."""
        painter.save()
        painter.fillRect(rect, QColor(80, 80, 80, 70))
        
        dpr = getattr(painter.device(), 'devicePixelRatioF', lambda: 1.0)()
        key = (rect.width(), rect.height(), int(dpr * 100), self._used_font.family(), self._used_font.pointSize())
        
        def create_pattern():
            w, h, dpr_val = rect.width(), rect.height(), max(1.0, dpr)
            pix = QPixmap(int(w * dpr_val), int(h * dpr_val))
            try:
                pix.setDevicePixelRatio(dpr_val)
            except:
                pass
            pix.fill(Qt.transparent)
            
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            p.setFont(self._used_font)
            p.translate(w / 2, h / 2)
            p.rotate(-45)
            
            tw, th = self._used_size
            sx, sy = tw + 30, th + 30
            diag = int((w**2 + h**2)**0.5)
            tiles_x, tiles_y = diag // sx + 4, diag // sy + 4
            
            p.setPen(QColor(255, 255, 255, 120))
            for i in range(int(tiles_y)):
                for j in range(int(tiles_x)):
                    p.drawText(int(-(tiles_x * sx) // 2 + j * sx), int(-(tiles_y * sy) // 2 + i * sy), "USED")
            p.end()
            return pix
        
        pix = _cache_get('pattern', key, create_pattern)
        if pix and not pix.isNull():
            painter.drawPixmap(rect.topLeft(), pix)
        painter.restore()

    def _draw_tags(self, painter, panel_rect, tags, fixed_bottom=True):
        """Draw combined tag chip with overflow."""
        tag_y = panel_rect.bottom() - self.PADDING - self.TAG_HEIGHT if fixed_bottom else panel_rect.top()
        tag_x = panel_rect.left() + self.PADDING + 2
        avail_w = panel_rect.right() - self.PADDING - 2 - tag_x
        
        metrics = self._metrics['tag']
        painter.setFont(self._fonts['tag'])
        
        # Cache tag layout calculation
        key = (tuple(tags), avail_w)
        layout = _cache_get('tag', key, lambda: self._calc_tag_layout(tags, metrics, avail_w))
        text, width, overflow, overflow_w = layout
        
        if not text:
            return
        
        self._draw_tag_chip(painter, tag_x, tag_y, width, text)
        if overflow:
            self._draw_tag_chip(painter, tag_x + width + self._tag_space, tag_y, overflow_w, overflow)

    def _calc_tag_layout(self, tags, metrics, avail_w):
        """Calculate combined tag text and overflow."""
        if not tags:
            return None, 0, None, 0
        
        max_overflow = f"+{len(tags)}"
        max_overflow_w = metrics.horizontalAdvance(max_overflow) + self._tag_pad + self._tag_space
        
        visible, text_w = [], 0
        for i, tag in enumerate(tags):
            tag_w = metrics.horizontalAdvance(tag)
            new_w = (text_w + self._tag_sep_w + tag_w) if visible else tag_w
            chip_w = new_w + self._tag_pad
            need_overflow = i < len(tags) - 1
            
            if chip_w + (max_overflow_w if need_overflow else 0) <= avail_w:
                visible.append(tag)
                text_w = new_w
            else:
                break
        
        if not visible:
            # Truncate first tag
            max_text = avail_w - self._tag_pad - max_overflow_w - metrics.horizontalAdvance("...")
            if max_text > 0:
                truncated = metrics.elidedText(tags[0], Qt.ElideRight, int(max_text))
                if truncated and truncated != "...":
                    visible.append(truncated)
                    text_w = metrics.horizontalAdvance(truncated)
        
        if not visible:
            return None, 0, None, 0
        
        combined = self._tag_sep.join(visible)
        combined_w = metrics.horizontalAdvance(combined) + self._tag_pad
        hidden = len(tags) - len(visible)
        
        if hidden > 0:
            overflow = f"+{hidden}"
            return combined, combined_w, overflow, metrics.horizontalAdvance(overflow) + self._tag_pad
        return combined, combined_w, None, 0

    def _draw_tag_chip(self, painter, x, y, w, text):
        """Draw a single tag chip."""
        rect = QRect(x, y, w, self.TAG_HEIGHT)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent_color)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(self._tag_text_color)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _measure_text(self, metrics: QFontMetrics, width: int, text: str) -> int:
        """Return wrapped text height."""
        if not text:
            return 0
        return metrics.boundingRect(QRect(0, 0, max(1, width), 1000), Qt.TextWordWrap, text).height()

    def _format_deadline(self, val):
        """Format deadline to DD/MM/YYYY."""
        try:
            if isinstance(val, (_date, datetime)):
                return f"{val.day:02d}/{val.month:02d}/{val.year:04d}"
            s = str(val).strip()[:10].replace('/', '-').split('-')
            if len(s) == 3 and len(s[0]) == 4:
                return f"{int(s[2]):02d}/{int(s[1]):02d}/{int(s[0]):04d}"
        except:
            pass
        return "N/A"

    def _draw_selection(self, painter, rect, state):
        """Draw selection/hover effects."""
        if not self._is_horizontal(rect):
            if state & QStyle.State_Selected:
                painter.setPen(QPen(self.primary_color, 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
            elif state & QStyle.State_MouseOver:
                painter.setPen(QPen(self._hover_color, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

    def _is_dark(self, color: QColor) -> bool:
        r, g, b, _ = color.getRgb()
        return (0.299 * r + 0.587 * g + 0.114 * b) < 127.5

"""
Background update manager for SteamKM2
Runs an automatic update check on an interval and emits signals with results.
Uses threading to avoid blocking the main UI.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Literal, List
from PySide6.QtCore import QObject, QTimer, Signal, QThread
from PySide6.QtWidgets import QApplication
import sys
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
import platform
from urllib.request import Request, urlopen


# Pre-compile regex for version parsing
import re
_VERSION_PATTERN = re.compile(r'(\d+)')


def _human_size(n: int) -> str:
    """Convert bytes to human-readable size string."""
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if n < 1024.0 or unit == 'GB':
            return f"{n:.1f} {unit}" if unit != 'bytes' else f"{n} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _parse_version(v: str) -> tuple:
    """Parse version string to comparable tuple. Cached for performance."""
    if not v:
        return (0,)
    nums = tuple(int(x) for x in _VERSION_PATTERN.findall(v))
    return nums if nums else (0,)


def _version_leq(a: str, b: str) -> bool:
    """Return True if version a <= b (semver-ish)."""
    pa, pb = _parse_version(a), _parse_version(b)
    # Pad to equal length for comparison
    max_len = max(len(pa), len(pb))
    return pa + (0,) * (max_len - len(pa)) <= pb + (0,) * (max_len - len(pb))


# Cache platform check at module level
_IS_WINDOWS = platform.system().lower() == 'windows'


def _choose_asset(assets: List[dict]) -> Optional[dict]:
    """Pick the best asset to download for the current platform.
    
    Single-pass algorithm with priority scoring:
    - Windows .exe: priority 3
    - Windows .zip: priority 2  
    - Any .zip: priority 1
    - Fallback: priority 0
    """
    if not assets:
        return None
    
    best_asset = None
    best_priority = -1
    
    for asset in assets:
        name = str(asset.get('name', '')).lower()
        priority = 0
        
        if _IS_WINDOWS:
            if name.endswith('.exe'):
                priority = 3
            elif 'windows' in name and name.endswith('.zip'):
                priority = 2
            elif name.endswith('.zip'):
                priority = 1
        else:
            if name.endswith('.zip'):
                priority = 1
        
        if priority > best_priority:
            best_priority = priority
            best_asset = asset
            if priority == 3:  # Max priority found, no need to continue
                break
    
    return best_asset if best_asset else assets[0]


class UpdateCheckWorker(QThread):
    """Worker thread for performing update checks without blocking the UI."""
    
    check_completed = Signal(dict)
    
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._settings = settings_manager
    
    def run(self):
        """Perform the update check in a background thread."""
        try:
            result = self._do_github_check()
            self.check_completed.emit(result)
        except Exception as ex:
            self.check_completed.emit({
                'state': 'error',
                'error': str(ex),
                'info': None,
                'releases': []
            })
    
    def _do_github_check(self) -> dict:
        """Check GitHub releases for updates based on settings."""
        try:
            app = QApplication.instance()
            current_version = (app.applicationVersion() if app else '') or '0.0.0'
            owner_repo = str(self._settings.get('update_repo', 'Stick-bon/SteamKM2-Sonnet')).strip()
            include_pre = self._settings.get_bool('update_include_prereleases', False)
            token = self._settings.get('github_api_token', '') or ''
            
            if not owner_repo or '/' not in owner_repo:
                raise RuntimeError('Invalid update repository. Use format owner/repo.')
            
            releases = self._github_get_json(f'https://api.github.com/repos/{owner_repo}/releases', token)
            if not isinstance(releases, list):
                releases = []
            
            # Single pass: filter releases (for UI) and find best candidate
            filtered: List[Dict[str, Any]] = []
            best_release = None
            
            for rel in releases:
                # Skip drafts
                if rel.get('draft'):
                    continue
                # Skip prereleases if not included
                is_prerelease = rel.get('prerelease')
                if is_prerelease and not include_pre:
                    continue
                
                tag_full = rel.get('tag_name') or ''
                ver = tag_full.lstrip('vV')
                
                # Determine if this version is skipped, but always include it in the changelog list.
                is_skipped = self._settings.is_version_skipped(ver)
                
                # Add to filtered list for UI (include asset info so UI can download older versions)
                asset = _choose_asset(rel.get('assets') or [])
                asset_name = asset.get('name', '') if asset else ''
                asset_size = asset.get('size', 0) if asset else 0
                download_url = (
                    asset.get('browser_download_url')
                    if asset
                    else (rel.get('zipball_url') or '')
                )
                filtered.append({
                    'tag': tag_full or ver,
                    'version': ver,
                    'body': rel.get('body') or '',
                    'published_at': rel.get('published_at') or '',
                    'asset_name': asset_name,
                    'download_url': download_url,
                    'file_size': _human_size(asset_size) if asset_size else '',
                    'file_size_bytes': asset_size,
                    'is_exe': asset_name.lower().endswith('.exe') if asset_name else False,
                    'skipped': is_skipped,
                })
                
                # Compare version numbers to find the truly latest release
                # Don't consider skipped versions when deciding which release is available.
                if not is_skipped:
                    if best_release is None:
                        best_release = rel
                    else:
                        best_ver = (best_release.get('tag_name') or '').lstrip('vV')
                        # If this version is newer than current best, use it
                        if not _version_leq(ver, best_ver):
                            best_release = rel
            
            if not best_release:
                return {'state': 'none', 'info': None, 'error': None, 'releases': filtered}
            
            latest_tag = (best_release.get('tag_name') or '').lstrip('vV')
            if _version_leq(latest_tag, current_version):
                return {'state': 'none', 'info': None, 'error': None, 'releases': filtered}
            
            asset = _choose_asset(best_release.get('assets') or [])
            asset_name = asset.get('name', '') if asset else ''
            asset_size = asset.get('size', 0) if asset else 0
            
            info: Dict[str, Any] = {
                'version': latest_tag,
                'tag': best_release.get('tag_name') or latest_tag,
                'file_size': _human_size(asset_size) if asset_size else '',
                'file_size_bytes': asset_size,
                'changelog': best_release.get('body') or '',
                'download_url': asset.get('browser_download_url') if asset else (best_release.get('zipball_url') or ''),
                'asset_name': asset_name,
                'is_exe': asset_name.lower().endswith('.exe'),
            }
            
            return {'state': 'available', 'info': info, 'error': None, 'releases': filtered}
            
        except Exception as ex:
            return {'state': 'error', 'error': str(ex), 'info': None, 'releases': []}
    
    def _github_get_json(self, url: str, token: str = '') -> Any:
        req = Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'SteamKM2-Updater'})
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))


class DownloadWorker(QThread):
    """Worker thread for downloading updates with progress reporting."""
    
    progress = Signal(int, int)  # bytes_downloaded, total_bytes
    download_completed = Signal(str)  # path to downloaded file
    download_error = Signal(str)  # error message
    
    def __init__(self, url: str, asset_name: str, token: str = '', download_dir: str = None, simulate: bool = False, parent=None):
        super().__init__(parent)
        self._url = url
        self._asset_name = asset_name
        self._token = token
        self._download_dir = download_dir
        self._cancelled = False
        self._simulate = simulate
        self._simulate_size = 15 * 1024 * 1024  # 15 MB simulated download
    
    def cancel(self):
        """Request cancellation of the download."""
        self._cancelled = True
    
    def run(self):
        """Download the file with progress reporting."""
        if self._simulate:
            self._run_simulated()
            return
        
        try:
            req = Request(self._url, headers={'User-Agent': 'SteamKM2-Updater'})
            if self._token:
                req.add_header('Authorization', f'Bearer {self._token}')
            
            temp_dir = None
            if self._download_dir:
                target_dir = self._download_dir
                os.makedirs(target_dir, exist_ok=True)
            else:
                temp_dir = tempfile.mkdtemp(prefix='skm2_update_')
                target_dir = temp_dir
                
            filename = self._asset_name or os.path.basename(self._url.split('?')[0]) or 'update'
            path = os.path.join(target_dir, filename)
            
            with urlopen(req, timeout=120) as resp:
                total_size = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                chunk_size = 131072  # 128KB chunks for better throughput, need to increase so updates are faster
                last_progress_emit = 0
                progress_threshold = max(total_size // 200, 32768)  # Emit ~200 updates or every 32KB min
                
                with open(path, 'wb') as f:
                    while True:
                        if self._cancelled:
                            # Clean up partial download
                            try:
                                f.close()
                                os.remove(path)
                                if temp_dir:
                                    shutil.rmtree(temp_dir, ignore_errors=True)
                            except Exception:
                                pass
                            self.download_error.emit("Download cancelled")
                            return
                        
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Throttle progress emissions to reduce UI overhead
                        if downloaded - last_progress_emit >= progress_threshold or downloaded == total_size:
                            self.progress.emit(downloaded, total_size)
                            last_progress_emit = downloaded
            
            self.download_completed.emit(path)
            
        except Exception as ex:
            self.download_error.emit(str(ex))
    
    def _run_simulated(self):
        """Run a simulated download for testing UI."""
        import time
        
        total_size = self._simulate_size
        downloaded = 0
        chunk_size = 50 * 1024  # 50KB per "chunk" for slower progress
        
        # Simulate download over ~15 seconds
        while downloaded < total_size:
            if self._cancelled:
                self.download_error.emit("Download cancelled")
                return
            
            # Simulate network delay (~15 seconds for 15MB at 50KB chunks)
            time.sleep(0.05)  # 50ms between chunks = ~15 seconds total
            
            downloaded += chunk_size
            if downloaded > total_size:
                downloaded = total_size
            
            self.progress.emit(downloaded, total_size)
        
        # Create a dummy file for staging
        tmpdir = tempfile.mkdtemp(prefix='skm2_update_')
        filename = self._asset_name or 'simulated_update.exe'
        path = os.path.join(tmpdir, filename)
        
        # Write a small placeholder file
        with open(path, 'w') as f:
            f.write("SIMULATED UPDATE FILE - NOT A REAL EXECUTABLE")
        
        self.download_completed.emit(path)


class UpdateManager(QObject):
    """Periodically checks for updates in the background.

    Signals:
        update_check_started: Emitted when a background check starts
        update_available(dict): Emitted with update info when an update is found
        no_update: Emitted when no update is available
        update_error(str): Emitted when an error occurs
        download_started: Emitted when download begins
        download_progress(int, int): bytes_downloaded, total_bytes
        download_completed(str): Emitted with path to downloaded file
        download_error(str): Emitted when download fails
    """

    update_check_started = Signal()
    update_available = Signal(dict)
    no_update = Signal()
    update_error = Signal(str)
    
    # Download signals
    download_started = Signal()
    download_progress = Signal(int, int)  # bytes_downloaded, total_bytes
    download_completed = Signal(str)  # path to downloaded file
    download_error = Signal(str)

    DEFAULT_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes

    def __init__(self, settings_manager, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._settings = settings_manager
        self._timer = QTimer(self)
        
        try:
            mins = int(self._settings.get_int('update_check_interval_min', 5))
            interval_ms = max(1, mins) * 60 * 1000
        except Exception:
            interval_ms = self.DEFAULT_INTERVAL_MS
        
        self._timer.setInterval(interval_ms)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._maybe_check)
        self._enabled = bool(self._settings.get_bool('auto_update_check', True))
        
        # State tracking
        self._last_state: Literal['unknown', 'available', 'none', 'error'] = 'unknown'
        self._last_info: Optional[Dict[str, Any]] = None
        self._last_error: Optional[str] = None
        self._in_progress: bool = False
        self._known_releases: List[Dict[str, Any]] = []
        
        # Download state
        self._download_worker: Optional[DownloadWorker] = None
        self._is_downloading: bool = False

    def start(self):
        """Start background checking according to current settings."""
        self.set_enabled(self._enabled)

    def stop(self):
        """Stop background checking."""
        self._timer.stop()
        self.cancel_download()

    def set_enabled(self, enabled: bool):
        """Enable or disable background checks and persist setting."""
        self._enabled = bool(enabled)
        try:
            self._settings.set('auto_update_check', self._enabled)
        except Exception:
            pass
        if self._enabled:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def set_interval_ms(self, interval_ms: int):
        """Adjust the background check interval (milliseconds)."""
        if interval_ms <= 0:
            return
        self._timer.setInterval(interval_ms)
        try:
            self._settings.set('update_check_interval_min', max(1, int(interval_ms / 60000)))
        except Exception:
            pass

    def set_interval_min(self, minutes: int):
        """Convenience wrapper to set interval in minutes."""
        self.set_interval_ms(max(1, int(minutes)) * 60 * 1000)

    def trigger_check_now(self):
        """Manually trigger a background-style check immediately."""
        self._do_check()

    def trigger_test_update(self, info: Optional[Dict[str, Any]] = None):
        """Emit a synthetic update_available for testing with simulated download."""
        if info is None:
            info = {
                'version': '9.9.9-dev',
                'tag': 'v9.9.9-dev',
                'file_size': '15.0 MB',
                'file_size_bytes': 15728640,
                'changelog': 'DEV: This is a simulated update for testing.\n\n'
                             '• Tests download progress bar\n'
                             '• Tests notification sync\n'
                             '• Tests page navigation during download\n'
                             '• No actual files are downloaded',
                'download_url': 'simulated://test-update',
                'asset_name': 'SteamKM2-dev-update.exe',
                'is_exe': True,
                '_simulated': True,  # Flag to trigger simulated download
            }
        self._last_state = 'available'
        self._last_info = info
        self._last_error = None
        self.update_available.emit(info)

    def get_last_result(self) -> Dict[str, Any]:
        """Return the last known result."""
        return {
            'state': self._last_state,
            'info': self._last_info,
            'error': self._last_error,
            'in_progress': self._in_progress,
        }

    def get_known_releases(self) -> List[Dict[str, Any]]:
        """Return cached list of known releases."""
        return list(self._known_releases)

    def get_changelog_file_path(self) -> str:
        """Get the path to the local changelog cache file."""
        app_data = self._settings.get_app_data_dir()
        return os.path.join(app_data, 'changelog_cache.json')

    def save_changelog_to_file(self, releases: List[Dict[str, Any]]) -> bool:
        """Save changelog data from releases to a local file.
        
        This allows viewing the changelog even when offline.
        
        Args:
            releases: List of release dictionaries with version, body, etc.
            
        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            changelog_path = self.get_changelog_file_path()
            
            # Compile changelog data with timestamps
            changelog_data = {
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'releases': releases
            }
            
            with open(changelog_path, 'w', encoding='utf-8') as f:
                json.dump(changelog_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"[UpdateManager] Failed to save changelog: {e}")
            return False

    def load_changelog_from_file(self) -> List[Dict[str, Any]]:
        """Load changelog data from local cache file.
        
        Returns:
            List of release dictionaries, or empty list if file doesn't exist.
        """
        try:
            changelog_path = self.get_changelog_file_path()
            
            if not os.path.exists(changelog_path):
                return []
            
            with open(changelog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data.get('releases', [])
        except Exception as e:
            print(f"[UpdateManager] Failed to load changelog: {e}")
            return []

    def clear_last_result(self):
        """Clear the last check result.

        This is used by UI callers when the user explicitly skips an
        available update so that subsequent UI syncs don't re-show the
        same available update from the manager's cached state.
        """
        try:
            self._last_state = 'none'
            self._last_info = None
            self._last_error = None
            # Notify listeners that there is no update now
            self.no_update.emit()
        except Exception:
            # Best-effort: don't raise on UI requests
            pass

    def is_downloading(self) -> bool:
        """Check if a download is currently in progress."""
        return self._is_downloading

    def _maybe_check(self):
        if not self._enabled:
            return
        self._do_check()

    def _do_check(self):
        """Perform an update check in a background thread."""
        if self._in_progress:
            return
        
        self._in_progress = True
        self.update_check_started.emit()
        
        self._worker = UpdateCheckWorker(self._settings, parent=self)
        self._worker.check_completed.connect(self._on_check_completed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
    
    def _on_check_completed(self, result: dict):
        """Handle completion of background update check."""
        try:
            state = result.get('state', 'error')
            info = result.get('info')
            error = result.get('error')
            releases = result.get('releases', [])
            
            self._last_state = state
            self._last_info = info
            self._last_error = error
            self._known_releases = releases
            
            # Save changelog to file on successful check (state != 'error')
            if state != 'error' and releases:
                self.save_changelog_to_file(releases)
            
            if state == 'available':
                self.update_available.emit(info)
            elif state == 'none':
                self.no_update.emit()
            elif state == 'error':
                self.update_error.emit(error or 'Unknown error')
        finally:
            self._in_progress = False

    def start_download(self, info: Dict[str, Any]) -> bool:
        """Start downloading an update in the background.
        
        Returns True if download started, False if already downloading.
        """
        if self._is_downloading:
            return False
        
        url = info.get('download_url')
        if not url:
            self.download_error.emit('No download URL available')
            return False
        
        token = str(self._settings.get('github_api_token', '') or '')
        asset_name = info.get('asset_name', '')
        simulate = bool(info.get('_simulated', False))
        
        self._is_downloading = True
        self.download_started.emit()
        
        # Use persistent AppData directory for updates
        app_data = self._settings.get_app_data_dir()
        update_dir = os.path.join(app_data, 'Updates')
        
        self._download_worker = DownloadWorker(url, asset_name, token, download_dir=update_dir, simulate=simulate, parent=self)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.download_completed.connect(self._on_download_completed)
        self._download_worker.download_error.connect(self._on_download_error)
        self._download_worker.finished.connect(self._download_worker.deleteLater)
        self._download_worker.start()
        
        return True

    def cancel_download(self):
        """Cancel the current download if one is in progress."""
        if self._download_worker and self._is_downloading:
            self._download_worker.cancel()

    def _on_download_progress(self, downloaded: int, total: int):
        """Forward download progress."""
        self.download_progress.emit(downloaded, total)

    def _on_download_completed(self, path: str):
        """Handle download completion."""
        self._is_downloading = False
        self._download_worker = None
        self.download_completed.emit(path)

    def _on_download_error(self, error: str):
        """Handle download error."""
        self._is_downloading = False
        self._download_worker = None
        self.download_error.emit(error)

    def stage_update(self, downloaded_path: str) -> str:
        """Prepare the update for installation.
        
        For .exe files: just return the path (no extraction needed)
        For .zip files: extract to staging directory
        
        Returns the path to the staged update (file or directory).
        """
        if downloaded_path.lower().endswith('.exe'):
            # EXE file - no extraction needed
            return downloaded_path
        
        # ZIP file - extract
        staging = tempfile.mkdtemp(prefix='skm2_stage_')
        with zipfile.ZipFile(downloaded_path, 'r') as zf:
            zf.extractall(staging)
        return staging

    def apply_update_on_restart(self, staged_path: str) -> bool:
        """Apply the staged update (if any) and restart the app.

        Critical behavior for PyInstaller one-file builds:
        - Do NOT relaunch from any extracted temp folder (e.g. sys._MEIPASS)
        - Always relaunch the *real* installed executable (sys.executable)

        Returns True if an external updater/relauncher was successfully started.
        """
        if not staged_path:
            return False

        # Development mode: best-effort restart without attempting to swap binaries.
        if not getattr(sys, 'frozen', False):
            try:
                argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ''
                args = [sys.executable]
                if argv0:
                    args.append(argv0)
                    args.extend(sys.argv[1:])
                creationflags = 0
                if _IS_WINDOWS:
                    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
                        if hasattr(subprocess, flag_name):
                            creationflags |= getattr(subprocess, flag_name)
                subprocess.Popen(args, close_fds=True, creationflags=creationflags)
                return True
            except Exception:
                return False

        current_exe = os.path.realpath(sys.executable)
        pid = os.getpid()

        update_file = staged_path
        if os.path.isdir(update_file):
            # If we ever stage a folder, try to find a matching exe inside.
            expected = os.path.join(update_file, os.path.basename(current_exe))
            if os.path.exists(expected):
                update_file = expected
            else:
                candidates: List[str] = []
                try:
                    for root, _dirs, files in os.walk(update_file):
                        for fn in files:
                            if fn.lower().endswith('.exe'):
                                candidates.append(os.path.join(root, fn))
                except Exception:
                    candidates = []
                if candidates:
                    update_file = candidates[0]
                else:
                    return False

        update_file = os.path.realpath(update_file)
        if not os.path.exists(current_exe) or not os.path.exists(update_file):
            return False

        try:
            if _IS_WINDOWS:
                updater_path = os.path.join(tempfile.gettempdir(), f"skm2_updater_{pid}.bat")
                script = f"""@echo off
setlocal enableextensions

set "PID={pid}"
set "EXE={current_exe}"
set "UPDATE={update_file}"
set "BACKUP={current_exe}.bak"
set "LOG=%TEMP%\\skm2_updater_{pid}.log"

echo ==== SteamKM2 updater start ==== > "%LOG%"
echo PID=%PID%>>"%LOG%"
echo EXE=%EXE%>>"%LOG%"
echo UPDATE=%UPDATE%>>"%LOG%"
echo BACKUP=%BACKUP%>>"%LOG%"

rem Reset PyInstaller onefile environment so the relaunched EXE doesn't
rem try to reuse a deleted _MEI folder from the parent process.
echo Resetting PyInstaller env...>>"%LOG%"
set _MEIPASS2=
set _PYI_PROCESS_LEVEL=
set _PYI_PARENT_PROCESS_LEVEL=
set _PYI_ARCHIVE_FILE=
set PYINSTALLER_RESET_ENVIRONMENT=1

rem Force extraction to user temp (more reliable than C:\\Windows\\Temp)
set "TMP=%LOCALAPPDATA%\\Temp"
set "TEMP=%LOCALAPPDATA%\\Temp"
if not exist "%TEMP%" mkdir "%TEMP%" >nul 2>&1
echo TEMP=%TEMP%>>"%LOG%"
echo TMP=%TMP%>>"%LOG%"

echo Waiting briefly before copy...>>"%LOG%"
timeout /t 1 /nobreak >nul

if not exist "%UPDATE%" (
    echo ERROR: Update file missing: %UPDATE%>>"%LOG%"
    goto start_app
)

if exist "%BACKUP%" del /f /q "%BACKUP%" >>"%LOG%" 2>&1
copy /y "%EXE%" "%BACKUP%" >>"%LOG%" 2>&1

set "UPDATED="
for /L %%i in (1,1,30) do (
  echo Attempt %%i: copy update over exe...>>"%LOG%"
  copy /y "%UPDATE%" "%EXE%" >>"%LOG%" 2>&1
  if not errorlevel 1 (
    set "UPDATED=1"
    goto start_app
  )
  timeout /t 1 /nobreak >nul
)

:start_app
if not defined UPDATED (
  echo Update copy failed; restoring backup if possible...>>"%LOG%"
  if exist "%BACKUP%" copy /y "%BACKUP%" "%EXE%" >>"%LOG%" 2>&1
) else (
  echo Update copy succeeded.>>"%LOG%"
)

echo Launching: %EXE% --post-update>>"%LOG%"
start "" "%EXE%" --post-update >>"%LOG%" 2>&1
echo Done.>>"%LOG%"
endlocal
"""

                # Default encoding tends to be the most compatible with cmd.exe.
                with open(updater_path, 'w', newline='\r\n') as f:
                    f.write(script)

                creationflags = 0
                for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
                    if hasattr(subprocess, flag_name):
                        creationflags |= getattr(subprocess, flag_name)

                subprocess.Popen(
                    f'"{updater_path}"',
                    shell=True,
                    close_fds=True,
                    creationflags=creationflags,
                )
                return True

            # Non-Windows: use a small Python helper (best-effort)
            updater_path = os.path.join(tempfile.gettempdir(), f"skm2_updater_{pid}.py")
            py_script = f"""import os
import time
import shutil
import subprocess

EXE = r"{current_exe}"
UPDATE = r"{update_file}"
BACKUP = EXE + ".bak"

# Wait briefly for locks to release
time.sleep(1.0)

try:
    if os.path.exists(BACKUP):
        os.remove(BACKUP)
except Exception:
    pass

try:
    shutil.copy2(EXE, BACKUP)
except Exception:
    pass

updated = False
for _ in range(30):
    try:
        shutil.copy2(UPDATE, EXE)
        os.chmod(EXE, 0o755)
        updated = True
        break
    except Exception:
        time.sleep(1.0)

if not updated:
    try:
        if os.path.exists(BACKUP):
            shutil.copy2(BACKUP, EXE)
    except Exception:
        pass

subprocess.Popen([EXE])
"""
            with open(updater_path, 'w', encoding='utf-8') as f:
                f.write(py_script)
            subprocess.Popen([sys.executable, updater_path], close_fds=True)
            return True

        except Exception:
            return False
       

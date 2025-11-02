# -*- coding: utf-8 -*-
from __future__ import print_function
"""
#########################################################
#                                                       #
#  Rai Play Download Manager Module                     #
#  Version: 1.9                                         #
#  Created by Lululla                                   #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0/   #
#  Last Modified: 15:35 - 2025-11-02                    #
#                                                       #
#  Features:                                            #
#    - Download queue management                        #
#    - Support for HLS streams (.m3u8)                  #
#    - Automatic quality selection (2400p > 1800p > 1200p)
#    - Resume interrupted downloads                     #
#    - Progress tracking and status monitoring          #
#    - Relinker URL processing                          #
#    - Multiple concurrent downloads (configurable)     #
#    - Disk space monitoring                            #
#    - Error handling and retry logic                   #
#    - Integration with Enigma2 JobManager              #
#                                                       #
#  Technical Features:                                  #
#    - ffmpeg integration for HLS streams               #
#    - wget fallback for direct downloads               #
#    - Automatic URL validation and sanitization        #
#    - JSON-based queue persistence                     #
#    - Thread-safe operations                           #
#    - Real-time progress updates                       #
#    - Support for RaiPlay DRM content                  #
#                                                       #
#  Credits:                                             #
#    - Original development by Lululla                  #
#    - Integration with Rai Play View Plugin            #
#    - HLS stream processing logic                      #
#                                                       #
#  Usage of this code without proper attribution        #
#  is strictly prohibited.                              #
#  For modifications and redistribution,                #
#  please maintain this credit header.                  #
#########################################################
"""
__author__ = "Lululla"

# 🧠 STANDARD LIBRARIES (Python built-ins)
import json
import math
import time
import threading
from re import findall, search, sub
from os import makedirs, statvfs
from os.path import exists, getsize, join
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from Screens.MessageBox import MessageBox

# 🧩 ENIGMA2 COMPONENTS
from Components.config import config
from Components.Task import Task, Job, job_manager as JobManager

# 🌐 EXTERNAL LIBRARIES
import requests

# 🧱 LOCAL MODULES
from .RaiPlayProgressParser import RaiPlayProgressParser

# HTTP headers support - preso da IPTVPlayer
HANDLED_HTTP_HEADER_PARAMS = [
    'Host', 'Accept', 'Cookie', 'Referer', 'User-Agent',
    'Range', 'Origin', 'X-Playback-Session-Id',
    'If-Modified-Since', 'If-None-Match',
    'X-Forwarded-For', 'Authorization', 'Accept-Language'
]

# ================================
# DOWNLOAD MANAGER
# ================================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"

# Import notification system
try:
    from .notify_play import show_download_notification
    NOTIFICATION_AVAILABLE = True
except ImportError as e:
    print("[DEBUG] Notification system not available:", e)
    NOTIFICATION_AVAILABLE = False


class DownloadWorker(threading.Thread):
    """
    Background worker thread for processing download queue.
    Monitors queue and starts downloads when slots are available.
    """
    def __init__(self, manager):
        threading.Thread.__init__(self)
        self.manager = manager
        self.running = True
        self.daemon = True
        print("[DOWNLOAD WORKER] Worker instance created")

    def run(self):
        """Worker that monitors only ACTIVE downloads — does not auto-start new ones"""
        print("[DOWNLOAD WORKER] Worker thread started - monitoring ACTIVE downloads only")

        while self.running:
            try:
                # Check only the status of active downloads — do NOT start new ones
                active_count = self.manager.get_active_count()
                queued_count = len([
                    item for item in self.manager.download_queue
                    if item['status'] in ['queued', 'paused']
                ])

                if active_count > 0 or queued_count > 0:
                    print(f"[DOWNLOAD WORKER] Monitoring: {active_count} active, {queued_count} queued/paused")

                # Perform cleanup every 10 cycles (about 5 minutes)
                if int(time.time()) % 300 < 30:  # Every 5 minutes
                    self.manager.cleanup_queue()

                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                print(f"[DOWNLOAD WORKER] Error in worker loop: {e}")
                time.sleep(30)


class RaiPlayDownloadManager:
    """
    Main download manager class for RaiPlay content.
    Handles queue management, URL processing, and download execution.
    """

    def __init__(self, session=None):
        """
        Initialize download manager with configuration and storage setup.

        Args:
            session: Enigma2 session object for UI integration
        """
        self.session = session
        self.download_queue = []
        self.active_downloads = {}

        self.download_dir = config.movielist.last_videodir.value
        if not self.download_dir.endswith("/"):
            self.download_dir += "/"

        self.downloads_file = join(
            self.download_dir, "raiplay_downloads.json")

        if not exists(self.download_dir):
            try:
                makedirs(self.download_dir)
                print("[DOWNLOAD MANAGER] Created movie directory: {}".format(self.download_dir))
            except Exception as e:
                print(f"[DOWNLOAD MANAGER] Error creating movie directory: {e}")

        # Configuration
        self.max_concurrent = 2
        self.worker = None
        self.running = False

        # Initialize manager WITHOUT worker thread
        self.load_downloads()
        # self.start_worker()  # COMMENT THIS LINE
        print("[DOWNLOAD MANAGER] Manager initialized WITHOUT worker thread")

    def start_worker(self):
        """Start worker thread ONLY when needed"""
        if self.running:
            return

        print("[DOWNLOAD MANAGER] Starting worker thread")
        self.running = True
        if not self.worker:
            self.worker = DownloadWorker(self)
            self.worker.start()

    def stop_worker(self):
        """Stop the background worker thread"""
        print("[DOWNLOAD MANAGER] Stopping worker thread")
        self.running = False
        if self.worker:
            self.worker.running = False
            # Don't use join() - it causes deadlocks
            # self.worker.join(timeout=5)
            self.worker = None

    def add_download(self, title, url, quality="best"):
        """Add a new download to queue"""
        try:
            print(f"[DOWNLOAD] Adding download: {title}")

            final_url = self.get_real_video_url(url)
            clean_title = self._clean_filename(title)
            download_id = str(int(time.time() * 1000))

            # Determine file extension based on URL type
            if '.m3u8' in final_url:
                extension = ".mp4"  # ffmpeg will convert HLS to mp4
                print("[DOWNLOAD] HLS stream - will use ffmpeg")
            else:
                extension = ".mp4"  # Default for direct streams
                print("[DOWNLOAD] Direct stream - will use wget")

            file_path = join(self.download_dir, f"{clean_title}{extension}")

            download_item = {
                'id': download_id,
                'title': title,
                'clean_title': clean_title,
                'url': final_url,
                'original_url': url,
                'quality': quality,
                'status': 'paused',
                'progress': 0,
                'file_path': file_path,
                'file_size': 0,
                'downloaded_bytes': 0,
                'speed': 0,
                'eta': 0,
                'added_time': time.time(),
                'start_time': None,
                'end_time': None,
                'extension': extension
            }

            self.download_queue.append(download_item)
            self.save_downloads()

            self.session.open(MessageBox, f"📥 Added to queue: {title}", MessageBox.TYPE_INFO, timeout=3)
            print(f"[DOWNLOAD] Successfully added: {title}")
            print(
                f"[DOWNLOAD] Stream type: {
                    'HLS (.m3u8)' if '.m3u8' in final_url else 'Direct'}")
            print(f"[DOWNLOAD] Output file: {file_path}")

            return download_id

        except Exception as e:
            print(f"[DOWNLOAD] Error adding download: {e}")
            self.session.open(MessageBox, "Error adding download", MessageBox.TYPE_ERROR, timeout=5)
            import traceback
            traceback.print_exc()
            return None

    def has_pending_downloads(self):
        """
        Check if there are downloads waiting to be processed.

        Returns:
            bool: True if there are queued or paused downloads
        """
        for item in self.download_queue:
            if item['status'] in ['queued', 'paused']:
                return True
        return False

    def load_downloads(self):
        """Load download queue from file"""
        print(f"[DOWNLOAD] Loading downloads from {self.downloads_file}")
        if exists(self.downloads_file):
            try:
                with open(self.downloads_file, "r") as f:
                    content = f.read()
                    print(f"[DOWNLOAD] File content length: {len(content)}")
                    if content.strip():
                        self.download_queue = json.loads(content)
                    else:
                        self.download_queue = []
                print("[DOWNLOAD] Loaded {} downloads".format(len(self.download_queue)))
            except Exception as e:
                print(f"[DOWNLOAD] Error loading downloads: {e}")
                import traceback
                traceback.print_exc()
                self.download_queue = []
        else:
            print("[DOWNLOAD] No downloads file found")
            self.download_queue = []

    def save_downloads(self):
        """Save the download queue only if there are changes."""
        try:
            # Check if there are any real changes
            current_state = json.dumps(self.download_queue, sort_keys=True)
            
            if hasattr(self, '_last_save_state'):
                if current_state == self._last_save_state:
                    print("[DOWNLOAD] No changes - skipping save")
                    return  # No changes, do not save
            
            # Save only if there are changes
            self._last_save_state = current_state
            print(f"[DOWNLOAD] Saving {len(self.download_queue)} downloads (changes detected)")
            
            with open(self.downloads_file, "w") as f:
                json.dump(self.download_queue, f, indent=2)

            print("[DOWNLOAD] Save completed successfully")
        except Exception as e:
            print(f"[DOWNLOAD] Error while saving downloads: {e}")

    def save_movie_json_metadata(self, title, video_info):
        """Save JSON metadata in movie folder"""
        try:
            movie_dir = config.movielist.last_videodir.value
            if not movie_dir.endswith('/'):
                movie_dir += '/'

            clean_title = self._clean_filename(title)
            json_filename = f"{clean_title}.json"
            json_path = join(movie_dir, json_filename)

            # Ensure all values exist and are serializable
            safe_video_info = {
                'title': str(video_info.get('title', '')),
                'file_path': str(video_info.get('file_path', '')),
                'file_size': int(video_info.get('file_size', 0)),
                'download_time': float(video_info.get('download_time', time.time())),
                'url': str(video_info.get('url', ''))
                # Don't include 'quality' if it doesn't exist
            }

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(safe_video_info, f, indent=2, ensure_ascii=False)

            print(f"[DOWNLOAD] JSON metadata saved to: {json_path}")
            return True

        except Exception as e:
            print(f"[DOWNLOAD] Error saving JSON metadata: {e}")
            return False

    def cleanup_queue(self):
        """Clean up the queue - remove completed/error downloads and clean files"""
        print("[DOWNLOAD] Cleaning up download queue...")

        items_to_remove = []

        for item in self.download_queue:
            # Remove completed downloads older than 1 hour
            if item['status'] == 'completed':
                if item.get('end_time'):
                    # Remove if completed more than 1 hour ago
                    if time.time() - item['end_time'] > 3600:
                        items_to_remove.append(item)
                        print(f"[DOWNLOAD] Removing old completed: {item['title']}")

            # Remove error downloads that can't be recovered
            elif item['status'] == 'error':
                # Keep recent errors for retry, remove old ones
                if item.get('added_time') and time.time() - item['added_time'] > 86400:  # 24 hours
                    items_to_remove.append(item)
                    print(f"[DOWNLOAD] Removing old error: {item['title']}")

        # Remove the items
        for item in items_to_remove:
            self.download_queue.remove(item)

        if items_to_remove:
            self.save_downloads()
            print(f"[DOWNLOAD] Cleanup removed {len(items_to_remove)} items")

        return len(items_to_remove)

    def start_download(self, item):
        """Start a paused download - WITH URL VALIDATION"""
        if item['status'] in ['completed', 'error']:
            print(f"[DOWNLOAD] Cannot start download with status: {item['status']}")
            return

        try:
            print(f"[DOWNLOAD] Starting download: {item['title']}")
            final_url = item['url']

            # CRITICAL CHECK: Ensure it's a valid video URL
            if not self.is_video_url(final_url):
                print(f"[DOWNLOAD] ERROR: URL is not a valid video: {final_url}")
                print("[DOWNLOAD] This appears to be an image or invalid URL")
                self.update_download_status(item['id'], "error", 0)

                self.session.open(MessageBox, "Invalid video URL detected", MessageBox.TYPE_ERROR, timeout=5)
                return

            # Continue with normal download process...
            cmd = self.build_download_command(final_url, item['file_path'], False)
            self.update_download_status(item['id'], "downloading", 1)

            job = RaiPlayDownloadJob(self, cmd, item['file_path'], item['title'], item['id'])
            JobManager.AddJob(job)

            print(f"[DOWNLOAD] Download job started: {item['title']}")

        except Exception as e:
            print(f"[DOWNLOAD] Error starting download: {e}")
            import traceback
            traceback.print_exc()
            self.update_download_status(item['id'], "error", 0)

    def pause_download(self, download_id):
        """Pause a download"""
        for item in self.download_queue:
            if item['id'] == download_id and item['status'] in ['downloading', 'waiting']:
                # Cancel the job
                for job in JobManager.getPendingJobs():
                    if hasattr(job, 'download_id') and job.download_id == download_id:
                        job.cancel()
                        break

                # Update status - notification will be handled in update_download_status
                self.update_download_status(download_id, "paused")
                print(f"[DOWNLOAD] Paused: {item['title']}")
                break

    def remove_download(self, download_id):
        """Remove a download from queue WITHOUT deleting the file - FIXED VERSION"""
        item_to_remove = None
        for item in self.download_queue:
            if item['id'] == download_id:
                item_to_remove = item
                break

        if item_to_remove:
            if item_to_remove['status'] in ['downloading', 'waiting']:
                self.pause_download(download_id)

            # Do NOT remove the file from the filesystem
            self.download_queue.remove(item_to_remove)
            self.save_downloads()
            print("[DOWNLOAD] Removed from queue (file preserved): {}".format(item_to_remove['title']))

            self.session.open(MessageBox, f"Removed from queue: {item_to_remove['title']}", MessageBox.TYPE_INFO, timeout=3)

    def updateList(self):
        """Update download list - hide completed downloads"""
        self.names = []

        for item in self.download_manager.get_queue():
            # OPZIONE: Nascondi i download completati
            if item['status'] == 'completed':
                continue  # Salta i completati

            status_icons = {
                'paused': '⏸️',
                'downloading': '⬇️',
                'completed': '✅',
                'error': '❌'
            }
            icon = status_icons.get(item['status'], '❓')

            if item['status'] == 'completed' and item.get('file_size', 0) > 0:
                size_mb = item['file_size'] / (1024 * 1024)
                status_text = f" - {size_mb:.1f}MB"
            elif item['status'] == 'downloading':
                status_text = " - Downloading..."
            else:
                status_text = ""

            name = f"{icon} {item['title']}{status_text}"
            self.names.append(name)

        self['text'].setList(self.names)
        self.save_downloads()

    def update_download_status(self, download_id, status, progress=0):
        """Update download status and progress by ID - WITH HYBRID NOTIFICATIONS"""
        print(f"[DOWNLOAD] update_download_status - ID: {download_id}, Status: {status}, Progress: {progress}")

        for item in self.download_queue:
            if item['id'] == download_id:
                old_status = item['status']

                if status == "error":
                    item['status'] = "error"
                    item['progress'] = 0
                    print(f"[DOWNLOAD] Download error: {item['title']}")
                    # HYBRID NOTIFICATION: Error
                    show_download_notification(item['title'], 'error')
                else:
                    item['status'] = status
                    item['progress'] = progress

                print(f"[DOWNLOAD] Status changed: {old_status} -> {status}")

                # Update file size if downloading
                if status == "downloading" and exists(item['file_path']):
                    try:
                        item['downloaded_bytes'] = getsize(item['file_path'])
                    except OSError:
                        pass

                # Notifications for important status changes
                if status == "downloading" and not item['start_time']:
                    item['start_time'] = time.time()
                    print(f"[DOWNLOAD] 🚀 Started: {item['title']}")
                    # HYBRID NOTIFICATION: Started
                    show_download_notification(item['title'], 'downloading')

                elif status == "completed" and not item['end_time']:
                    item['end_time'] = time.time()
                    file_size = item.get('file_size', 0)
                    print(f"[DOWNLOAD] ✅ Completed: {item['title']}")
                    # HYBRID NOTIFICATION: Completed (with size)
                    show_download_notification(item['title'], 'completed', file_size)

                elif status == "paused" and old_status == "downloading":
                    print(f"[DOWNLOAD] ⏸️ Paused: {item['title']}")
                    # HYBRID NOTIFICATION: Paused
                    show_download_notification(item['title'], 'paused')

                break

    def validate_url(self, url):
        """
        Validate URL for safety and correct format.
        Args:
            url (str): URL to validate

        Returns:
            bool: True if URL is valid and safe
        """
        try:
            if not url or not isinstance(url, str):
                return False

            # Check URL scheme
            if not url.startswith(('http://', 'https://')):
                return False

            # Check for dangerous shell injection patterns
            dangerous_patterns = [
                '`', '$', ';', '|', '&', '>', '<', '\n', '\r', '\t']
            for pattern in dangerous_patterns:
                if pattern in url:
                    print(f"[DOWNLOAD] Dangerous pattern in URL: {pattern}")
                    return False

            return True
        except Exception as e:
            print(f"[DOWNLOAD] URL validation error: {e}")
            return False

    def build_download_command(self, url, file_path, resume=False):
        """
        Build appropriate download command based on URL type.
        Args:
            url (str): Video URL
            file_path (str): Output file path
            resume (bool): Whether to resume existing download

        Returns:
            str: Shell command for downloading
        """
        print(f"[DOWNLOAD] Building download command for: {url}")

        # Use ffmpeg for HLS streams, wget for direct downloads
        if '.m3u8' in url:
            print("[DOWNLOAD] HLS stream detected, using ffmpeg")
            return self.build_ffmpeg_command(url, file_path)
        else:
            print("[DOWNLOAD] Direct video stream, using wget")
            return self.build_wget_command(url, file_path, resume)

    def build_ffmpeg_command(self, url, file_path):
        """Build ffmpeg command with detailed progress output"""
        if not file_path.endswith('.mp4'):
            file_path = file_path.rsplit('.', 1)[0] + '.mp4' if '.' in file_path else file_path + '.mp4'

        cmd_parts = [
            'ffmpeg',
            '-user_agent', f'"{USER_AGENT}"',
            '-headers', '"Referer: https://www.raiplay.it/"',
            '-i', f'"{url}"',
            '-c', 'copy',
            '-y',
            '-hide_banner',
            '-loglevel', 'warning',
            '-progress', 'pipe:1',
            '-stats_period', '1',
            f'"{file_path}"'
        ]

        cmd_str = ' '.join(cmd_parts)
        print(f"[DOWNLOAD] FFmpeg command: {cmd_str}")
        return cmd_str

    def build_wget_command(self, url, file_path, resume=False):
        """
        Build wget command for direct video downloads.

        Args:
            url (str): Direct video URL
            file_path (str): Output file path
            resume (bool): Whether to resume download

        Returns:
            str: wget command string
        """
        cmd_parts = ['wget']

        # Basic wget options
        cmd_parts.extend([
            '--progress=bar:force',
            '--no-check-certificate',
            '--timeout=30',
            '--waitretry=5',
            '--tries=3',
            '--user-agent', f'"{USER_AGENT}"'
        ])

        # RaiPlay specific headers
        cmd_parts.extend(['--header', '"Referer: https://www.raiplay.it/"'])

        # Resume support
        if resume:
            cmd_parts.append('-c')
            print("[DOWNLOAD] Resuming partial download")
        else:
            print("[DOWNLOAD] Starting new download")

        # Output and URL
        cmd_parts.extend(['-O', f'"{file_path}"', f'"{url}"'])

        cmd_str = ' '.join(cmd_parts)
        print(f"[DOWNLOAD] Wget command: {cmd_str}")
        return cmd_str

    def download_finished(self, filename, title, download_id):
        """Called when download finishes successfully"""
        for item in self.download_queue:
            if item['id'] == download_id:
                # Only update if not already completed
                if item['status'] != 'completed':
                    item['status'] = 'completed'
                    item['progress'] = 100
                    item['end_time'] = time.time()

                    # Get final file size
                    if exists(filename):
                        try:
                            item['file_size'] = getsize(filename)
                            item['downloaded_bytes'] = item['file_size']
                            video_info = {
                                'title': title,
                                'file_path': filename,
                                'file_size': item['file_size'],
                                'download_time': time.time(),
                                'url': item['url'],
                                'quality': item['quality']
                            }
                            self.save_movie_json_metadata(title, video_info)

                        except OSError:
                            pass

                    if NOTIFICATION_AVAILABLE:
                        show_download_notification(title, 'completed', item['file_size'])

                    self.save_downloads()
                    print(f"[DOWNLOAD] Completed: {title}")
                else:
                    print(f"[DOWNLOAD] Download already marked as completed: {title}")
                break

    def is_video_url(self, url):
        """Verify if URL points to a video file"""
        video_extensions = ['.mp4', '.m3u8', '.ts', '.mkv', '.avi', '.mov']
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']

        url_lower = url.lower()

        # Check for image extensions
        for ext in image_extensions:
            if ext in url_lower:
                return False

        # Check for video extensions or patterns
        for ext in video_extensions:
            if ext in url_lower:
                return True

        # Check for video patterns in URL
        video_patterns = ['/video/', '.mp4', '.m3u8', 'videoplayback', 'manifest']
        for pattern in video_patterns:
            if pattern in url_lower:
                return True

        return False

    def _extract_video_url_from_xml(self, xml_content):
        """Extract video URL from relinker XML response"""
        video_url = None

        # Pattern 1: URL in <url> tag
        url_match = search(r'<url[^>]*type="content"[^>]*>([^<]*)</url>', xml_content)
        if url_match:
            video_url = url_match.group(1).strip()
            print(f"[DOWNLOAD] Found video URL in <url> tag: {video_url}")

        # Pattern 2: URL in CDATA
        if video_url and '<![CDATA[' in video_url:
            cdata_match = search(r'<!\[CDATA\[([^\]]+)\]\]>', video_url)
            if cdata_match:
                video_url = cdata_match.group(1).strip()
                print(f"[DOWNLOAD] Extracted from CDATA: {video_url}")

        # Pattern 3: Direct URL search patterns
        if not video_url:
            video_patterns = [
                r'https?://[^\s<>\'"]+\.mp4[^\s<>\'"]*',
                r'https?://[^\s<>\'"]+\.ts[^\s<>\'"]*',
                r'https?://[^\s<>\'"]+\.m3u8[^\s<>\'"]*',
                r'https?://mediapolisvod\.rai\.it[^\s<>\'"]+',
                r'https?://cdnraivodostr\d+\.msvdn\.net[^\s<>\'"]+'
            ]

            for pattern in video_patterns:
                video_match = search(pattern, xml_content)
                if video_match:
                    candidate_url = video_match.group(0)
                    # Prefer non-HLS URLs
                    if '.m3u8' not in candidate_url:
                        video_url = candidate_url
                        print(f"[DOWNLOAD] Found non-HLS video URL: {video_url}")
                        return video_url

        print("[DOWNLOAD] No direct video URL found, will use original URL")
        return None

    def process_queue(self):
        """Process download queue - SKIP COMPLETED DOWNLOADS"""
        if not self.running:
            return

        print("[DOWNLOAD] Processing queue...")

        # Count active downloads
        active_count = len([item for item in self.download_queue
                           if item['status'] in ['downloading', 'waiting']])

        # Start queued/paused downloads if there's space
        for item in self.download_queue:
            if active_count >= self.max_concurrent:
                break

            # SKIP completed and error downloads
            if item['status'] in ['completed', 'error']:
                continue

            if item['status'] in ['queued', 'paused']:
                print(f"[DOWNLOAD] Auto-starting: {item['title']}")
                self.start_download(item)
                active_count += 1

    def process_hls_master_playlist(self, master_url):
        """
        Process HLS master playlist to select the best quality stream.

        Args:
            master_url (str): URL of HLS master playlist

        Returns:
            str: URL of the best quality stream or original URL on failure
        """
        try:
            print(f"[DOWNLOAD] Processing HLS master playlist: {master_url}")

            headers = {
                "User-Agent": USER_AGENT,
                "Referer": "https://www.raiplay.it/"
            }

            # Download master playlist
            response = requests.get(
                master_url,
                headers=headers,
                timeout=30,
                verify=False)
            response.raise_for_status()
            playlist_content = response.text

            print("[DOWNLOAD] Master playlist downloaded successfully")

            # Parse playlist to find best quality
            lines = playlist_content.split('\n')
            best_bandwidth = 0
            best_stream_url = None
            base_url = '/'.join(master_url.split('/')[:-1]) + '/'
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Look for stream information
                if line.startswith('#EXT-X-STREAM-INF:'):
                    bandwidth_match = search(r'BANDWIDTH=(\d+)', line)
                    if bandwidth_match:
                        bandwidth = int(bandwidth_match.group(1))
                        print("[DOWNLOAD] Found stream with bandwidth: {}".format(bandwidth))

                        # Get stream URL from next line
                        if i + 1 < len(lines):
                            stream_url = lines[i + 1].strip()
                            if stream_url and not stream_url.startswith('#'):
                                # Construct full URL
                                full_url = stream_url if stream_url.startswith(
                                    'http') else base_url + stream_url

                                # Select stream with highest bandwidth
                                if bandwidth > best_bandwidth:
                                    best_bandwidth = bandwidth
                                    best_stream_url = full_url
                                    print("[DOWNLOAD] New best quality: {} bps - {}".format(bandwidth, full_url))
                        i += 2  # Skip info and URL lines
                    else:
                        i += 1
                else:
                    i += 1

            if best_stream_url:
                quality = "2400p" if best_bandwidth >= 2344000 else "1800p" if best_bandwidth >= 1758000 else "1200p"
                print("[DOWNLOAD] Selected {} stream: {}".format(quality, best_stream_url))
                return best_stream_url
            else:
                print("[DOWNLOAD] No suitable stream found in master playlist")
                return master_url

        except Exception as e:
            print(f"[DOWNLOAD] Error processing HLS master playlist: {e}")
            return master_url

    def get_real_video_url(self, url):
        """
        Extract the actual video URL from RaiPlay's relinker service.
        """
        print(f"[DOWNLOAD] Processing URL through relinker: {url}")

        # If it's not a relinker URL, use it as-is
        if "relinkerServlet" not in url:
            print("[DOWNLOAD] Not a relinker URL, using as-is")
            return url

        try:
            print("[DOWNLOAD] Detected relinker URL, processing...")

            # Prepare the URL for the XML response
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query["output"] = ["64"]  # Correct format for video
            new_query = urlencode(query, doseq=True)
            relinker_url = urlunparse(parsed._replace(query=new_query))

            print(f"[DOWNLOAD] Fetching from: {relinker_url}")

            headers = {
                "User-Agent": USER_AGENT,
                "Referer": "https://www.raiplay.it/",
                "Accept": "application/xml, text/xml, */*"
            }

            # Fetch the XML response
            response = requests.get(relinker_url, headers=headers, timeout=30, verify=False)
            response.raise_for_status()
            content = response.text

            print(f"[DOWNLOAD] Response length: {len(content)}")

            # Search for video URLs in common formats
            video_patterns = [
                r'<url[^>]*>(https?://[^<]+\.mp4[^<]*)</url>',
                r'<url[^>]*>(https?://[^<]+\.m3u8[^<]*)</url>',
                r'<mediaurl[^>]*>(https?://[^<]+)</mediaurl>',
                r'https?://[^\s<>&"]+\.mp4[^\s<>&"]*',
                r'https?://[^\s<>&"]+\.m3u8[^\s<>&"]*'
            ]

            for pattern in video_patterns:
                matches = findall(pattern, content)
                for match in matches:
                    if match and any(ext in match for ext in ['.mp4', '.m3u8', '.ts']):
                        video_url = match.replace('&amp;', '&').strip()
                        print(f"[DOWNLOAD] Found video URL: {video_url}")

                        # Skip if it's an image
                        if any(img_ext in video_url.lower() for img_ext in ['.png', '.jpg', '.jpeg', '.gif']):
                            print(f"[DOWNLOAD] Skipping image URL: {video_url}")
                            continue

                        return video_url

            print("[DOWNLOAD] No valid video URL found, using original URL")
            return url

        except Exception as e:
            print(f"[DOWNLOAD] Error processing relinker: {e}")
            return url

    def get_queue(self):
        """Get current download queue"""
        # Update progress only for active downloads
        for item in self.download_queue:
            if item['status'] in ['downloading', 'waiting', 'paused']:
                # Check if file exists and update size
                if exists(item['file_path']):
                    try:
                        current_size = getsize(item['file_path'])
                        item['downloaded_bytes'] = current_size
                        if item['file_size'] > 0:
                            item['progress'] = min(99, int((current_size / item['file_size']) * 100))
                    except OSError:
                        pass

        self.save_downloads()
        return self.download_queue

    def get_active_count(self):
        """Get count of active downloads"""
        return len([item for item in self.download_queue
                   if item['status'] in ['downloading', 'waiting']])

    def get_queued_count(self):
        """Get count of queued downloads"""
        return len([item for item in self.download_queue
                   if item['status'] == 'queued'])

    def get_disk_space(self):
        """Get disk space information"""
        try:
            stat = statvfs(self.download_dir)
            free_bytes = stat.f_bfree * stat.f_bsize
            total_bytes = stat.f_blocks * stat.f_bsize
            free = convert_size(free_bytes)
            total = convert_size(total_bytes)
            return free, total
        except Exception as e:
            print(f"[DOWNLOAD] Error getting disk space: {e}")
            return "0B", "0B"

    def _clean_and_validate_url(self, url):
        """Clean and validate extracted URL - prefer direct videos over HLS"""
        if not url:
            return None

        # Remove CDATA tags and normalize
        url = url.replace('<![CDATA[', '').replace(']]>', '')
        url = url.strip()
        url = url.replace('&amp;', '&')
        url = ' '.join(url.split())

        # Ensure complete URL
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://mediapolisvod.rai.it" + url

        # Final validation
        if not url.startswith(('http://', 'https://')):
            print(f"[DOWNLOAD] Invalid URL format after cleaning: {url}")
            return None

        # Prefer direct video URLs over HLS
        if '.m3u8' in url:
            print(f"[DOWNLOAD] Warning: URL is HLS stream: {url}")
            # We'll still return it, but warn the user

        return url

    def _clean_filename(self, filename):
        """
        Clean filename for safe filesystem use.

        Args:
            filename (str): Original filename

        Returns:
            str: Cleaned filename safe for filesystem
        """
        # Remove invalid filesystem characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # Normalize spaces and trim
        filename = sub(r'\s+', ' ', filename).strip()
        filename = filename.replace(' ', '_')
        filename = sub(r'_+', '_', filename)

        return filename[:100]  # Limit length

    def _clear_completed(self):
        """Clear completed downloads"""
        self.download_queue = [item for item in self.download_queue
                               if item['status'] != 'completed']
        self.save_downloads()
        print("[DOWNLOAD] Cleared completed downloads")


class RaiPlayDownloadJob(Job):
    def __init__(self, download_manager, command_line, output_filename, content_title, unique_download_id):
        Job.__init__(self, content_title)
        self.command_line = command_line
        self.output_filename = output_filename
        self.download_manager = download_manager
        self.unique_download_id = unique_download_id
        self.download_processor = RaiPlayDownloadTask(
            self, command_line, output_filename, content_title, unique_download_id)

    def attempt_retry(self):
        """Retry failed download"""
        if self.status == self.FAILED:
            self.restart()

    def cancel_download(self):
        """Cancel download operation"""
        self.abort()


class RaiPlayDownloadTask(Task):
    def __init__(self, job, command_line, output_filename, content_title, unique_download_id):
        Task.__init__(self, job, content_title)
        self.download_handler = job.download_manager
        self.unique_download_id = unique_download_id
        self.output_filename = output_filename
        self.content_title = content_title
        self.progress_value = 0
        self.previous_progress = 0
        self.initial_run = True
        self.task_start_time = time.time()

        # Initialize custom progress parser
        self.raiplay_parser = RaiPlayProgressParser()

        # File growth tracking (fallback mechanism)
        self.previous_file_size = 0
        self.last_check_time = time.time()

        if isinstance(command_line, list):
            command_string = ' '.join(command_line)
            self.setCmdline(command_string)
        else:
            self.setCmdline(command_line)

    def processOutput(self, raw_data):
        """Process download output using custom RaiPlay parser"""
        try:
            data_string = str(raw_data)

            if "Opening 'ht" in data_string or "[https @" in data_string:
                # Skip printing these noisy logs
                pass
            else:
                print(f"[RAIPLAY TASK] {data_string.strip()}")

            # Use custom parser for FFmpeg output analysis
            progress_analysis = self.raiplay_parser.analyze_ffmpeg_output(data_string)

            # Update progress based on parser results
            if progress_analysis['completion_percentage'] > 0:
                self.progress_value = progress_analysis['completion_percentage']
                print(f"[RAIPLAY TASK] Progress update: {self.progress_value}%")

                if hasattr(self, 'download_handler') and hasattr(self, 'unique_download_id'):
                    self.download_handler.update_download_status(
                        self.unique_download_id, "downloading", self.progress_value
                    )
                    self.previous_progress = self.progress_value

            # Fallback: file growth tracking if parser doesn't provide progress
            elif progress_analysis['current_size_bytes'] > 0:
                self._update_progress_using_file_growth(progress_analysis['current_size_bytes'])

            Task.processOutput(self, raw_data)

        except Exception as processing_error:
            print(f"[RAIPLAY TASK] Error processing output: {processing_error}")
            Task.processOutput(self, raw_data)

    def _update_progress_using_file_growth(self, current_file_size):
        """Fallback progress tracking based on file growth patterns"""
        try:
            current_timestamp = time.time()

            # Calculate speed and estimate progress
            if self.previous_file_size > 0 and current_timestamp > self.last_check_time:
                time_difference = current_timestamp - self.last_check_time
                size_difference = current_file_size - self.previous_file_size

                if time_difference > 5 and size_difference > 0:  # Every 5 seconds with growth
                    speed_bps = size_difference / time_difference
                    elapsed_time = current_timestamp - self.task_start_time

                    # Estimate total size based on speed and typical durations
                    if speed_bps > 0 and elapsed_time > 30:
                        estimated_total_duration = self._estimate_content_duration()
                        estimated_total_size = speed_bps * estimated_total_duration

                        if estimated_total_size > current_file_size:
                            self.progress_value = min(99, int((current_file_size / estimated_total_size) * 100))

                            if hasattr(self, 'download_handler') and hasattr(self, 'unique_download_id') and self.progress_value > self.previous_progress:
                                self.download_handler.update_download_status(
                                    self.unique_download_id, "downloading", self.progress_value
                                )
                                self.previous_progress = self.progress_value
                                print(f"[RAIPLAY TASK] Fallback progress: {self.progress_value}%")

            self.previous_file_size = current_file_size
            self.last_check_time = current_timestamp

        except Exception as growth_error:
            print(f"[RAIPLAY TASK] Error in file growth progress: {growth_error}")

    def _estimate_content_duration(self):
        """Estimate content duration based on title analysis"""
        try:
            title_lowercase = self.content_title.lower()

            # TV series: typically 40-50 minutes
            if any(indicator in title_lowercase for indicator in ['s0', 's1', 's2', 's3', 's4', 's5', 'episodio', 'stagione', 'e0', 'e1', 'e2']):
                return 45 * 60  # 45 minutes

            # Movies: typically 90-120 minutes
            elif any(indicator in title_lowercase for indicator in ['film', 'movie', 'feature']):
                return 105 * 60  # 1 hour 45 minutes

            # Documentaries: 50-60 minutes
            elif any(indicator in title_lowercase for indicator in ['doc', 'documentar']):
                return 55 * 60

            # Default: 40 minutes
            return 40 * 60

        except:
            return 40 * 60  # Fallback to 40 minutes

    def afterRun(self):
        """Improved completion detection for RaiPlay downloads"""
        print(f"[RAIPLAY TASK] Task completed - Progress: {self.progress_value}%, Exit code: {self.returncode}")

        try:
            if exists(self.output_filename):
                final_file_size = getsize(self.output_filename)
                print(f"[RAIPLAY TASK] Final file size: {final_file_size} bytes")

                # SUCCESS: Download completed
                if final_file_size > 100000:
                    self.download_handler.download_finished(self.output_filename, self.content_title, self.unique_download_id)
                else:
                    # ERROR: File too small
                    self.download_handler.update_download_status(self.unique_download_id, "error", 0)
            else:
                # ERROR: File doesn't exist
                self.download_handler.update_download_status(self.unique_download_id, "error", 0)

        except Exception as completion_error:
            print(f"[RAIPLAY TASK] Error in completion handler: {completion_error}")
            self.download_handler.update_download_status(self.unique_download_id, "error", 0)


def convert_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

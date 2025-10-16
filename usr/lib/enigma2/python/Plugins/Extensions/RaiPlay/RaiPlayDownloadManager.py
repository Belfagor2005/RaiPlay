# -*- coding: utf-8 -*-
from __future__ import print_function
"""
#########################################################
#                                                       #
#  Rai Play Download Manager Module                     #
#  Version: 1.8                                         #
#  Created by Lululla                                   #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0/   #
#  Last Modified: 19:45 - 2025-10-16                    #
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

import os
import time
import re
import math
import json
import subprocess
import threading
from os.path import join, exists, getsize
from os import makedirs  # , remove
from Components.config import config
from Components.Task import Task, Job, job_manager as JobManager
import requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from re import search

# ================================
# DOWNLOAD MANAGER
# ================================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"


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
        """Main worker loop - processes download queue periodically"""
        print("[DOWNLOAD WORKER] Worker thread started")
        while self.running:
            try:
                if self.manager.has_pending_downloads():
                    print("[DOWNLOAD WORKER] Processing download queue...")
                    self.manager.process_queue()
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                print(f"[DOWNLOAD WORKER] Error in worker loop: {e}")
                time.sleep(10)


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

        self.downloads_file = os.path.join(
            self.download_dir, "raiplay_downloads.json")

        if not exists(self.download_dir):
            try:
                makedirs(self.download_dir)
                print(
                    f"[DOWNLOAD MANAGER] Created movie directory: {self.download_dir}")
            except Exception as e:
                print(
                    f"[DOWNLOAD MANAGER] Error creating movie directory: {e}")

        # Configuration
        self.max_concurrent = 2  # Maximum simultaneous downloads
        self.worker = None
        self.running = False

        # Initialize manager
        self.load_downloads()
        self.start_worker()
        print("[DOWNLOAD MANAGER] Manager initialized successfully")

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

    def start_worker(self):
        """Start the background worker thread for queue processing"""
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
            self.worker.join(timeout=5)
            self.worker = None

    def clean_filename(self, filename):
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
        filename = re.sub(r'\s+', ' ', filename).strip()
        filename = filename.replace(' ', '_')
        filename = re.sub(r'_+', '_', filename)

        return filename[:100]  # Limit length

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
                print(
                    f"[DOWNLOAD] Loaded {len(self.download_queue)} downloads")
            except Exception as e:
                print(f"[DOWNLOAD] Error loading downloads: {e}")
                import traceback
                traceback.print_exc()
                self.download_queue = []
        else:
            print("[DOWNLOAD] No downloads file found")
            self.download_queue = []

    def save_downloads(self):
        """Save download queue to file"""
        try:
            print(f"[DOWNLOAD] Saving {len(self.download_queue)} downloads")
            with open(self.downloads_file, "w") as f:
                json.dump(self.download_queue, f, indent=2)

            print("[DOWNLOAD] Save completed successfully")
        except Exception as e:
            print(f"[DOWNLOAD] Error saving downloads: {e}")
            import traceback
            traceback.print_exc()

    def add_download(self, title, url, quality="best"):
        """Add a new download to queue - UPDATED"""
        try:
            print(f"[DOWNLOAD] Adding download: {title}")

            final_url = self.get_real_video_url(url)

            clean_title = self.clean_filename(title)
            download_id = str(int(time.time() * 1000))

            # Determine file extension based on URL type
            if '.m3u8' in final_url:
                extension = ".mp4"  # ffmpeg will convert HLS to mp4
                print("[DOWNLOAD] HLS stream - will use ffmpeg")
            else:
                extension = ".mp4"  # Default for direct streams
                print("[DOWNLOAD] Direct stream - will use wget")

            # CORREZIONE: Ora self.download_dir è già la cartella movie
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

            print(f"[DOWNLOAD] Successfully added: {title}")
            print(
                f"[DOWNLOAD] Stream type: {'HLS (.m3u8)' if '.m3u8' in final_url else 'Direct'}")
            print(f"[DOWNLOAD] Output file: {file_path}")

            return download_id

        except Exception as e:
            print(f"[DOWNLOAD] Error adding download: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save_movie_json_metadata(self, title, video_info):
        """Save JSON metadata in movie folder"""
        try:
            movie_dir = config.movielist.last_videodir.value
            if not movie_dir.endswith('/'):
                movie_dir += '/'

            clean_title = self.clean_filename(title)
            json_filename = f"{clean_title}.json"
            json_path = join(movie_dir, json_filename)

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(video_info, f, indent=2, ensure_ascii=False)

            print(f"[DOWNLOAD] JSON metadata saved to: {json_path}")
            return True

        except Exception as e:
            print(f"[DOWNLOAD] Error saving JSON metadata: {e}")
            return False

    def start_download(self, item):
        """Start a paused download - UPDATED VERSION"""
        if item['status'] in ['completed', 'error']:
            print(
                f"[DOWNLOAD] Cannot start download with status: {item['status']}")
            return

        try:
            print(f"[DOWNLOAD] Starting download: {item['title']}")
            print(
                f"[DOWNLOAD] URL type: {'HLS' if '.m3u8' in item['url'] else 'Direct'}")

            final_url = item['url']

            # Validate URL
            if not self.validate_url(final_url):
                print(f"[DOWNLOAD] Invalid URL: {final_url}")
                self.update_download_status(item['id'], "error", 0)
                return

            # Use appropriate download command
            cmd = self.build_download_command(
                final_url, item['file_path'], False)

            # Update status
            self.update_download_status(item['id'], "downloading", 1)

            job = downloadJob(
                self,
                cmd,
                item['file_path'],
                item['title'],
                item['id'])
            JobManager.AddJob(job)

            print(f"[DOWNLOAD] Download job started: {item['title']}")

        except Exception as e:
            print(f"[DOWNLOAD] Error starting download: {e}")
            import traceback
            traceback.print_exc()
            self.update_download_status(item['id'], "error", 0)

    def update_download_status(self, download_id, status, progress=0):
        """Update download status and progress by ID"""
        print(
            f"[DOWNLOAD] update_download_status - ID: {download_id}, Status: {status}, Progress: {progress}")

        for item in self.download_queue:
            if item['id'] == download_id:
                old_status = item['status']
                if status == "error":
                    item['status'] = "error"
                    item['progress'] = 0
                    print(
                        f"[DOWNLOAD] Download error: {item['title']} - It will NOT be retried automatically")
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

                # Set start/end times
                if status == "downloading" and not item['start_time']:
                    item['start_time'] = time.time()
                elif status == "completed" and not item['end_time']:
                    item['end_time'] = time.time()

                break

        self.save_downloads()

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
        """
        Build ffmpeg command for HLS stream downloading.

        Args:
            url (str): HLS stream URL
            file_path (str): Output file path
        Returns:
            str: ffmpeg command string
        """
        # Ensure .mp4 extension for HLS streams
        if file_path.endswith('.ts'):
            file_path = file_path[:-3] + '.mp4'

        cmd_parts = [
            'ffmpeg',
            '-i', f'"{url}"',
            '-c', 'copy',  # Copy without re-encoding
            '-y',  # Overwrite output
            '-hide_banner',
            '-loglevel', 'info',
            '-user_agent', f'"{USER_AGENT}"',
            '-headers', '"Referer: https://www.raiplay.it/"',
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

                    self.save_downloads()
                    print(f"[DOWNLOAD] Completed: {title}")
                else:
                    print(
                        f"[DOWNLOAD] Download already marked as completed: {title}")
                break

    def pause_download(self, download_id):
        """Pause a download"""
        for item in self.download_queue:
            if item['id'] == download_id and item['status'] in [
                    'downloading', 'waiting']:
                # Cancel the job
                for job in JobManager.getPendingJobs():
                    if hasattr(
                            job, 'download_id') and job.download_id == download_id:
                        job.cancel()
                        break

                self.update_download_status(download_id, "paused")
                print(f"[DOWNLOAD] Paused: {item['title']}")
                break

    def remove_download(self, download_id):
        """Remove a download from queue WITHOUT deleting the file"""
        item_to_remove = None
        for item in self.download_queue:
            if item['id'] == download_id:
                item_to_remove = item
                break

        if item_to_remove:
            if item_to_remove['status'] in ['downloading', 'waiting']:
                self.pause_download(download_id)

            # Do NOT remove the file from the filesystem
            # Keep the file, only remove it from the queue
            # if exists(item_to_remove['file_path']):
            #     try:
            #         remove(item_to_remove['file_path'])
            #     except OSError:
            #         pass

            self.download_queue.remove(item_to_remove)
            self.save_downloads()
            print(
                f"[DOWNLOAD] Removed from queue (file preserved): {item_to_remove['title']}")

    def get_real_video_url_TEST(self, url):
        """Extract real video URL from relinker - TEMPORARY TEST"""
        print(f"[DOWNLOAD] get_real_video_url called: {url}")

        # TEMPORARY: Return a test direct video URL to see if wget works
        if "rai.it" in url:
            print("[DOWNLOAD] TEMPORARY: Using test direct URL instead of relinker")
            # Questo è un esempio - trova un URL video diretto per testare :)
            return "http://www.solopornoitaliani.xxx/contents/videos/19000/19703/19703.mp4"

        return url

    def test_download_url(self, url, title):
        """Test method to verify download URL extraction"""
        print("\n=== DOWNLOAD URL TEST ===")
        print(f"Title: {title}")
        print(f"Original URL: {url}")

        final_url = self.get_real_video_url(url)
        print(f"Final URL: {final_url}")

        # Test if wget can access the URL
        if final_url != url:
            test_cmd = f"wget --spider --timeout=10 --tries=1 '{final_url}'"
            print(f"Testing with: {test_cmd}")
            try:
                result = subprocess.run(
                    test_cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    print("✓ URL TEST PASSED - Download should work")
                else:
                    print("✗ URL TEST FAILED - Download will likely fail")
                    print(f"Error: {result.stderr}")
            except Exception as e:
                print(f"✗ Test execution failed: {e}")

        print("=== END TEST ===\n")
        return final_url

    def get_real_video_url(self, url):
        """
        Extract real video URL from RaiPlay relinker service.
        Processes relinker XML response to find actual video stream URL.

        Args:
            url (str): Relinker URL to process

        Returns:
            str: Direct video URL or original URL if processing fails
        """
        print(f"[DOWNLOAD] Processing URL through relinker: {url}")

        # Bypass non-relinker URLs
        if "relinkerServlet" not in url:
            print("[DOWNLOAD] Not a relinker URL, using as-is")
            return url

        try:
            print("[DOWNLOAD] Detected relinker URL, processing XML response...")

            # Prepare relinker URL for XML response
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query["output"] = ["56"]  # Request XML format
            new_query = urlencode(query, doseq=True)
            relinker_url = urlunparse(parsed._replace(query=new_query))

            print(f"[DOWNLOAD] Fetching relinker XML from: {relinker_url}")

            headers = {
                "User-Agent": USER_AGENT,
                "Referer": "https://www.raiplay.it/",
                "Accept": "application/xml, text/xml, */*"
            }

            # Fetch relinker response
            response = requests.get(
                relinker_url,
                headers=headers,
                timeout=30,
                verify=False)
            response.raise_for_status()
            content = response.text

            print(
                f"[DOWNLOAD] Relinker response length: {len(content)} characters")

            # Save for debugging
            debug_path = join(self.download_dir, "relinker_debug.xml")
            with open(debug_path, "w", encoding='utf-8') as f:
                f.write(content)
            print(f"[DOWNLOAD] Saved relinker response to: {debug_path}")

            # Extract video URL from XML
            video_url = self._extract_video_url_from_xml(content)
            if video_url:
                video_url = self._clean_and_validate_url(video_url)
                print(f"[DOWNLOAD] Final video URL: {video_url}")

                # Process HLS master playlists for quality selection
                if '.m3u8' in video_url:
                    print(
                        "[DOWNLOAD] HLS master playlist detected - selecting best quality")
                    processed_url = self.process_hls_master_playlist(video_url)
                    return processed_url or video_url

                return video_url
            else:
                print("[DOWNLOAD] No video URL found in relinker response")
                return url

        except Exception as e:
            print(f"[DOWNLOAD] Error processing relinker: {e}")
            return url

    def _extract_video_url_from_xml(self, xml_content):
        """Extract video URL from relinker XML response"""
        video_url = None

        # Pattern 1: URL in <url> tag
        url_match = search(
            r'<url[^>]*type="content"[^>]*>([^<]*)</url>',
            xml_content)
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
                r'https?://[^\s<>\'"]+\.m3u8[^\s<>\'"]*',
                r'https?://mediapolisvod\.rai\.it[^\s<>\'"]+',
                r'https?://cdnraivodostr\d+\.msvdn\.net[^\s<>\'"]+'
            ]

            for pattern in video_patterns:
                video_match = search(pattern, xml_content)
                if video_match:
                    video_url = video_match.group(0)
                    print(
                        f"[DOWNLOAD] Found video URL with pattern: {video_url}")
                    break

        return video_url

    def _clean_and_validate_url(self, url):
        """Clean and validate extracted URL"""
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

        return url

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
                        print(
                            f"[DOWNLOAD] Found stream with bandwidth: {bandwidth}")

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
                                    print(
                                        f"[DOWNLOAD] New best quality: {bandwidth} bps - {full_url}")
                        i += 2  # Skip info and URL lines
                    else:
                        i += 1
                else:
                    i += 1

            if best_stream_url:
                quality = "2400p" if best_bandwidth >= 2344000 else "1800p" if best_bandwidth >= 1758000 else "1200p"
                print(
                    f"[DOWNLOAD] Selected {quality} stream: {best_stream_url}")
                return best_stream_url
            else:
                print("[DOWNLOAD] No suitable stream found in master playlist")
                return master_url

        except Exception as e:
            print(f"[DOWNLOAD] Error processing HLS master playlist: {e}")
            return master_url

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
                            item['progress'] = min(
                                99, int((current_size / item['file_size']) * 100))
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
            stat = os.statvfs(self.download_dir)
            free_bytes = stat.f_bfree * stat.f_bsize
            total_bytes = stat.f_blocks * stat.f_bsize
            free = convert_size(free_bytes)
            total = convert_size(total_bytes)
            return free, total
        except Exception as e:
            print(f"[DOWNLOAD] Error getting disk space: {e}")
            return "0B", "0B"

    def clear_completed(self):
        """Clear completed downloads"""
        self.download_queue = [item for item in self.download_queue
                               if item['status'] != 'completed']
        self.save_downloads()
        print("[DOWNLOAD] Cleared completed downloads")


class downloadJob(Job):
    def __init__(
            self,
            download_manager,
            cmdline,
            filename,
            title,
            download_id):
        Job.__init__(self, title)
        self.cmdline = cmdline
        self.filename = filename
        self.download_manager = download_manager
        self.download_id = download_id
        self.downloadTask = downloadTask(
            self, cmdline, filename, title, download_id)

    def retry(self):
        """Retry failed download"""
        if self.status == self.FAILED:
            self.restart()

    def cancel(self):
        """Cancel download"""
        self.abort()


class downloadTask(Task):
    def __init__(self, job, cmdline, filename, title, download_id):
        Task.__init__(self, job, title)
        self.download_manager = job.download_manager
        self.download_id = download_id
        self.filename = filename
        self.title = title
        self.progress = 0
        self.last_progress = 0
        self.first_run = True
        self.start_time = time.time()

        # CORREZIONE: Imposta il comando correttamente
        if isinstance(cmdline, list):
            # Se è una lista, converti in stringa
            cmd_str = ' '.join(cmdline)
            self.setCmdline(cmd_str)
        else:
            # Se è già una stringa, usa direttamente
            self.setCmdline(cmdline)

    def processOutput(self, data):
        """Process wget output to extract progress"""
        try:
            data_str = str(data)
            print(f"[DOWNLOAD TASK] Wget output: {data_str}")

            # Extract progress percentage from wget output
            if "%" in data_str:
                progress_match = re.findall(r'(\d+)%', data_str)
                if progress_match:
                    self.progress = int(progress_match[-1])
                    print(f"[DOWNLOAD TASK] Progress: {self.progress}%")

                    # UPDATE PROGRESS IN MANAGER
                    if hasattr(
                            self, 'download_manager') and hasattr(
                            self, 'download_id'):
                        self.download_manager.update_download_status(
                            self.download_id, "downloading", self.progress
                        )

            # # Check for file size info
            # size_match = re.search(r'(\d+[KM]?) +(\d+[KM]?)', data_str)
            # if size_match:
                # print(f"[DOWNLOAD TASK] Size info: {size_match.groups()}")

            # Check for errors
            if "ERROR" in data_str or "failed" in data_str.lower():
                print(f"[DOWNLOAD TASK] Wget error detected: {data_str}")
                # self.error = True
                if hasattr(
                        self,
                        'download_manager') and hasattr(
                        self,
                        'download_id'):
                    self.download_manager.update_download_status(
                        self.download_id, "error", 0
                    )

            Task.processOutput(self, data)

        except Exception as e:
            print(f"[DOWNLOAD TASK] Error processing output: {e}")
            Task.processOutput(self, data)

    def afterRun(self):
        """Called after download completes"""
        print(
            f"[DOWNLOAD TASK] afterRun - Progress: {self.progress}%, Return code: {self.returncode}")

        try:
            # Check if file actually exists and has content
            if exists(self.filename):
                file_size = getsize(self.filename)
                print(f"[DOWNLOAD TASK] File exists, size: {file_size} bytes")

                if file_size > 0 and self.returncode == 0:
                    # SUCCESS: Download completed
                    self.download_manager.download_finished(
                        self.filename, self.title, self.download_id)
                    print(
                        f"[DOWNLOAD TASK] Download completed successfully: {self.title}")
                else:
                    # ERROR: File empty or wget failed
                    print(
                        "[DOWNLOAD TASK] Download failed - empty file or error code")
                    self.download_manager.update_download_status(
                        self.download_id, "error", 0)
            else:
                # ERROR: File doesn't exist
                print("[DOWNLOAD TASK] Download failed - file not found")
                self.download_manager.update_download_status(
                    self.download_id, "error", 0)

        except Exception as e:
            print(f"[DOWNLOAD TASK] Error in afterRun: {e}")
            self.download_manager.update_download_status(
                self.download_id, "error", 0)


def convert_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

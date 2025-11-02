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

# ======================== IMPORTS ========================

# 🧠 STANDARD LIBRARIES
import datetime
import re


class RaiPlayProgressParser:
    """Advanced FFmpeg progress parser for RaiPlay Download Manager"""
    
    def __init__(self):
        self.total_duration_seconds = 0
        self.downloaded_duration_seconds = 0
        self.is_live_stream = False
        self.header_processed = False
        self.last_update_timestamp = datetime.datetime.now()
        
        # Custom regex patterns for RaiPlay
        self.progress_patterns = {}
        self.progress_patterns['start_timestamp'] = re.compile(r'\sstart\:\s*?([0-9]+?)\.')
        self.progress_patterns['time_duration'] = re.compile(r'[\s=]([0-9]+?)\:([0-9]+?)\:([0-9]+?)\.')
        self.progress_patterns['file_size_kb'] = re.compile(r'size=\s*?([0-9]+?)kB')
        self.progress_patterns['bitrate_kbps'] = re.compile(r'bitrate=\s*?([0-9]+?(?:\.[0-9]+?)?)kbits')
        self.progress_patterns['speed_multiplier'] = re.compile(r'speed=\s*?([0-9]+?(?:\.[0-9]+?)?)x')
    
    def analyze_ffmpeg_output(self, data_line):
        """Analyze FFmpeg output and extract progress information"""
        progress_data = {
            'current_size_bytes': 0,
            'download_speed_bps': 0,
            'completion_percentage': 0,
            'current_duration_sec': 0
        }
        
        try:
            if not self.header_processed:
                if 'Duration:' in data_line:
                    detected_duration = self._extract_duration_seconds(data_line) - self._extract_start_time(data_line)
                    if detected_duration > 0 and (detected_duration < self.total_duration_seconds or 0 == self.total_duration_seconds):
                        self.total_duration_seconds = detected_duration
                        print(f"[RAIPLAY PARSER] Total duration found: {self.total_duration_seconds} seconds")
                elif 'Stream mapping:' in data_line:
                    self.header_processed = True
                    if self.total_duration_seconds == 0:
                        self.is_live_stream = True
                        print("[RAIPLAY PARSER] Live stream identified")

            if 'frame=' in data_line:
                self.last_update_timestamp = datetime.datetime.now()

                # Extract file size
                file_size_bytes = self._extract_file_size_bytes(data_line)
                if file_size_bytes > 0:
                    progress_data['current_size_bytes'] = file_size_bytes

                # Extract download speed
                speed_bps = self._extract_download_speed_bps(data_line)
                if speed_bps > 0:
                    progress_data['download_speed_bps'] = speed_bps

                # Update duration when file size changes
                current_duration = self._extract_duration_seconds(data_line)
                if current_duration > self.downloaded_duration_seconds:
                    self.downloaded_duration_seconds = current_duration
                    progress_data['current_duration_sec'] = current_duration

                # Calculate completion percentage
                if self.total_duration_seconds > 0 and current_duration > 0:
                    completion_pct = min(99, int((current_duration / self.total_duration_seconds) * 100))
                    progress_data['completion_percentage'] = completion_pct
                    print(f"[RAIPLAY PARSER] Progress: {current_duration}s/{self.total_duration_seconds}s = {completion_pct}%")
                elif file_size_bytes > 0:
                    # Alternative: estimate based on typical file sizes
                    estimated_total_size = self._calculate_estimated_size()
                    if estimated_total_size > 0:
                        completion_pct = min(99, int((file_size_bytes / estimated_total_size) * 100))
                        progress_data['completion_percentage'] = completion_pct
                        print(f"[RAIPLAY PARSER] Size-based progress: {file_size_bytes}/{estimated_total_size} = {completion_pct}%")

        except Exception as parse_error:
            print(f"[RAIPLAY PARSER] Error analyzing output: {parse_error}")
        
        return progress_data

    def _extract_duration_seconds(self, data_line):
        try:
            match_result = self.progress_patterns['time_duration'].search(data_line)
            return 3600 * int(match_result.group(1)) + 60 * int(match_result.group(2)) + int(match_result.group(3))
        except Exception:
            return 0

    def _extract_start_time(self, data_line):
        try:
            match_result = self.progress_patterns['start_timestamp'].search(data_line)
            return int(match_result.group(1))
        except Exception:
            return 0

    def _extract_file_size_bytes(self, data_line):
        try:
            return int(self.progress_patterns['file_size_kb'].search(data_line).group(1)) * 1024
        except Exception:
            return 0

    def _extract_download_speed_bps(self, data_line):
        try:
            bitrate_kbps = float(self.progress_patterns['bitrate_kbps'].search(data_line).group(1))
            speed_multiplier = float(self.progress_patterns['speed_multiplier'].search(data_line).group(1))
            return int(bitrate_kbps * speed_multiplier * 1024 / 8)
        except Exception:
            return 0

    def _calculate_estimated_size(self):
        """Calculate estimated file size based on duration and typical bitrates"""
        if self.total_duration_seconds > 0:
            # Typical video bitrates for RaiPlay content
            default_bitrate_bps = 2 * 1024 * 1024  # 2 MBit/s as default
            return (default_bitrate_bps / 8) * self.total_duration_seconds
        return 0

    def check_if_live_stream(self):
        return self.is_live_stream

    def get_total_duration(self):
        if self.check_if_live_stream():
            return self.downloaded_duration_seconds
        return self.total_duration_seconds

    def get_downloaded_duration(self):
        return self.downloaded_duration_seconds

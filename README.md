![](https://komarev.com/ghpvc/?username=Belfagor2005)

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC_BY_NC_SA_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

[![Python package](https://github.com/Belfagor2005/RaiPlay/actions/workflows/pylint.yml/badge.svg)](https://github.com/Belfagor2005/RaiPlay/actions/workflows/pylint.yml)

<img src="https://github.com/Belfagor2005/tvRaiPreview/blob/main/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay/logo.png">

# Rai Play View Plugin
## Overview

Rai Play View is a comprehensive plugin to browse, stream, and download Rai Play content on compatible platforms.  
It allows users to navigate categories, programs, and videos via Rai Play's JSON API, play streams directly, and manage downloads.

## Features

### Core Features
- Browse Rai Play on-demand categories and genres  
- Access detailed program information and seasons  
- Play videos and movies seamlessly  
- Supports subtitles and multiple video qualities (if available)  
- Search functionality to find specific programs and videos  
- Uses Rai's relinker service to resolve video URLs for smooth playback  

### Download Manager
- **Advanced Download System**: Queue and manage multiple downloads
- **HLS Stream Support**: Download .m3u8 streams with automatic MP4 conversion
- **Quality Selection**: Automatic best quality detection (2400p > 1800p > 1200p)
- **Progress Tracking**: Real-time download progress with percentage and speed
- **Queue Management**: Pause, resume, remove, and prioritize downloads
- **Background Downloads**: Continue downloads even when plugin is closed
- **Resume Support**: Resume interrupted downloads
- **Disk Space Monitoring**: Automatic disk space checks
- **File Validation**: Ensure downloaded files are complete and valid

### Notification System
- **Hybrid Notifications**: Works both inside and outside the plugin
- **Smart Filtering**: Only important download notifications when plugin is closed
- **Global Alerts**: Download completion/error notifications system-wide
- **Clean Interface**: Non-intrusive notification system

### Technical Features
- Debug logging for easier troubleshooting  
- Clean, user-friendly interface
- JSON-based queue persistence
- Thread-safe operations
- Automatic URL validation and sanitization
- Support for RaiPlay DRM content
- Integration with Enigma2 JobManager

## Installation

1. Clone or download this repository to your plugin directory.  
2. Install dependencies if needed (e.g., `requests`).  
3. Restart your media platform to load the plugin.

## Usage

### Basic Navigation
- Navigate the Rai Play categories from the plugin menu.  
- Select a program or season to view episodes or videos.  
- Press OK/Select to start playback.

### Download Management
- Access the download manager from the plugin menu
- Add videos to download queue with quality selection
- Monitor download progress in real-time
- Manage queue (pause, resume, remove downloads)
- View completed downloads and file sizes

### Notifications
- Receive notifications for download completion
- Get error alerts for failed downloads
- Notifications work both inside and outside the plugin

## Development

- Built in Python 3 with API integration to Rai Play JSON endpoints.  
- Advanced download system with HLS stream processing
- Hybrid notification system for optimal user experience
- Debug logs are printed in console for development assistance.  
- Contributions welcome — please fork and submit pull requests.

## File Structure
RaiPlay/
├── plugin.py # Main plugin interface
├── RaiPlayDownloadManager.py # Download management system
├── notify_play.py # Hybrid notification system
├── RaiPlayProgressParser.py # Advanced progress tracking
└── [Other support files]

## License

This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).  
See the [LICENSE](LICENSE) file for details.

## Credits

- Developed by Lululla  
- Inspired by Rai Play API and existing plugins  
- Advanced download system based on modern streaming protocols
- Notification system optimized for Enigma2 environment

## Contact

For questions or feedback, please open an issue or contact Lululla.


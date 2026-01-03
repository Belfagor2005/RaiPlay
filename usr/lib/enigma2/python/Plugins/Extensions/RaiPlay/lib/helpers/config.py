# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals

"""
#########################################################
#                                                       #
#  Rai Play View Plugin                                 #
#  Version: 1.3                                         #
#  Created by Lululla                                   #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0/   #
#  Last Modified: "15:14 - 20250724"                    #
#                                                       #
#  Features:                                            #
#  - Access Rai Play content                            #
#  - Browse categories, programs, and videos            #
#  - Play streaming video                               #
#  - JSON API integration                               #
#  - Debug logging                                      #
#  - User-friendly interface                            #
#                                                       #
#  Credits:                                             #
#  - Original development by Lululla                    #
#  - Inspired by previous Rai Play plugins and API docs #
#                                                       #
#  Usage of this code without proper attribution        #
#  is strictly prohibited.                              #
#  For modifications and redistribution,                #
#  please maintain this credit header.                  #
#########################################################
"""
__author__ = "Lululla"

"""Configuration constants"""

# Supported InputStream protocols and their Kodi addon IDs
INPUTSTREAM_PROTOCOLS = {
    "mpd": "inputstream.adaptive",
    "hls": "inputstream.adaptive",
    "dash": "inputstream.adaptive",
    # add more if needed
}

# DRM schemes supported and their identifiers
DRM_SCHEMES = {
    "widevine": "widevine",
    # add more if needed
}

# Widevine support architecture list
WIDEVINE_SUPPORTED_ARCHS = ["armv7", "arm64", "x86_64", "x86"]

# Widevine supported operating systems
WIDEVINE_SUPPORTED_OS = ["Android", "Darwin", "Linux", "Windows"]

# Minimum Kodi version for Widevine per OS
WIDEVINE_MINIMUM_KODI_VERSION = {
    "Android": "19.0",
    "Darwin": "19.0",
    "Linux": "19.0",
    "Windows": "19.0",
}

# Minimum InputStream Adaptive version for HLS support
HLS_MINIMUM_IA_VERSION = "2.4.14"

# Minimum InputStream version for 64bit arm support (example)
MINIMUM_INPUTSTREAM_VERSION_ARM64 = {
    "inputstream.adaptive": "2.4.14"
}

# Mapping architecture names from repo to system arch
WIDEVINE_ARCH_MAP_REPO = {
    "armv7": "armv7",
    "arm64": "arm64",
    "x86": "x86",
    "x86_64": "x86_64",
}

# Filename of Widevine CDM library per OS
WIDEVINE_CDM_FILENAME = {
    "Android": "libwidevinecdm.so",
    "Linux": "libwidevinecdm.so",
    "Darwin": "libwidevinecdm.dylib",
    "Windows": "widevinecdm.dll",
}

# Short issue URL for bug reporting
SHORT_ISSUE_URL = "https://github.com/yourrepo/issues"

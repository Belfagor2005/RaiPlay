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

"""General utilities for InputStream Helper"""

import os
import platform
import shutil
import tempfile
import urllib.request


def arch():
    """Return system architecture string"""
    import platform
    arch_str = platform.machine().lower()
    # Normalize common arch names
    if arch_str in ("x86_64", "amd64"):
        return "x86_64"
    if arch_str.startswith("arm"):
        if "64" in arch_str:
            return "arm64"
        return "armv7"
    if arch_str in ("i386", "i686"):
        return "x86"
    return arch_str


def system_os():
    """Return OS name"""
    name = platform.system()
    if name == "Darwin":
        return "Darwin"
    if name == "Windows":
        return "Windows"
    if name == "Linux":
        return "Linux"
    return name


def download_path(url):
    """Return a temporary download path for a given URL"""
    filename = os.path.basename(url)
    tempdir = tempfile.gettempdir()
    return os.path.join(tempdir, filename)


def http_download(url):
    """Download a file from url to a temp path"""
    dest = download_path(url)
    try:
        urllib.request.urlretrieve(url, dest)
        return dest
    except Exception:
        return None


def parse_version(version_string):
    """Parse version string into tuple for comparison"""
    try:
        return tuple(int(x) for x in version_string.split("."))
    except Exception:
        return (0, 0, 0)


def remove_tree(path):
    """Remove directory tree if exists"""
    if os.path.exists(path) and os.path.isdir(path):
        shutil.rmtree(path)
        return True
    return False


def temp_path():
    """Return temporary directory path"""
    return tempfile.gettempdir()


def userspace64():
    """Detect if userspace is 64 bit (stub returns False)"""
    # More complex detection could be implemented
    return False


def unzip(zip_path, dest_path):
    """Extract zip file"""
    import zipfile
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_path)
        return True
    except Exception:
        return False

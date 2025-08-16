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

"""Implements the main InputStream Helper class for Enigma2"""

import os
import re
import json


# Dummy placeholders for Enigma2 environment utilities (da sostituire con le tue implementazioni)
def log(level, msg, **kwargs):
    print("[LOG{}] {}".format(level, msg.format(**kwargs)))


def ok_dialog(title, message):
    print("[OK DIALOG] {}: {}".format(title, message))
    return True  # Simulare sempre OK premuto


def yesno_dialog(title, message, yeslabel="Yes", nolabel="No"):
    print("[YESNO DIALOG] {}: {} ({} / {})".format(title, message, yeslabel, nolabel))
    # Qui puoi mettere logica di risposta, per esempio input da console o default True
    return True


def notification(title, message):
    print("[NOTIFICATION] {}: {}".format(title, message))


def select_dialog(title, options):
    print("[SELECT DIALOG] {}".format(title))
    for idx, option in enumerate(options):
        print("  {}: {}".format(idx, option))
    # Seleziono il primo per default
    return 0 if options else -1


def progress_dialog():
    class Progress:

        def create(self, heading="", message=""):
            print("[PROGRESS START] {} - {}".format(heading, message))

        def update(self, percent=0, message=""):
            print("[PROGRESS] {}% - {}".format(percent, message))

        def close(self):
            print("[PROGRESS END]")

    return Progress()


def exists(path):
    return os.path.exists(path)


def delete(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
            log(0, "Deleted file: {path}", path=path)
            return True
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
            log(0, "Deleted directory: {path}", path=path)
            return True
    except Exception as e:
        log(3, "Error deleting {path}: {error}", path=path, error=e)
    return False


def listdir(path):
    try:
        return os.listdir(path)
    except Exception:
        return []


def parse_version(v):
    # Simple version parsing for comparison: "1.2.3" -> (1,2,3)
    parts = re.findall(r'\d+', v)
    return tuple(int(p) for p in parts)


def system_os():
    import platform
    return platform.system()


def arch():
    import platform
    machine = platform.machine().lower()
    if 'arm' in machine or 'aarch64' in machine:
        return 'arm64' if '64' in machine else 'arm'
    if 'x86_64' in machine or 'amd64' in machine:
        return 'x86_64'
    if 'i386' in machine or 'i686' in machine:
        return 'x86'
    return machine


# Config simile a quello originale
class config:
    INPUTSTREAM_PROTOCOLS = {
        'dash': 'inputstream.adaptive',
        'hls': 'inputstream.adaptive',
        'smooth': 'inputstream.smoothstreaming'
    }

    DRM_SCHEMES = {
        'widevine': 'widevine',
        'playready': 'playready',
        'clearkey': 'clearkey'
    }

    WIDEVINE_SUPPORTED_ARCHS = ['x86_64', 'arm', 'arm64']
    WIDEVINE_SUPPORTED_OS = ['Linux', 'Android', 'Darwin', 'Windows']

    WIDEVINE_MINIMUM_KODI_VERSION = {
        'Linux': '18.0.0',
        'Android': '18.0.0',
        'Darwin': '18.0.0',
        'Windows': '18.0.0',
    }

    MINIMUM_INPUTSTREAM_VERSION_ARM64 = {
        'inputstream.adaptive': '2.4.23',
    }

    HLS_MINIMUM_IA_VERSION = "2.4.23"

    WIDEVINE_CDM_FILENAME = {
        'Linux': 'libwidevinecdm.so',
        'Android': 'libwidevinecdm.so',
        'Darwin': 'libwidevinecdm.dylib',
        'Windows': 'widevinecdm.dll'
    }

    SHORT_ISSUE_URL = "https://github.com/yourrepo/issues"


# Placeholder per funzioni di Widevine (da implementare se serve)
def has_widevinecdm():
    return exists('/path/to/widevinecdm')  # Cambia con controllo reale


def widevinecdm_path():
    return '/path/to/widevinecdm'  # Cambia con path reale


def widevine_config_path():
    return '/path/to/widevine/config.json'


def load_widevine_config():
    try:
        with open(widevine_config_path(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def install_cdm_from_backup(version):
    log(0, "Installing CDM backup version: {version}", version=version)


def remove_tree(path):
    delete(path)


def userspace64():
    # placeholder for 64bit user space detection
    return True


# Inizio Helper class adattata per Enigma2
class InputStreamException(Exception):
    pass


class Helper:
    def __init__(self, protocol, drm=None):
        self.protocol = protocol
        self.drm = drm

        log(0, "Platform information: {uname}", uname=os.uname())

        if protocol not in config.INPUTSTREAM_PROTOCOLS:
            raise InputStreamException("UnsupportedProtocol")

        self.inputstream_addon = config.INPUTSTREAM_PROTOCOLS[protocol]

        if drm:
            if drm not in config.DRM_SCHEMES:
                raise InputStreamException("UnsupportedDRMScheme")
            self.drm = config.DRM_SCHEMES[drm]

    def _has_inputstream(self):
        # Simulato: in Enigma2 normalmente il plugin è sempre disponibile se installato
        log(0, "{} is assumed installed.", addon=self.inputstream_addon)
        return True

    def _inputstream_enabled(self):
        # Assumiamo sempre attivo
        return True

    def _supports_widevine(self):
        if arch() not in config.WIDEVINE_SUPPORTED_ARCHS:
            log(4, "Unsupported Widevine architecture: {arch}", arch=arch())
            ok_dialog("Widevine Not Supported", "Unsupported architecture: {}".format(arch()))
            return False

        if system_os() not in config.WIDEVINE_SUPPORTED_OS:
            log(4, "Unsupported Widevine OS: {os}", os=system_os())
            ok_dialog("Widevine Not Supported", "Unsupported OS: {}".format(system_os()))
            return False

        return True

    def check_inputstream(self):
        if self.drm == 'widevine' and not self._supports_widevine():
            return False

        if not self._has_inputstream():
            ok_dialog("Error", "{} is missing.".format(self.inputstream_addon))
            return False

        if not self._inputstream_enabled():
            if not yesno_dialog("Enable InputStream", "{} is disabled. Enable it?".format(self.inputstream_addon)):
                return False

        log(0, "{} is installed and enabled.", addon=self.inputstream_addon)

        return True

    def info_dialog(self):
        text = "System: {}\nArchitecture: {}\nInputStream: {}\nDRM: {}\n".format(system_os(), arch(), self.inputstream_addon, self.drm or "None")
        notification("InputStream Helper Info", text)

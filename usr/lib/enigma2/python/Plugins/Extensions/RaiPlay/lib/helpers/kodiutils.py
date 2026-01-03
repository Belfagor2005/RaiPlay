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

"""Mock Kodi utils for InputStream Helper"""

import os


class Addon:
    """Mock xbmcaddon.Addon class"""

    def __init__(self, addon_id=None):
        self.addon_id = addon_id or "inputstream.helper"
        self._settings = {}

    def getAddonInfo(self, info):
        if info == "version":
            return "2.4.15"
        if info == "id":
            return self.addon_id
        return ""

    def getSetting(self, key):
        return self._settings.get(key, "")

    def setSetting(self, key, value):
        self._settings[key] = value


class AddonSettings:
    """Addon settings singleton"""

    _settings = {}

    @classmethod
    def get_setting(cls, key, default=None):
        return cls._settings.get(key, default)

    @classmethod
    def set_setting(cls, key, value):
        cls._settings[key] = value


class ADDON:
    @staticmethod
    def openSettings():
        print("Opening addon settings...")


def log(level, message, **kwargs):
    """Simple log function"""
    if kwargs:
        message = message.format(**kwargs)
    level_str = {0: "DEBUG", 1: "INFO", 2: "NOTICE", 3: "WARNING", 4: "ERROR"}.get(level, "INFO")
    print("[{level}] {msg}".format(level=level_str, msg=message))


def notification(title, message, duration=5000, icon=None):
    print("[Notification] {title}: {message}".format(title=title, message=message))


def ok_dialog(title, message):
    print("[OK Dialog] {title}: {message}".format(title=title, message=message))


def yesno_dialog(heading, line1, nolabel="No", yeslabel="Yes"):
    print("[Yes/No Dialog] {heading}: {line1} ({yes}/{no})".format(heading=heading, line1=line1, yes=yeslabel, no=nolabel))
    # For testing always yes:
    return True


def localize(string_id, **kwargs):
    """Mock localization"""
    translations = {
        30001: "Widevine update required",
        30002: "Widevine DRM is required to play this content.",
        30004: "Error",
        30005: "An error occurred",
        30007: "Widevine is not available on this architecture: {arch}",
        30008: "InputStream is missing on this system: {addon}",
        30009: "InputStream is disabled: {addon}",
        30010: "Kodi version too old. Minimum required: {version}",
        30011: "Operating system not supported by Widevine: {os}",
        30012: "Windows Store Kodi is not supported.",
        30017: "HLS requires minimum InputStream version {version} of {addon}.",
        30028: "No",
        30033: "Widevine update is available.",
        30034: "Yes",
        30037: "Success",
        30038: "Install",
        30040: "Update Widevine",
        30041: "Widevine is required to play this content. Do you want to install it?",
        30043: "Extracting Widevine CDM",
        30044: "Please wait while the files are extracted.",
        30049: "Installing Widevine CDM",
        30050: "Finishing installation",
        30051: "Widevine CDM successfully installed.",
        30052: "Widevine successfully removed.",
        30053: "Widevine CDM not found.",
        30054: "Disabled",
        30056: "No Widevine backups available.",
        30057: "Select Widevine version to rollback to",
        30800: "Kodi version: {version}\nSystem: {system}\nArchitecture: {arch}",
        30810: "InputStream Helper version: {version} {state}",
        30811: "InputStream version: {version} {state}",
        30820: "Android specific info",
        30821: "Widevine library version: {version}\nLast update: {date}",
        30822: "Chrome OS image: {name} version {version}",
        30823: "Last widevine update check: {date}",
        30824: "Widevine CDM path: {path}",
        30825: "Lacros Chrome OS image version: {version}",
        30826: "webOS specific info",
        30901: "InputStream Helper Info",
    }
    text = translations.get(string_id, str(string_id))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def get_setting(key, default=None):
    return AddonSettings.get_setting(key, default)


def set_setting(key, value):
    AddonSettings.set_setting(key, value)


def get_setting_bool(key, default=False):
    val = get_setting(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    return bool(val)


def get_setting_int(key, default=0):
    val = get_setting(key, default)
    try:
        return int(val)
    except Exception:
        return default


def get_setting_float(key, default=0.0):
    val = get_setting(key, default)
    try:
        return float(val)
    except Exception:
        return default


def delete(path):
    try:
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True
    except Exception:
        return False


def exists(path):
    return os.path.exists(path)


def listdir(path):
    try:
        return os.listdir(path)
    except Exception:
        return []


def jsonrpc(method, params=None):
    """Stub for Kodi jsonrpc call"""
    # For test, always assume addon is installed and enabled
    if method == "Addons.GetAddonDetails":
        addonid = params.get("addonid") if params else None
        if addonid == "inputstream.adaptive":
            return {"result": {"addon": {"enabled": True}}}
        else:
            return {"error": "Addon not found"}
    elif method == "Addons.SetAddonEnabled":
        # pretend enabling addon always success
        return {"result": {"success": True}}
    return {}


def kodi_version():
    return "19.3"


def addon_version():
    return "2.4.15"


def kodi_to_ascii(text):
    return str(text)


def browsesingle(type_, heading, mask):
    """Mock browse single file dialog"""
    print("Browse single called: type {0}, heading {1}, mask {2}".format(type_, heading, mask))
    return "/tmp/fakeimage.img"


def progress_dialog():
    """Mock progress dialog class"""
    class Progress:
        def create(self, heading="", message=""):
            print("[Progress] {0} - {1}".format(heading, message))

        def update(self, percent=0, message=""):
            print("[Progress] {0}% - {1}".format(percent, message))

        def close(self):
            print("[Progress] closed")

    return Progress()


def select_dialog(heading, list_):
    print("[Select Dialog] {0}".format(heading))
    for i, item in enumerate(list_):
        print("  {0}: {1}".format(i, item))
    # For test always select first
    return 0


def textviewer(heading, text):
    print("[Text Viewer] {0}\n{1}".format(heading, text))

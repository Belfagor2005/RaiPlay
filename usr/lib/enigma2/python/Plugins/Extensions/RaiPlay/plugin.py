# -*- coding: utf-8 -*-
from __future__ import print_function

"""
#########################################################
#                                                       #
#  Rai Play View Plugin                                 #
#  Version: 1.9                                         #
#  Created by Lululla                                   #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0/   #
#  Last Modified: 15:35 - 2025-11-02                    #
#                                                       #
#  Features:                                            #
#    - Access Rai Play content                          #
#    - Browse categories, programs, and videos          #
#    - Play streaming video                             #
#    - Download streaming video                         #
#    - JSON API integration                             #
#    - Debug logging                                    #
#    - User-friendly interface                          #
#    - Widevine DRM check for RaiPlay video playback    #
#    - Download Manager with queue system               #
#                                                       #
#  Credits:                                             #
#    - Original development by Lululla                  #
#    - Inspired by Rai Play plugins and API docs        #
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
import codecs
import chardet
import html as _html
import sys
import threading
import time
import traceback
from datetime import date, datetime, timedelta
from json import dump, dumps, load, loads
from os import access, W_OK, makedirs, remove, system
from os.path import exists, isdir, join
from re import DOTALL, findall, match, search
from urllib.parse import parse_qs, urljoin, urlparse, urlencode, urlunparse

# 🌐 EXTERNAL LIBRARIES
import requests
from twisted.web.client import downloadPage

# 🧩 ENIGMA2 COMPONENTS
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryPixmapAlphaTest, MultiContentEntryText
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import InfoBarBase, ServiceEventTracker
from Components.config import ConfigSelection, ConfigSubsection, ConfigYesNo, config

try:
    from Components.AVSwitch import AVSwitch
except ImportError:
    from Components.AVSwitch import eAVControl as AVSwitch

# 🪟 ENIGMA2 SCREENS
from Screens.InfoBarGenerics import (
    InfoBarAudioSelection,
    InfoBarMenu,
    InfoBarNotifications,
    InfoBarSeek,
    InfoBarSubtitleSupport,
)
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Setup import Setup
from Screens.VirtualKeyBoard import VirtualKeyBoard

# 🧰 ENIGMA2 TOOLS
from Tools.Directories import SCOPE_PLUGINS, defaultRecordingLocation, resolveFilename

# 📺 ENIGMA2 CORE
from enigma import (
    RT_HALIGN_LEFT,
    RT_VALIGN_CENTER,
    eListboxPythonMultiContent,
    ePicLoad,
    eServiceReference,
    eTimer,
    gFont,
    getDesktop,
    iPlayableService,
    loadPNG,
)

# 🧱 LOCAL MODULES
from . import _
from . import Utils
from .RaiPlayDownloadManager import RaiPlayDownloadManager
from .lib.helpers.helper import Helper
from .lib.html_conv import html_unescape

# Import notification system
try:
    from .notify_play import init_notification_system
    NOTIFICATION_AVAILABLE = True
except ImportError as e:
    print("[DEBUG] Notification system not available:", e)
    NOTIFICATION_AVAILABLE = False

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==================== UTILITY FUNCTIONS ====================
def deletetmp():
    system('rm -rf /tmp/unzipped;rm -f /tmp/*.ipk;rm -f /tmp/*.tar;rm -f /tmp/*.zip;rm -f /tmp/*.tar.gz;rm -f /tmp/*.tar.bz2;rm -f /tmp/*.tar.tbz2;rm -f /tmp/*.tar.tbz;rm -f /tmp/*.m3u')
    return


def get_mounted_devices():
    """Get list of mounted and writable devices."""
    basic_paths = [
        ("/media/hdd/", _("HDD Drive")),
        ("/media/usb/", _("USB Drive")),
        ("/media/ba/", _("Barry Allen")),
        ("/media/net/", _("Network Storage")),
        ("/tmp/", _("Temporary"))
    ]

    # Check which paths exist and are writable
    valid_devices = []
    for path, desc in basic_paths:
        if isdir(path) and access(path, W_OK):
            valid_devices.append((path, desc))

    # Add additional USB devices if available (usb1, usb2...)
    for i in range(1, 4):
        usb_path = "/media/usb%d/" % i
        if isdir(usb_path) and access(usb_path, W_OK):
            valid_devices.append((usb_path, _("USB Drive") + " %d" % i))

    return valid_devices


def default_movie_path():
    """Get default movie path from Enigma2 configuration."""
    result = config.usage.default_path.value
    if not result.endswith("/"):
        result += "/"
    if not isdir(result):
        return defaultRecordingLocation(config.usage.default_path.value)
    return result


def update_mounts_configuration():
    """Update the list of mounted devices and update config choices."""
    mounts = get_mounted_devices()
    if not mounts:
        default_path = default_movie_path()
        mounts = [(default_path, default_path)]
    config.plugins.raiplay.lastdir.setChoices(mounts, default=mounts[0][0])
    config.plugins.raiplay.lastdir.save()


DEBUG_MODE = False
config.plugins.raiplay = ConfigSubsection()
config.plugins.raiplay.debug = ConfigYesNo(default=True)
default_dir = config.movielist.last_videodir.value if isdir(
    config.movielist.last_videodir.value) else default_movie_path()
config.plugins.raiplay.lastdir = ConfigSelection(
    default=default_dir, choices=[])


if config.plugins.raiplay.debug.value:
    DEBUG_MODE = True


aspect_manager = Utils.AspectManager()
PY3 = sys.version_info.major >= 3
if sys.version_info >= (2, 7, 9):
    try:
        import ssl
        sslContext = ssl._create_unverified_context()
    except BaseException:
        sslContext = None


def fake_detect(data):
    return {"encoding": "utf-8", "confidence": 1.0}


chardet.detect = fake_detect


def debug_log(message):
    if DEBUG_MODE:
        print(message)


def check_widevine_ready():
    h = Helper(protocol="mpd", drm="widevine")
    if not h.check_inputstream():
        # show error message or trigger installation
        # h = Helper("mpd", drm="widevine")
        # h._update_widevine()
        print("[DEBUG]Widevine not installed or not working")
        # You can call h.install_widevine() if you want to force installation
        return False
    return True


name_plugin = 'TiVu Rai Play'
currversion = '1.9'
desc_plugin = '..:: TiVu Rai Play by Lululla %s ::.. ' % currversion
plugin_path = '/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay'
plugin_res = join(plugin_path, "res", "pics")
DEFAULT_ICON = join(plugin_path, "res/pics/icon.png")
pluglogo = join(plugin_path, "res/pics/logo.png")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
ntimeout = 10

png_amb = join(plugin_res, "ambiente.png")
png_artis = join(plugin_res, "artiespettacolo.png")
png_crim = join(plugin_res, "crime.png")
png_econ = join(plugin_res, "economia.png")
png_mon = join(plugin_res, "mappamondo.png")
png_news = join(plugin_res, "cronaca-new.png")
png_noti = join(plugin_res, "notiziari.png")
png_poli = join(plugin_res, "politica.png")
png_sal = join(plugin_res, "salute.png")
png_sci = join(plugin_res, "raiscienza.png")
png_search = join(plugin_res, "search_rai.png")
png_spec = join(plugin_res, "speciali.png")
png_sport = join(plugin_res, "rai_sports.png")
png_sto = join(plugin_res, "storia.png")
png_tg1 = join(plugin_res, "tg1.png")
png_tg2 = join(plugin_res, "tg2.png")
png_tg3 = join(plugin_res, "tg3.png")
png_tgd = join(plugin_res, "tgdialogo.png")
png_tgec = join(plugin_res, "tgeconomia.png")
png_tglib = join(plugin_res, "tglibri.png")
png_tgm = join(plugin_res, "tgmotori.png")
png_tgmed = join(plugin_res, "tgmedicina.png")
png_tgpers = join(plugin_res, "tgpersone.png")
png_tgr = join(plugin_res, "tgr.png")
png_tgsp = join(plugin_res, "tgsport.png")
png_tgspec = join(plugin_res, "tgspeciale.png")
png_tv7 = join(plugin_res, "tv7.png")
png_via = join(plugin_res, "viaggi.png")


screenwidth = getDesktop(0).size()
skin_path = join(plugin_path, "res/skins/")
if screenwidth.width() == 1920:
    skin_path = join(plugin_path, "res/skins/fhd/")
elif screenwidth.width() == 2560:
    skin_path = join(plugin_path, "res/skins/uhd/")

if not exists(join(skin_path, "settings.xml")):
    skin_path = join(plugin_path, "res/skins/hd/")
    print("[DEBUG]Skin non trovata, uso il fallback:", skin_path)


def is_serviceapp_available():
    """Check if ServiceApp is installed"""
    return exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/ServiceApp")


def returnIMDB(session, text_clear):
    """Show IMDB/TMDB information for the content"""
    text = html_unescape(text_clear)

    if Utils.is_TMDB and Utils.TMDB:
        try:
            session.open(Utils.TMDB.tmdbScreen, text, 0)
        except Exception as e:
            print("[DEBUG][XCF] TMDB error:", str(e))
        return True

    elif Utils.is_tmdb and Utils.tmdb:
        try:
            session.open(Utils.tmdb.tmdbScreen, text, 0)
        except Exception as e:
            print("[DEBUG][XCF] tmdb error:", str(e))
        return True

    elif Utils.is_imdb and Utils.imdb:
        try:
            Utils.imdb(session, text)
        except Exception as e:
            print("[DEBUG][XCF] IMDb error:", str(e))
        return True

    session.open(MessageBox, text, MessageBox.TYPE_INFO)
    return True


class strwithmeta(str):
    def __new__(cls, value, meta={}):
        obj = str.__new__(cls, value)
        if isinstance(value, strwithmeta):
            obj.meta = dict(value.meta)
        else:
            obj.meta = {}
        obj.meta.update(meta)
        return obj


try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except BaseException:
    sslverify = False
if sslverify:
    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx


def extract_real_video_url(page_url):
    """Extract real video URL from a RaiPlay page."""
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.raiplay.it/"
        }
        response = requests.get(page_url, headers=headers, timeout=10)
        response.raise_for_status()

        if 'application/json' in response.headers.get('Content-Type', ''):
            data = response.json()
        else:
            json_match = search(
                r'<rainews-aggregator-broadcast-archive\s+data="([^"]+)"',
                response.text
            )
            if json_match:
                json_str = html_unescape(json_match.group(1))
                data = loads(json_str)
            else:
                return None

        paths = [
            ["video", "content_url"],
            ["content_url"],
            ["props", "pageProps", "contentItem", "video", "contentUrl"],
            ["props", "pageProps", "program", "video", "contentUrl"],
            ["props", "pageProps", "data", "items", 0, "video", "contentUrl"]
        ]

        for path in paths:
            current = data
            valid = True
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                elif isinstance(current, list) and isinstance(key, int) and key < len(current):
                    current = current[key]
                else:
                    valid = False
                    break
            if valid and current:
                video_url = current
                if video_url.startswith("//"):
                    video_url = "https:" + video_url
                elif not video_url.startswith("http"):
                    video_url = "https://mediapolisvod.rai.it" + video_url
                return video_url
        return None

    except requests.exceptions.HTTPError as e:
        print("[DEBUG]HTTP error for {}: {}".format(page_url, e))
    except Exception as e:
        print("[ERROR] extracting video URL: {}".format(str(e)))

    return None


def normalize_url(url):
    """Normalizes the URL to ensure it is valid"""
    if not url:
        return url

    baseUrl = "https://www.raiplay.it/"
    url = url.replace(" ", "%20")
    if url[0:2] == "//":
        url = "https:" + url
    elif url[0] == "/":
        url = baseUrl[:-1] + url

    # http://www.rai.it/raiplay/programmi/dtime-iltempodiladyd/?json
    if "rai.it/raiplay" in url and url.endswith("/?json"):
        url = url.replace(
            "/?json",
            ".json").replace(
            "rai.it/raiplay",
            "raiplay.it")

    if url.endswith(".html?json"):
        url = url.replace(".html?json", ".json")
    # elif url.endswith("/?json"):
        # url = url.replace("/?json", "/index.json")
    elif url.endswith("?json"):
        url = url.replace("?json", ".json")

    url = url.replace("http://", "https://")
    video_url = extract_real_video_url(url)
    if video_url:
        return video_url
    else:
        return url


class setPlaylist(MenuList):
    def __init__(self, liste):
        MenuList.__init__(self, liste, True, eListboxPythonMultiContent)
        if screenwidth.width() == 2560:
            self.l.setFont(0, gFont('Regular', 48))
            self.l.setItemHeight(56)
        elif screenwidth.width() == 1920:
            self.l.setFont(0, gFont('Regular', 30))
            self.l.setItemHeight(50)
        else:
            self.l.setFont(0, gFont('Regular', 24))
            self.l.setItemHeight(45)


def RaiPlaySetListEntry(name):
    res = [name]
    pngx = resolveFilename(
        SCOPE_PLUGINS,
        "Extensions/{}/res/pics/setting.png".format('RaiPlay'))
    if screenwidth.width() == 2560:
        res.append(
            MultiContentEntryPixmapAlphaTest(
                pos=(
                    10, 15), size=(
                    40, 40), png=loadPNG(pngx)))
        res.append(
            MultiContentEntryText(
                pos=(
                    80,
                    0),
                size=(
                    2000,
                    60),
                font=0,
                text=name,
                color=0xa6d1fe,
                flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    elif screenwidth.width() == 1920:
        res.append(
            MultiContentEntryPixmapAlphaTest(
                pos=(
                    5, 5), size=(
                    40, 40), png=loadPNG(pngx)))
        res.append(
            MultiContentEntryText(
                pos=(
                    70,
                    0),
                size=(
                    1150,
                    50),
                font=0,
                text=name,
                color=0xa6d1fe,
                flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    else:
        res.append(
            MultiContentEntryPixmapAlphaTest(
                pos=(
                    3, 10), size=(
                    40, 40), png=loadPNG(pngx)))
        res.append(
            MultiContentEntryText(
                pos=(
                    50,
                    0),
                size=(
                    670,
                    50),
                font=0,
                text=name,
                color=0xa6d1fe,
                flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    return res


def show_list(data, listas):
    icount = 0
    plist = []
    for line in data:
        name = str(data[icount])
        plist.append(RaiPlaySetListEntry(name))
        icount += 1
    listas.setList(plist)
    if hasattr(listas, 'instance') and listas.instance is not None:
        listas.instance.invalidate()


class RaiPlaySettings(Setup):
    def __init__(self, session, parent=None):
        Setup.__init__(
            self,
            session,
            setup="RaiPlaySettings",
            plugin="Extensions/RaiPlay")
        self.parent = parent

    def keySave(self):
        Setup.keySave(self)


class RaiPlayState:
    """
    Stores navigation history for RaiPlay screens,
    including screen name, selected index, and optional parameters.
    """

    def __init__(self):
        """Initialize an empty navigation history."""
        self.history = []

    def push(self, screen_class, index, params=None):
        """
        Add a new state to the history.
        Avoids adding the state if it is identical to the last one.
        :param screen_class: Name of the screen class.
        :param index: Selected index in the list.
        :param params: Optional additional parameters.
        """
        if self.history and self.history[-1][0] == screen_class and self.history[-1][1] == index:
            return
        self.history.append((screen_class, index, params))

    def pop(self):
        """
        Remove and return the last state from the history.
        Returns None if the history is empty.
        """
        if self.history:
            return self.history.pop()
        return None


class SafeScreen(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.screen_ready = False
        self.closing = False
        self.Update = False
        self.state_index = 0
        self.last_index = -1
        self.icons = []
        self.api = RaiPlayAPI()
        self.picload = ePicLoad()
        self['text'] = setPlaylist([])
        if "text" in self:
            self['text'].onSelectionChanged.append(self.selectionChanged)
        if not hasattr(session, 'raiplay_state'):
            session.raiplay_state = RaiPlayState()

        # Variabili per download
        self.selected_name = ""
        self.selected_url = ""
        self.is_video_screen = False

        self.onLayoutFinish.append(self.initPicload)
        self.onShown.append(self.onScreenShown)
        self.onHide.append(self.save_state)
        self.onClose.append(self.cleanup)

    def initPicload(self):
        """Initialize the image loader (picload) after screen layout is complete."""
        try:
            size = self["poster"].instance.size()
            self.poster_width = size.width()
            self.poster_height = size.height()
            print("[DEBUG]Poster dimensions: " + str(self.poster_width) +
                  "x" + str(self.poster_height))

            try:
                self.picload.PictureData.get().append(self.setPoster)
            except BaseException:
                self.picload_conn = self.picload.PictureData.connect(
                    self.setPoster)

            self.screen_ready = True
        except Exception as e:
            print("[ERROR] initializing picload: " + str(e))
            self.screen_ready = False

    def firstSelection(self):
        """
        Handles the first selection when the screen is shown.
        Does nothing if the screen is not ready or a saved state has been restored.
        Otherwise, moves selection to the first item and triggers selectionChanged.
        """
        try:
            if not self.screen_ready:
                return

            # Do not override selection if a saved state was already restored
            if hasattr(
                    self,
                    "restored_from_state") and self.restored_from_state:
                return

            if hasattr(self, "names") and self.names:
                self["text"].moveToIndex(0)
                self.selectionChanged()
        except Exception as e:
            # You may want to handle/log the exception here
            print("[ERROR] in firstSelection:", str(e))
            pass

    def updateUI(self):
        """Force UI to update"""
        if self['text'].instance:
            self['text'].instance.invalidate()

        if self.instance:
            self.instance.invalidate()

    def onLayoutFinished(self):
        """Called when the layout of the screen has finished; updates poster size."""
        try:
            size = self["poster"].instance.size()
            self.poster_width = size.width()
            self.poster_height = size.height()
            print("[DEBUG]Poster dimensions: %dx%d" %
                  (self.poster_width, self.poster_height))
        except BaseException:
            pass

    def onScreenShown(self):
        """
        Called when the screen is shown.
        Restores the previous selection index if available,
        otherwise selects the first item by default.
        """
        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
            self.selectionChanged()
        else:
            self.firstSelection()

    def save_state(self):
        """
        Saves the current selection index and any additional parameters
        into the RaiPlay state history for this screen.
        """
        text_obj = self['text'] if 'text' in self else None
        current_index = text_obj.getSelectionIndex() if text_obj else 0
        params = self.get_state_params()
        self.session.raiplay_state.push(
            self.__class__.__name__, current_index, params)

    def restore_state(self):
        """
        Restores the selection index for this screen from the RaiPlay state history.
        Returns True if a valid index was restored, False otherwise.
        """
        if not hasattr(
                self.session,
                "raiplay_state") or not self.session.raiplay_state:
            return False

        screen_name = self.__class__.__name__
        history = self.session.raiplay_state.history

        for state in reversed(history):
            if state[0] == screen_name:
                _, index, _ = state
                if 0 <= index < len(self['text'].list):
                    self.state_index = index
                    return True
                else:
                    return False

        return False

    def get_state_params(self):
        """To be overridden in subclasses to save specific parameters"""
        print("[DEBUG]>>> get_state_params called - returning None by default")
        return None

    def selectionChanged(self):
        """Update the poster image based on the current selection."""
        if not self.screen_ready:
            return

        try:
            self.ensure_icons_list()
            current_index = self["text"].getSelectionIndex()

            if current_index is None:
                return

            if current_index == self.last_index:
                return

            self.last_index = current_index
            self.setPoster()
        except Exception as e:
            print("[ERROR] in selectionChanged: " + str(e))
            self.setFallbackPoster()

    def updatePoster(self):
        """Update the poster image according to the selected item."""
        if self.closing or not self.screen_ready:
            return

        try:
            if self.closing:
                print("[DEBUG]Cannot update poster - screen closing")
                return

            if not hasattr(self, "icons") or not self.icons:
                print("[DEBUG]No icons available, using default")
                self.setFallbackPoster()
                return
            idx = self["text"].getSelectionIndex()

            if idx is None or idx < 0 or idx >= len(self.icons):
                self.setFallbackPoster()
                return

            icon_url = self.icons[idx]
            print(
                "[DEBUG]Updating poster for index %d: %s" %
                (idx, str(icon_url)))

            if not icon_url or not isinstance(
                    icon_url, str) or not icon_url.startswith("http"):
                print("[DEBUG]Using default icon - invalid URL:", icon_url)
                self.setFallbackPoster()
                return

            self.picload.setPara((
                self.poster_width,
                self.poster_height,
                1,  # scale
                1,  # aspect ratio
                False,
                1,
                "#FF000000"
            ))
            self.picload.startDecode(icon_url)
        except Exception as e:
            print("[ERROR] updating poster: " + str(e))
            self.setFallbackPoster()

    def ensure_icons_list(self):
        """Ensure the icons list exists and has the correct length."""
        if not hasattr(self, "icons"):
            self.icons = []

        if hasattr(self, "names"):
            # Estendi la lista delle icone se necessario
            while len(self.icons) < len(self.names):
                self.icons.append(self.api.DEFAULT_ICON_URL)

    def setPoster(self, data=None):
        """Callback for when the image is ready to be displayed."""
        if self.closing:
            return
        try:
            from six import PY3, ensure_binary
            pictmp = '/tmp/poster.png'
            idx = self["text"].getSelectionIndex()
            if idx is None or idx < 0 or idx >= len(self.icons):
                print("[DEBUG]Invalid index: %s (icons: %d)" %
                      (str(idx), len(self.icons)))
                self.setFallbackPoster()
                return

            icon_url = self.icons[idx]
            self.pixim = str(icon_url)

            if self.pixim == self.api.DEFAULT_ICON_URL:
                self.setFallbackPoster()
                return

            if self.pixim.startswith(plugin_path):
                self.decodeImage(self.pixim)
                return

            if PY3:
                self.pixim = ensure_binary(self.pixim)
            if self.pixim.startswith(b"https") and sslverify:
                parsed_uri = urlparse(self.pixim)
                domain = parsed_uri.hostname
                sniFactory = SNIFactory(domain)
                downloadPage(
                    self.pixim,
                    pictmp,
                    sniFactory,
                    timeout=ntimeout).addCallback(
                    self.image_downloaded,
                    pictmp).addErrback(
                    self.downloadError)
            else:
                downloadPage(
                    self.pixim,
                    pictmp).addCallback(
                    self.image_downloaded,
                    pictmp).addErrback(
                    self.downloadError)

        except Exception as e:
            print(e)
            self.downloadError()

    def image_downloaded(self, data, pictmp):
        """Called when the image download completes successfully."""
        if exists(pictmp):
            try:
                if DEBUG_MODE:
                    with open(pictmp, "rb") as f:
                        head = f.read(20)
                        print("[DEBUG] Image head bytes:", head)
                self.decodeImage(pictmp)
            except Exception as e:
                print("[ERROR] decoding image:", e)

    def decodeImage(self, png):
        """Decode and display the downloaded image."""
        self["poster"].hide()
        if exists(png):
            size = self['poster'].instance.size()
            self.picload = ePicLoad()
            self.scale = AVSwitch().getFramebufferScale()
            self.picload.setPara(
                [size.width(), size.height(), self.scale[0], self.scale[1], 1, 1, '#00000000'])
            if exists('/var/lib/dpkg/status'):
                self.picload.startDecode(png, False)
            else:
                self.picload.startDecode(png, 0, 0, False)
            ptr = self.picload.getData()
            if ptr is not None:
                self['poster'].instance.setPixmap(ptr)
                self['poster'].show()
            return
        else:
            self.setFallbackPoster()

    def downloadError(self, error=""):
        """Handle errors occurred during image download."""
        try:
            if self["poster"].instance:
                self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
                self['poster'].show()
            print('error download: ', error)
        except Exception as e:
            print('error downloadError poster', e)
            self.setFallbackPoster()

    def setFallbackPoster(self):
        """Display a default poster when image loading fails."""
        try:
            self.picload.setPara((
                self.poster_width,
                self.poster_height,
                0,              # scale X (0 = no scale on framebuffer)
                1,              # aspect ratio (1 = keep aspect ratio)
                True,           # resize to fit poster
                1,              # keep aspect ratio
                "#00000000"     # transparent background
            ))
            self.picload.startDecode(DEFAULT_ICON)
        except Exception as e:
            print("[ERROR] setFallbackPoster failed in picload:", e)
            try:
                self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
                self['poster'].show()
            except Exception as e2:
                print("[ERROR] setFallbackPoster failed setting pixmap:", e2)

    def getFullImagePath(self, path):
        """Return the full path for local images or return default URL."""
        if not path:
            return self.api.DEFAULT_ICON_URL

        if path.startswith("http"):
            return self.getFullUrl(path)

        if path.startswith("/") or path.startswith(plugin_path):
            return path

        return self.api.DEFAULT_ICON_URL

    def addToDownloadQueue(self, title, url):
        """Adds a video to the download queue"""
        print(f"[DEBUG] addToDownloadQueue called: {title}")
        print(f"[DEBUG] URL: {url}")

        try:
            # Ensure download manager exists
            if not hasattr(self.session, 'download_manager'):
                print("[DEBUG] Creating new download manager instance...")
                self.session.download_manager = RaiPlayDownloadManager(self.session)

            if not self.session.download_manager:
                print("[DEBUG] ERROR: Download manager is None!")
                self.session.open(
                    MessageBox,
                    _("Error: Download manager not available"),
                    MessageBox.TYPE_ERROR
                )
                return

            print("[DEBUG] Download manager ready, adding download...")

            # Normalize URL before adding to download
            normalized_url = normalize_url(url)
            print(f"[DEBUG] Normalized download URL: {normalized_url}")

            # Add download to manager and get the assigned ID
            download_id = self.session.download_manager.add_download(title, normalized_url)

            if download_id:
                print(f"[DEBUG] Download added successfully with ID: {download_id}")

                # Force save and reload queue to verify
                self.session.download_manager.save_downloads()
                queue = self.session.download_manager.get_queue()
                print(f"[DEBUG] Queue now has {len(queue)} items")
            else:
                print("[DEBUG] Failed to add download")
                self.session.open(MessageBox, f"📥 Added to queue: {title}", MessageBox.TYPE_INFO, timeout=3)

        except Exception as e:
            print(f"[DEBUG] Exception in addToDownloadQueue: {e}")
            import traceback
            traceback.print_exc()
            self.session.open(MessageBox, "Error adding download", MessageBox.TYPE_ERROR, timeout=5)

    def playDirect(self, name, url):
        """Direct playback with provided URL."""
        try:
            print(f"[DEBUG] playDirect called: {name}")
            print(f"[DEBUG] Original URL: {url}")

            url = normalize_url(url)
            print(f"[DEBUG] Normalized URL: {url}")

            url = strwithmeta(url, {
                'User-Agent': USER_AGENT,
                'Referer': 'https://www.raiplay.it/'
            })

            safe_name = str(name)
            try:
                safe_name = safe_name.encode(
                    "utf-8", errors="ignore").decode("utf-8")
            except Exception:
                pass

            print(f"[DEBUG] Opening Playstream2 with: {safe_name}")
            self.session.open(Playstream2, safe_name, url)

        except Exception as e:
            print(f'[ERROR] playing direct: {str(e)}')
            import traceback
            traceback.print_exc()
            self.session.open(
                MessageBox,
                _("Error playing stream: {}").format(str(e)),
                MessageBox.TYPE_ERROR)

    def infohelp(self):
        """Info for Plugin RaiPlay."""
        self.session.open(RaiPlayInfo)

    def cleanup(self):
        """Clean up resources and prepare screen for closure."""
        if self.closing:
            return
        self.closing = True
        print("[DEBUG][SafeScreen] Cleaning up " + self.__class__.__name__)
        try:
            # Add explicit cleanup of UI elements
            if 'text' in self:
                self['text'].setList([])

            # Clear data lists
            for attr in [
                    'videos',
                    'names',
                    'urls',
                    '_history',
                    'items',
                    'blocks']:
                if hasattr(self, attr):
                    setattr(self, attr, [])

            if hasattr(self, 'pic_timer'):
                self.pic_timer.stop()

            if hasattr(self, 'picload'):
                del self.picload
            """
            # for attr in [
                # 'videos',
                # 'names',
                # 'urls',
                # '_history',
                # 'items',
                    # 'blocks']:
                # if attr in self.__dict__:
                    # delattr(self, attr)
            """
            import gc
            gc.collect()
        except Exception as e:
            print("[DEBUG]Cleanup error: " + str(e))
            traceback.print_exc()

    def close(self, *args, **kwargs):
        """Override close method with safe handling."""
        print("[DEBUG][SafeScreen] Closing " + self.__class__.__name__)
        if hasattr(self.session, 'download_manager'):
            self.session.download_manager.stop_worker()

        self.cleanup()
        deletetmp()
        self.restore_state()
        if NOTIFICATION_AVAILABLE:
            from .notify_play import cleanup_notifications
            cleanup_notifications()
        super(SafeScreen, self).close(*args, **kwargs)

    def force_close(self):
        """Force close the screen if normal close fails."""
        if not self.closing and self.execing:
            print("[DEBUG]Force closing screen due to timeout")
            try:
                self.close()
            except BaseException:
                print("[DEBUG]Force close failed")
                for key in list(self.__dict__.keys()):
                    if key not in ['session', 'desktop', 'instance']:
                        delattr(self, key)
                try:
                    super(Screen, self).close()
                except BaseException:
                    pass

    def doClose(self):
        """Attempt to close the screen, ignoring exceptions."""
        try:
            self.close()
        except Exception:
            pass


class RaiPlayAPI:
    def __init__(self):
        """Initialize the RaiPlayAPI with URLs and constants used for requests."""
        self.MAIN_URL = 'https://www.raiplay.it/'
        self.MEDIA_URL = 'https://mediapolisvod.rai.it'
        self.MENU_URL = "https://www.rai.it/dl/RaiPlay/2016/menu/PublishingBlock-20b274b1-23ae-414f-b3bf-4bdc13b86af2.html?homejson"

        self.DEFAULT_ICON_URL = "https://images-eu.ssl-images-amazon.com/images/I/41%2B5P94pGPL.png"
        self.NOTHUMB_URL = "https://www.rai.it/cropgd/256x144/dl/components/img/imgPlaceholder.png"

        self.HTTP_HEADER = {'User-Agent': USER_AGENT}
        # self.LOCALIZEURL = "https://mediapolisgs.rai.it/relinker/relinkerServlet.htm?cont=201342"

        self.HOME_INDEX = "https://www.raiplay.it/index.json"
        self.GUIDA_TV = "https://www.raiplay.it/guidatv.json"

        self.ON_AIR_URL = "https://www.raiplay.it/palinsesto/onAir.json"
        self.RAIPLAY_AZ_TV_SHOW_PATH = "https://www.raiplay.it/dl/RaiTV/RaiPlayMobile/Prod/Config/programmiAZ-elenco.json"
        self.RAIPLAY_AZ_RADIO_SHOW_PATH = "https://www.raiplay.it/dl/RaiTV/RaiRadioMobile/Prod/Config/programmiAZ-elenco.json"

        self.CHANNELS_URL = "https://www.raiplay.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        self.CHANNELS_URL2 = "https://www.rai.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        self.CHANNELS_THEATRE = "https://www.raiplay.it/raiplay/tipologia/musica-e-teatro/index.json"
        self.EPG_URL = "https://www.rai.it/dl/palinsesti/Page-e120a813-1b92-4057-a214-15943d95aa68-json.html?canale={}&giorno={}"
        self.EPG_REPLAY_URL = "https://www.raiplay.it/palinsesto/app/old/{}/{}.json"
        self.PROGRAMS_ALL_URL = "https://www.raiplay.it/genere/Programmi---Tutti-20269973-8d0d-4cc4-9f82-66bd9fa2b03a.json"
        # PALINSESTO_URL_HTML = "https://www.raiplay.it/palinsesto/guidatv/lista/[idCanale]/[dd-mm-yyyy].html"

        self.TG_URL = "https://www.tgr.rai.it/dl/tgr/mhp/home.xml"

        # Raiplay RADIO
        # self.BASEURL = "https://www.raiplayradio.it/"
        self.CHANNELS_RADIO_URL = "https://www.raiplaysound.it/dirette.json"
        # PALINSESTO_URL = "https://www.raiplaysound.it/dl/palinsesti/Page-a47ba852-d24f-44c2-8abb-0c9f90187a3e-json.html?canale=[nomeCanale]&giorno=[dd-mm-yyyy]&mode=light"
        # self.NOTHUMB_RADIO_URL = "https://www.raiplayradio.it/dl/components/img/radio/player/placeholder_img.png"

        # Rai Sport urls
        self.RAISPORT_MAIN_URL = 'https://www.raisport.rai.it'
        self.RAISPORT_LIVE_URL = self.RAISPORT_MAIN_URL + '/dirette.html'
        self.RAISPORT_ARCHIVIO = self.RAISPORT_MAIN_URL + '/archivio.html'
        self.RAISPORT_ARCHIVIO_URL = 'https://www.rainews.it/notiziari/tgsport/archivio'
        self.RAISPORTDOMINIO = "RaiNews|Category-6dd7493b-f116-45de-af11-7d28a3f33dd2"
        self.RAISPORT_CATEGORIES_URL = "https://www.rainews.it/category/6dd7493b-f116-45de-af11-7d28a3f33dd2.json"
        self.RAISPORT_SEARCH_URL = "https://www.rainews.it/atomatic/news-search-service/api/v3/search"

        self.debug_dir = '/tmp/raiplay_debug/'
        try:
            if not exists(self.debug_dir):
                makedirs(self.debug_dir)
        except Exception as e:
            print("[DEBUG] Cannot create debug directory:", e)
            return []

        self.data_json_path = join(self.debug_dir, "rai_data.json")
        self.CACHE_FILE = join(self.debug_dir, "rai_categories.json")
        self.root_json = None
        self.RaiSportKeys = []
        self.exclude_paths = {
            "tipologia/guidatv",
            "tipologia/dirette",
            "tipologia/musica",
            "user/login",
            "user/ultimivisti",
            "user/preferiti",
            "user/guardadopo",
            "aiuto",
            "privacy/PrivacyPolicyRegistration",
            "guidatv", "dirette", "musica",
            "account/FAQ-PIATTAFORME-RAI",
            "Page-7a557e15-fc3f-48de-ae45-f80de8732886"  # Specific problematic path
        }

        self.exclude_names = {
            "home", "tv guide / replay", "live", "login / register",
            "recently watched", "my favorites", "watch later", "watch offline",
            "tutorial", "faq", "contact us", "privacy policy",
            "rai corporate", "privacy attività giornalistica", "cookie policy", "preferenze cookie",
            "rai", "rainews", "raiplay sound", "rai cultura", "rai scuola",
            "rai teche", "raiplay yoyo", "canone", "lavora con noi", "vai all'elenco completo",
            "x", "facebook", "instagram", "login"  # , "raiplay"
        }

    def load_categories_cached(self):
        """Load RaiSport categories from a cache file if available, otherwise download and cache them.
        """
        if exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    print("[DEBUG] Loading categories from cache file")
                    data = load(f)
                    if DEBUG_MODE:
                        # Save the structure for debugging
                        with open(join(self.debug_dir, "raisport_categories.json"), "w", encoding="utf-8") as debug_f:
                            dump(data, debug_f, indent=2, ensure_ascii=False)

                        print(
                            "[DEBUG] Saved categories structure to raisport_categories.json")

                    return data
            except Exception as e:
                print("[ERROR] Failed to load cache, will re-download:", e)
                try:
                    remove(self.CACHE_FILE)
                except BaseException:
                    pass

        url = self.RAISPORT_CATEGORIES_URL
        try:
            print("[DEBUG] Downloading categories JSON")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            if DEBUG_MODE:
                # Save the structure for debugging
                file_path = join(self.debug_dir, "raisport_categories.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    dump(data, f, indent=2, ensure_ascii=False)

            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                dump(data, f)
            return data
        except Exception as e:
            print("[ERROR] Failed to download categories JSON:", e)
            return None

    def find_category_by_unique_name(self, node, unique_name):
        """Helper function to find category by unique name"""
        if node.get("uniqueName") == unique_name:
            return node
        for child in node.get("children", []):
            result = self.find_category_by_unique_name(child, unique_name)
            if result:
                return result
        return None

    def fixPath(self, path):
        """
        Fixes malformed paths by ensuring the path starts with '/tipologia/'.
        Returns the original path if it's already correctly formatted.
        """
        if not path:
            return ""

        # If the path is already in the correct format, return it as is
        if match(r"^/tipologia/[^/]+/PublishingBlock-", path):
            return path

        # Fix malformed paths like /tipologiafiction/PublishingBlock-...
        malformed = match(r"^/tipologia([a-z]+)(/PublishingBlock-.*)", path)
        if malformed:
            fixed = "/tipologia/" + malformed.group(1) + malformed.group(2)
            print(
                "[DEBUG] fixPath: fixed malformed path: " +
                path +
                " -> " +
                fixed)
            return fixed

        return path

    def prepare_url(self, url):
        """Prepare the URL using existing functions with exclusion check"""
        if not url:
            return ""

        # First check if URL contains any excluded path
        url_lower = url.lower()
        if any(ep in url_lower for ep in self.exclude_paths):
            return ""

        # Then process the URL
        url = self.convert_old_url(url)
        url = normalize_url(url)
        if url.startswith("https://www.raiplay.it//"):
            url = url.replace("//", "/", 1)
            url = "https://www.raiplay.it" + url
        return url

    def convert_old_url(self, old_url):
        print("[DEBUG] Converting old URL: " + str(old_url))
        if not old_url:
            return old_url

        # Always convert www.rai.it to www.raiplay.it
        if "www.rai.it" in old_url:
            old_url = old_url.replace("www.rai.it", "www.raiplay.it")

        # Extract the relative path from the absolute URL (if any)
        parsed = urlparse(old_url)
        path = parsed.path
        query = ("?" + parsed.query) if parsed.query else ""

        path_and_query = path + query

        special_mapping = {
            "/raiplay/?json": "index.json",
            "/raiplay/fiction/?json": "tipologia/serieitaliane/index.json",
            "/raiplay/serietv/?json": "tipologia/serieinternazionali/index.json",
            "/raiplay/bambini//?json": "tipologia/bambini/index.json",
            "/raiplay/bambini/?json": "tipologia/bambini/index.json",
            "/raiplay/programmi/?json": "tipologia/programmi/index.json",
            "/raiplay/film/?json": "tipologia/film/index.json",
            "/raiplay/documentari/?json": "tipologia/documentari/index.json",
            "/raiplay/musica/?json": "tipologia/musica/index.json",
            "/raiplay/sport/?json": "tipologia/sport/index.json",
            "/raiplay/crime/?json": "tipologia/crime/index.json",
            "/raiplay/original/?json": "tipologia/original/index.json",
            "/raiplay/teen/?json": "tipologia/teen/index.json",
            "/raiplay/musica-e-teatro/?json": "tipologia/musica-e-teatro/index.json",
            "/raiplay/techerai/?json": "tipologia/techerai/index.json",
            "/raiplay/learning/?json": "tipologia/learning/index.json",
            "/raiplay/sostenibilita/?json": "tipologia/sostenibilita/index.json"}

        # Usa path+query per verificare se esiste nella mappa speciale
        if path_and_query in special_mapping:
            new_url = self.MAIN_URL + special_mapping[path_and_query]
            print("[DEBUG] Special mapping: {} -> {}".format(path_and_query, new_url))
            return new_url

        # Fix double extension issue (.html + /index.json)
        if ".html/index.json" in path_and_query:
            new_url = path_and_query.replace(".html/index.json", ".json")
            print(
                "[DEBUG] Fixed double extension: {} -> {}".format(path_and_query, new_url))
            return new_url

        # Generic conversion using regex
        matched = search(r'/raiplay/([^/]+)/?\?json', path_and_query)
        if matched:
            category = matched.group(1)
            new_url = self.MAIN_URL + "tipologia/" + category + "/index.json"
            print(
                "[DEBUG] Generic conversion: {} -> {}".format(path_and_query, new_url))
            return new_url

        # If it was an absolute URL but not found in the map, return the
        # original URL
        if parsed.scheme in ("http", "https"):
            print(
                "[DEBUG] No conversion for absolute URL {}, returning as is".format(old_url))
            return old_url

        # If relative URL without scheme and not in mapping, add MAIN_URL
        if not old_url.startswith("/"):
            new_url = self.MAIN_URL.rstrip("/") + "/" + old_url.lstrip("/")
            print(
                "[DEBUG] Added MAIN_URL to relative URL: {} -> {}".format(old_url, new_url))
            return new_url

        # No conversion found, return original URL
        print("[DEBUG] No conversion for {}, returning as is".format(old_url))
        return old_url

    def process_relinker(self, url):
        """Process relinker URL to extract playback URL and license key"""
        try:
            if "relinkerServlet" not in url:
                print("[Relinker] Not a relinker URL, skipping processing")
                return url, None

            print("[Relinker] Processing URL: " + url)

            # Modify URL to get XML response
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query["output"] = ["56"]  # Request XML format
            new_query = urlencode(query, doseq=True)
            new_url = urlunparse(parsed._replace(query=new_query))

            print("[Relinker] Fetching XML from: " + new_url)
            response = requests.get(
                new_url, headers=self.HTTP_HEADER, timeout=15)
            response.raise_for_status()
            content = response.text

            # Debug: save XML content
            if DEBUG_MODE:
                with open("/tmp/relinker.xml", "w") as f:
                    f.write(content)
                print("[Relinker] Saved XML to /tmp/relinker.xml")

            # Parse XML response
            url_match = search(r'<url type="content">(.*?)</url>', content)
            if not url_match:
                print("[Relinker] No content URL found in XML")
                return url, None

            content_url = url_match.group(1)
            print("[Relinker] Raw content URL: " + content_url)

            # Extract URL from CDATA if present
            if "<![CDATA[" in content_url:
                cdata_match = search(r'<!\[CDATA\[(.*?)\]\]>', content_url)
                if cdata_match:
                    content_url = cdata_match.group(1)
                    print("[Relinker] Extracted CDATA URL: " + content_url)

            # Check for DRM license
            license_key = None

            license_match = search(
                r'<license_url>(.*?)</license_url>', content)
            if license_match:
                license_json_str = license_match.group(1)
                print("[Relinker] Raw license JSON: " + license_json_str)

                if "<![CDATA[" in license_json_str:

                    cdata_match = search(
                        r'<!\[CDATA\[(.*?)\]\]>', license_json_str)
                    if cdata_match:
                        license_json_str = cdata_match.group(1)

                        print(
                            "[Relinker] Extracted CDATA license JSON: " +
                            license_json_str)

                try:
                    license_data = loads(license_json_str)
                    print("[Relinker] License data: " + str(license_data))

                    for item in license_data.get("drmLicenseUrlValues", []):
                        if item.get("drm") == "WIDEVINE":
                            license_key = item.get("licenceUrl")

                            print(
                                "[Relinker] Found Widevine license: " +
                                str(license_key))

                            break
                except Exception as e:
                    print("[Relinker] License parse error: " + str(e))

            print("[DEBUG][Relinker] Final URL: " + content_url)
            print("[DEBUG][Relinker] License key: " + str(license_key))
            return content_url, license_key

        except Exception as e:
            print("[DEBUG][Relinker] Error: " + str(e))
            return url, None

    def getPage(self, url):
        """Fetch the content of a page from a URL using HTTP GET.
        """
        try:
            # Skip URLs in the blacklist
            if any(ep in url for ep in self.exclude_paths):
                return False, None

            print("[DEBUG] Fetching URL: %s" % url)
            response = requests.get(
                url,
                headers=self.HTTP_HEADER,
                timeout=15,
                verify=False
            )
            response.raise_for_status()
            print("[DEBUG] Response status: %d" % response.status_code)
            return True, response.text
        except Exception as e:
            print("[ERROR] Error fetching page: %s" % str(e))
            return False, None

    def getFullUrl(self, url):
        """Return a full, absolute URL from a possibly relative or partial URL.
        """
        if not url:
            return ""

        if url.startswith('http'):
            return url

        if url.startswith("//"):
            return "https:" + url

        return urljoin(self.MAIN_URL, url)

    def getLiveTVChannels(self):
        """Fetch live TV channels and add archived videos.
        """
        data = Utils.getUrlSiVer(self.CHANNELS_URL)
        live_channels = []
        if data:
            try:
                response = loads(data)
                channels = response.get("dirette", [])
                for channel in channels:
                    live_channels.append({
                        'title': channel.get("channel", ""),
                        'url': channel.get("video", {}).get("contentUrl", ""),
                        'icon': self.getThumbnailUrl2(channel),
                        'desc': channel.get("description", ""),
                        'category': 'live_tv'
                    })
            except BaseException:
                pass

        # Add archived videos
        archive_videos = self.getArchivedVideos()
        return live_channels + archive_videos

    def getLiveRadioChannels(self):
        """Fetch live radio channels from the radio JSON feed.
        """
        data = Utils.getUrlSiVer(self.CHANNELS_RADIO_URL)
        if not data:
            return []

        try:
            response = loads(data)
            channels = response.get("contents", [])
            result = []

            for channel in channels:
                title = channel.get("title", "")
                audio = channel.get("audio", {})
                url = audio.get("url", "")

                if not title or not url:
                    continue

                icon = self.getThumbnailUrl2(channel)
                if not icon or icon == self.DEFAULT_ICON_URL:
                    icon = self.getThumbnailUrl2(audio)
                result.append({
                    "title": title,
                    "url": url,
                    "icon": icon,
                    "desc": channel.get("track_info", {}).get("title", ""),
                    "category": "live_radio"
                })

            return result
        except Exception as e:
            print("[DEBUG] [getLiveRadioChannels] JSON parse error:", e)
            return []

    def getArchivedVideos(self):
        """Fetch and parse archived videos from RaiNews sports archive page.
        """
        archive_url = self.RAISPORT_ARCHIVIO_URL
        print("[DEBUG] Fetching archive URL:", archive_url)
        data = Utils.getUrlSiVer(archive_url)

        if not data:
            print("[DEBUG] No data received from archive URL.")
            return []

        try:
            m = search(
                r'<rainews-aggregator-broadcast-archive[^>]+data="([^"]+)"',
                data)
            if not m:
                print("[DEBUG] No suitable JSON found in HTML.")
                return []

            raw_json = _html.unescape(m.group(1))
            print("[DEBUG] Extracted JSON length:", len(raw_json))
            if DEBUG_MODE:
                with open(self.debug_dir + "raw_json.txt", "w", encoding="utf-8") as f:
                    raw_path = join(self.debug_dir, "raw_json.txt")

                with open(raw_path, "w", encoding="utf-8") as f:
                    f.write(raw_json)

                print("[DEBUG] Saved raw JSON -> " + raw_path)

            json_data = loads(raw_json)
            if DEBUG_MODE:
                with open(self.debug_dir + "parsed_json.txt", "w", encoding="utf-8") as f:
                    f.write(dumps(json_data, indent=4, ensure_ascii=False))
                print("[DEBUG] Saved formatted JSON.")

            def parse_iso_date(date_str):
                if date_str and (len(date_str) > 5) and (
                        date_str[-5] in ['+', '-']) and (date_str[-3] != ':'):
                    date_str = date_str[:-2] + ':' + date_str[-2:]
                try:
                    return datetime.fromisoformat(date_str)
                except Exception:
                    try:
                        return datetime.strptime(
                            date_str, "%Y-%m-%dT%H:%M:%S%z")
                    except Exception:
                        return None

            cards = json_data.get("contents", [])[0].get("cards", [])
            print("[DEBUG] Found videos:", len(cards))

            result = []
            for idx, video in enumerate(cards):
                print("[DEBUG] Processing video {}/{}: {}".format(idx +
                      1, len(cards), video.get('title', 'NO TITLE')))

                title = video.get("title", "")
                content_url = video.get("content_url", "")
                video_path = video.get("weblink", "")
                video_page_url = "https://www.rainews.it{}".format(
                    video_path) if video_path else ""

                image_path = video.get(
                    "image",
                    {}).get(
                    "media_url",
                    video.get(
                        "images",
                        {}).get(
                        "locandinaOrizzontale",
                        ""))

                icon = self.getFullUrl(image_path) if image_path else ""

                date_iso = video.get("date", "")
                if not date_iso and "broadcast" in video:
                    date_iso = video["broadcast"].get(
                        "edition", {}).get("dateIso", "")

                print("[DEBUG] Raw dateIso:", date_iso)
                dt = parse_iso_date(date_iso)
                if dt:
                    formatted_date = dt.strftime("%d/%m/%Y %H:%M")
                else:
                    formatted_date = ""

                print("[DEBUG] Formatted date:", formatted_date)

                result.append({
                    "title": title,
                    "url": content_url,
                    "icon": icon,
                    "desc": video.get("description", ""),
                    "date": formatted_date,
                    "category": "archive",
                    "page_url": video_page_url,
                })

            print("[DEBUG] Total processed videos: {}".format(len(result)))
            return result

        except Exception as e:
            print("[DEBUG] Error parsing archive: {}".format(str(e)))
            return []

    def get_programs(self, channel_api_name, date_api):
        """
        Retrieve the list of programs with video for the given channel and date.
        """
        url = self.EPG_REPLAY_URL.format(channel_api_name, date_api)
        try:
            data = Utils.getUrlSiVer(url)
            if not data:
                print("[DEBUG] No data returned from URL:", url)
                return []

            response = loads(data)
            # Find matching channel key ignoring spaces
            channel_key = None
            for key in response.keys():
                if key.replace(" ", "") == channel_api_name:
                    channel_key = key
                    break

            if not channel_key:
                print("[DEBUG] Channel key not found, fallback to first key")
                channel_key = list(response.keys())[0]

            channel_data = response[channel_key]
            programs = []

            # Check new structure (list of days)
            if isinstance(channel_data, list):
                for day_data in channel_data:
                    palinsesti = day_data.get("palinsesto", [])
                    for palinsesto in palinsesti:
                        if palinsesto.get("giorno") == date_api:
                            programs = palinsesto.get("programmi", [])
                            break
            else:
                # Old structure (dict)
                palinsesti = channel_data.get("palinsesto", [])
                for palinsesto in palinsesti:
                    if palinsesto.get("giorno") == date_api:
                        programs = palinsesto.get("programmi", [])
                        break

            result = []
            for program in programs:
                if not program.get("hasVideo", False):
                    continue

                title = program.get("name", "No title")
                time_str = program.get("timePublished", "")
                video_url = program.get(
                    "pathID",
                    "") or program.get(
                    "video",
                    {}).get(
                    "contentUrl",
                    "")

                if video_url.startswith("//"):
                    video_url = "https:" + video_url
                elif not video_url.startswith("http"):
                    video_url = "https://www.raiplay.it" + video_url

                icon_url = self.getThumbnailUrl2(program)
                display_title = (time_str + " " if time_str else "") + title

                result.append({
                    "title": display_title,
                    "url": video_url,
                    "icon": icon_url,
                    "timePublished": time_str,
                })

            return result

        except Exception as e:
            print("[DEBUG] Error in get_programs:", str(e))
            return []

    def getOnDemandMenu(self):
        """Retrieve the on-demand menu categories and special entries."""
        url = self.MENU_URL
        data = Utils.getUrlSiVer(url)
        if not data:
            return []

        try:
            response = loads(data)
            result = []
            seen_urls = set()

            for item in response.get("menu", []):

                if "url" in item:
                    item["url"] = self.prepare_url(item["url"])

                if "PathID" in item:
                    item["PathID"] = self.prepare_url(item["PathID"])

                path_id = item.get("PathID", "")
                # Exclude by name
                name = item.get("name", "")
                if name.lower() in self.exclude_names:
                    continue
                # Exclude if path_id contains a segment to exclude
                if any(exclude_path in path_id.lower()
                       for exclude_path in self.exclude_paths):
                    continue

                if item.get("sub-type") in ("RaiPlay Tipologia Page",
                                            "RaiPlay Genere Page",
                                            "RaiPlay Tipologia Editoriale Page"):
                    name = item.get("name", "")

                    # Handling special categories
                    if name == "Kids and Teens":
                        # Subcategory Kids
                        kids_url = self.prepare_url(
                            "/raiplay/tipologia/bambini/index.json")
                        if kids_url not in seen_urls:
                            result.append({
                                "title": "Kids",
                                "url": kids_url,
                                "icon": self.getThumbnailUrl2(item),
                                "sub-type": "RaiPlay Tipologia Page"
                            })
                            seen_urls.add(kids_url)

                        # Subcategory Teen
                        teen_url = self.prepare_url(
                            "/raiplay/tipologia/teen/index.json")
                        if teen_url not in seen_urls:
                            result.append({
                                "title": "Teen",
                                "url": teen_url,
                                "icon": self.getThumbnailUrl2(item),
                                "sub-type": "RaiPlay Tipologia Page"
                            })
                            seen_urls.add(teen_url)

                    elif name == "Fiction":
                        # Italian series
                        italian_url = self.prepare_url(
                            "/raiplay/tipologia/serieitaliane/index.json")
                        if italian_url not in seen_urls:
                            result.append({
                                "title": "Italian Series",
                                "url": italian_url,
                                "icon": self.getThumbnailUrl2(item),
                                "sub-type": "RaiPlay Tipologia Page"
                            })
                            seen_urls.add(italian_url)

                        # Original
                        original_url = self.prepare_url(
                            "/raiplay/tipologia/original/index.json")
                        if original_url not in seen_urls:
                            result.append({
                                "title": "Original",
                                "url": original_url,
                                "icon": self.getThumbnailUrl2(item),
                                "sub-type": "RaiPlay Tipologia Page"
                            })
                            seen_urls.add(original_url)

                    elif name == "International Series":
                        # International series
                        intl_url = self.prepare_url(
                            "/raiplay/tipologia/serieinternazionali/index.json")
                        if intl_url not in seen_urls:
                            result.append({
                                "title": "International Series",
                                "url": intl_url,
                                "icon": self.getThumbnailUrl2(item),
                                "sub-type": "RaiPlay Tipologia Page"
                            })
                            seen_urls.add(intl_url)

                    else:
                        # Standard categories
                        converted_url = self.prepare_url(path_id)
                        if converted_url and converted_url not in seen_urls:
                            result.append({
                                "title": name,
                                "url": converted_url,
                                "icon": self.getThumbnailUrl2(item),
                                "sub-type": item.get("sub-type", "")
                            })
                            seen_urls.add(converted_url)

            # Add fixed categories outside the loop
            fixed_categories = [{"title": "Theatre and Music",
                                 "url": self.CHANNELS_THEATRE,
                                 "icon": self.getFullUrl("/dl/img/2018/06/04/1528115285089_ico-teatro.png"),
                                 "sub-type": "RaiPlay Tipologia Page"},

                                {"title": "Documentaries",
                                 "url": "https://www.raiplay.it/tipologia/documentari/index.json",
                                 "icon": self.getFullUrl("/dl/img/2018/06/04/1528115285089_ico-documentari.png"),
                                 "sub-type": "RaiPlay Tipologia Page"}]

            for cat in fixed_categories:
                if cat["url"] not in seen_urls:
                    result.append(cat)
                    seen_urls.add(cat["url"])

            return result
        except Exception as e:
            print("[DEBUG]Error in getOnDemandMenu: " + str(e))
            return []

    def getOnDemandCategory(self, url):
        """
        Fetch and parse JSON data from the given URL and extract category items.
        """
        # Prepare the URL
        url = self.prepare_url(url)
        print("[DEBUG] Fetching category: {}".format(url))
        data = Utils.getUrlSiVer(url)
        if not data:
            print("[ERROR] No data received for URL: {}".format(url))
            return []

        try:
            response = loads(data)
            print("[DEBUG] JSON response keys: " + str(list(response.keys())))
            items = []
            az_structures = []

            # 1. Check if there is a direct AZ structure
            az_keys = ['0-9'] + [chr(ord('A') + i) for i in range(26)]
            if any(key in response for key in az_keys):
                print("[DEBUG] Found direct AZ structure")
                az_structures.append(response)

            # 2. Check if there is an AZ structure inside 'contents'
            if "contents" in response and isinstance(
                    response["contents"], dict):
                print("[DEBUG] Found AZ structure inside 'contents'")
                az_structures.append(response["contents"])

            # 3. Check if there is an AZ structure inside 'blocks'
            if "blocks" in response and isinstance(response["blocks"], list):
                for block in response["blocks"]:
                    if "contents" in block and isinstance(
                            block["contents"], dict):
                        if any(key in block["contents"] for key in az_keys):
                            print("[DEBUG] Found AZ structure inside block")
                            az_structures.append(block["contents"])

            # Process all AZ structures found
            for az_structure in az_structures:
                for key in az_keys:
                    if key in az_structure and az_structure[key]:
                        for item in az_structure[key]:
                            name = item.get("name", "")
                            if not name:
                                continue

                            raw_url = item.get(
                                "path_id") or item.get("PathID") or ""
                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            icon_url = self.getThumbnailUrl2(item)

                            items.append({
                                "name": name,
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": item.get("type", "PLR programma Page")
                            })

                # If we already found items, return them immediately
                if items:
                    print(
                        "[DEBUG] Found {} items in AZ structure".format(
                            len(items)))
                    return items

            # Case 1: Direct list of items
            if "items" in response and isinstance(response["items"], list):
                for i, item in enumerate(response["items"]):
                    print(
                        "[DEBUG] Item #{}: {}".format(
                            i, item.get(
                                "name", "no-name")))
                    raw_url = item.get("path_id") or item.get(
                        "url") or item.get("PathID") or ""
                    url_fixed = self.fixPath(raw_url) if raw_url else None
                    icon_url = self.getThumbnailUrl2(item)
                    item_data = {
                        "name": item.get("name", ""),
                        "url": url_fixed,
                        "icon": icon_url,
                        "sub-type": item.get("type", item.get("sub_type", ""))
                    }
                    items.append(item_data)

            # Case 2: Response with blocks structure
            elif "blocks" in response and isinstance(response["blocks"], list):
                print("[DEBUG] Found 'blocks' structure")
                for block in response["blocks"]:
                    block_type = block.get("type", "")
                    print(
                        "[DEBUG] Processing block type: {}".format(block_type))
                    if block_type == "RaiPlay Slider Generi Block":
                        for j, item in enumerate(block.get("contents", [])):
                            raw_url = item.get(
                                "path_id") or item.get("url") or ""
                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            icon_url = self.getFullUrl(item.get("image", ""))
                            item_data = {
                                "name": item.get("name", ""),
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": item.get("sub_type", "")
                            }
                            print("[DEBUG] Adding genre item: {} URL:{} ICON:{}".format(
                                item_data["name"], item_data["url"], item_data["icon"]))
                            items.append(item_data)

                    elif block_type == "RaiPlay Multimedia Block":
                        for j, item in enumerate(block.get("sets", [])):

                            print(
                                "[DEBUG] Set #{}: {}".format(
                                    j, item.get(
                                        "name", "no-name")))

                            icon_url = self.getThumbnailUrl2(item)

                            raw_url = item.get(
                                "path_id") or item.get("url") or ""

                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            item_data = {
                                "name": item.get("name", ""),
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": item.get("type", "")
                            }
                            items.append(item_data)

                    elif block_type == "RaiPlay Lista Programmi Block":
                        for content in block.get("contents", []):

                            raw_url = content.get(
                                "path_id") or content.get("PathID") or ""

                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            icon_url = self.getThumbnailUrl2(content)
                            item_data = {
                                "name": content.get("name", ""),
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": content.get("type", "")
                            }
                            items.append(item_data)

            # Case 3: Nested 'contents' structure
            elif "contents" in response and isinstance(response["contents"], list):
                print("[DEBUG] Found 'contents' array")
                for content_block in response["contents"]:
                    if "contents" in content_block and isinstance(
                            content_block["contents"], list):

                        for item in content_block["contents"]:

                            raw_url = item.get(
                                "path_id") or item.get("PathID") or ""

                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            icon_url = self.getThumbnailUrl2(item)
                            item_data = {
                                "name": item.get("name", ""),
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": item.get("type", "")
                            }
                            items.append(item_data)

            # Case 4: Alphabetical AZ list
            elif any(key in response for key in ["A", "B", "0-9"]):
                print("[DEBUG] Found AZ list structure")
                az_keys = ['0-9'] + [chr(ord('A') + i) for i in range(26)]
                for key in az_keys:
                    if key in response and response[key]:
                        for item in response[key]:
                            name = item.get("name", "")
                            if not name:
                                continue
                            raw_url = item.get(
                                "path_id") or item.get("PathID") or ""
                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            icon_url = self.getThumbnailUrl2(item)
                            item_data = {
                                "name": name,
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": item.get("type", "PLR programma Page")
                            }
                            items.append(item_data)
            print("[DEBUG] Found {} items in category".format(len(items)))
            return items

        except Exception as e:
            print("[ERROR] in getOnDemandCategory: " + str(e))
            traceback.print_exc()
            return []

    def getThumbnailUrl(self, pathOrUrl):
        """
        This function returns the thumbnail URL for a given pathId.
        If pathId is empty, it returns the default icon URL.
        Otherwise, it replaces the resolution placeholder with a fixed size.
        """
        if not pathOrUrl:
            return self.DEFAULT_ICON_URL
        if pathOrUrl.startswith("http"):
            url = pathOrUrl
        else:
            url = self.getFullUrl(pathOrUrl)
        return url.replace("[RESOLUTION]", "256x-")

    def getThumbnailUrl2(self, item):
        """
        Estrae l'URL della thumbnail più appropriata da un dizionario item.
        Ordine di priorità:
          1. image.media_url
          2. transparent-icon
          3. chImage
          4. images.* in ordine definito manualmente
        """
        print("[DEBUG]>>> getThumbnailUrl2 - item keys:", item.keys())

        def full_url(path):
            return path if path.startswith(
                "http") else "https://www.rainews.it" + path

        # 1. image.media_url
        image_data = item.get("image")
        if isinstance(image_data, dict):
            media_url = image_data.get("media_url")
        elif isinstance(image_data, str):
            media_url = image_data
        else:
            media_url = None

        if media_url:
            icon_url = full_url(media_url)
            print("[DEBUG]>>> Using image.media_url:", icon_url)
            return self.getThumbnailUrl(icon_url)

        # 2. transparent-icon
        if "transparent-icon" in item:
            icon_url = item["transparent-icon"]
            if "[an error occurred" not in icon_url:
                print("[DEBUG]>>> Using transparent-icon:", icon_url)
                return self.getThumbnailUrl(icon_url)
            else:
                print(
                    "[DEBUG]>>> Skipping invalid transparent-icon:",
                    icon_url)

        # 3. chImage
        if "chImage" in item:
            ch_image_url = item["chImage"]
            print("[DEBUG]>>> Using chImage:", ch_image_url)
            return self.getThumbnailUrl(ch_image_url)

        # 4. images dict (ordine originale)
        if "images" in item and isinstance(item["images"], dict):
            images = item["images"]
            print("[DEBUG]>>> Available image keys:", images.keys())

            if "locandinaOrizzontale" in images:
                icon_url = full_url(images["locandinaOrizzontale"])
                print("[DEBUG]>>> Using locandinaOrizzontale:", icon_url)
                return self.getThumbnailUrl(icon_url)
            elif "landscape" in images:
                print("[DEBUG]>>> Using landscape:", images["landscape"])
                return self.getThumbnailUrl(images["landscape"])
            elif "landscape43" in images:
                print("[DEBUG]>>> Using landscape43:", images["landscape43"])
                return self.getThumbnailUrl(images["landscape43"])
            elif "portrait" in images:
                print("[DEBUG]>>> Using portrait:", images["portrait"])
                return self.getThumbnailUrl(images["portrait"])
            elif "portrait43" in images:
                print("[DEBUG]>>> Using portrait43:", images["portrait43"])
                return self.getThumbnailUrl(images["portrait43"])
            elif "portrait_logo" in images:
                print(
                    "[DEBUG]>>> Using portrait_logo:",
                    images["portrait_logo"])
                return self.getThumbnailUrl(images["portrait_logo"])
            elif "square" in images:
                print("[DEBUG]>>> Using square:", images["square"])
                return self.getThumbnailUrl(images["square"])
            elif "default" in images:
                print("[DEBUG]>>> Using default:", images["default"])
                return self.getThumbnailUrl(images["default"])

        print("[DEBUG]>>> No valid thumbnail found, using DEFAULT_ICON_URL")
        return self.DEFAULT_ICON_URL

    def getProgramDetails(self, url):
        """Retrieve detailed information about a program including blocks and typology."""
        # url = self.prepare_url(url)
        url = self.getFullUrl(url)
        data = Utils.getUrlSiVer(url)
        if not data:
            return None

        try:
            response = loads(data)
            program_info = {
                "name": response.get("name", ""),
                "description": response.get("vanity", ""),
                "year": response.get("year", ""),
                "country": response.get("country", ""),
                "first_item_path": response.get("first_item_path", ""),
                "is_movie": False
            }

            # Check if the program is a movie
            typologies = response.get("typologies", [])
            for typology in typologies:
                if typology.get("name") == "Film":
                    program_info["is_movie"] = True
                    break

            blocks = []
            for block in response.get("blocks", []):
                block_data = {
                    "name": block.get("name", ""),
                    "type": block.get("type", ""),
                    "sets": []
                }

                for set_item in block.get("sets", []):
                    set_data = {
                        "name": set_item.get("name", ""),
                        "path_id": set_item.get("path_id", ""),
                        "type": set_item.get("type", "")
                    }
                    block_data["sets"].append(set_data)

                blocks.append(block_data)

            return {
                "info": program_info,
                "blocks": blocks
            }
        except Exception as e:
            print("[DEBUG]Error parsing program details: " + str(e))
            return None

    def getProgramItems(self, url):
        """Retrieve program elements for radio programs."""
        url = self.getFullUrl(url)
        data = Utils.getUrlSiVer(url)
        if not data:
            return []

        try:
            response = loads(data)
            items = []

            # Radio program structure
            if "block" in response and isinstance(response["block"], dict):
                cards = response["block"].get("cards", [])
                for card in cards:
                    audio_info = card.get("audio", {})
                    if not audio_info:
                        continue

                    title = card.get("title", "")
                    audio_url = audio_info.get("url", "")
                    icon_url = card.get("image", "")

                    items.append({
                        'title': title,
                        'url': audio_url,
                        'icon': icon_url,
                        'duration': audio_info.get("duration", 0),
                    })

            return items

        except Exception:
            return []

    def get_video_url_from_page(self, page_url):
        """Wrapper per la tua funzione esistente"""
        return extract_real_video_url(page_url)

    def get_tg_archive(self, tg_channel, page=1):
        """
        Retrieve all archived editions of the specified TG channel with pagination.
        """
        archive_url = "https://www.rainews.it/notiziari/{}/archivio".format(
            tg_channel)
        try:
            # Request parameters
            params = {'page': page} if page > 1 else {}
            headers = {
                "User-Agent": USER_AGENT,
                "Referer": "https://www.rainews.it/notiziari/{}/".format(tg_channel)}

            # Perform the HTTP request
            response = requests.get(
                archive_url,
                params=params,
                headers=headers,
                timeout=15,
                verify=False)
            response.raise_for_status()
            content = response.text

            # DEBUG: Save the HTML for analysis
            if DEBUG_MODE:
                file_path = join(
                    self.debug_dir,
                    "{}_archive_{}.html".format(
                        tg_channel,
                        page))
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print("[DEBUG] Saved archive page -> {}".format(file_path))

            # Extract pagination information
            pagination_info = {}
            pagination_match = search(
                r'<rainews-paginator\s+pageindex="(\d+)"\s+pagesize="(\d+)"\s+length="(\d+)"',
                content)
            if pagination_match:
                total_items = int(pagination_match.group(3))
                page_size = int(pagination_match.group(2))
                pagination_info = {
                    "current_page": int(pagination_match.group(1)),
                    "page_size": page_size,
                    "total_items": total_items,
                    "total_pages": (total_items + page_size - 1) // page_size
                }

            # 1. Extract JSON from <rainews-aggregator-broadcast-archive> tag
            json_match = search(
                r'<rainews-aggregator-broadcast-archive\s+data="([^"]+)"',
                content
            )

            if not json_match:
                print("JSON data not found in HTML!")
                return {"videos": [], "pagination": {}}

            # Decode JSON (remove HTML escaping)
            json_str = html_unescape(json_match.group(1))
            data = loads(json_str)

            # 2. Extract video editions from JSON
            videos = []
            for content_block in data.get("contents", []):
                for card in content_block.get("cards", []):
                    broadcast = card.get("broadcast", {})
                    edition = broadcast.get("edition", {})

                    # Use the 'link' field for the video page URL
                    video_path = card.get("link", "")
                    if not video_path:
                        continue

                    video_page_url = "https://www.rainews.it" + video_path

                    # Extract information for display
                    title = card.get("title", edition.get("title", "No title"))
                    date_str = "{} {}".format(
                        edition.get(
                            "date", ""), edition.get(
                            "hour", ""))
                    duration = card.get("duration", "")

                    # Use the existing function for thumbnail
                    img_url = self.getThumbnailUrl2(card)

                    # Add content_url directly if available
                    content_url = card.get("content_url", "")

                    videos.append({
                        "title": title,
                        "date": date_str,
                        "duration": duration,
                        "page_url": video_page_url,
                        "content_url": content_url,
                        "icon": img_url
                    })

            return {
                "videos": videos,
                "pagination": pagination_info
            }

        except Exception as e:
            print("[DEBUG]Error fetching TG archive: {}".format(str(e)))
            traceback.print_exc()
            return {
                "videos": [],
                "pagination": {}
            }

    def get_tg_content(self, tg_channel):
        """
        Retrieve the latest video content for the specified TG (TG1, TG2, TG3).
        """
        tg_urls = {
            "tg1": "https://www.rainews.it/notiziari/tg1",
            "tg2": "https://www.rainews.it/notiziari/tg2",
            "tg3": "https://www.rainews.it/notiziari/tg3"
        }

        if tg_channel not in tg_urls:
            return []

        try:
            response = requests.get(
                tg_urls[tg_channel],
                headers=self.HTTP_HEADER,
                timeout=10)
            response.raise_for_status()
            content = response.text

            # Extract the content of <rainews-player> tag using regex
            player_match = search(
                r'<rainews-player\s+data=\'(.*?)\'', content, DOTALL)
            if not player_match:
                return []

            # Decode HTML entities
            player_json = player_match.group(1)
            player_json = player_json.replace(
                '&quot;', '"').replace(
                '&#x3D;', '=')

            # Convert to Python object
            player_data = loads(player_json)

            # Extract video details
            return [
                {
                    "title": player_data.get(
                        "track_info", {}).get(
                        "title", "No title"), "subtitle": player_data.get(
                        "track_info", {}).get(
                        "episode_title", ""), "url": player_data.get(
                            "content_url", ""), "icon": self.getFullUrl(
                                player_data.get(
                                    "image", "")), "date": player_data.get(
                                        "track_info", {}).get(
                                            "create_date", "")}]

        except Exception as e:
            print("[DEBUG]Error fetching TG content: {}".format(str(e)))
            return []

    def getSportCategories(self):
        """Retrieve the main sports categories from the RAISport API."""
        try:
            data = Utils.getUrlSiVer(self.RAISPORT_CATEGORIES_URL)
            if not data:
                return []

            response = loads(data)
            categories = []

            sport_category = None
            if response.get("name") == "Sport":
                sport_category = response
            else:
                for category in response.get("children", []):
                    if category.get("name") == "Sport":
                        sport_category = category
                        break

            if not sport_category:
                return []

            for category in sport_category.get("children", []):
                title = category.get("name", "")
                unique_name = category.get("uniqueName", "")

                if title and unique_name:
                    thumbnail = ""
                    images = category.get("images", {})
                    if images:
                        if images.get("landscape", ""):
                            thumbnail = images["landscape"]
                        elif images.get("portrait", ""):
                            thumbnail = images["portrait"]
                        elif images.get("square", ""):
                            thumbnail = images["square"]

                    categories.append({
                        "title": title,
                        "key": unique_name,
                        "icon": thumbnail
                    })

            return categories

        except Exception as e:
            print("[DEBUG]Error getting sports categories:", str(e))
            traceback.print_exc()
            return []

    def getSportSubcategories(self, category_key):
        """Get subcategories for a specific sport category"""
        try:
            data = Utils.getUrlSiVer(self.RAISPORT_CATEGORIES_URL)
            if not data:
                return []

            response = loads(data)

            target_category = None
            for category in response.get("children", []):
                if category.get("uniqueName") == category_key:
                    target_category = category
                    break

            if not target_category:
                return []

            subcategories = []
            for subcategory in target_category.get("children", []):
                title = subcategory.get("name", "")
                unique_name = subcategory.get("uniqueName", "")
                if title and unique_name:
                    """
                    # # Get thumbnail if available
                    # thumbnail = ""
                    # images = subcategory.get("images", {})
                    # if images:
                        # if images.get("landscape", ""):
                            # thumbnail = images["landscape"]
                        # elif images.get("portrait", ""):
                            # thumbnail = images["portrait"]
                        # elif images.get("square", ""):
                            # thumbnail = images["square"]
                        # else:
                            # thumbnail = self.getThumbnailUrl2(images)
                    """
                    subcategories.append({
                        "title": title,
                        "key": unique_name
                        # 'icon': thumbnail
                    })

            return subcategories

        except Exception as e:
            print("[DEBUG]Error getting sport subcategories:", str(e))
            traceback.print_exc()
            return []

    def getSportVideos(self, key, root_json, page=0):
        print(
            "[API] getSportVideos called: key=" +
            str(key) +
            ", page=" +
            str(page))
        pageSize = 50
        # Find the category node
        category_node = self.find_category_by_unique_name(root_json, key)
        if not category_node:
            return {"videos": []}
        if page > 100:
            print("[WARNING] Maximum number of pages reached")
            return {"videos": [], "total": 0}
        # Prepare the payload
        payload = {
            "page": page,
            "pageSize": pageSize,
            "mode": "archive",
            "filters": {
                "tematica": [category_node.get("name") + "|" + str(key)],
                "dominio": self.RAISPORTDOMINIO
            }
        }
        print("[API] Request payload: " + str(payload))
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": self.RAISPORT_MAIN_URL,
            "Referer": self.RAISPORT_ARCHIVIO,
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest"
        }

        try:
            print(
                "[API] Sending request to: https://www.rainews.it/atomatic/news-search-service/api/v3/search")
            response = requests.post(
                self.RAISPORT_SEARCH_URL,
                headers=headers,
                json=payload,
                timeout=15
            )

            print("[API] Response status: " + str(response.status_code))
            """
            # import urllib.parse
            # debug_url = "https://www.rainews.it/atomatic/news-search-service/api/v3/search?"
            # debug_url += urllib.parse.urlencode(payload)
            # print("[DEBUG] You can try this URL in browser (if API supported GET):")
            # print(debug_url)

            # print("[DEBUG] Or use this curl command:")
            # print("curl -X POST 'https://www.rainews.it/atomatic/news-search-service/api/v3/search' "
                  # "-H 'Content-Type: application/json' "
                  # "-d '" + dumps(payload) + "'")
            """
            if response.status_code != 200:
                print("[API] Error response: " + response.text[:500])
                return {"videos": []}

            data = response.json()
            print("[API] Response data: " +
                  str(dumps(data, indent=2)[:500]) + "...")
            videos = []
            hits = data.get("hits", [])

            # Process only video items
            for h in hits:
                if h.get("data_type") == "video":
                    media = h.get("media", {})
                    video_url = media.get("mediapolis", "")
                    if not video_url:
                        continue

                    # Normalize URL
                    if not video_url.startswith("http"):
                        video_url = self.MEDIA_URL + video_url

                    title = h.get("title", "")
                    create_date = h.get("create_date", "")
                    icon = self.getThumbnailUrl2(h)

                    videos.append({
                        "title": title,
                        "url": video_url,
                        "icon": icon,
                        "date": create_date
                    })

            print("[API] Found " + str(len(videos)) + " videos")
            return {"videos": videos}

        except Exception as e:
            print("[API] Error: " + str(e))
            traceback.print_exc()
            return {"videos": []}

    def get_sport_videos_page(self, key, page=0, page_size=50):
        """Retrieve a page of sport videos"""
        try:
            print("[Sport] Loading page {} for key: {}".format(page + 1, key))

            # Load categories if needed
            if not hasattr(
                    self,
                    'categories_data') or not self.categories_data:
                self.categories_data = self.load_categories_cached()
                if not self.categories_data:
                    return []

            # Find the category node
            category_node = self.find_category_by_unique_name(
                self.categories_data, key)
            if not category_node:
                print("[Sport] Category not found: {}".format(key))
                return []

            # Prepare request
            dominio = "RaiNews|Category-6dd7493b-f116-45de-af11-7d28a3f33dd2"
            tematica = category_node.get("name", "") + "|" + str(key)

            payload = {
                "page": page,
                "pageSize": page_size,
                "mode": "archive",
                "filters": {
                    "tematica": [tematica],
                    "dominio": dominio
                }
            }

            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json; charset=UTF-8",
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest"
            }

            # Send request
            response = requests.post(
                self.RAISPORT_SEARCH_URL,
                headers=headers,
                json=payload,
                timeout=15
            )

            if response.status_code != 200:
                print("[Sport] API error: {}".format(response.status_code))
                return []

            data = response.json()
            hits = data.get("hits", [])

            # Filter only videos
            return [h for h in hits if h.get("data_type") == "video"]

        except Exception as e:
            print("[API] Error getting page " + str(page) + ": " + str(e))
            return []

    def debug_images(self, item):
        """Log all possible image paths in an item for debugging"""
        print("[DEBUG] Starting image debug for item:")

        # 1. Log the full item structure first
        try:
            import json
            print("[DEBUG]Full item structure:")
            print(json.dumps(item, indent=2, ensure_ascii=False))
        except BaseException:
            print("[DEBUG]Could not serialize item for debug")

        # 2. Check specific paths
        paths_to_check = [
            "image",
            "images.landscape",
            "images.portrait",
            "images.square",
            "images.landscape_logo",
            "images.portrait_logo",
            "contentItem.images.landscape",
            "contentItem.images.portrait",
            "program.images.landscape",
            "program.images.portrait"
        ]

        found_images = []

        for path in paths_to_check:
            keys = path.split('.')
            current = item
            valid = True

            for key in keys:
                # Handle array indices like "A[0]"
                if '[' in key and ']' in key:
                    array_key = key.split('[')[0]
                    index = int(key.split('[')[1].split(']')[0])

                    if isinstance(current, dict) and array_key in current:
                        if isinstance(
                                current[array_key], list) and len(
                                current[array_key]) > index:
                            current = current[array_key][index]
                        else:
                            valid = False
                            break
                    else:
                        valid = False
                        break
                # Normal dictionary key
                elif isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    valid = False
                    break

            if valid and current:
                print("[DEBUG]Found image at '" + path + "': " + str(current))
                found_images.append(current)

        if not found_images:
            print("[DEBUG]No images found in any known paths!")

        print("[DEBUG]Total images found: " + str(len(found_images)) + "\n")
        return found_images


class RaiPlayMain(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False

        self.program_categories = []
        self.categories_loaded = False

        self.loading_counter = 0
        self.loading_timer = eTimer()

        self.loading_timer.callback.append(self.update_loading_status)
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Main"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions', "MenuActions"], {
            'ok': self.okRun,
            'cancel': self.close,
            "menu": self.open_settings,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load main categories and prepare UI."""
        self.names = []
        self.urls = []
        self.icons = []
        categories = [
            (_("Live TV"), "live_tv", "https://www.rai.it/dl/img/2016/06/10/1465549191335_icon_live.png"),
            (_("Live Radio"), "live_radio", "https://www.rai.it/dl/img/2018/06/08/1528459668481_ico-musica.png"),
            (_("Replay TV"), "replay", "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"),
            (_("On Demand"), "ondemand", "https://www.raiplay.it/dl/img/2018/06/04/1528115285089_ico-teatro.png"),
            (_("TV News"), "tg", "https://www.rai.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"),
            (_("Sports"), "sport", "https://3.bp.blogspot.com/-zo6bSJzIHwA/UNs7tWXhOnI/AAAAAAAANJ0/HCfIRNmmbNI/s1600/png_fondo_blanco_by_camilhitha124-d3hgxl4.png"),
            (_("Programs"), "programs", "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png")
        ]

        categories += [(_("On Air Programs"),
                        "on_air",
                        "https://www.rai.it/dl/img/2016/06/10/1465549191335_icon_live.png"),
                       (_("A-Z All Programs"),
                        "all_programs",
                        "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"),
                       (_("A-Z TV Shows"),
                        "az_tv",
                        "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"),
                       (_("A-Z Radio Shows"),
                        "az_radio",
                        "https://www.rai.it/dl/img/2018/06/08/1528459668481_ico-musica.png"),
                       (_("News Categories"),
                        "news_categories",
                        "https://www.rai.it/dl/img/2018/06/08/1528459744316_ico-documentari.png")]

        categories += [(_("Search"), "search", png_search), (_("Download Manager"), "downloads",
                                                             "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png")]
        # Populate immediate lists
        self.names = [name for name, x, y in categories]
        self.urls = [url for x, url, y in categories]
        self.icons = [icon for x, y, icon in categories]

        show_list(self.names, self['text'])
        self['info'].setText(_('Initializing...'))
        self.loading_timer.start(1000, True)

        threading.Thread(target=self.load_program_categories).start()

        self.updatePoster()

        # Restore selection or select first item
        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def open_settings(self):
        self.session.open(RaiPlaySettings)

    def load_program_categories(self):
        """Load categories synchronously"""
        try:
            raw_categories = self.api.getOnDemandMenu()
            self.program_categories = []

            for cat in raw_categories:
                name = cat.get("name", "").lower()
                code = cat.get("id", "").lower()

                if name in self.excluded_categories or code in self.excluded_thread_categories:
                    continue

                prepared_url = self.api.prepare_url(cat['url'])
                self.program_categories.append({
                    'title': cat['title'],
                    'url': prepared_url,
                    'icon': cat['icon'],
                    'sub-type': cat.get('sub-type', '')
                })

            self.categories_loaded = True

        except Exception as e:
            print("[DEBUG]Error loading program categories: {}".format(str(e)))
            self.categories_loaded = True

    @property
    def excluded_thread_categories(self):
        return {"on_air", "az_tv", "az_radio", "news_categories"}

    @property
    def excluded_categories(self):
        """List of category names to exclude (lowercase)"""
        return {
            "home",
            "tv guide / replay",
            "live",
            "login / register",
            "recently watched",
            "my favorites",
            "watch later",
            "watch offline",
            "tutorial",
            "faq",
            "contact us",
            "privacy policy",
            "rai corporate",
            "privacy attività giornalistica",
            "cookie policy",
            "preferenze cookie",
            "rai",
            "rainews",
            "raiplay sound",
            "rai cultura",
            "rai scuola",
            "rai teche",
            "raiplay yoyo",
            "canone",
            "lavora con noi",
            "vai all'elenco completo",
            "x",
            "facebook",
            "instagram",
            "login",
            "raiplay"}

    def update_loading_status(self):
        """Update loading status with minimal operations"""
        self.loading_counter = (self.loading_counter + 1) % 4
        dots = '.' * self.loading_counter

        if self.categories_loaded:
            status = _('Loading complete! Select an option')
            self.loading_timer.stop()
        else:
            status = _('Loading program data') + dots

        self['info'].setText(status)

        # Only restart timer if still loading
        if not self.categories_loaded:
            self.loading_timer.start(300, True)  # Reduced interval

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        category = self.urls[idx]
        if category == "search":
            if not self.categories_loaded:
                self.session.open(
                    MessageBox,
                    _("Program list is still loading. Please wait..."),
                    MessageBox.TYPE_INFO)
            elif not self.program_categories:
                self.session.open(
                    MessageBox,
                    _("No program categories available"),
                    MessageBox.TYPE_INFO)
            else:
                self.session.open(RaiPlaySearch, self.program_categories)

        elif category == "live_tv":
            self.session.open(RaiPlayLiveTV)
        elif category == "live_radio":
            self.session.open(RaiPlayLiveRadio)
        elif category == "replay":
            self.session.open(RaiPlayReplayDates)
        elif category == "ondemand":
            self.session.open(RaiPlayOnDemand)
        elif category == "tg":
            self.session.open(RaiPlayTG)
        elif category == "sport":
            self.session.open(RaiPlaySport)
        elif category == "programs":
            self.session.open(RaiPlayPrograms)
        elif category == "on_air":
            self.session.open(RaiPlayOnAir)
        elif category == "az_tv":
            self.session.open(RaiPlayAZPrograms, "tv")
        elif category == "az_radio":
            self.session.open(RaiPlayAZPrograms, "radio")
        elif category == "news_categories":
            self.session.open(RaiPlayNewsCategories)
        elif category == "all_programs":
            self.session.open(RaiPlayAllPrograms, self.api.PROGRAMS_ALL_URL)
        elif category == "downloads":
            self.session.open(RaiPlayDownloadManagerScreen)

    def closeKeyboards(self):
        """Close any open virtual keyboards"""
        for screen in self.session.dialog_stack:
            if isinstance(screen, VirtualKeyBoard):
                screen.close()


class RaiPlayLiveTV(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Live"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load live TV channels and prepare the list."""
        self.names = []
        self.urls = []
        self.categories = []
        self.dates = []

        for item in self.api.getLiveTVChannels():
            prefix = ""
            if item['category'] == 'live_tv':
                prefix = "[LIVE] "
            elif item['category'] == 'archive':
                prefix = "[SPORT] "

            # Build name with date appended (o solo nome se preferisci)
            date_str = item.get('date', '')
            display_name = "{}{} {}".format(prefix, item['title'], date_str)

            self.names.append(display_name)
            self.urls.append(item['url'])
            self.icons.append(item['icon'])
            self.categories.append(item['category'])
            self.dates.append(date_str)

        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        """Main method - displays the play/download menu for videos"""
        print("[DEBUG] okRun called in RaiPlayLiveTV")
        print("[DEBUG] is_video_screen: {self.is_video_screen}")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information
        name = self.names[idx]
        url = self.get_video_url(idx)

        if not url:
            print(f"[DEBUG] No URL found for index {idx}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def get_video_url(self, idx):
        """Extracts video URL for RaiPlayLiveTV"""
        if idx < len(self.urls):
            return self.urls[idx]
        return ""

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayLiveTV"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayLiveRadio(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Live Radio"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load available live radio channels."""
        self.names = []
        self.urls = []
        self.icons = []

        channels = self.api.getLiveRadioChannels()
        for channel in channels:
            self.names.append(channel['title'])
            self.urls.append(channel['url'])
            self.icons.append(channel['icon'])

        show_list(self.names, self['text'])
        self['info'].setText(_('Select channel'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        """Main method - displays the play/download menu for radio streams"""
        print("[DEBUG] okRun called in RaiPlayLiveRadio")
        print(f"[DEBUG] is_video_screen: {self.is_video_screen}")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get radio stream information
        name = self.names[idx]
        url = self.get_stream_url(idx)

        if not url:
            print(f"[DEBUG] No stream URL found for index {idx}")
            self.session.open(
                MessageBox,
                _("No stream URL available"),
                MessageBox.TYPE_ERROR
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Stream URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def get_stream_url(self, idx):
        """Extracts stream URL for RaiPlayLiveRadio"""
        if idx < len(self.urls):
            return self.urls[idx]
        return ""

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayLiveRadio"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayReplayDates(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Replay TV"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Populate the list with the last 8 dates for replay selection"""
        self.names = []
        self.dates = []

        today = date.today()
        for i in range(8):  # Last 8 days
            day = today - timedelta(days=i)
            day_str = day.strftime("%A %d %B")
            api_date = day.strftime("%d%m%y")  # e.g. 060825 for August 6, 2025
            self.names.append(day_str)
            self.dates.append(api_date)

        show_list(self.names, self['text'])
        self['info'].setText(_('Select date'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        date_info = self.dates[idx]
        self.session.open(RaiPlayReplayChannels, date_info)


class RaiPlayReplayPrograms(SafeScreen):
    def __init__(self, session, channel_info, date):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.channel_info = channel_info
        self.date = date
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Replay: ") +
                              "{} - {}".format(self.channel_info['display'], self.date))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load the replay programs for the selected channel and date."""
        self.names = []
        self.urls = []
        self.icons = []
        date_api = datetime.strptime(self.date, "%d%m%y").strftime("%d-%m-%Y")
        print("[DEBUG] Converted date for API comparison:", date_api)

        programs = self.api.get_programs(self.channel_info["api"], date_api)

        for p in programs:
            self.names.append(p["title"])
            self.urls.append(p["url"])
            self.icons.append(p["icon"])

        if self.names:
            show_list(self.names, self['text'])
            self['info'].setText(_('Select program'))
        else:
            self['info'].setText(_('No programs available for this day'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        """Main method - displays the play/download menu for replay programs"""
        print("[DEBUG] okRun called in RaiPlayReplayPrograms")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get program information
        name = self.names[idx]
        video_url = self.urls[idx] if idx < len(self.urls) else ""

        if not video_url:
            print(f"[DEBUG] No video URL found for index {idx}")
            self.session.open(
                MessageBox,
                _("Video URL not available"),
                MessageBox.TYPE_ERROR
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {video_url}")

        self.selected_name = name
        self.selected_url = video_url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayReplayChannels(SafeScreen):
    def __init__(self, session, date_info):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.items = []
        self.names = []
        self.channels = []
        self.date = date_info
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Replay TV") + " " + str(self.date))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load available replay TV channels for the given date."""
        url = self.api.CHANNELS_URL
        data = Utils.getUrlSiVer(url)
        if not data:
            print("[DEBUG] No data returned from URL")
            self['info'].setText(_('Error loading data'))
            return
        try:
            response = loads(data)
            channels = response.get("dirette", [])
            for channel in channels:
                title = channel.get("channel", "")
                if not title:
                    continue

                # Store both display name and API name
                self.names.append(title)
                self.channels.append({
                    'display': title,  # Original display name
                    'api': title.replace(" ", "")  # API expects no spaces
                })
                icon = self.api.getThumbnailUrl2(channel)
                self.icons.append(icon)

            if not self.names:
                self['info'].setText(_('No TV channels available'))
            else:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select channel'))

            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print('Error loading TV channels:', str(e))
            traceback.print_exc()
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        channel_info = self.channels[idx]
        self.session.open(RaiPlayReplayPrograms, channel_info, self.date)


class RaiPlayOnDemand(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.categories = []
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play On Demand"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load on-demand categories from the API and display them."""
        self.categories = self.api.getOnDemandMenu()
        if not self.categories:
            self['info'].setText(_('No categories available'))
            return

        filtered_categories = []
        for cat in self.categories:
            if cat.get('title') != "Search" and cat.get('url') != "search":
                filtered_categories.append(cat)

        self.categories = filtered_categories
        self.names = [cat['title'] for cat in self.categories]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        category = self.categories[idx]

        if category['url'] == "search":
            # Open search screen directly with program categories
            self.session.open(RaiPlaySearch, self.categories)
        else:
            title = category.get("title") or ""
            url = category.get("url") or ""
            subtype = category.get("sub-type") or ""
            self.session.open(
                RaiPlayOnDemandCategory,
                str(title),
                str(url),
                str(subtype))


class RaiPlayProgramBlocks(SafeScreen):
    def __init__(self, session, name, program_data):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.items = []
        self.names = []
        self.channels = []
        self.program_data = program_data
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Parse program data blocks, extract items with icons, and display their names."""
        self.blocks = []
        for block in self.program_data.get("blocks", []):
            for set_item in block.get("sets", []):
                icon_url = ""
                if set_item.get("images", {}).get("portrait", ""):
                    icon_url = self.api.getThumbnailUrl(
                        set_item["images"]["portrait"])

                elif set_item.get("images", {}).get("landscape", ""):
                    icon_url = self.api.getThumbnailUrl(
                        set_item["images"]["landscape"])

                elif set_item.get("images", {}).get("square", ""):
                    icon_url = self.api.getThumbnailUrl(
                        set_item["images"]["square"])

                elif set_item.get("images", {}).get("landscape_logo", ""):

                    icon_url = self.api.getThumbnailUrl(
                        set_item["images"]["landscape_logo"])
                else:
                    # Fallback if no image found
                    icon_url = self.api.getThumbnailUrl2(set_item)

                if DEBUG_MODE:
                    self.api.debug_images(set_item)

                self.blocks.append({
                    'name': set_item.get("name", ""),
                    'url': set_item.get("path_id", ""),
                    'icon': icon_url
                })

        self.names = [block['name'] for block in self.blocks]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select block'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        block = self.blocks[idx]
        self.session.open(RaiPlayBlockItems, block['name'], block['url'])


class RaiPlayBlockItems(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.url = url
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load program items for the given URL and display their titles."""
        items = self.api.getProgramItems(self.url)
        self.videos = []

        for item in items:
            title = item['title']
            if item.get('subtitle'):
                title = title + " (" + item['subtitle'] + ")"

            if DEBUG_MODE:
                self.api.debug_images(item)

            self.videos.append({
                'title': title,
                'url': item['url'],
                'icon': item.get('icon', ""),
                'desc': item.get('description', '')
            })

        self.names = [video['title'] for video in self.videos]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select video'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        """Main method - displays the play/download menu for block items"""
        print("[DEBUG] okRun called in RaiPlayBlockItems")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information from videos list
        if not hasattr(self, 'videos') or idx >= len(self.videos):
            print(f"[DEBUG] No video found for index {idx}")
            self.session.open(
                MessageBox,
                _("Video not available"),
                MessageBox.TYPE_ERROR
            )
            return

        video = self.videos[idx]
        name = video['title']
        url = video.get('url', '')

        if not url:
            print(f"[DEBUG] No URL found for video: {name}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayLiveRadio"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayOnDemandCategory(SafeScreen):
    def __init__(self, session, name, url, sub_type):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.sub_type = sub_type
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def get_state_params(self):
        return {'name': self.name, 'url': self.url, 'sub_type': self.sub_type}

    def _gotPageLoad(self):
        """
        Load items when the layout is finished
        """
        # print("[DEBUG] Loading category: %s" % self.name)
        # print("[DEBUG] Category URL: %s" % self.url)
        # print("[DEBUG] Sub-type: %s" % self.sub_type)
        try:
            items = self.api.getOnDemandCategory(self.url)
            self.items = []
            self.icons = []
            # Populate both items and icons
            for item in items:
                url = item.get("url", "") or item.get("path_id", "")
                if not url:
                    print(
                        "[WARNING] Skipping item '%s' because url is empty" %
                        item.get(
                            "name", ""))
                    continue

                url_full = self.api.getFullUrl(url)
                icon_url = item.get('icon', "")
                if not icon_url:
                    icon_url = self.api.getThumbnailUrl2(item)
                item_data = {
                    'name': item.get('name', ""),
                    'url': url_full,
                    'icon': item.get('icon', ""),
                    'sub-type': item.get('sub-type', "")
                }
                self.items.append(item_data)
                # CRITICAL: Populate icons list for poster widget
                self.icons.append(icon_url)

            if not self.items:
                print("[DEBUG] No items available")
                self['info'].setText(_('No items available'))
            else:
                # self.items.sort(key=lambda x: x.get("name", "").lower())
                # unique = list({item['name']: item for item in self.items}.values())
                # self.items = unique
                self.names = [item['name'] for item in self.items]
                show_list(self.names, self['text'])
                self['info'].setText(_('Select item'))

            # self.selectionChanged()
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("[ERROR] in _gotPageLoad: %s" % str(e))
            self['info'].setText(str(_('Error loading data: %s') % str(e)))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        item = self.items[idx]
        name = item['name']
        url = item['url']
        sub_type = item.get('sub-type', '')

        if sub_type == "Raiplay Tipologia Item":
            self.session.open(
                RaiPlayOnDemandAZ,
                name,
                url
            )
            return

        elif sub_type == "PLR programma Page":
            program_data = self.api.getProgramDetails(url)
            if program_data:
                is_movie = False
                for typology in program_data['info'].get("typologies", []):
                    if typology.get("name") == "Film":
                        is_movie = True
                        break

                if is_movie and program_data['info'].get("first_item_path"):
                    # FOR MOVIES: Show play/download menu instead of direct play
                    self.selected_name = name
                    self.selected_url = program_data['info']["first_item_path"]

                    menu = [
                        (_("Play"), "play"),
                        (_("Download"), "download"),
                        (_("Play & Download"), "both")
                    ]

                    self.session.openWithCallback(
                        self.menuCallback,
                        MessageBox,
                        _("Choose action for: {}").format(name),
                        list=menu
                    )
                    return
                else:
                    self.session.open(
                        RaiPlayProgramBlocks,
                        name,
                        program_data
                    )
                    return

        elif sub_type == "RaiPlay Video Item":
            # Direct play from okRun without intermediate screen
            pathId = self.api.getFullUrl(url)
            data = Utils.getUrlSiVer(pathId)
            if not data:
                self['info'].setText(_('Error loading video data'))
                return

            try:
                response = loads(data)
                print("[DEBUG] Video JSON response keys: {}".format(list(response.keys())))
                video_url = response.get("video", {}).get("content_url", None)
                if video_url:
                    print(f"[DEBUG] Found video URL: {video_url}")
                    # MOSTRA MENU invece di play diretto
                    self.selected_name = name
                    self.selected_url = video_url

                    menu = [
                        (_("Play"), "play"),
                        (_("Download"), "download"),
                        (_("Play & Download"), "both")
                    ]

                    self.session.openWithCallback(
                        self.menuCallback,
                        MessageBox,
                        _("Choose action for: {}").format(name),
                        list=menu
                    )
                    return  # ← AGGIUNGI RETURN
                else:
                    print("[DEBUG] No video URL found in response. Available keys: {}".format(list(video_json.keys())))
                    self.session.open(
                        MessageBox,
                        _("No video URL found in the response"),
                        MessageBox.TYPE_ERROR
                    )
                    return  # ← AGGIUNGI RETURN
            except Exception as e:
                print(f"[DEBUG] Error parsing video data: {e}")
                print(f"[DEBUG] Raw data (first 500 chars): {data[:500]}")
                self.session.open(
                    MessageBox,
                    _("Error parsing video data: {}").format(str(e)),
                    MessageBox.TYPE_ERROR
                )
                return  # ← AGGIUNGI RETURN

        # Solo se nessuno dei casi sopra matcha
        self.session.open(RaiPlayOnDemandCategory, name, url, sub_type)

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayOnDemandAZ(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """
        Populate the list with letters A-Z and 0-9 for selection
        """
        self.items = []
        self.items.append({'title': "0-9", 'name': "0-9", 'url': self.url})

        for i in range(26):
            letter = chr(ord('A') + i)
            self.items.append(
                {'title': letter, 'name': letter, 'url': self.url})

        self.names = [item['title'] for item in self.items]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select letter'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        item = self.items[idx]
        self.session.open(
            RaiPlayOnDemandIndex,
            item['name'],
            item['url']
        )


class RaiPlayOnDemandIndex(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """
        Load the program list for the selected index letter and populate UI list
        """
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrlSiVer(pathId)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        response = loads(data)
        self.items = []
        items = response.get(self.name, [])
        icon_url = ""
        for item in items:
            icon_url = self.api.getThumbnailUrl2(item)
            self.items.append({
                'name': item.get("name", ""),
                'url': item.get("PathID", ""),
                'sub-type': 'PLR programma Page',
                'icon': icon_url,
            })

        self.names = [item['name'] for item in self.items]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select program'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        item = self.items[idx]
        self.session.open(
            RaiPlayOnDemandProgram,
            item['name'],
            item['url']
        )


class RaiPlayAllPrograms(SafeScreen):
    def __init__(self, session, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.url = url
        self.items = []
        self.names = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading all programs...'))
        self['title'] = Label(_("All Programs"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load all programs and organize them by first letter"""
        data = Utils.getUrlSiVer(self.url)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        try:
            response = loads(data)
            programs = []

            # Extract all programs from the contents
            if "contents" in response and isinstance(
                    response["contents"], dict):
                for letter, items in response["contents"].items():
                    for program in items:
                        # Get the correct URL - use info_url if available,
                        # otherwise use path_id
                        program_url = program.get(
                            "info_url", program.get("path_id", ""))
                        if program_url and not program_url.startswith("http"):
                            program_url = self.api.getFullUrl(program_url)

                        # Ensure it's a JSON URL
                        if program_url and not program_url.endswith('.json'):
                            program_url += '.json'

                        programs.append({
                            'name': program.get("name", ""),
                            'url': program_url,
                            'icon': self.api.getThumbnailUrl2(program),
                            'sub-type': program.get("type", "PLR programma Page")
                        })

            # Sort programs alphabetically
            programs.sort(key=lambda x: x['name'].lower())

            # Group programs by first letter
            self.programs_by_letter = {}
            for program in programs:
                first_letter = program['name'][0].upper(
                ) if program['name'] else '#'
                if first_letter not in self.programs_by_letter:
                    self.programs_by_letter[first_letter] = []
                self.programs_by_letter[first_letter].append(program)

            # Create list of letters
            self.letters = sorted(self.programs_by_letter.keys())
            self.names = [
                "{} ({})".format(letter, len(self.programs_by_letter[letter]))
                for letter in self.letters
            ]
            show_list(self.names, self['text'])
            self['info'].setText(_('Select letter'))

            if self.names:
                self["text"].moveToIndex(0)
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("[ERROR] loading all programs:", str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        selected_letter = self.letters[idx]
        programs = self.programs_by_letter[selected_letter]

        # Open a new screen showing programs for this letter
        self.session.open(RaiPlayProgramsByLetter, selected_letter, programs)


class RaiPlayProgramsByLetter(SafeScreen):
    def __init__(self, session, letter, programs):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.letter = letter
        self.programs = programs
        self.names = []
        self.urls = []
        self.icons = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading programs...'))
        self['title'] = Label("Programs - {}".format(letter))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Display programs for the selected letter"""
        self.names = [program['name'] for program in self.programs]
        self.urls = [program['url'] for program in self.programs]
        self.icons = [program['icon'] for program in self.programs]

        show_list(self.names, self['text'])
        self['info'].setText(_('Select program'))

        if self.names:
            self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        program = self.programs[idx]

        # First, try to get the content directly
        content_data = Utils.getUrlSiVer(program['url'])
        if not content_data:
            self.session.open(
                MessageBox,
                _("Could not load program content"),
                MessageBox.TYPE_ERROR)
            return

        try:
            content_json = loads(content_data)

            # Debug: print the structure to understand what we're dealing with
            print("[DEBUG]Content JSON keys:", list(content_json.keys()))

            # Check if this is a content set with items
            if content_json.get('items') and isinstance(
                    content_json['items'], list):
                # This is a content set, open it directly
                self.session.open(
                    RaiPlayContentSet,
                    program['name'],
                    program['url'])
            # Check if this is a program with blocks
            elif content_json.get('blocks') and isinstance(content_json['blocks'], list):
                # For programs with blocks, we need to find the actual content
                # set
                content_set_url = self.find_content_set_url(content_json)
                if content_set_url:
                    self.session.open(
                        RaiPlayContentSet,
                        program['name'],
                        content_set_url)
                else:
                    self.session.open(
                        MessageBox,
                        _("No content found in this program"),
                        MessageBox.TYPE_ERROR)
            # Check if this is a direct video item
            elif content_json.get('video_url'):
                # This is a direct video, play it
                self.playDirect(program['name'], content_json['video_url'])
            # Check if this is a program info page that needs to be redirected
            elif content_json.get('weblink'):
                # Try to get the content from the weblink
                weblink = content_json['weblink']
                if not weblink.startswith('http'):
                    weblink = self.api.getFullUrl(weblink)
                if not weblink.endswith('.json'):
                    weblink += '.json'
                self.session.open(RaiPlayProgramsByLetter, program['name'], [{
                    'name': program['name'],
                    'url': weblink,
                    'icon': program['icon']
                }])
            else:
                # Unknown content type - try to debug by printing the structure
                print("[DEBUG]Unknown content structure:",
                      dumps(content_json, indent=2)[:500])
                self.session.open(
                    MessageBox,
                    _("Unknown content type"),
                    MessageBox.TYPE_ERROR)

        except Exception as e:
            print("[ERROR] parsing content:", str(e))
            self.session.open(
                MessageBox,
                _("Error parsing content"),
                MessageBox.TYPE_ERROR)

    def find_content_set_url(self, program_json):
        """Find the content set URL in a program with blocks"""
        # Look for the first content set in blocks
        for block in program_json.get('blocks', []):
            for set_item in block.get('sets', []):
                set_url = set_item.get('path_id', '')
                if set_url:
                    return self.api.getFullUrl(set_url)
        return None


class RaiPlayOnDemandProgram(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading program details...'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load and process program details"""
        url = self.api.prepare_url(self.url)
        print("[DEBUG][Program] Loading program details from: " + url)
        data = Utils.getUrlSiVer(url)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        try:
            response = loads(data)
            program_info = {
                'name': response.get(
                    "name", ""), 'description': response.get(
                    "vanity", response.get(
                        "description", "")), 'year': response.get(
                    "year", ""), 'country': response.get(
                        "country", ""), 'first_item_path': response.get(
                            "first_item_path", ""), 'is_movie': False}

            # Check if it's a movie
            for typology in response.get("typologies", []):
                if typology.get("name") == "Film":
                    program_info['is_movie'] = True
                    break

            # If it's a movie and has a first item path, play it directly
            if program_info['is_movie'] and program_info['first_item_path']:
                self.playDirect(program_info['name'])
                self.api.getFullUrl(program_info['first_item_path'])
                return

            # Process blocks and sets
            self.items = []
            for block in response.get("blocks", []):
                block_type = block.get("type", "")
                block_name = block.get("name", "")

                # Only process relevant blocks
                if block_type not in [
                    "RaiPlay Multimedia Block",
                        "RaiPlay Lista Programmi Block"]:
                    continue

                for set_item in block.get("sets", []):
                    set_name = set_item.get("name", "")
                    set_path = set_item.get("path_id", "")

                    if not set_name or not set_path:
                        continue

                    # Get full URL for the set
                    set_url = self.api.getFullUrl(set_path)

                    self.items.append({
                        "name": block_name + " - " + set_name,
                        "url": set_url,
                        "type": "set"
                    })

            if "block" in response and "cards" in response["block"]:
                self.loadRadioEpisodes(response)
                return

            # If no sets found, try to get videos directly from the program
            if not self.items:
                self.items = self.get_videos_from_program(response)

            if not self.items:
                self['info'].setText(_('No content available'))
                return

            self.names = [item["name"] for item in self.items]
            show_list(self.names, self['text'])
            self['info'].setText(_('Select content set'))
            self["text"].moveToIndex(0)
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("[ERROR] loading program details: " + str(e))
            self['info'].setText(_('Error loading data: {}').format(str(e)))

    def loadRadioEpisodes(self, response):
        """Load and display radio episodes directly"""
        self.items = []
        cards = response["block"]["cards"]

        for card in cards:
            audio_info = card.get("audio", {})
            if not audio_info:
                continue

            title = card.get("title", "No title")
            audio_url = audio_info.get("url", "")
            # icon = card.get("image", self.api.DEFAULT_ICON_URL)

            self.items.append({
                "name": title,
                "url": audio_url,
                "type": "audio"
            })

        if not self.items:
            self['info'].setText(_('No episodes available'))
            return

        self.names = [item["name"] for item in self.items]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select episode'))
        self["text"].moveToIndex(0)
        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def get_videos_from_program(self, program_data):
        """Extract videos directly from program data if available"""
        videos = []

        # Check if the program has items directly
        items = program_data.get("items", [])
        for item in items:
            video_url = item.get("video_url") or item.get("content_url") or ""
            if not video_url:
                continue

            title = item.get("name", item.get("title", "No title"))
            videos.append({
                "name": title,
                "url": video_url,
                "type": "video"
            })

        return videos

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        item = self.items[idx]
        if item["type"] in ("audio", "video"):
            safe_name = item["name"]
            if isinstance(safe_name, bytes):
                safe_name = safe_name.decode("utf-8", errors="ignore")
            else:
                safe_name = str(safe_name).encode(
                    "utf-8", errors="ignore").decode("utf-8")

            self.playDirect(safe_name, item["url"])
        else:
            self.session.open(RaiPlayContentSet, item["name"], item["url"])


class RaiPlayContentSet(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.url = url
        self.videos = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading videos...'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load videos from content set"""
        print("[DEBUG][ContentSet] Loading content set: " + self.url)
        data = Utils.getUrlSiVer(self.url)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        try:
            response = loads(data)
            self.videos = []

            # Extract videos from items array
            items = response.get("items", [])
            for item in items:
                # Get video URL - try multiple possible fields
                video_url = item.get("video_url") or item.get(
                    "content_url") or ""
                if not video_url:
                    # Check if there's a video object
                    video_obj = item.get("video", {})
                    video_url = video_obj.get("content_url", "")

                if not video_url:
                    continue

                title = item.get("name", item.get("title", "No title"))
                # Add subtitle if available
                subtitle = item.get("subtitle", "")
                if subtitle and subtitle != title:
                    title = "{} - {}".format(title, subtitle)

                # Add date if available
                toptitle = item.get("toptitle", "")
                if toptitle:
                    title = "{} - {}".format(toptitle, title)

                self.videos.append({
                    "title": title,
                    "url": video_url,
                    "icon": self.api.getThumbnailUrl2(item)
                })

            if not self.videos:
                # Try alternative structure - check if it's a direct video
                if response.get("video_url"):
                    self.videos.append({
                        "title": response.get("name", response.get("title", "No title")),
                        "url": response.get("video_url"),
                        "icon": self.api.getThumbnailUrl2(response)
                    })
                else:
                    self['info'].setText(_('No videos found'))
                    return

            self.names = [video["title"] for video in self.videos]
            self.icons = [video.get("icon", self.api.DEFAULT_ICON_URL)
                          for video in self.videos]
            show_list(self.names, self['text'])
            self['info'].setText(_('Select video'))
            self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print("[ERROR] loading content set: " + str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        """Main method - displays the play/download menu for content set videos"""
        print("[DEBUG] okRun called in RaiPlayContentSet")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information from videos list
        if not hasattr(self, 'videos') or idx >= len(self.videos):
            print(f"[DEBUG] No video found for index {idx}")
            self.session.open(
                MessageBox,
                _("Video not available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        video = self.videos[idx]
        name = video["title"]
        url = video.get("url", "")

        if not url:
            print(f"[DEBUG] No URL found for video: {name}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayOnDemandProgramItems(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.url = url
        self.items = []
        self.names = []
        self.channels = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrlSiVer(pathId)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        response = loads(data)
        items = response.get("items", [])
        self.videos = []
        for item in items:
            title = item.get("name", "")
            subtitle = item.get("subtitle", "")

            if subtitle and subtitle != title:
                title = "%s (%s)" % (title, subtitle)

            videoUrl = item.get("pathID", "")
            # images = item.get("images", {})
            icon_url = ""
            if item.get("images", {}).get("portrait", ""):
                icon_url = self.api.getThumbnailUrl(item["images"]["portrait"])
            elif item.get("images", {}).get("landscape", ""):
                icon_url = self.api.getThumbnailUrl(
                    item["images"]["landscape"])

            elif item.get("images", {}).get("square", ""):
                icon_url = self.api.getThumbnailUrl(item["images"]["square"])
            elif item.get("images", {}).get("landscape_logo", ""):
                icon_url = self.api.getThumbnailUrl(
                    item["images"]["landscape_logo"])
            else:
                # Fallback to debug_images if no image found
                icon_url = self.api.getThumbnailUrl2(item)

            if DEBUG_MODE:
                self.api.debug_images(item)

            self.videos.append({
                'title': title,
                'url': videoUrl,
                'icon': icon_url
            })

        self.names = [video['title'] for video in self.videos]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select video'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        """Main method - displays the play/download menu for content set videos"""
        print("[DEBUG] okRun called in RaiPlayContentSet")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information from videos list
        if not hasattr(self, 'videos') or idx >= len(self.videos):
            print(f"[DEBUG] No video found for index {idx}")
            self.session.open(
                MessageBox,
                _("Video not available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        video = self.videos[idx]
        name = video["title"]
        url = video.get("url", "")

        if not url:
            print(f"[DEBUG] No URL found for video: {name}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayOnAir(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading on-air programs...'))
        self['title'] = Label(_("On Air Programs"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        """Load and display currently airing programs"""
        url = self.api.ON_AIR_URL  # "https://www.raiplay.it/palinsesto/onAir.json"
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            self.programs = []

            # Extract channels from different possible structures
            channels = data.get("on_air", []) or data.get("channels", [])

            for channel in channels:
                current_item = channel.get("currentItem", {})
                if not current_item:
                    continue

                title = current_item.get("name", "")
                if not title:
                    continue

                # Get video URL - try multiple locations
                video_url = current_item.get(
                    "path_id",
                    "") or current_item.get(
                    "weblink",
                    "") or current_item.get(
                    "event_weblink",
                    "")
                if not video_url:
                    continue

                # Make URL absolute
                if not video_url.startswith("http"):
                    video_url = "https://www.raiplay.it" + video_url

                # Format time information
                start_time = current_item.get("hour", "")
                channel_name = channel.get("channel", "")
                time_str = "[" + channel_name + "] " + \
                    start_time if channel_name and start_time else ""

                # Get image
                icon = current_item.get("image", "")
                # icon = self.api.getThumbnailUrl2(channel)
                if icon and not icon.startswith("http"):
                    icon = "https://www.raiplay.it" + icon

                self.programs.append({
                    "title": time_str + title,
                    "url": video_url,
                    "icon": icon,
                    "channel": channel_name
                })

            if not self.programs:
                self['info'].setText(_('No programs currently on air'))
                return

            self.names = [p["title"] for p in self.programs]
            self.icons = [p["icon"] for p in self.programs]
            show_list(self.names, self['text'])
            self['info'].setText(_('Select program to watch'))
            self["text"].moveToIndex(0)
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("[ERROR] loading onAir data: " + str(e))
            self['info'].setText(_('Error loading data: {}').format(str(e)))

    def okRun(self):
        """Main method - displays the play/download menu for on-air programs"""
        print("[DEBUG] okRun called in RaiPlayOnAir")

        if not hasattr(self, 'programs') or not self.programs:
            print("[DEBUG] No programs available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.programs):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get program information
        program = self.programs[idx]
        name = program["title"]
        url = program.get("url", "")

        if not url:
            print(f"[DEBUG] No URL found for program: {name}")
            self.session.open(
                MessageBox,
                _("No program URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Program URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayAZPrograms(SafeScreen):
    def __init__(self, session, program_type):
        self.session = session
        self.program_type = program_type
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading programs...'))
        title = _(
            "TV Programs A-Z") if program_type == "tv" else _("Radio Programs A-Z")
        self['title'] = Label(title)
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        """Load A-Z program list with improved structure handling"""
        try:
            print("[DEBUG][AZ] Loading " + self.program_type + " programs")
            if self.program_type == "tv":
                # "https://www.raiplay.it/dl/RaiTV/RaiPlayMobile/Prod/Config/programmiAZ-elenco.json"
                url = self.api.RAIPLAY_AZ_TV_SHOW_PATH
            else:
                # "https://www.raiplay.it/dl/RaiTV/RaiRadioMobile/Prod/Config/programmiAZ-elenco.json"
                url = self.api.RAIPLAY_AZ_RADIO_SHOW_PATH

            # Add cache busting parameter to avoid stale data
            url += "?t=" + str(int(time.time()))

            print("[DEBUG][AZ] Fetching URL: {}".format(url))
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            # Debug: save JSON for analysis
            if DEBUG_MODE:
                debug_path = join(
                    self.api.debug_dir,
                    "az_{}.json".format(
                        self.program_type))
                with open(debug_path, "w", encoding="utf-8") as f:
                    dump(data, f, indent=2)
                print("[DEBUG][AZ] Saved JSON to {}".format(debug_path))

            self.programs = []

            # Handle different JSON structures
            if isinstance(data, dict):
                # Dictionary format: keys are letters (A, B, ..., 0-9)
                print("[DEBUG][AZ] Processing dictionary format")
                for letter, items in data.items():
                    if isinstance(items, list):
                        for program in items:
                            self.add_program(program)
                    else:
                        print("[WARNING] Unexpected data type for letter " +
                              str(letter) + ": " + str(type(items)))
            elif isinstance(data, list):
                # Array format: list of programs
                print("[DEBUG][AZ] Processing array format")
                for program in data:
                    self.add_program(program)
            else:
                print("[ERROR] Unknown JSON format: " + str(type(data)))
                self['info'].setText(_('Unknown data format'))
                return

            if not self.programs:
                # Try alternative parsing method
                self.programs = self.extract_programs_alternative(data)

            if not self.programs:
                self['info'].setText(_('No programs found in A-Z list'))
                if isinstance(data, dict):
                    print("[DEBUG][AZ] No programs found. JSON keys: " +
                          str(list(data.keys())))
                else:
                    print("[DEBUG][AZ] No programs found. JSON keys: N/A")
                return

            # Sort alphabetically
            self.programs.sort(key=lambda x: x["title"].lower())

            # icon = self.api.getThumbnailUrl2(channel)
            print("[DEBUG][AZ] Found {} programs".format(len(self.programs)))
            self.names = [p["title"] for p in self.programs]
            self.icons = [p["icon"] for p in self.programs]
            show_list(self.names, self['text'])
            self['info'].setText(_('Select program'))
            self["text"].moveToIndex(0)
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("[DEBUG][AZ] Error loading data: {}".format(str(e)))
            self['info'].setText(
                _('Error loading A-Z programs: {}').format(str(e)))

    def extract_programs_alternative(self, data):
        """Alternative method to extract programs from JSON"""
        programs = []

        # Method 1: Search for programs recursively
        def search_programs(obj):
            if isinstance(obj, dict):
                # Check if this looks like a program
                if "name" in obj or "nome" in obj:
                    programs.append(obj)
                else:
                    # Recursively search values
                    for value in obj.values():
                        search_programs(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_programs(item)

        search_programs(data)

        # Method 2: Direct extraction from known keys
        if not programs:
            for key in ["items", "programs", "contents"]:
                if key in data and isinstance(data[key], list):
                    programs = data[key]
                    break

        # Process found programs
        result = []
        for program in programs:
            try:
                title = program.get("name") or program.get("nome") or ""
                if not title:
                    continue

                url = program.get("PathID") or program.get(
                    "path_id") or program.get("url") or ""
                if not url:
                    continue

                # Normalize URL
                url = self.normalize_url(url)

                # icon = self.get_program_icon(program)
                icon = self.api.getThumbnailUrl2(program)

                result.append({
                    "title": title,
                    "url": url,
                    "icon": icon
                })
            except Exception as e:
                print(
                    "[DEBUG][AZ] Error processing program: {}".format(
                        str(e)))

        return result

    def normalize_url(self, url):
        """Normalizes the URL to ensure it is valid"""
        if not url:
            return url

        baseUrl = "https://www.raiplay.it/"
        url = url.replace(" ", "%20")
        if url[0:2] == "//":
            url = "https:" + url
        elif url[0] == "/":
            url = baseUrl[:-1] + url

        # http://www.rai.it/raiplay/programmi/dtime-iltempodiladyd/?json
        if url.endswith("/?json"):
            # url = url.replace("rai.it/raiplay", "raiplay.it")
            url = url.replace("/?json", ".json")

        # Make URL absolute and correct domain
        if not url.startswith("http"):
            url = "https://www.raiplay.it" + url
        else:
            url = url.replace("http://", "https://")
            url = url.replace("www.rai.it", "www.raiplay.it")

        if url.startswith("https://www.raiplay.it/raiplay/"):
            url = url.replace(
                "https://www.raiplay.it/raiplay/",
                "https://www.raiplay.it/")

        if not self.program_type == "tv":
            url = url.replace("www.raiplay.it", "www.raiplaysound.it")

        return url

    def add_program(self, program):
        """Add a program to the list with proper validation"""
        # Get program name - try multiple fields
        title = program.get("name") or program.get("nome") or ""
        if not title:
            return

        # Get program URL - try multiple fields
        url = program.get("PathID") or program.get("path_id") or ""
        if not url:
            return

        # Normalize URL
        url = self.normalize_url(url)
        icon = self.api.getThumbnailUrl2(program)

        # If no image found, use default
        if not icon or icon == self.api.DEFAULT_ICON_URL:
            icon = program.get("image", self.api.DEFAULT_ICON_URL)

        # Make icon URL absolute
        if icon and not icon.startswith("http"):
            icon = "https://www.raiplay.it" + icon

        self.programs.append({
            "title": title,
            "url": url,
            "icon": icon
        })

    def get_program_icon(self, program):
        """Get program icon with fallbacks"""
        icon = self.api.getThumbnailUrl2(program)
        if icon:
            if not icon.startswith("http"):
                return "https://www.raiplay.it" + icon
            return icon

        # Finally, use default icon
        return self.api.DEFAULT_ICON_URL

    def okRun(self):
        if not self.programs:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.programs):
            return

        program = self.programs[idx]
        self.session.open(
            RaiPlayOnDemandProgram,
            program["title"],
            program["url"])


class RaiPlayNewsCategories(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading news categories...'))
        self['title'] = Label(_("News Categories"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        # Define the main news categories with their API endpoints
        self.categories = [{"name": "Ambiente",
                            "path": "ambiente",
                            "url": "https://www.rainews.it/app/ambiente.json",
                            "icon": png_amb,
                            "type": "category"},
                           {"name": "Arti e Spettacolo",
                            "path": "artiespettacolo",
                            "url": "https://www.rainews.it/app/artiespettacolo.json",
                            "icon": png_artis,
                            "type": "category"},
                           {"name": "Cronaca",
                            "path": "cronaca",
                            "url": "https://www.rainews.it/app/cronaca.json",
                            "icon": png_news,
                            "type": "category"},
                           {"name": "Economia e Finanza",
                            "path": "economiaefinanza",
                            "url": "https://www.rainews.it/app/economiaefinanza.json",
                            "icon": png_econ,
                            "type": "category"},
                           {"name": "Esteri",
                            "path": "esteri",
                            "url": "https://www.rainews.it/app/esteri.json",
                            "icon": png_noti,
                            "type": "category"},
                           {"name": "Notiziari",
                            "path": "notiziari",
                            "url": "https://www.rainews.it/app/notiziari.json",
                            "icon": png_noti,
                            "type": "category"},
                           {"name": "Politica",
                            "path": "politica",
                            "url": "https://www.rainews.it/app/politica.json",
                            "icon": png_poli,
                            "type": "category"},
                           {"name": "Salute",
                            "path": "salute",
                            "url": "https://www.rainews.it/app/salute.json",
                            "icon": png_sal,
                            "type": "category"},
                           {"name": "Scienza e Tecnologia",
                            "path": "scienzaetecnologia",
                            "url": "https://www.rainews.it/app/scienzaetecnologia.json",
                            "icon": png_sci,
                            "type": "category"},
                           {"name": "Sport",
                            "path": "sport",
                            "url": "https://www.rainews.it/app/sport.json",
                            "icon": png_sport,
                            "type": "category"},
                           {"name": "Stili di vita e tempo libero",
                            "path": "stilidivitaetempolibero",
                            "url": "https://www.rainews.it/app/stilidivitaetempolibero.json",
                            "icon": png_artis,
                            "type": "category"},
                           {"name": "Crimini e Misteri",
                            "path": "criminiandmisteri",
                            "url": "https://www.rainews.it/app/storie/criminiandmisteri.json",
                            "icon": png_crim,
                            "type": "category"},
                           {"name": "Gli Speciali",
                            "path": "glispeciali",
                            "url": "https://www.rainews.it/app/storie/glispeciali.json",
                            "icon": png_spec,
                            "type": "category"},
                           {"name": "Mappamondi",
                            "path": "mappamondi",
                            "url": "https://www.rainews.it/app/storie/mappamondi.json",
                            "icon": png_mon,
                            "type": "category"},
                           {"name": "Video Storie",
                            "path": "video",
                            "url": "https://www.rainews.it/app/storie/video.json",
                            "icon": png_sto,
                            "type": "category"},
                           {"name": "Viaggi e Turismo",
                            "path": "viaggieturismo",
                            "url": "https://www.rainews.it/app/viaggieturismo.json",
                            "icon": png_via,
                            "type": "category"}]

        self.names = [cat["name"] for cat in self.categories]
        self.urls = [cat["url"] for cat in self.categories]
        self.icons = [cat["icon"] for cat in self.categories]

        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))
        self["text"].moveToIndex(0)
        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        category = self.categories[idx]
        self.session.open(
            RaiPlayNewsCategory,
            category["name"],
            category["url"],
            category["path"])


class RaiPlayNewsCategory(SafeScreen):
    def __init__(self, session, name, url, path):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.path = path
        self.items = []
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading news items...'))
        self['title'] = Label(str(self.name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        """Load and parse news items for the selected category"""
        print("[DEBUG][NewsCategory] Loading: " + str(self.url))
        try:
            data = Utils.getUrlSiVer(self.url)
            if not data:
                raise Exception("No data received")

            try:
                response = loads(data)
            except BaseException:
                json_match = search(
                    r'<rainews-aggregator-broadcast-archive\s+data="([^"]+)"',
                    data
                )
                if json_match:
                    print("[DEBUG][NewsCategory] Found JSON in HTML")
                    raw_json = _html.unescape(json_match.group(1))
                    response = loads(raw_json)
                else:
                    raise Exception("No JSON found in response")

            # DEBUG: Save response for analysis
            if DEBUG_MODE:
                debug_file = join(self.api.debug_dir,
                                  "news_category_" + str(self.name) + ".json")
                with open(debug_file, "w", encoding="utf-8") as f:
                    dump(response, f, indent=2, ensure_ascii=False)
                print("[DEBUG] Saved news category response to " + debug_file)

            # SPECIAL CASE: New thematic structure (e.g., Environment)
            if "tematiche" in response and isinstance(
                    response["tematiche"], list):
                print("[DEBUG][NewsCategory] Found thematic structure")
                self.handle_thematic_structure(response)
                return

            # CASE 1: Response with "contents" structure
            if "contents" in response and isinstance(
                    response["contents"], list):
                print("[DEBUG][NewsCategory] Found 'contents' array")
                for content_block in response["contents"]:
                    if "contents" in content_block and isinstance(
                            content_block["contents"], list):
                        for item in content_block["contents"]:
                            self.add_news_item(item)
                    elif "cards" in content_block and isinstance(content_block["cards"], list):
                        for card in content_block["cards"]:
                            self.add_news_item(card)

            # CASE 2: Response with direct "cards" structure
            elif "cards" in response and isinstance(response["cards"], list):
                print("[DEBUG][NewsCategory] Found direct 'cards' array")
                for card in response["cards"]:
                    self.add_news_item(card)

            # CASE 3: Response with "items" structure
            elif "items" in response and isinstance(response["items"], list):
                print("[DEBUG][NewsCategory] Found 'items' array")
                for item in response["items"]:
                    self.add_news_item(item)

            # CASE 4: New structure for thematic archive
            elif "tematiche" in response and isinstance(response["tematiche"], list):
                print("[DEBUG][NewsCategory] Found new thematic structure")
                self.handle_new_thematic_structure(response)
                return  # Exit after handling new structure

            if not self.items:
                print("[DEBUG][NewsCategory] No items found. Response keys: " +
                      str(list(response.keys())))
                self['info'].setText(_('No items found in this category'))
                return

            # If there are no thematics, search for direct contents
            if not self.items:
                print(
                    "[NewsCategory] No subcategories found, searching for direct content")
                if "contents" in response and isinstance(
                        response["contents"], list):
                    for content_block in response["contents"]:
                        cards = content_block.get("cards", [])
                        for card in cards:
                            self.add_news_item(card)

                # If still no items, try alternative parsing
                if not self.items:
                    if "cards" in response and isinstance(
                            response["cards"], list):
                        for card in response["cards"]:
                            self.add_news_item(card)
                    elif "items" in response and isinstance(response["items"], list):
                        for item in response["items"]:
                            self.add_news_item(item)

            if not self.items:
                print("[DEBUG][NewsCategory] No items found. Response keys: " +
                      str(list(response.keys())))
                self['info'].setText(_('No items found in this category'))
                return

            # Prepare visualization
            self.names = []
            for item in self.items:
                # Format title with date if available
                date_str = item.get("date", "")
                if date_str:
                    try:
                        # Parse ISO date and reformat
                        dt = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00"))
                        date_str = dt.strftime("%d/%m/%Y %H:%M")
                    except BaseException:
                        pass
                display_title = (
                    date_str + " " + item['name']) if date_str else item['name']
                self.names.append(display_title)

            self.icons = [item["icon"] for item in self.items]
            show_list(self.names, self['text'])
            self['title'].setText(str(self.name) + " Archive")
            self['info'].setText(_('Select item'))
            self["text"].moveToIndex(0)
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print("[DEBUG][NewsCategory] Error loading news category: " + str(e))
            self['info'].setText(_('Error: Could not load news data'))
            # Attempt to show the raw response for debugging
            if DEBUG_MODE and data:
                debug_path = join(self.api.debug_dir,
                                  "news_error_" + str(self.name) + ".txt")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(data[:5000])  # Save first 5000 characters
                print("[DEBUG] Saved error response to " + debug_path)

    def handle_thematic_archive(self, response):
        """Handles the special structure of thematic archives"""
        try:
            print("[DEBUG][ThematicArchive] Handling thematic archive structure")

            # Get the archive URL
            archive_url = response.get("meta", {}).get("canonical")
            if not archive_url:
                self['info'].setText(_('Archive URL not found'))
                return

            print(
                "[DEBUG][ThematicArchive] Loading archive: " +
                str(archive_url))
            archive_data = Utils.getUrlSiVer(archive_url)
            if not archive_data:
                self['info'].setText(_('No archive data found'))
                return

            archive_json = loads(archive_data)

            # Reuse the loadData logic to extract items/cards/contents
            self.items = []
            if "items" in archive_json:
                for item in archive_json["items"]:
                    self.add_news_item(item)
            if "cards" in archive_json:
                for card in archive_json["cards"]:
                    self.add_news_item(card)
            if "contents" in archive_json:
                for block in archive_json["contents"]:
                    for item in block.get("contents", []):
                        self.add_news_item(item)
                    for card in block.get("cards", []):
                        self.add_news_item(card)

            if not self.items:
                self['info'].setText(_('No items found in this archive'))
                return

            # Update list
            self.names = []
            for item in self.items:
                date_str = item.get("date", "")
                if date_str:
                    try:
                        dt = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00"))
                        date_str = dt.strftime("%d/%m/%Y %H:%M")
                    except BaseException:
                        pass
                display_title = (
                    date_str + " " + item['name']) if date_str else item['name']
                self.names.append(display_title)

            show_list(self.names, self['text'])
            self['title'].setText(response.get("mainThemeName", self.name))
            self['info'].setText(_('Select item'))
            self["text"].moveToIndex(0)
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print("[DEBUG][ThematicArchive] Error: " + str(e))
            self['info'].setText(_('Error processing archive'))
            traceback.print_exc()

    def openArchiveScreen(self, title, payload):
        """Open the API archive screen after a short delay"""
        try:
            print("[DEBUG][Archive] Opening API archive for: {}".format(title))
            self.session.openWithCallback(
                self.archiveClosedCallback,
                RaiPlayNewsAPIArchive,
                title,
                payload
            )
        except Exception as e:
            print("[DEBUG][Archive] Error opening archive: {}".format(str(e)))

    def archiveClosedCallback(self, *args, **kwargs):
        print("[DEBUG][Category] Archive screen closed")
        self['info'].setText(_('Select category'))
        self['title'].setText(self.name)
        self.loadData()

    def handle_thematic_structure(self, response):
        """Handles the new thematic structure (e.g., Environment)"""
        try:
            print("[DEBUG][ThematicStructure] Handling thematic structure")

            # Extract main information from the response
            main_theme = response.get("mainThemeName", self.name)
            main_theme_unique = response.get("mainThemeUniqueName", "")
            category_domain = response.get("categoryDomain", "RaiNews")

            if not main_theme or not main_theme_unique:
                self['info'].setText(_('No main theme found'))
                return

            # Prepare the payload for the API request
            payload = {
                "page": 1,
                "pageSize": 50,
                "mode": "archive",
                "filters": {
                    "tematica": [main_theme_unique],
                    "dominio": category_domain
                }
            }

            print("[DEBUG][ThematicStructure] API payload: " + str(payload))

            # Perform the API search request
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json; charset=UTF-8",
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest"
            }

            try:
                api_response = requests.post(
                    "https://www.rainews.it/atomatic/news-search-service/api/v3/search",
                    headers=headers,
                    json=payload,
                    timeout=15)

                if api_response.status_code != 200:
                    raise Exception(
                        "API error: " + str(api_response.status_code))

                api_data = api_response.json()
                hits = api_data.get("hits", [])

                # Process only videos
                self.items = []
                for hit in hits:
                    if hit.get("data_type") == "video":
                        media = hit.get("media", {})
                        content_url = media.get("mediapolis", "")

                        if content_url:
                            if not content_url.startswith("http"):
                                content_url = "https://mediapolisvod.rai.it" + content_url

                            self.items.append({
                                "name": hit.get("title", ""),
                                "url": content_url,
                                "page_url": "",
                                "icon": self.api.getThumbnailUrl2(hit),
                                "date": hit.get("create_date", ""),
                                "duration": media.get("duration", ""),
                                "type": "video"
                            })

                if not self.items:
                    self['info'].setText(_('No videos found'))
                    return

                # Prepare visualization
                self.names = []
                for item in self.items:
                    date_str = item.get("date", "")
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00"))
                            date_str = dt.strftime("%d/%m/%Y %H:%M")
                        except BaseException:
                            pass
                    display_title = (
                        date_str + " " + item['name']) if date_str else item['name']
                    self.names.append(display_title)

                self.icons = [item["icon"] for item in self.items]
                show_list(self.names, self['text'])
                self['title'].setText(main_theme)
                self['info'].setText(_('Select item'))
                self["text"].moveToIndex(0)
                restored = self.restore_state()
                if restored:
                    self["text"].moveToIndex(self.state_index)
                else:
                    if self.names:
                        self["text"].moveToIndex(0)
                self.selectionChanged()

            except Exception as e:
                print("[DEBUG][ThematicStructure] API request error: " + str(e))
                self['info'].setText(_('Error loading content from API'))

        except Exception as e:
            print("[DEBUG][ThematicStructure] Error: " + str(e))
            self['info'].setText(_('Error processing thematic content'))
            traceback.print_exc()

    def handle_new_thematic_structure(self, response):
        """Handles the new thematic structure (e.g., Environment)"""
        try:
            print("[DEBUG][NewThematic] Handling new thematic structure")
            main_theme = response.get("mainThemeName", "")
            main_theme_unique = response.get("mainThemeUniqueName", "")
            category_domain = response.get("categoryDomain", "RaiNews")

            if not main_theme or not main_theme_unique:
                self['info'].setText(_('No main theme found'))
                return

            # Prepare the payload for the API request
            self.archive_payload = {
                "page": 1,
                "pageSize": 50,
                "mode": "archive",
                "filters": {
                    "tematica": [main_theme + "|" + main_theme_unique],
                    "dominio": category_domain
                }
            }
            self.archive_title = main_theme
            self.openArchiveScreen(main_theme, self.archive_payload)
        except Exception as e:
            print("[DEBUG][NewThematic] Error: " + str(e))
            self['info'].setText(_('Error processing archive'))
            traceback.print_exc()

    def add_news_item(self, item):
        """Add a news item to the list"""
        name = item.get("title") or item.get("name") or ""
        if not name:
            return

        # Get content URL - try multiple fields
        content_url = item.get("content_url") or item.get("video_url") or ""

        # Get page URL as fallback
        page_url = ""
        if "weblink" in item:
            page_url = "https://www.rainews.it" + item["weblink"]
        elif "link" in item:
            page_url = "https://www.rainews.it" + item["link"]

        # Get the icon
        icon = self.api.getThumbnailUrl2(item)

        # Add to results
        self.items.append({
            "name": name,
            "url": content_url,
            "page_url": page_url,
            "icon": icon,
            "date": item.get("create_date", item.get("date", "")),
            "type": "video"
        })

    def okRun(self):
        if not self.names or not hasattr(self, 'items'):
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.items):
            return

        item = self.items[idx]
        if item["type"] == "video" and item.get("url"):
            self.playDirect(item['name'], item['url'])
        else:
            self.session.open(
                MessageBox,
                _("Video URL not available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )


class RaiPlayNewsAPIArchive(SafeScreen):
    def __init__(self, session, name, api_payload):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.api_payload = api_payload
        self.current_page = 1
        self.page_size = api_payload.get("pageSize", 20)
        self.names = []
        self.videos = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading archive...'))
        self['title'] = Label("{} Archive".format(name))
        self['actions'] = ActionMap(['OkCancelActions', 'EPGSelectActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'nextBouquet': self.nextPage,
            'prevBouquet': self.prevPage,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def restore_state(self):
        """Disable state restoration for this screen"""
        print("[DEBUG][APIArchive] Skipping state restoration")
        return False

    def save_state(self):
        """Disable state saving for this screen"""
        print("[DEBUG][APIArchive] Skipping state saving")
        pass

    def loadData(self):
        """Reset state before loading data"""
        self.videos = []
        self.names = []
        self['info'].setText(_('Loading archive data...'))
        print("[DEBUG][APIArchive] Loading archive for: {}".format(self.name))
        print("[DEBUG][APIArchive] Payload: {}".format(
            dumps(self.api_payload, indent=2)))

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest"
        }

        self.api_payload["page"] = self.current_page

        try:
            response = requests.post(
                "https://www.rainews.it/atomatic/news-search-service/api/v3/search",
                headers=headers,
                json=self.api_payload,
                timeout=15)

            if response.status_code != 200:
                self['info'].setText(_('Error loading archive data'))
                return

            data = response.json()
            hits = data.get("hits", [])

            self.videos = []
            for hit in hits:
                if hit.get("data_type") == "video":
                    media = hit.get("media", {})
                    content_url = media.get("mediapolis", "")
                    if not content_url:
                        continue

                    if not content_url.startswith("http"):
                        content_url = "https://mediapolisvod.rai.it" + content_url

                    self.videos.append({
                        "title": hit.get("title", ""),
                        "url": content_url,
                        "date": hit.get("create_date", ""),
                        "icon": self.api.getThumbnailUrl2(hit),
                        "duration": media.get("duration", "")
                    })

            if not self.videos:
                self['info'].setText(_('No videos available'))
                return

            self.names = []
            for video in self.videos:
                date_str = " - {}".format(video['date']
                                          ) if video.get('date') else ""
                duration_str = " ({})".format(
                    video['duration']) if video.get('duration') else ""
                self.names.append(
                    "{}{}{}".format(
                        video['title'],
                        date_str,
                        duration_str))

            show_list(self.names, self['text'])
            self['info'].setText(_('Select item'))
            self["text"].moveToIndex(0)
            self['title'].setText("{} Archive".format(self.name))
            self.selectionChanged()
            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("[ERROR] loading archive: " + str(e))
            self['info'].setText(
                _('Error loading archive data: {}').format(
                    str(e)))

    def nextPage(self):
        self["text"].setList([])
        self.current_page += 1
        self.loadData()

    def prevPage(self):
        if self.current_page > 1:
            self["text"].setList([])
            self.current_page -= 1
            self.loadData()

    def extractAndPlay(self, video):
        """Extract the video URL from the page and play it"""
        self['info'].setText(_('Extracting video URL...'))
        try:
            page_data = Utils.getUrlSiVer(video["page_url"])
            if not page_data:
                self['info'].setText(_('Error loading video page'))
                return

            # Find the video URL in the page
            video_url = None

            # Method 1: Search for the rainews-player component
            player_match = search(
                r'<rainews-player\s+data=\'([^\']+)\'',
                page_data
            )
            if player_match:
                try:
                    player_json = player_match.group(1).replace('&quot;', '"')
                    player_data = loads(player_json)
                    video_url = player_data.get("content_url", "")
                except Exception as e:
                    print("[ERROR] parsing player JSON: " + str(e))

            # Method 2: Search for direct URL in JSON
            if not video_url:
                json_match = search(
                    r'"content_url"\s*:\s*"([^"]+)"', page_data)
                if json_match:
                    video_url = json_match.group(1)

            # Method 3: Search for direct video source
            if not video_url:
                source_match = search(
                    r'<source\s+src="([^"]+)"\s+type="video/[^"]+"',
                    page_data
                )
                if source_match:
                    video_url = source_match.group(1)

            if video_url:
                if not video_url.startswith("http"):
                    video_url = "https://www.rainews.it" + video_url
                self.playDirect(video['title'], video_url)
            else:
                self['info'].setText(_('Could not find video URL'))

        except Exception as e:
            print("[ERROR] extracting video URL: " + str(e))
            self['info'].setText(_('Error extracting video URL'))

    def okRun(self):
        if not self.videos:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.videos):
            return

        video = self.videos[idx]
        self.playDirect(video["title"], video["url"])


class RaiPlayTG(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai News"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """
        Load the list of TG categories and icons
        """
        self.names = ["TG1", "TG2", "TG3", "Altri"]
        self.urls = ["tg1", "tg2", "tg3", "altri"]
        self.icons = [png_tg1, png_tg2, png_tg3, png_tgr]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        category = self.urls[idx]
        if category in ["tg1", "tg2", "tg3"]:
            self.session.open(RaiPlayTGList, category)
        elif category == "altri":
            self.session.open(RaiPlayTGR)


class RaiPlayTGList(SafeScreen):
    def __init__(self, session, channel):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.channel = channel
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label("Rai {}".format(channel.upper()))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """
        Load available editions for the selected TG,
        including the "Archive" option and the latest videos.
        """
        # Add the "Archive" option at the top of the list
        self.names = [_("View Full Archive")]
        self.urls = ["archive"]
        self.icons = [self.api.DEFAULT_ICON_URL]

        # Add current editions
        videos = self.api.get_tg_content(self.channel)
        for video in videos:
            if video["subtitle"]:
                title = "{} - {}".format(video["title"], video["subtitle"])
            else:
                title = video["title"]

            self.names.append(title)
            self.urls.append(video["url"])
            self.icons.append(video["icon"])

        show_list(self.names, self["text"])
        self["info"].setText(_("Select edition"))

        if self.restore_state():
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        """Main method - displays the play/download menu for TG editions"""
        print("[DEBUG] okRun called in RaiPlayTGList")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Check if it's the archive option
        if self.urls[idx] == "archive":
            # Archive is navigation, not a video - open archive screen directly
            self.session.open(RaiPlayTGArchive, self.channel)
            return

        # Get video information
        name = self.names[idx]
        url = self.urls[idx] if idx < len(self.urls) else ""

        if not url:
            print(f"[DEBUG] No URL found for index {idx}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayTGArchive(SafeScreen):
    def __init__(self, session, channel):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.channel = channel
        self.current_page = 1
        self.total_pages = 1
        self.videos = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label("{} Archive".format(channel.upper()))
        self['actions'] = ActionMap(['OkCancelActions', 'EPGSelectActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'nextBouquet': self.nextPage,
            'prevBouquet': self.prevPage,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        """
        Load the data for the current archive page.
        """
        self['info'].setText(_('Loading archive data...'))

        archive_data = self.api.get_tg_archive(self.channel, self.current_page)
        self.videos = archive_data.get("videos", [])
        pagination = archive_data.get("pagination", {})

        self.total_pages = pagination.get("total_pages", 1)
        self.total_items = pagination.get("total_items", 0)

        if not self.videos:
            self['info'].setText(_('No editions available'))
            return

        # Prepare the list for display
        self.names = []
        for video in self.videos:
            date_str = " - {}".format(video['date']
                                      ) if video.get('date') else ""
            duration_str = " ({})".format(
                video['duration']) if video.get('duration') else ""
            self.names.append(
                "{}{}{}".format(
                    video['title'],
                    date_str,
                    duration_str))

        show_list(self.names, self['text'])
        self['info'].setText("{} Archive - Page {}/{}".format(
            self.channel.upper(), self.current_page, self.total_pages))
        if self.restore_state():
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def nextPage(self):
        """Go to the next page"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.loadData()

    def prevPage(self):
        """Go back to the previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            self.loadData()

    def okRun(self):
        """Main method - displays the play/download menu for TG archive videos"""
        print("[DEBUG] okRun called in RaiPlayTGArchive")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information from videos list
        if not hasattr(self, 'videos') or idx >= len(self.videos):
            print(f"[DEBUG] No video found for index {idx}")
            self.session.open(
                MessageBox,
                _("Video not available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        video = self.videos[idx]
        name = video['title']

        # Prefer content_url if available, otherwise use page_url
        url = video.get("content_url", "")
        if not url:
            url = video.get('page_url', '')

        if not url:
            print(f"[DEBUG] No URL found for video: {name}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayTGR(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("TGR and Special Programs"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Load both regional TGR programs and the special programs"""
        # Existing regional TGR programs with specific icons
        categories = [{"name": "TG Regionale",
                       "url": "https://www.rainews.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?tgr",
                       "icon": png_tgr},
                      {"name": "Meteo Regionale",
                       "url": "https://www.rainews.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?meteo",
                       "icon": "https://www.rainews.it/dl/tgr/mhp/immagini/meteo.png"},
                      {"name": "Buongiorno Italia",
                       "url": "https://www.rainews.it/dl/rai24/tgr/rubriche/mhp/ContentSet-88d248b5-6815-4bed-92a3-60e22ab92df4.html",
                       "icon": "https://www.rainews.it/dl/tgr/mhp/immagini/buongiorno%20italia.png"},
                      {"name": "Buongiorno Regione",
                       "url": "https://www.rainews.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?buongiorno",
                       "icon": "https://www.rainews.it/dl/tgr/mhp/immagini/buongiorno%20regione.png"},
                      {"name": "Il Settimanale",
                       "url": "https://www.rainews.it/dl/rai24/tgr/rubriche/mhp/ContentSet-b7213694-9b55-4677-b78b-6904e9720719.html",
                       "icon": "https://www.rainews.it/dl/tgr/mhp/immagini/il%20settimanale.png"},
                      {"name": "Rubriche",
                       "url": "https://www.rainews.it/dl/rai24/tgr/rubriche/mhp/list.xml",
                       "icon": "https://www.rainews.it/dl/tgr/mhp/immagini/rubriche.png"}]

        # Add the new special programs
        special_programs = [
            {"name": "TV7",
             "url": "https://www.rainews.it/rubriche/tv7/archivio",
             "icon": png_tv7},
            {"name": "Speciale TG1",
             "url": "https://www.rainews.it/rubriche/specialetg1/archivio",
             "icon": png_tgspec},
            {"name": "TG1 Dialogo",
             "url": "https://www.rainews.it/rubriche/tg1dialogo/archivio",
             "icon": png_tgd},
            {"name": "TG1 Economia",
             "url": "https://www.rainews.it/rubriche/tg1economia/archivio",
             "icon": png_tgec},
            {"name": "TG1 Libri",
             "url": "https://www.rainews.it/rubriche/tg1libri/archivio",
             "icon": png_tglib},
            {"name": "TG1 Medicina",
             "url": "https://www.rainews.it/rubriche/tg1medicina/archivio",
             "icon": png_tgmed},
            {"name": "TG1 Motori",
             "url": "https://www.rainews.it/rubriche/tg1motori/archivio",
             "icon": png_tgm},
            {"name": "TG1 Persone",
             "url": "https://www.rainews.it/rubriche/tg1persone/archivio",
             "icon": png_tgpers},
            # {"name": "TG Sport (Archivio)", "url": "https://www.rainews.it/notiziari/tgsport/archivio", "icon": png_tgsp}
        ]

        # Combine both lists
        self.programs = categories + special_programs

        # Extract names, urls, and icons
        self.names = [program["name"] for program in self.programs]
        self.urls = [program["url"] for program in self.programs]
        self.icons = [program["icon"] for program in self.programs]

        show_list(self.names, self['text'])
        self['info'].setText(_('Select program'))

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]

        # Check if it's a special program (use direct archive)
        is_special = name in [
            "Speciale TG1",
            "TG1 Motori",
            "TG1 Medicina",
            "TG1 Dialogo",
            "TV7",
            "TG1 Libri",
            "TG1 Persone",
            "TG1 Economia",
            "Tg Sport (Archivio)"]
        # Check if it's a regional TGR program (use existing navigation)
        is_regional = name in [
            "TG Regionale", "Meteo Regionale", "Buongiorno Italia",
            "Buongiorno Regione", "Il Settimanale", "Rubriche"
        ]

        if is_special:
            self.session.open(RaiPlayTGDirectArchive, name, url)
        elif is_regional:
            self.session.open(tgrRai2, name, url)
        else:
            # Default to regional navigation
            self.session.open(tgrRai2, name, url)


class RaiPlayTGDirectArchive(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.url = url
        self.current_page = 1
        self.videos = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading archive...'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'EPGSelectActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'nextBouquet': self.nextPage,
            'prevBouquet': self.prevPage,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        """Load archive data directly from the provided URL"""
        self['info'].setText(_('Loading archive data...'))

        try:
            # Fetch the archive page
            data = Utils.getUrlSiVer(self.url)
            if not data:
                self['info'].setText(_('No content available'))
                return

            # Handle TG Sport archive differently
            if "tgsport/archivio" in self.url:
                self.parseTgSportArchive(data)
            else:
                self.parseGenericArchive(data)

            if not self.videos:
                self['info'].setText(_('No videos found in archive'))
                return

            # Prepare the list for display
            self.names = []
            for video in self.videos:
                # Format the title with date and duration if available
                display_title = video["title"]
                if video.get("date"):
                    try:
                        dt = datetime.fromisoformat(
                            video["date"].replace("Z", "+00:00"))
                        display_title = "{} - {}".format(
                            dt.strftime('%d/%m/%Y'), display_title)
                    except BaseException:
                        pass
                if video.get("duration"):
                    display_title += " ({})".format(video['duration'])

                self.names.append(display_title)

            show_list(self.names, self['text'])
            self['info'].setText(_('Select video'))

            if self.names:
                self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print("[ERROR] loading archive: " + str(e))
            self['info'].setText(
                _('Error loading archive data: {}').format(
                    str(e)))

    def parseTgSportArchive(self, data):
        """Special parser for TG Sport archive page"""
        self.videos = []

        # Find all program blocks
        program_blocks = findall(
            r'<div class="grid__item col-12 col-sm-6 col-lg-4">(.*?)</div>\s*</div>',
            data,
            DOTALL)

        for block in program_blocks:
            # Extract title
            title_match = search(r'<h3 class="card__title">(.*?)</h3>', block)
            if not title_match:
                continue
            title = title_match.group(1).strip()

            # Extract date
            date_match = search(r'<div class="card__date">(.*?)</div>', block)
            date_str = date_match.group(1).strip() if date_match else ""

            # Extract duration
            duration_match = search(
                r'<div class="launch-item__duration">.*?<span>(.*?)</span>', block, DOTALL)
            duration = duration_match.group(
                1).strip() if duration_match else ""
            # Extract page URL
            url_match = search(r'href="(.*?)"', block)
            if not url_match:
                continue
            page_url = url_match.group(1)
            if not page_url.startswith("http"):
                page_url = "https://www.rainews.it" + page_url

            # Extract image URL
            img_match = search(r'data-src="(.*?)"', block)
            img_url = img_match.group(1) if img_match else ""
            if img_url and not img_url.startswith("http"):
                img_url = "https://www.rainews.it" + img_url

            self.videos.append({
                "title": title,
                "page_url": page_url,
                "icon": img_url,
                "date": date_str,
                "duration": duration
            })

        # If no items found with the first method, try alternative method
        if not self.videos:
            self.parseAlternativeSportArchive(data)

    def parseAlternativeSportArchive(self, data):
        """Alternative parser for TG Sport archive"""
        # Find all video items
        video_items = findall(
            r'<a\s+class="[^"]*?beforeicon_video[^"]*?"[^>]*?href="([^"]+)"[^>]*?>.*?<img[^>]*?data-src="([^"]+)"[^>]*?alt="([^"]+)".*?<div class="launch-item__duration">.*?<span>([^<]+)</span>',
            data,
            DOTALL)
        for matchx in video_items:
            page_url, img_url, title, duration = matchx
            if not page_url.startswith("http"):
                page_url = "https://www.rainews.it" + page_url
            if not img_url.startswith("http"):
                img_url = "https://www.rainews.it" + img_url

            self.videos.append({
                "title": title,
                "page_url": page_url,
                "icon": img_url,
                "duration": duration
            })

    def parseGenericArchive(self, data):
        """Parser for generic archive pages"""
        self.videos = []

        # Method 1: Extract JSON data from rainews-aggregator-broadcast-archive
        json_match = search(
            r'<rainews-aggregator-broadcast-archive\s+data="([^"]+)"',
            data
        )
        if json_match:
            try:
                # Parse the JSON
                json_str = html_unescape(json_match.group(1))
                archive_data = loads(json_str)

                # Process the videos
                cards = archive_data.get("contents", [])[0].get("cards", [])
                for card in cards:
                    video = {
                        "title": card.get(
                            "title",
                            ""),
                        "content_url": card.get(
                            "content_url",
                            ""),
                        "page_url": "https://www.rainews.it" +
                        card.get(
                            "link",
                            ""),
                        "icon": self.api.getThumbnailUrl2(card),
                        "date": card.get(
                            "broadcast",
                            {}).get(
                            "edition",
                            {}).get(
                            "dateIso",
                            ""),
                        "duration": card.get(
                            "duration",
                            "")}
                    self.videos.append(video)
            except Exception as e:
                print("[ERROR] parsing JSON archive: " + str(e))

        # If no videos found, try HTML parsing
        if not self.videos:
            self.parseHtmlArchive(data)

    def parseHtmlArchive(self, data):
        """Parse archive by scanning HTML structure"""
        # Find all video items in the HTML
        video_items = findall(
            r'<a\s+class="[^"]*?beforeicon_video[^"]*?"[^>]*?href="([^"]+)"[^>]*?>.*?<img[^>]*?data-src="([^"]+)"[^>]*?alt="([^"]+)".*?<div class="launch-item__duration">.*?<span>([^<]+)</span>',
            data,
            DOTALL)
        for matchx in video_items:
            page_url, img_url, title, duration = matchx
            if not page_url.startswith("http"):
                page_url = "https://www.rainews.it" + page_url
            if not img_url.startswith("http"):
                img_url = "https://www.rainews.it" + img_url

            self.videos.append({
                "title": title,
                "page_url": page_url,
                "icon": img_url,
                "duration": duration
            })

    def extractAndPlay(self, video):
        """Extract the actual video URL from the video page"""
        self['info'].setText(_('Extracting video URL...'))
        try:
            page_data = Utils.getUrlSiVer(video["page_url"])
            if not page_data:
                self['info'].setText(_('Error loading video page'))
                return

            # Find the video URL in the page
            video_url = None

            # Method 1: Look for content_url in JSON
            json_match = search(r'content_url\s*:\s*"([^"]+)"', page_data)
            if json_match:
                video_url = json_match.group(1)

            # Method 2: Look for rainews-player data
            if not video_url:
                player_match = search(
                    r'<rainews-player\s+data=\'([^\']+)\'', page_data)
                if player_match:
                    try:
                        player_json = player_match.group(
                            1).replace('&quot;', '"')
                        player_data = loads(player_json)
                        video_url = player_data.get("content_url", "")
                    except BaseException:
                        pass

            # Method 3: Look for video source
            if not video_url:
                source_match = search(
                    r'<source\s+src="([^"]+)"\s+type="video/[^"]+"', page_data)
                if source_match:
                    video_url = source_match.group(1)

            if video_url:
                if not video_url.startswith("http"):
                    video_url = "https://www.rainews.it" + video_url
                self.playDirect(video['title'], video_url)
            else:
                self['info'].setText(_('Could not find video URL'))

        except Exception as e:
            print("[ERROR] extracting video URL: " + str(e))
            self['info'].setText(_('Error extracting video URL'))

    def nextPage(self):
        # These archives don't support pagination
        self['info'].setText(_('Pagination not supported for this archive'))

    def prevPage(self):
        # These archives don't support pagination
        self['info'].setText(_('Pagination not supported for this archive'))

    def okRun(self):
        """Main method - displays the play/download menu for TG direct archive videos"""
        print("[DEBUG] okRun called in RaiPlayTGDirectArchive")

        if not hasattr(self, 'videos') or not self.videos:
            print("[DEBUG] No videos available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.videos):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information
        video = self.videos[idx]
        name = video["title"]

        # Prefer content_url if available, otherwise use page_url
        url = video.get("content_url", "")
        if not url:
            url = video.get('page_url', '')

        if not url:
            print(f"[DEBUG] No URL found for video: {name}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayTGDirectArchive"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Menu choice: {choice[1]}")

        if choice[1] == "play":
            print("[DEBUG] User selected PLAY")
            # Use content_url if available, otherwise extract from page
            if self.selected_url and self.selected_url.startswith('http'):
                self.playDirect(self.selected_name, self.selected_url)
            else:
                self.extractAndPlay(
                    {'title': self.selected_name, 'page_url': self.selected_url})
        elif choice[1] == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif choice[1] == "both":
            print("[DEBUG] User selected BOTH")
            if self.selected_url and self.selected_url.startswith('http'):
                self.playDirect(self.selected_name, self.selected_url)
                # Add small delay before starting download
                timer = eTimer()
                timer.callback.append(
                    lambda: self.addToDownloadQueue(
                        self.selected_name, self.selected_url))
                timer.start(1000, True)
            else:
                self.extractAndPlay(
                    {'title': self.selected_name, 'page_url': self.selected_url})


class tgrRai2(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Parse TGR content from XML"""
        try:
            content = Utils.getUrlSiVer(self.url)
            if not content:
                self['info'].setText(_('Error loading data'))
                return

            content = content.replace(
                "\r",
                "").replace(
                "\t",
                "").replace(
                "\n",
                "")

            # Alternative parsing
            matches = findall(
                r'data-video-json="(.*?).json".*?<img alt="(.*?)"',
                content,
                DOTALL)
            if matches:
                for url, name in matches:
                    full_url = "https://www.raiplay.it" + url + '.html'
                    self.names.append(name)
                    self.urls.append(full_url)
                    self.icons.append(png_tgr)

                if self.names:
                    show_list(self.names, self['text'])
                    self['info'].setText(_('Select video'))

                    if self.restore_state():
                        self["text"].moveToIndex(self.state_index)
                    else:
                        if self.names:
                            self["text"].moveToIndex(0)
                    self.selectionChanged()
                    return

            # Original XML parsing
            # Search for directories
            dirs = findall(
                '<item behaviour="(?:region|list)">(.*?)</item>',
                content,
                DOTALL
            )
            for item in dirs:
                title = search('<label>(.*?)</label>', item)
                url = search('<url type="list">(.*?)</url>', item)
                image = search('<url type="image">(.*?)</url>', item)
                if title and url:
                    self.names.append(title.group(1))
                    self.urls.append(self.api.getFullUrl(url.group(1)))
                    self.icons.append(
                        self.api.getFullUrl(
                            image.group(1)) if image else self.api.DEFAULT_ICON_URL)

            # Search for videos
            videos = findall(
                '<item behaviour="video">(.*?)</item>',
                content,
                DOTALL
            )
            for item in videos:
                title = search('<label>(.*?)</label>', item)
                url = search('<url type="video">(.*?)</url>', item)
                image = search('<url type="image">(.*?)</url>', item)
                if title and url:
                    self.names.append(title.group(1))
                    self.urls.append(url.group(1))
                    self.icons.append(
                        self.api.getFullUrl(
                            image.group(1)) if image else self.api.DEFAULT_ICON_URL)

            if self.names:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select item'))
            else:
                self['info'].setText(_('No items found'))

            if self.restore_state():
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print('Error parsing TGR:', str(e))
            self['info'].setText(_('Error parsing data'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]
        if 'relinker' in url:
            self.playDirect(name, url)
        else:
            self.session.open(tgrRai3, name, url)


class tgrRai3(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.name = name
        self.url = url
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Parse nested TGR content"""
        try:
            content = Utils.getUrlSiVer(self.url)
            if not content:
                self['info'].setText(_('Error loading data'))
                return

            content = content.replace(
                "\r",
                "").replace(
                "\t",
                "").replace(
                "\n",
                "")
            if 'type="video">' in content:
                regex = r'<label>(.*?)</label>.*?type="video">(.*?)</url>'
            elif 'type="list">' in content:
                regex = r'<label>(.*?)</label>.*?type="list">(.*?)</url>'
            else:
                # Try alternative parsing for video content
                matches = findall(
                    r'data-video-json="(.*?).json".*?<img alt="(.*?)"',
                    content,
                    DOTALL)
                if matches:
                    for url, name in matches:
                        full_url = "https://www.raiplay.it" + url + '.html'
                        self.names.append(name)
                        self.urls.append(full_url)
                        self.icons.append(png_tgr)
                    if self.names:
                        show_list(self.names, self['text'])
                        self['info'].setText(_('Select video'))
                        return
                else:
                    self['info'].setText(_('Content type not recognized'))
                    return

            matches = findall(regex, content, DOTALL)
            for name, url in matches:
                if not url.startswith('http'):
                    url = "https://www.tgr.rai.it" + url
                self.names.append(name)
                self.urls.append(url)
                self.icons.append(png_tgr)

            if self.names:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select item'))
            else:
                self['info'].setText(_('No items found'))

            if self.restore_state():
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print('Error parsing TGR content: {}'.format(str(e)))
            self['info'].setText(_('Error parsing data'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]

        if 'relinker' in url or 'video' in url:
            self.playDirect(name, url)
        else:
            self.session.open(tgrRai4, name, url)


class tgrRai4(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.url = url
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        """Parse final video content"""
        try:
            content = Utils.getUrlSiVer(self.url)
            if not content:
                self['info'].setText(_('Error loading data'))
                return

            # Find video JSON references
            matches = findall(
                r'data-video-json="(.*?)".*?<img alt="(.*?)"',
                content,
                DOTALL)
            for url, name in matches:
                # Build full video URL
                content2 = Utils.getUrlSiVer("https://www.raiplay.it" + url)
                if not content2:
                    continue
                # Extract video path
                match2 = search(r'"/video/(.*?)"', content2)
                if match2:
                    video_path = match2.group(1).replace("json", "html")
                    video_url = "https://www.raiplay.it/video/" + video_path
                    self.names.append(name)
                    self.urls.append(video_url)
                    self.icons.append(png_tgr)

            if self.names:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select video'))
            else:
                self['info'].setText(_('No videos found'))

            if self.restore_state():
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print('Error parsing video content: {}'.format(str(e)))
            self['info'].setText(_('Error parsing data'))

    def okRun(self):
        """Main method - displays the play/download menu for TGR videos"""
        print("[DEBUG] okRun called in tgrRai4")

        if not hasattr(self, 'names') or not self.names:
            print("[DEBUG] No names available, returning")
            return

        idx = self["text"].getSelectionIndex()
        print(f"[DEBUG] Selected index: {idx}")

        if idx is None or idx >= len(self.names):
            print(f"[DEBUG] Invalid index: {idx}")
            return

        # Get video information
        name = self.names[idx]
        url = self.urls[idx] if idx < len(self.urls) else ""

        if not url:
            print(f"[DEBUG] No URL found for index {idx}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlaySport(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.navigation_stack = []
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Sport"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.goBack,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadCategories)

    def loadCategories(self):
        """Load the main sports categories with debug"""
        print("[DEBUG] Loading sport categories")
        self.navigation_stack = []
        self.categories = self.api.getSportCategories()

        if not self.categories:
            error_msg = _('No sports categories available')
            print("[ERROR] " + error_msg)
            self['info'].setText(error_msg)
            return

        # print("[DEBUG] Found " + str(len(self.categories)) + " sport categories")
        self.names = [cat['title'] for cat in self.categories]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))
        self['title'].setText(_("Rai Sport - Categories"))
        self.current_level = "categories"

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def loadSubcategories(self, category):
        """Load subcategories for a specific category"""
        print("[DEBUG][Sport] Loading subcategories for: " + category['title'])
        self.navigation_stack.append({
            'type': 'category',
            'data': category
        })

        self.subcategories = self.api.getSportSubcategories(category['key'])
        print("[DEBUG][Sport] Found {} subcategories".format(
            len(self.subcategories)))

        if not self.subcategories:
            print("[DEBUG][Sport] No subcategories found, loading videos directly")
            self.loadVideos(category)
            return

        self.names = [subcat['title'] for subcat in self.subcategories]
        # self.icons.append(str(png_sport))
        show_list(self.names, self['text'])
        self['info'].setText(_('Select subcategory'))
        self['title'].setText(_("Rai Sport - Subcategories"))
        self.current_level = "subcategories"
        self.current_category = category

        if self.restore_state():
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)

        self.selectionChanged()
        self.updatePoster()

        self.updateUI()

    def loadVideos(self, category, subcategory=None):
        dominio = "RaiNews|Category-6dd7493b-f116-45de-af11-7d28a3f33dd2"
        key = subcategory['key'] if subcategory else category['key']
        self.session.open(
            RaiPlaySportVideos,
            subcategory['title'] if subcategory else category['title'],
            key,
            dominio,
            0
        )

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        if self.current_level == "categories":
            category = self.categories[idx]
            self.loadSubcategories(category)
            self.updateUI()

        elif self.current_level == "subcategories":
            subcategory = self.subcategories[idx]
            self.loadVideos(self.current_category, subcategory)

    def goBack(self):
        """Manages backward navigation"""
        if not self.navigation_stack:
            self.close()
            return

        last_state = self.navigation_stack.pop()

        if last_state['type'] == 'subcategory':
            self.loadSubcategories(last_state['parent'])
        elif last_state['type'] == 'category':
            self.loadCategories()
        else:
            self.close()


class RaiPlaySportVideos(SafeScreen):
    def __init__(self, session, name, key, dominio, parent=None):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = True
        self.name = name
        self.key = key
        self.dominio = dominio
        self.current_page = 0
        self.page_size = 20
        self.videos = []
        self.all_videos = []
        self.displayed_videos = []
        self.loading = False
        self.seen_videos = set()
        self.cancel_loading = False
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions'], {
            'ok': self.okRun,
            'cancel': self.cancelAction,
            'info': self.infohelp
        }, -1)
        self.onLayoutFinish.append(self.loadData)

    def loadData(self):
        """Start loading all videos"""
        if not self.loading:
            self.loading = True
            self['info'].setText(_('Loading all videos... Please wait'))
            threading.Thread(target=self.loadVideosThread).start()

    def loadVideosThread(self):
        """Load ALL available videos removing duplicates"""
        try:
            print("[DEBUG][Sport] Loading ALL videos for key: " + str(self.key))
            page = 0
            max_pages = 100
            unique_videos = []  # List for unique videos

            while page < max_pages:
                videos = self.api.get_sport_videos_page(
                    self.key,
                    page,
                    self.page_size
                )

                if not videos:
                    break

                # Filter duplicates and add unique videos
                for video in videos:
                    # Create a unique identifier based on title and date
                    title = video.get("title", "")
                    date_str = video.get(
                        "create_date", video.get(
                            "publication_date", ""))
                    video_id = title + "|" + date_str

                    # If this video was not already seen, add it
                    if video_id not in self.seen_videos:
                        self.seen_videos.add(video_id)
                        unique_videos.append(video)

                page += 1
                time.sleep(0.1)

                self['title'].setText(
                    "Loading all videos... Please wait - " +
                    _("Page with duplicate") +
                    " " +
                    str(page))
            print("[DEBUG][Sport] Total unique videos: " +
                  str(len(unique_videos)))

            # Sort videos by date (most recent first)
            try:
                unique_videos.sort(
                    key=lambda v: v.get(
                        "create_date",
                        v.get(
                            "publication_date",
                            "")),
                    reverse=True)

            except Exception as e:
                print("[DEBUG][Sport] Sorting error: " + str(e))

            self.all_videos = unique_videos
            self.total_pages = (len(self.all_videos) +
                                self.page_size - 1) // self.page_size

            # Show the first page
            self.showCurrentPage()
        except Exception as e:
            print("[DEBUG][Sport] Error loading videos: " + str(e))
            self.session.open(
                MessageBox,
                _("Error loading videos: ") + str(e),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
        finally:
            self.loading = False

    def showCurrentPage(self):
        """Show ONLY the videos of the current page"""
        # 1. Reset lists BEFORE adding new elements
        self.displayed_videos = []
        self.names = []
        self.icons = []

        # 2. Compute indices for the current page
        start_idx = self.current_page * self.page_size
        end_idx = start_idx + self.page_size
        page_videos = self.all_videos[start_idx:end_idx]

        # 3. Add videos of the current page
        for video in page_videos:
            title = video.get("title", "No title")
            date_str = video.get(
                "create_date", video.get(
                    "publication_date", ""))
            duration = video.get("duration", "")

            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_display = dt.strftime("%d/%m/%Y %H:%M")

                # Add duration if available
                if duration:
                    display_title = date_display + " - " + \
                        title + " (" + duration + ")"
                else:
                    display_title = date_display + " - " + title

            except Exception:
                display_title = title

            self.displayed_videos.append(video)
            self.names.append(display_title)
            self.icons.append(self.get_video_icon(video))

        # 4. Add "Next page" if there are more pages
        if self.current_page < self.total_pages - 1:
            next_page = self.current_page + 1
            self.displayed_videos.append({
                "title": _("Next page"),
                "page": next_page,
                "is_page": True
            })
            self.names.append(
                _("Next page") + " (" + str(next_page + 1) + "/" + str(self.total_pages) + ")")
            self.icons.append(self.api.DEFAULT_ICON_URL)
        elif not self.displayed_videos:
            self.names.append(_("No videos found"))
            self.icons.append(self.api.DEFAULT_ICON_URL)
            self.displayed_videos.append({"is_empty": True})

        # 5. Update UI list
        show_list(self.names, self["text"])

        # 6. Update title
        self['title'].setText(self.name +
                              " - " +
                              _("Page") +
                              " " +
                              str(self.current_page +
                                  1) +
                              "/" +
                              str(self.total_pages))

        # 7. Restore selection
        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

        # 8. Update poster
        self.updatePoster()

        # 9. Update status
        self['info'].setText(_('Select a video'))

    def get_video_icon(self, video):
        """Return the URL of the icon for a video"""
        icon = self.api.getThumbnailUrl2(video)
        return icon

    def playVideo(self, video):
        """Play a video"""
        try:
            media = video.get("media", {})
            content_url = media.get("mediapolis", "")
            if not content_url:
                raise ValueError(_("Video URL not found"))

            if not content_url.startswith("http"):
                content_url = "https://mediapolisvod.rai.it" + content_url

            title = video.get("title", _("Unknown title"))
            self.session.open(Playstream2, title, content_url)

        except Exception as e:
            self.session.open(
                MessageBox,
                _("Error playing video: ") + str(e),
                MessageBox.TYPE_ERROR,
                timeout=5
            )

    def stopLoading(self):
        """Stop loading"""
        self.cancel_loading = True
        self.loading = False

    def cancelAction(self):
        """Handles the Back/Exit button with the original behavior"""
        if self.current_page > 0:
            self.current_page -= 1
            self.showCurrentPage()
        else:
            self.close()

    def goBack(self):
        """Go back to the previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.showCurrentPage()
        else:
            self.cancelAction()

    def okRun(self):
        """Main method - displays the play/download menu for sport videos"""
        print("[DEBUG] okRun called in RaiPlaySportVideos")

        if not self.displayed_videos or self.displayed_videos[0].get(
                "is_empty"):
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.displayed_videos):
            return

        item = self.displayed_videos[idx]

        # Handle pagination - not a video
        if item.get("is_page"):
            self.current_page = item["page"]
            self.showCurrentPage()
            return

        # Get video information
        name = item.get("title", "No title")
        media = item.get("media", {})
        url = media.get("mediapolis", "")

        if not url:
            print(f"[DEBUG] No URL found for video: {name}")
            self.session.open(
                MessageBox,
                _("No video URL available"),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return

        # Make URL absolute if needed
        if not url.startswith("http"):
            url = "https://mediapolisvod.rai.it" + url

        print(f"[DEBUG] Selected: {name}")
        print(f"[DEBUG] Video URL: {url}")

        self.selected_name = name
        self.selected_url = url
        self.selected_item = item  # Store the full item for playVideo

        # Show menu with options
        menu = [
            (_("Play"), "play"),
            (_("Download"), "download"),
            (_("Play & Download"), "both")
        ]

        self.session.openWithCallback(
            self.menuCallback,
            MessageBox,
            _("Choose action for: {}").format(name),
            list=menu
        )

    def menuCallback(self, choice):
        """Handle menu selection for RaiPlayOnDemandCategory"""
        if choice is None:
            print("[DEBUG] Menu selection cancelled")
            return

        print(f"[DEBUG] Full choice object: {choice}")
        print(f"[DEBUG] Choice type: {type(choice)}")

        # MessageBox con lista restituisce direttamente la stringa della scelta
        if isinstance(choice, str):
            action = choice.lower()
            print(f"[DEBUG] Menu choice string: {choice}")
        else:
            print(f"[DEBUG] Unexpected choice format: {choice}")
            return

        if action == "play":
            print("[DEBUG] User selected PLAY")
            self.playDirect(self.selected_name, self.selected_url)
        elif action == "download":
            print("[DEBUG] User selected DOWNLOAD")
            self.addToDownloadQueue(self.selected_name, self.selected_url)
        elif action == "play & download":
            print("[DEBUG] User selected BOTH")
            self.playDirect(self.selected_name, self.selected_url)
            # Add small delay before starting download
            timer = eTimer()
            timer.callback.append(
                lambda: self.addToDownloadQueue(
                    self.selected_name,
                    self.selected_url))
            timer.start(1000, True)  # 1 second delay
        else:
            print(f"[DEBUG] Unknown action: {action}")


class RaiPlayPrograms(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Programs"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'info': self.infohelp
        }, -2)
        self.onLayoutFinish.append(self.loadProgramCategories)

    def loadProgramCategories(self):
        categories = [{"name": _("Exclusive Programs"),
                       "url": "raccolta/Programmi-in-esclusiva-f62a210b-d5a5-4b0d-ae73-1625c1da15b6.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                      {"name": _("Society & Culture"),
                       "url": "genere/PROGRAMMI---Costume-e-Societa-8875c1f7-799b-402b-92f9-791bde8fb141.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                      {"name": _("Crime Investigations"),
                       "url": "genere/Programmi---Crime-d8b77fff-5018-4ad6-9d4d-40d7dc548086.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                      {"name": _("Games & Quizzes"),
                       "url": "genere/Giochi--Quiz-ad635fda-4dd5-445f-87ff-64d60404f1ca.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                      {"name": _("News & Documentaries"),
                       "url": "genere/Programmi---Inchieste-e-Reportage-18990102-8310-47ac-9976-07467ffc6924.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                      {"name": _("Entertainment"),
                       "url": "genere/Programmi---Intrattenimento-373672aa-a1d2-4da7-a7c7-52a3fc1fda6d.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                      {"name": _("Lifestyle"),
                       "url": "genere/Programmi---Lifestyle-f247c5a8-1272-42cf-81c3-462f585ed0ab.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                      {"name": _("Music"),
                       "url": "genere/PROGRAMMI---Musica-09030aa3-7cae-4e46-babb-30e7b8c5d47a.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459668481_ico-musica.png"},
                      {"name": _("Music Classic"),
                       "url": "genere/Musica-Classica-2c49bffc-50a1-426a-86ac-d23e4bc285f7.json",
                       "icon": "https://www.raiplay.it/dl/img/2021/11/29/1638200397142_2048x1152.jpg"},
                      {"name": _("Sports"),
                       "url": "genere/Programmi---Sport-2a822ae2-cc29-4cac-b813-74be6d2d249f.json",
                       "icon": png_sport},
                      {"name": _("History & Art"),
                       "url": "genere/Programmi---Storia--Arte-ea281d79-9ffb-4aaa-a86d-33f7391650e7.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                      {"name": _("Talk Shows"),
                       "url": "genere/Programmi---Talk-Show-2d2c3d6d-1aec-4d41-b926-cea21b88b245.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                      {"name": _("Travel & Adventure"),
                       "url": "genere/Programmi---Viaggi-e-Avventure-640ff485-ac26-4cff-8214-d9370664ffe2.json",
                       "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"}]
        """
        nuovi_generi = [
            {
                "name": _("For Families & Kids"),
                "url": "https://www.raiplay.it/genere/Per-famiglie-Ragazzi-vTxdMctD-NFtKfCGM-Uimc-VGFF-dxXt-RPiEyLEeDKun.json",
                "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"
            },
            {
                "name": _("Soap Operas"),
                "url": "https://www.raiplay.it/genere/soap-opera-KyAgZVLX-CotHykqb-sRRs-yNIK-LhVw-UBmSxchKrzvo.json",
                "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"
            }
        ]
        """
        nuovi_tipologie = [{"name": _("Films"),
                            "url": "https://www.raiplay.it/tipologia/film/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Italian Series"),
                            "url": "https://www.raiplay.it/tipologia/serieitaliane/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                           {"name": _("Sports"),
                            "url": "https://www.raiplay.it/tipologia/sport/index.json",
                            "icon": png_sport},
                           {"name": _("International Series"),
                            "url": "https://www.raiplay.it/tipologia/serieinternazionali/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Crime"),
                            "url": "https://www.raiplay.it/tipologia/crime/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                           {"name": _("Kids"),
                            "url": "https://www.raiplay.it/tipologia/bambini/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Programs"),
                            "url": "https://www.raiplay.it/tipologia/programmi/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Originals"),
                            "url": "https://www.raiplay.it/tipologia/original/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Documentaries"),
                            "url": "https://www.raiplay.it/tipologia/documentari/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"},
                           {"name": _("Teens"),
                            "url": "https://www.raiplay.it/tipologia/teen/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Music & Theater"),
                            "url": "https://www.raiplay.it/tipologia/musica-e-teatro/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459668481_ico-musica.png"},
                           {"name": _("Tech & Learning"),
                            "url": "https://www.raiplay.it/tipologia/techerai/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Learning"),
                            "url": "https://www.raiplay.it/tipologia/learning/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"},
                           {"name": _("Sustainability"),
                            "url": "https://www.raiplay.it/tipologia/sostenibilita/index.json",
                            "icon": "https://www.raiplay.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"}]

        # List of already existing URLs for checking
        existing_urls = {cat["url"] for cat in categories}

        # Add new genres if they are not already present
        """
        # for gen in nuovi_generi:
            # if gen["url"] not in existing_urls:
                # categories.append(gen)
                # existing_urls.add(gen["url"])
        """
        # Add new types if they are not already present
        for tip in nuovi_tipologie:
            if tip["url"] not in existing_urls:
                categories.append(tip)
                existing_urls.add(tip["url"])

        # Sort alphabetically by name
        categories.sort(key=lambda x: x["name"])

        exclude_names = {
            "home", "tv guide / replay", "live", "login / register",
            "recently watched", "my favorites", "watch later", "watch offline",
            "tutorial", "faq", "contact us", "privacy policy",
            "rai corporate", "privacy attività giornalistica", "cookie policy", "preferenze cookie",
            "rai", "rainews", "raiplay sound", "rai cultura", "rai scuola",
            "rai teche", "raiplay yoyo", "canone", "lavora con noi", "vai all'elenco completo",
            "x", "facebook", "instagram", "login"  # , "raiplay"
        }

        # Filter the categories list excluding names in
        # exclude_names, all in lower case
        categories = [
            cat for cat in categories if cat["name"].lower() not in exclude_names]
        self.names = [cat["name"] for cat in categories]
        self.urls = [cat["url"] for cat in categories]
        self.icons = [cat["icon"] for cat in categories]

        show_list(self.names, self['text'])
        self['info'].setText(_('Select a category'))
        self.updatePoster()

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.session.open(RaiPlayOnDemandCategory, name, url, "category")


class RaiPlaySearch(SafeScreen):
    def __init__(self, session, program_categories):
        self.session = session
        self.program_categories = program_categories
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        self.names = []
        self.query = ""
        self.results = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Search"))
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions'], {
            'ok': self.okRun,
            'cancel': self.close,
            'green': self.showVirtualKeyboard,
            'info': self.infohelp
        }, -2)
        # Create the timer for the keyboard
        self.keyboard_timer = eTimer()
        self.keyboard_timer.callback.append(self.showVirtualKeyboard)
        self.onLayoutFinish.append(self.startKeyboardTimer)

    def startKeyboardTimer(self):
        """Start the timer to show the virtual keyboard"""
        self.keyboard_timer.start(100, True)

    def showVirtualKeyboard(self):
        """Show the virtual keyboard for the search query"""
        self.session.openWithCallback(
            self.VirtualKeyBoardCallback,
            VirtualKeyBoard,
            title=_("Enter search query"),
            text=self.query
        )

    def VirtualKeyBoardCallback(self, callback=None):
        """Handle the virtual keyboard callback"""
        if callback is None:
            # User pressed cancel
            self.close()
            return

        if len(callback) > 2:
            # Valid query, perform the search
            self.query = callback
            self.performSearch()
        else:
            # Query too short, show error and reopen the keyboard
            self['info'].setText(_('Query too short (min 3 characters)'))
            self.showVirtualKeyboard()

    def performSearch(self):
        """Search through all program categories"""
        self.closeVirtualKeyboard()

        self['info'].setText(_('Searching through programs...'))
        self.results = []
        query_lower = self.query.lower()

        self.show()

        try:
            # Search all program categories
            for category in self.program_categories:
                programs = self.api.getOnDemandCategory(category['url'])
                for program in programs:
                    title = program.get('name', '').lower()
                    if query_lower in title:
                        # Prepare the program URL
                        program_url = self.api.prepare_url(
                            program.get('url', ''))

                        self.results.append({
                            'title': program['name'],
                            'url': program_url,
                            'icon': program.get('icon', self.api.DEFAULT_ICON_URL),
                            'sub-type': program.get('sub-type', '')
                        })

            if not self.results:
                self['info'].setText(_('No programs found for: ') + self.query)
            else:
                self['info'].setText(_('Found {0} programs for: {1}').format(
                    len(self.results), self.query))

            self.names = [result['title'] for result in self.results]
            self.icons = [result['icon'] for result in self.results]

            show_list(self.names, self['text'])
            self['text'].instance.moveSelectionTo(0)
            self.updatePoster()
            self.selectionChanged()

        except Exception as e:
            print("[DEBUG]Search error: " + str(e))
            self['info'].setText(_('Search error. Please try again.'))

    def closeVirtualKeyboard(self):
        """Close any open virtual keyboards"""
        for screen in self.session.dialog_stack[:]:
            if isinstance(screen, VirtualKeyBoard):
                try:
                    screen.close()
                except BaseException:
                    pass

    def okRun(self):
        """Handle selection of a search result"""
        if not self.results:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.results):
            return

        result = self.results[idx]
        self.session.open(
            RaiPlayOnDemandCategory,
            result['title'],
            result['url'],
            result['sub-type']
        )


class TvInfoBarShowHide():
    """ InfoBar show/hide control, accepts toggleShow and hide actions, might start
    fancy animations. """
    STATE_HIDDEN = 0
    STATE_HIDING = 1
    STATE_SHOWING = 2
    STATE_SHOWN = 3
    skipToggleShow = False

    def __init__(self):
        self["ShowHideActions"] = ActionMap(["InfobarShowHideActions"], {
            "toggleShow": self.OkPressed,
            "hide": self.hide
        }, 0)

        self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evStart: self.serviceStarted
        })
        self.__state = self.STATE_SHOWN
        self.__locked = 0

        self.helpOverlay = Label("")
        self.helpOverlay.skinAttributes = [
            ("position", "0,0"),
            ("size", "1280,50"),
            ("font", "Regular;28"),
            ("halign", "center"),
            ("valign", "center"),
            ("foregroundColor", "#FFFFFF"),
            ("backgroundColor", "#666666"),
            ("transparent", "0"),
            ("zPosition", "100")
        ]

        self["helpOverlay"] = self.helpOverlay
        self["helpOverlay"].hide()

        self.hideTimer = eTimer()
        try:
            self.hideTimer_conn = self.hideTimer.timeout.connect(
                self.doTimerHide)
        except BaseException:
            self.hideTimer.callback.append(self.doTimerHide)
        self.hideTimer.start(5000, True)
        self.onShow.append(self.__onShow)
        self.onHide.append(self.__onHide)

    def show_help_overlay(self):
        help_text = (
            "OK = Info | INFO = CYCLE STREAM | PLAY/PAUSE = Toggle | STOP = Stop | EXIT = Exit"
        )
        self["helpOverlay"].setText(help_text)
        self["helpOverlay"].show()

        self.help_timer = eTimer()
        self.help_timer.callback.append(self.hide_help_overlay)
        self.help_timer.start(5000, True)

    def hide_help_overlay(self):
        self["helpOverlay"].hide()

    def OkPressed(self):
        if self["helpOverlay"].visible:
            self.help_timer.stop()
            self.hide_help_overlay()
        else:
            self.show_help_overlay()
        self.toggleShow()

    def __onShow(self):
        self.__state = self.STATE_SHOWN
        self.startHideTimer()

    def __onHide(self):
        self.__state = self.STATE_HIDDEN

    def serviceStarted(self):
        if self.execing and config.usage.show_infobar_on_zap.value:
            self.doShow()

    def startHideTimer(self):
        if self.__state == self.STATE_SHOWN and not self.__locked:
            self.hideTimer.stop()
            self.hideTimer.start(5000, True)

    def doShow(self):
        self.hideTimer.stop()
        self.show()
        self.startHideTimer()

    def doTimerHide(self):
        self.hideTimer.stop()
        if self.__state == self.STATE_SHOWN:
            self.hide()

    def toggleShow(self):
        if not self.skipToggleShow:
            if self.__state == self.STATE_HIDDEN:
                self.show()
                self.hideTimer.stop()
                self.show_help_overlay()

            else:
                self.hide()
                self.startHideTimer()

                if self["helpOverlay"].visible:
                    self.help_timer.stop()
                    self.hide_help_overlay()
        else:
            self.skipToggleShow = False

    def lockShow(self):
        try:
            self.__locked += 1
        except BaseException:
            self.__locked = 0
        if self.execing:
            self.show()
            self.hideTimer.stop()
            self.skipToggleShow = False

    def unlockShow(self):
        try:
            self.__locked -= 1
        except BaseException:
            self.__locked = 0
        if self.__locked < 0:
            self.__locked = 0
        if self.execing:
            self.startHideTimer()

    def debug(self, obj, text=""):
        print(text + " %s\n" % obj)


class Playstream2(
        Screen,
        InfoBarMenu,
        InfoBarBase,
        InfoBarSeek,
        InfoBarNotifications,
        InfoBarAudioSelection,
        TvInfoBarShowHide,
        InfoBarSubtitleSupport):

    STATE_IDLE = 0
    STATE_PLAYING = 1
    STATE_PAUSED = 2
    ENABLE_RESUME_SUPPORT = True
    ALLOW_SUSPEND = True
    screen_timeout = 5000

    def __init__(self, session, name, url):
        Screen.__init__(self, session)
        self.session = session
        self.skinName = 'MoviePlayer'
        self.api = RaiPlayAPI()
        self.name = name
        self.url = url
        self.state = self.STATE_PLAYING
        self.allowPiP = False
        self.service = None
        self.license_key = None
        self.servicetype = '4097'
        for base in [
            InfoBarMenu, InfoBarNotifications, InfoBarBase,
            TvInfoBarShowHide, InfoBarAudioSelection, InfoBarSubtitleSupport
        ]:
            base.__init__(self)

        InfoBarSeek.__init__(self, actionmap='InfobarSeekActions')
        self["actions"] = ActionMap(
            [
                "WizardActions",
                "MoviePlayerActions",
                "MovieSelectionActions",
                "MediaPlayerActions",
                "EPGSelectActions",
                "MediaPlayerSeekActions",
                "ColorActions",
                "ButtonSetupActions",
                "InfobarShowHideActions",
                "InfobarActions",
                "InfobarSeekActions"
            ],
            {
                "leavePlayer": self.cancel,
                "epg": self.showIMDB,
                "info": self.cycleStreamType,
                "tv": self.cycleStreamType,
                "stop": self.leavePlayer,
                "cancel": self.cancel,
                "back": self.cancel,
                "playpauseService": self.playpauseService
            },
            -1
        )
        self.srefInit = self.session.nav.getCurrentlyPlayingServiceReference()
        self.onFirstExecBegin.append(self.startPlayback)

    def startPlayback(self):
        """Start playback with the appropriate method"""
        try:
            print("[DEBUG][Player] Starting: {}".format(self.name))
            print("[DEBUG][Player] URL: {}".format(self.url))

            # If the URL is a relinker, extract URL and license key
            if 'relinkerServlet' in self.url:
                self.url, self.license_key = self.api.process_relinker(
                    self.url)
                print("[DEBUG][Player] Processed URL: {}".format(self.url))
                print(
                    "[DEBUG][Player] DRM: {}".format(
                        self.license_key is not None))

            # If Widevine DRM content
            if self.license_key:
                if not check_widevine_ready():
                    print(
                        "[Player] Widevine not ready or installed, trying to install...")
                """
                # h = Helper(protocol="mpd", drm="widevine")
                # if not h.check_inputstream():
                    # print("[DEBUG][Player] Widevine not ready or installed, trying to install...")
                    # if not h.install_widevine():
                        # raise Exception("Widevine installation failed")
                # At this point Widevine is ready
                """
                print("[DEBUG][Player] Using ServiceApp for DRM playback")
                self.play_with_serviceapp()
                return

            if is_serviceapp_available():
                print("[DEBUG][Player] Using ServiceApp for playback")
                self.use_serviceapp()
            else:
                print("[DEBUG][Player] Using standard playback")
                self.use_standard_method()

        except Exception as e:
            error_msg = "Playback error: {}".format(str(e))
            print("[DEBUG][Player] {}".format(error_msg))
            self.show_error(error_msg)

    def play_with_serviceapp(self):
        """DRM playback with ServiceApp"""
        try:
            print("[DEBUG][ServiceApp-DRM] Starting playback: {}".format(self.url))

            if not self.license_key:
                raise ValueError("License key is missing")

            ref = eServiceReference(4097, 0, self.url)
            ref.setName(self.name)

            ref.setData(0, 4097)  # Service type
            ref.setData(1, 0)     # Flags

            # Try passing license key in different formats
            license_passed = False
            for data_format, data_value in [
                ("string", self.license_key),
                ("int", None),
                ("bytes", None),
            ]:
                try:
                    if data_format == "int":
                        data_value = int(self.license_key)
                    elif data_format == "bytes":
                        data_value = bytearray(self.license_key, "utf-8")

                    ref.setData(2, data_value)
                    print("[DEBUG]License passed as {}".format(data_format))
                    license_passed = True
                    break  # Stop at first success
                except Exception as e:
                    print(
                        "Error passing license as {}: {}".format(
                            data_format, e))

            if not license_passed:
                raise RuntimeError("Failed to pass license key to ServiceRef")

            print("[DEBUG][ServiceApp-DRM] ServiceRef: {}".format(ref.toString()))

            self.session.nav.stopService()
            self.session.nav.playService(ref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[DEBUG][ServiceApp-DRM] Playback started")

        except Exception as e:
            error_msg = "ServiceApp DRM error: " + str(e)
            print("[DEBUG][Player] {}".format(error_msg))
            self.show_error(error_msg)

    def use_serviceapp(self):
        """Standard playback with ServiceApp"""
        try:
            print("[DEBUG][ServiceApp] Playing: {}".format(self.url))

            ref = eServiceReference(4097, 0, self.url)
            ref.setName(self.name)

            print("[DEBUG][ServiceApp] ServiceRef: {}".format(ref.toString()))

            self.session.nav.stopService()
            self.session.nav.playService(ref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[DEBUG][ServiceApp] Playback started")

        except Exception as e:
            error_msg = "ServiceApp error: {}".format(str(e))
            print("[DEBUG][Player] {}".format(error_msg))
            self.show_error(error_msg)

    def use_standard_method(self):
        """Standard playback without ServiceApp"""
        try:
            print("[DEBUG][Standard] Playing: {}".format(self.url))

            # Format URL for standard playback
            if '://' in self.url:
                url = self.url.replace(':', '%3a').replace(' ', '%20')
                ref = "4097:0:1:0:0:0:0:0:0:0:{}".format(url)
            else:
                ref = self.url

            sref = eServiceReference(ref)
            sref.setName(self.name)

            print("[DEBUG][Standard] ServiceRef: {}".format(sref.toString()))

            self.session.nav.stopService()
            self.session.nav.playService(sref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[DEBUG][Standard] Playback started")

        except Exception as e:
            error_msg = "Standard playback error: {}".format(str(e))
            print("[DEBUG][Player] {}".format(error_msg))
            self.show_error(error_msg)

    def openTest(self, servicetype, url):
        url = url.replace(':', '%3a').replace(' ', '%20')
        ref = str(servicetype) + ':0:1:0:0:0:0:0:0:0:' + str(url)
        print('final reference 2:   ', ref)
        sref = eServiceReference(ref)
        sref.setName(self.name)
        self.session.nav.stopService()
        self.session.nav.playService(sref)

        self.show()
        self.state = self.STATE_PLAYING
        if self.state == self.STATE_PLAYING:
            self.show_help_overlay()

    def cycleStreamType(self):
        stream_types = ["4097", "5002", "5001", "8192"]
        # Get current type
        current_type = self.servicetype
        # Find next type
        try:
            idx = stream_types.index(current_type)
            next_idx = (idx + 1) % len(stream_types)
            self.servicetype = stream_types[next_idx]
        except ValueError:
            self.servicetype = "4097"
        print("[DEBUG]Switching stream type to: {}".format(self.servicetype))
        self.openTest(self.servicetype, self.url)

    def playpauseService(self):
        """Toggle play/pause"""
        service = self.session.nav.getCurrentService()
        if not service:
            print("[WARNING] No current service")
            return

        pauseable = service.pause()
        if pauseable is None:
            print("[WARNING] Service is not pauseable")
            # Instead of failing, just stop and restart the service
            if self.state == self.STATE_PLAYING:
                current_ref = self.session.nav.getCurrentlyPlayingServiceReference()
                if current_ref:
                    self.session.nav.stopService()
                    self.state = self.STATE_PAUSED
                    print("[DEBUG]Info: Playback stopped (pause not supported)")
            elif self.state == self.STATE_PAUSED:
                current_ref = self.session.nav.getCurrentlyPlayingServiceReference()
                if current_ref:
                    self.session.nav.playService(current_ref)
                    self.state = self.STATE_PLAYING
                    print("[DEBUG]Info: Playback resumed (pause not supported)")
            return

        try:
            if self.state == self.STATE_PLAYING:
                if hasattr(pauseable, "pause"):
                    pauseable.pause()
                    self.state = self.STATE_PAUSED
                    print("[DEBUG]Info: Playback paused")
            elif self.state == self.STATE_PAUSED:
                if hasattr(pauseable, "play"):
                    pauseable.play()
                    self.state = self.STATE_PLAYING
                    print("[DEBUG]Info: Playback resumed")
        except Exception as e:
            print("[ERROR]: Play/pause error: " + str(e))
            self.show_error(_("Play/pause not supported for this stream"))

    def show_error(self, message):
        """Show error message and close player"""
        self.session.openWithCallback(
            self.leavePlayer,
            MessageBox,
            message,
            MessageBox.TYPE_ERROR,
            timeout=5
        )

    def showIMDB(self):
        """Show IMDB/TMDB information"""
        returnIMDB(self.session, self.name)

    def showVideoInfo(self):
        if self.shown:
            self.hideInfobar()
        if self.infoCallback is not None:
            self.infoCallback()
        return

    def showAfterSeek(self):
        if isinstance(self, TvInfoBarShowHide):
            self.doShow()

    def cancel(self, *args):
        if exists('/tmp/hls.avi'):
            remove('/tmp/hls.avi')
        self.session.nav.stopService()
        if self.srefInit:
            self.session.nav.playService(self.srefInit)
        aspect_manager.restore_aspect()
        self.close()

    def leavePlayer(self, *args):
        self.session.nav.stopService()
        if self.srefInit:
            self.session.nav.playService(self.srefInit)
        self.close()


# ================================
# IMPROVED DOWNLOAD MANAGER
# ================================


class RaiPlayDownloadManagerScreen(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'downloads.xml')
        # skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False

        if not hasattr(session, 'download_manager'):
            session.download_manager = RaiPlayDownloadManager(session)

        self.download_manager = session.download_manager
        self.update_timer = eTimer()
        self.update_timer.callback.append(self.updateList)
        self.selected_item = None

        self['poster'] = Pixmap()
        self['info'] = Label(_('Download Manager'))
        self['title'] = Label(_("Download Manager"))
        self['key_red'] = Label(_("Back"))
        self['key_green'] = Label("")
        self['key_yellow'] = Label("")
        self['key_blue'] = Label("")
        self['text'] = MenuList([], enableWrapAround=True)

        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions'], {
            'ok': self.toggleDownload,
            'cancel': self.close,
            'red': self.close,
            'green': self.startStopDownload,
            'yellow': self.removeDownload,
            # 'blue': self.openMenu
        }, -2)

        self.onLayoutFinish.append(self.onStart)
        self.onClose.append(self.onCloseScreen)

    def onStart(self):
        """Initialize screen with slower updates"""
        self.update_timer.start(5000)  # 5 seconds instead of 3000
        self.updateList()
        self.updateButtons()

    def fix_existing_errors(self):
        """Automatically repair download errors on startup"""
        queue = self.download_manager.get_queue()
        for item in queue:
            if item['status'] == 'error':
                print(f"[DOWNLOAD MANAGER] Auto-fixing error: {item['title']}")
                self.download_manager.fix_error_status(item['id'])

    def close(self, *args, **kwargs):
        """Override close method with safe handling"""
        print("[DEBUG][SafeScreen] Closing " + self.__class__.__name__)

        # DON'T stop the worker - it causes deadlocks
        # if hasattr(self.session, 'download_manager'):
        #     self.session.download_manager.stop_worker()  # COMMENT THIS

        self.cleanup()
        deletetmp()
        self.restore_state()
        super(SafeScreen, self).close(*args, **kwargs)

    def onCloseScreen(self):
        """Cleanup on screen close"""
        print("[DOWNLOAD MANAGER] onCloseScreen called")
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
            print("[DOWNLOAD MANAGER] Update timer stopped")

    def updateList(self):
        """Update download list with throttling"""
        if hasattr(self, '_last_update') and time.time() - self._last_update < 5:
            return  # Skip if less than 5 seconds passed

        self._last_update = time.time()
        print("[DOWNLOAD MANAGER] Updating list...")

        # Update progress from file size (less frequently)
        if hasattr(self, '_last_progress_update') and time.time() - self._last_progress_update > 10:
            self.download_manager.update_progress_from_filesize()
            self._last_progress_update = time.time()

        queue = self.download_manager.get_queue()  # This now returns read-only copy
        print(f"[DOWNLOAD MANAGER] Got {len(queue)} items from queue")

        self.names = []
        self.items = queue

        if not queue:
            self.names.append(_("No downloads in queue"))
            print("[DOWNLOAD MANAGER] No downloads in queue")
        else:
            for i, item in enumerate(queue):
                print(
                    f"[DOWNLOAD MANAGER] Item {i}: {item['title']} - {item['status']}")
                status_icons = {
                    'queued': '⏳',
                    'waiting': '⏱️',
                    'downloading': '⬇️',
                    'paused': '⏸️',
                    'completed': '✅',
                    'error': '❌'
                }

                icon = status_icons.get(item['status'], '❓')

                # Progress and size info
                progress_text = " - {}%".format(item['progress']) if item['status'] in ['downloading', 'waiting', 'completed'] else ""

                size_info = ""
                if item['downloaded_bytes'] > 0:
                    size_mb = item['downloaded_bytes'] / (1024 * 1024)
                    if item['file_size'] > 0:
                        total_mb = item['file_size'] / (1024 * 1024)
                        size_info = f" - {size_mb:.1f}/{total_mb:.1f}MB"
                    else:
                        size_info = f" - {size_mb:.1f}MB"

                # Status text
                status_text = _(item['status'].capitalize())
                name = "{} {}{}{} [{}]".format(icon, item['title'], progress_text, size_info, status_text)
                self.names.append(name)

        self['text'].setList(self.names)
        self.updateStatusInfo()
        self.updateButtons()

    def updateStatusInfo(self):
        """Update status information"""
        queue = self.download_manager.get_queue()
        if not queue:
            self['info'].setText(_("No downloads"))
            return

        total = len(queue)
        active = self.download_manager.get_active_count()
        queued = self.download_manager.get_queued_count()
        completed = len(
            [item for item in queue if item['status'] == 'completed'])
        errors = len([item for item in queue if item['status'] == 'error'])

        # Get disk space
        free_space, total_space = self.download_manager.get_disk_space()

        stats = _("Total: {total} | Active: {active} | Queued: {queued} | Completed: {completed} | Errors: {errors}").format(
            total=total, active=active, queued=queued, completed=completed, errors=errors)

        disk_info = _("Free Space: {free} of {total}").format(
            free=free_space, total=total_space
        )

        self['info'].setText(f"{stats}\n{disk_info}")

    def updateButtons(self):
        """Update button labels based on selection"""
        idx = self["text"].getSelectionIndex()
        if idx is None or not self.items or idx >= len(self.items):
            self['key_green'].setText("")
            self['key_yellow'].setText("")
            self['key_blue'].setText("")
            return

        item = self.items[idx]
        status = item['status']

        if status in ['queued', 'paused', 'error']:
            self['key_green'].setText(_("Start"))
        elif status in ['downloading', 'waiting']:
            self['key_green'].setText(_("Stop"))
        else:
            self['key_green'].setText("")

        self['key_yellow'].setText(_("Remove"))

    def toggleDownload(self):
        """Handle OK button press"""
        idx = self["text"].getSelectionIndex()
        if idx is None or not self.items or idx >= len(self.items):
            return

        item = self.items[idx]
        self.selected_item = item

        if item['status'] == 'completed':
            self.playDownloadedFile(item)
        else:
            self.startStopDownload()

    def startStopDownload(self):
        """Start or stop selected download"""
        idx = self["text"].getSelectionIndex()
        if idx is None or not self.items or idx >= len(self.items):
            return

        item = self.items[idx]
        print("[DOWNLOAD MANAGER] startStopDownload - Current status: {}".format(item['status']))

        if item['status'] == 'paused':
            print("[DOWNLOAD MANAGER] Starting paused download: {}".format(item['title']))
            # Start download directly
            self.download_manager.start_download(item)
            self.session.open(
                MessageBox,
                _("Download started: {}").format(item['title']),
                MessageBox.TYPE_INFO,
                timeout=5)

        elif item['status'] == 'queued':
            print("[DOWNLOAD MANAGER] Starting queued download: {}".format(item['title']))
            # Start download directly
            self.download_manager.start_download(item)
            self.session.open(
                MessageBox,
                _("Download started: {}").format(item['title']),
                MessageBox.TYPE_INFO,
                timeout=5)

        elif item['status'] in ['downloading', 'waiting']:
            print("[DOWNLOAD MANAGER] Stopping active download: {}".format(item['title']))
            self.download_manager.pause_download(item['id'])
            self.session.open(
                MessageBox,
                _("Download stopped: {}").format(
                    item['title']),
                MessageBox.TYPE_INFO,
                timeout=5)

        self.updateList()

    def cleanup_queue(self):
        """Clean duplicate and error downloads from queue"""
        unique_downloads = []
        seen_titles = set()

        for item in self.download_manager.download_queue:
            # Keep only first occurrence of each title
            if item['title'] not in seen_titles:
                unique_downloads.append(item)
                seen_titles.add(item['title'])

        self.download_manager.download_queue = unique_downloads
        self.download_manager.save_downloads()
        self.updateList()

        self.session.open(MessageBox, "Clean queue from duplicates", MessageBox.TYPE_INFO, timeout=3)

    def removeDownload(self):
        """Remove selected download with enhanced confirmation"""
        idx = self["text"].getSelectionIndex()
        if idx is None or not self.items or idx >= len(self.items):
            return

        item = self.items[idx]

        if item['status'] in ['downloading', 'waiting']:
            self.session.open(
                MessageBox,
                _("Stop the download first before removing"),
                MessageBox.TYPE_WARNING,
                timeout=3
            )
            return

        self.session.openWithCallback(
            lambda result: self.removeDownloadConfirmed(result, item),
            MessageBox,
            _("Remove download: {}?").format(item['title']),
            MessageBox.TYPE_YESNO
        )

    def removeDownloadConfirmed(self, result, item):
        """Confirm and remove download"""
        if result:
            self.download_manager.remove_download(item['id'])
            self.updateList()
            self.session.open(MessageBox, _(f"Download removed: {str(item['title'])}"), MessageBox.TYPE_INFO, timeout=5)

    def playDownloadedFile(self, item):
        """Play downloaded file"""
        if exists(item['file_path']):
            try:
                local_url = f"file://{item['file_path']}"
                self.session.open(Playstream2, item['title'], local_url)
            except Exception as e:
                self.session.open(
                    MessageBox,
                    _("Error playing file: {}").format(str(e)),
                    MessageBox.TYPE_ERROR,
                    timeout=5
                )
        else:
            self.session.open(
                MessageBox,
                _("File not found: {}").format(item['file_path']),
                MessageBox.TYPE_ERROR,
                timeout=5
            )

    def test_download_function(self):
        """Test method to verify download functionality"""
        test_url = "https://www.raiplay.it/video/2020/11/The-End-Linferno-fuori-694ee472-d5a6-4684-9297-34c772e1ba17.html"
        test_title = "Test Download"

        if hasattr(self.session, 'download_manager'):
            result = self.session.download_manager.add_download(
                test_title, test_url)
            if result:
                self.session.open(
                    MessageBox,
                    _("Test download added to queue"),
                    MessageBox.TYPE_INFO,
                    timeout=5)
            else:
                self.session.open(
                    MessageBox,
                    _("Test download failed"),
                    MessageBox.TYPE_ERROR,
                    timeout=5)

    def handle_normal_selection(self, idx):
        """Override per compatibilità - non usato in questa schermata"""
        pass


class RaiPlayInfo(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'info.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.is_video_screen = False
        name = _('WELCOME TO RAI PLAY PLUGINS BY LULULLA')
        self['poster'] = Pixmap()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.close,
            'cancel': self.close
        }, -2)
        self.onLayoutFinish.append(self.finishLayout)

    def finishLayout(self):
        self.showHelp()

    def showHelp(self):
        help_lines = [
            "==============================",
            "     Rai Play View Plugin     ",
            "==============================",
            "",
            "Version: " + currversion,
            "Created by: Lululla",
            "License: CC BY-NC-SA 4.0",
            "",
            "------- Features -------",
            " • Access Rai Play content",
            " • Browse categories, programs, and videos",
            " • Play streaming video",
            " • JSON API integration",
            " • User-friendly interface",
            " • Download Manager with queue system",
            "",
            "------- Usage -------",
            " Press OK to play the selected video",
            " Press Back to return",
            " Use Download Manager to download videos",
            "",
            "Enjoy Rai Play streaming!",
            "",
            "If you like this plugin, consider",
            "buying me a coffee ☕",
            "Scan the QR code to support development",
            "It helps keep the plugin alive",
            "and updated. Thank you!",
            "",
            "bye bye Lululla"
        ]
        show_list(help_lines, self['text'])

    def handle_normal_selection(self, idx):
        self.close()


def main(session, **kwargs):
    try:
        # Initialize download manager
        if not hasattr(session, 'download_manager'):
            session.download_manager = RaiPlayDownloadManager(session)

        # Initialize notification system
        if NOTIFICATION_AVAILABLE:
            init_notification_system(session)
            print("[DEBUG] Notification system initialized")

        session.open(RaiPlayMain)
    except Exception as e:
        print("[ERROR] starting plugin:", str(e))
        traceback.print_exc()
        session.open(
            MessageBox,
            _("Error starting plugin"),
            MessageBox.TYPE_ERROR,
            timeout=5
        )


def Plugins(**kwargs):
    from Plugins.Plugin import PluginDescriptor
    ico_path = 'logo.png'
    if not exists('/var/lib/dpkg/status'):
        ico_path = plugin_path + '/res/pics/logo.png'
    extensions_menu = PluginDescriptor(
        name=name_plugin,
        description=desc_plugin,
        where=PluginDescriptor.WHERE_EXTENSIONSMENU,
        fnc=main,
        needsRestart=True)
    result = [
        PluginDescriptor(
            name=name_plugin,
            description=desc_plugin,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon=ico_path,
            fnc=main)]
    result.append(extensions_menu)
    return result

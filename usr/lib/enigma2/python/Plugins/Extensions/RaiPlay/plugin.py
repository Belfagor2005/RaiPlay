# -*- coding: utf-8 -*-
from __future__ import print_function

"""
#########################################################
#                                                       #
#  Rai Play View Plugin                                 #
#  Version: 1.5                                         #
#  Created by Lululla                                   #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0/   #
#  Last Modified: 15:14 - 2025-07-24                    #
#                                                       #
#  Features:                                            #
#    - Access Rai Play content                          #
#    - Browse categories, programs, and videos          #
#    - Play streaming video                             #
#    - JSON API integration                             #
#    - Debug logging                                    #
#    - User-friendly interface                          #
#    - Widevine DRM check for RaiPlay video playback    #
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


# Standard library
import codecs
import sys
from json import loads, dumps, load, dump
from os import remove, makedirs
from os.path import join, exists  # , getmtime
from re import search, match, findall, DOTALL, IGNORECASE  # , compile, escape
from datetime import date, datetime, timedelta
import requests
import html as _html
import threading
import time

# Enigma2 Components
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryPixmapAlphaTest, MultiContentEntryText
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from Components.config import config, ConfigSubsection, ConfigYesNo
from Components.Pixmap import Pixmap

# Enigma2 Screens
from Screens.InfoBarGenerics import (
    InfoBarAudioSelection,
    InfoBarMenu,
    InfoBarNotifications,
    InfoBarSeek,
    InfoBarSubtitleSupport,
)
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard

# Enigma2 Tools
from Tools.Directories import SCOPE_PLUGINS, resolveFilename
import traceback
try:
    from Components.AVSwitch import AVSwitch
except ImportError:
    from Components.AVSwitch import eAVControl as AVSwitch

from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from twisted.web.client import downloadPage

# Enigma2 enigma
from enigma import (
    RT_HALIGN_LEFT,
    RT_VALIGN_CENTER,
    eListboxPythonMultiContent,
    eServiceReference,
    eTimer,
    gFont,
    getDesktop,
    iPlayableService,
    loadPNG,
    ePicLoad,

)

# Local imports
from . import _
from . import Utils
from .Utils import RequestAgent
from .lib.html_conv import html_unescape
from .lib.helpers.helper import Helper
# from html import unescape as html_unescape  # test


import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEBUG_MODE = False


def getUrlSiVer(url, verify=True):
    """Fetch URL content with optional SSL verification"""
    try:
        headers = {'User-Agent': RequestAgent()}
        response = requests.get(
            url,
            headers=headers,
            timeout=10,
            verify=verify)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print("Error fetching URL " + str(url) + ": " + str(e))
        return None


def debug_log(message):
    if DEBUG_MODE:
        print(message)


def check_widevine_ready():
    h = Helper(protocol="mpd", drm="widevine")
    if not h.check_inputstream():
        # show error message or trigger installation
        # h = Helper("mpd", drm="widevine")
        # h._update_widevine()
        print("Widevine not installed or not working")
        # You can call h.install_widevine() if you want to force installation
        return False
    return True


config.plugins.raiplay = ConfigSubsection()
config.plugins.raiplay.debug = ConfigYesNo(default=False)


aspect_manager = Utils.AspectManager()

PY3 = False
PY3 = sys.version_info.major >= 3
if sys.version_info >= (2, 7, 9):
    try:
        import ssl
        sslContext = ssl._create_unverified_context()
    except BaseException:
        sslContext = None

currversion = '1.5'
plugin_path = '/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay'
DEFAULT_ICON = join(plugin_path, "res/pics/icon.png")
pluglogo = join(plugin_path, "res/pics/logo.png")
png_tg1 = join(plugin_path, "res/pics/tg1.png")
png_tg2 = join(plugin_path, "res/pics/tg2.png")
png_tg3 = join(plugin_path, "res/pics/tg3.png")
png_sport = join(plugin_path, "res/pics/rai_sports.png")
png_search = join(plugin_path, "res/pics/search_rai.png")
png_tgr = join(plugin_path, "res/pics/tgr.png")
png_tgd = join(plugin_path, "res/pics/tgdialogo.png")
png_tgm = join(plugin_path, "res/pics/tgmotori.png")
png_tv7 = join(plugin_path, "res/pics/tv7.png")
png_tgsp = join(plugin_path, "res/pics/tgsport.png")
png_tgec = join(plugin_path, "res/pics/tgeconomia.png")
png_tgmed = join(plugin_path, "res/pics/tgmedicina.png")
png_tgspec = join(plugin_path, "res/pics/tgspeciale.png")
png_tgpers = join(plugin_path, "res/pics/tgpersone.png")
png_tglib = join(plugin_path, "res/pics/tglibri.png")


desc_plugin = '..:: TiVu Rai Play by Lululla %s ::.. ' % currversion
name_plugin = 'TiVu Rai Play'
ntimeout = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"

screenwidth = getDesktop(0).size()
skin_path = join(plugin_path, "res/skins/")
if screenwidth.width() == 1920:
    skin_path = join(plugin_path, "res/skins/fhd/")
elif screenwidth.width() == 2560:
    skin_path = join(plugin_path, "res/skins/uhd/")

if not exists(join(skin_path, "settings.xml")):
    skin_path = join(plugin_path, "res/skins/hd/")
    print("Skin non trovata, uso il fallback:", skin_path)


def is_serviceapp_available():
    """Check if ServiceApp is installed"""
    return exists("/usr/lib/enigma2/python/Plugins/SystemPlugins/ServiceApp")


"""
mkdir -p /etc/serviceapp
# Create the configuration file
cat <<EOL > /etc/serviceapp/serviceapp.conf
[serviceapp]
enable=1
player=gstreamer
gst_audio=autoaudiosink
gst_video=autovideosink
http_port=8088
http_ip=0.0.0.0
use_alternate_audio_track=0
user_agent=Mozilla/5.0
EOL
"""

"""
# Global patch to disable summary screens completely
def disable_summary_screens():
    original_screen_init = Screen.__init__
    def new_screen_init(self, session, *args, **kwargs):
        # Disable summary screens for all screens
        self.hasSummary = False
        self.createSummary = lambda: None
        # Call original constructor
        original_screen_init(self, session, *args, **kwargs)
    Screen.__init__ = new_screen_init
disable_summary_screens()
"""


def returnIMDB(session, text_clear):
    """Show IMDB/TMDB information for the content"""
    text = html_unescape(text_clear)

    if Utils.is_TMDB and Utils.TMDB:
        try:
            session.open(Utils.TMDB.tmdbScreen, text, 0)
        except Exception as e:
            print("[XCF] TMDB error:", str(e))
        return True

    elif Utils.is_tmdb and Utils.tmdb:
        try:
            session.open(Utils.tmdb.tmdbScreen, text, 0)
        except Exception as e:
            print("[XCF] tmdb error:", str(e))
        return True

    elif Utils.is_imdb and Utils.imdb:
        try:
            Utils.imdb(session, text)
        except Exception as e:
            print("[XCF] IMDb error:", str(e))
        return True

    session.open(MessageBox, text, MessageBox.TYPE_INFO)
    return True


class strwithmeta(str):
    def __new__(cls, value, meta={}):
        # Create a new string instance
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
        print("HTTP error for {}: {}".format(page_url, e))
    except Exception as e:
        print("Error extracting video URL: {}".format(str(e)))

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
    if url.endswith(".html?json"):
        url = url.replace(".html?json", ".json")
    elif url.endswith("/?json"):
        url = url.replace("/?json", "/index.json")
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
                    500,
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
            print("Poster dimensions: " + str(self.poster_width) +
                  "x" + str(self.poster_height))

            try:
                self.picload.PictureData.get().append(self.setPoster)
            except BaseException:
                self.picload_conn = self.picload.PictureData.connect(
                    self.setPoster)

            self.screen_ready = True
        except Exception as e:
            print("Error initializing picload: " + str(e))
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
            print("Error in firstSelection:", str(e))
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
            print("Poster dimensions: %dx%d" %
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
        print(">>> get_state_params called - returning None by default")
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
            print("Error in selectionChanged: " + str(e))
            self.setFallbackPoster()

    def updatePoster(self):
        """Update the poster image according to the selected item."""
        if self.closing or not self.screen_ready:
            return

        try:
            if self.closing:
                print("Cannot update poster - screen closing")
                return

            if not hasattr(self, "icons") or not self.icons:
                print("No icons available, using default")
                self.setFallbackPoster()
                return
            idx = self["text"].getSelectionIndex()

            if idx is None or idx < 0 or idx >= len(self.icons):
                self.setFallbackPoster()
                return

            icon_url = self.icons[idx]
            print("Updating poster for index %d: %s" % (idx, str(icon_url)))

            if not icon_url or not isinstance(
                    icon_url, str) or not icon_url.startswith("http"):
                print("Using default icon - invalid URL:", icon_url)
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
            print("Error updating poster: " + str(e))
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
                print("Invalid index: %s (icons: %d)" %
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

    def playDirect(self, name, url):
        """Direct playback with provided URL."""
        try:
            url = normalize_url(url)
            url = strwithmeta(url, {
                'User-Agent': USER_AGENT,
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def infohelp(self):
        """Info for Plugin RaiPlay."""
        self.session.open(RaiPlayInfo)

    def cleanup(self):
        """Clean up resources and prepare screen for closure."""
        if self.closing:
            return
        self.closing = True

        try:
            if hasattr(self, 'pic_timer'):
                self.pic_timer.stop()

            if hasattr(self, 'picload'):
                del self.picload

            for attr in [
                'videos',
                'names',
                'urls',
                '_history',
                'items',
                    'blocks']:
                if attr in self.__dict__:
                    delattr(self, attr)

            import gc
            gc.collect()
        except Exception as e:
            print("Cleanup error: " + str(e))
            traceback.print_exc()

    def force_close(self):
        """Force close the screen if normal close fails."""
        if not self.closing and self.execing:
            print("Force closing screen due to timeout")
            try:
                self.close()
            except BaseException:
                print("Force close failed")
                for key in list(self.__dict__.keys()):
                    if key not in ['session', 'desktop', 'instance']:
                        delattr(self, key)
                try:
                    super(Screen, self).close()
                except BaseException:
                    pass

    def close(self, *args, **kwargs):
        """Override close method with safe handling."""
        self.cleanup()
        Utils.deletetmp()
        self.restore_state()
        super(SafeScreen, self).close(*args, **kwargs)

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

        self.CHANNELS_URL = "https://www.raiplay.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        self.CHANNELS_URL2 = "https://www.rai.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        self.CHANNELS_THEATRE = "https://www.raiplay.it/raiplay/tipologia/musica-e-teatro/index.json"
        self.EPG_URL = "https://www.rai.it/dl/palinsesti/Page-e120a813-1b92-4057-a214-15943d95aa68-json.html?canale={}&giorno={}"
        self.EPG_REPLAY_URL = "https://www.raiplay.it/palinsesto/app/old/{}/{}.json"

        self.TG_URL = "https://www.tgr.rai.it/dl/tgr/mhp/home.xml"

        # Raiplay RADIO
        # self.BASEURL = "https://www.raiplayradio.it/"
        self.CHANNELS_RADIO_URL = "https://www.raiplaysound.it/dirette.json"
        # self.NOTHUMB_RADIO_URL = "https://www.raiplayradio.it/dl/components/img/radio/player/placeholder_img.png"

        # Rai Sport urls
        self.RAISPORT_MAIN_URL = 'https://www.raisport.rai.it'
        self.RAISPORT_LIVE_URL = self.RAISPORT_MAIN_URL + '/dirette.html'
        self.RAISPORT_ARCHIVIO = self.RAISPORT_MAIN_URL + '/archivio.html'
        self.RAISPORT_ARCHIVIO_URL = 'https://www.rainews.it/notiziari/tgsport/archivio'
        self.RAISPORTDOMINIO = "RaiNews|Category-6dd7493b-f116-45de-af11-7d28a3f33dd2"
        self.RAISPORT_CATEGORIES_URL = "https://www.rainews.it/category/6dd7493b-f116-45de-af11-7d28a3f33dd2.json"
        self.RAISPORT_SEARCH_URL = "https://www.rainews.it/atomatic/news-search-service/api/v3/search"

        # # future work
        # PALINSESTO_URL_HTML = "https://www.raiplay.it/palinsesto/guidatv/lista/[idCanale]/[dd-mm-yyyy].html"
        # ON_AIR_URL = "https://www.raiplay.it/palinsesto/onAir.json"
        # RAIPLAY_AZ_TV_SHOW_PATH = "https://www.raiplay.it/dl/RaiTV/RaiPlayMobile/Prod/Config/programmiAZ-elenco.json"
        # RAIPLAY_AZ_RADIO_SHOW_PATH = "https://www.raiplay.it/dl/RaiTV/RaiRadioMobile/Prod/Config/programmiAZ-elenco.json"
        # PALINSESTO_URL = "https://www.raiplaysound.it/dl/palinsesti/Page-a47ba852-d24f-44c2-8abb-0c9f90187a3e-json.html?canale=[nomeCanale]&giorno=[dd-mm-yyyy]&mode=light"

        self.debug_dir = '/tmp/rainews_debug/'
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

    def getPage(self, url):
        """Fetch the content of a page from a URL using HTTP GET.
        """
        try:
            print("[DEBUG] Fetching URL: %s" % url)
            response = requests.get(
                url,
                headers=self.HTTP_HEADER,
                timeout=15,
                verify=False  # Disabilita verifica SSL
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

    def getMainMenu(self):
        """Retrieve the main menu data from RaiPlay menu URL.
        """
        data = Utils.getUrlSiVer(self.MENU_URL)
        if not data:
            return []

        try:
            response = loads(data)
            items = response.get("menu", [])
            result = []

            for item in items:
                if item.get("sub-type") in ("RaiPlay Tipologia Page",
                                            "RaiPlay Genere Page"):
                    icon_url = self.getThumbnailUrl2(item)
                    result.append({
                        'title': item.get("name", ""),
                        'url': self.getFullUrl(item.get("PathID", "")),
                        'icon': icon_url,
                        'sub-type': item.get("sub-type", "")
                    })
            return result
        except BaseException:
            return []

    def load_categories_cached(self):
        """Load RaiSport categories from a cache file if available, otherwise download and cache them.
        """
        if exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    print("[DEBUG] Loading categories from cache file")
                    data = load(f)
                    if DEBUG_MODE:
                        # Salva la struttura per debug
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
                # Salva la struttura per debug
                file_path = join(self.debug_dir, "raisport_categories.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    dump(data, f, indent=2, ensure_ascii=False)

            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                dump(data, f)
            return data
        except Exception as e:
            print("[ERROR] Failed to download categories JSON:", e)
            return None

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
            with open(self.debug_dir + "raw_json.txt", "w", encoding="utf-8") as f:
                raw_path = join(self.debug_dir, "raw_json.txt")

            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw_json)

            print(f"[DEBUG] Saved raw JSON -> {raw_path}")

            json_data = loads(raw_json)

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
            print("[getLiveRadioChannels] JSON parse error:", e)
            return []

    def getEPGDates(self):
        """Generate a list of dates (last 8 days) for EPG (Electronic Program Guide).
        """
        dates = []
        today = datetime.now()
        for i in range(8):  # Last 8 days
            date = today - timedelta(days=i)
            dates.append({
                'title': date.strftime("%A %d %B"),
                'date': date.strftime("%d-%m-%Y")
            })
        return dates

    def getEPGChannels(self, date):
        """Fetch EPG channels for a given date.
        """
        data = Utils.getUrlSiVer(self.CHANNELS_URL)
        if not data:
            return []

        try:
            response = loads(data)
            channels = response.get("dirette", [])
            result = []

            for channel in channels:
                result.append({
                    'title': channel.get("channel", ""),
                    'date': date,
                    'icon': self.getThumbnailUrl2(channel)
                })
            return result
        except BaseException:
            return []

    def get_programs(self, channel_api_name, date_api):
        """
        Retrieve the list of programs with video for the given channel and date.
        """
        url = self.EPG_REPLAY_URL.format(channel_api_name, date_api)
        try:
            data = Utils.getUrlSiVer(url)
            if not data:
                print("DEBUG: No data returned from URL:", url)
                return []

            response = loads(data)
            # Find matching channel key ignoring spaces
            channel_key = None
            for key in response.keys():
                if key.replace(" ", "") == channel_api_name:
                    channel_key = key
                    break

            if not channel_key:
                print("DEBUG: Channel key not found, fallback to first key")
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
            print("Error in get_programs:", str(e))
            return []

    def convert_old_url(self, old_url):
        print("[DEBUG] Converting old URL: " + str(old_url))
        if not old_url:
            return old_url

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

                exclude_names = {
                    "home", "tv guide / replay", "live", "login / register",
                    "recently watched", "my favorites", "watch later", "watch offline",
                    "tutorial", "faq", "contact us", "privacy policy",
                    "rai corporate", "privacy attività giornalistica", "cookie policy", "preferenze cookie",
                    "rai", "rainews", "raiplay sound", "rai cultura", "rai scuola",
                    "rai teche", "raiplay yoyo", "canone", "lavora con noi", "vai all'elenco completo",
                    "x", "facebook", "instagram", "login"  # , "raiplay"
                }

                # aggiungi anche i path not validi da escludere per evitare 404
                exclude_paths = {
                    "tipologia/guidatv",
                    "tipologia/dirette",
                    "tipologia/musica",
                    "user/login",
                    "user/ultimivisti",
                    "user/preferiti",
                    "user/guardadopo",
                    "aiuto",
                    "privacy/PrivacyPolicyRegistration"
                }

                if item.get("sub-type") in ("RaiPlay Tipologia Page",
                                            "RaiPlay Genere Page",
                                            "RaiPlay Tipologia Editoriale Page"):
                    name = item.get("name", "")
                    path_id = item.get("PathID", "").lower()

                    # escludi in base al nome
                    if name.lower() in exclude_names:
                        continue

                    # escludi se path_id contiene un segmento da escludere

                    if any(
                            exclude_path in path_id for exclude_path in exclude_paths):
                        continue

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

            # # Add search
            # result.append({
                # "title": "Search",
                # "url": "search",
                # "icon": '',
                # "sub-type": "search"
            # })

            return result
        except Exception as e:
            print("Error in getOnDemandMenu: " + str(e))
            return []

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
        """Prepare the URL using existing functions"""
        if not url:
            return ""

        url = self.convert_old_url(url)

        url = normalize_url(url)

        if url.startswith("https://www.raiplay.it//"):
            url = url.replace("//", "/", 1)
            url = "https://www.raiplay.it" + url

        return url

    def get_az_keys(self):
        """Generate all possible AZ keys including numbers and special characters"""
        keys = []
        # Add numbers
        keys.extend(str(i) for i in range(10))
        # Add letters A-Z
        keys.extend(chr(ord('A') + i) for i in range(26))
        # Add common special characters
        keys.extend(['#', '*', '&', '@'])
        return keys

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

    def is_valid_url(self, url):

        return isinstance(
            url, str) and url and (
            "http" in url or url.startswith("/")) and "[an error occurred" not in url

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
        print(">>> getThumbnailUrl2 - item keys:", item.keys())

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
            print(">>> Using image.media_url:", icon_url)
            return self.getThumbnailUrl(icon_url)

        # 2. transparent-icon
        if "transparent-icon" in item:
            icon_url = item["transparent-icon"]
            if "[an error occurred" not in icon_url:
                print(">>> Using transparent-icon:", icon_url)
                return self.getThumbnailUrl(icon_url)
            else:
                print(">>> Skipping invalid transparent-icon:", icon_url)

        # 3. chImage
        if "chImage" in item:
            ch_image_url = item["chImage"]
            print(">>> Using chImage:", ch_image_url)
            return self.getThumbnailUrl(ch_image_url)

        # 4. images dict (ordine originale)
        if "images" in item and isinstance(item["images"], dict):
            images = item["images"]
            print(">>> Available image keys:", images.keys())

            if "locandinaOrizzontale" in images:
                icon_url = full_url(images["locandinaOrizzontale"])
                print(">>> Using locandinaOrizzontale:", icon_url)
                return self.getThumbnailUrl(icon_url)
            elif "landscape" in images:
                print(">>> Using landscape:", images["landscape"])
                return self.getThumbnailUrl(images["landscape"])
            elif "landscape43" in images:
                print(">>> Using landscape43:", images["landscape43"])
                return self.getThumbnailUrl(images["landscape43"])
            elif "portrait" in images:
                print(">>> Using portrait:", images["portrait"])
                return self.getThumbnailUrl(images["portrait"])
            elif "portrait43" in images:
                print(">>> Using portrait43:", images["portrait43"])
                return self.getThumbnailUrl(images["portrait43"])
            elif "portrait_logo" in images:
                print(">>> Using portrait_logo:", images["portrait_logo"])
                return self.getThumbnailUrl(images["portrait_logo"])
            elif "square" in images:
                print(">>> Using square:", images["square"])
                return self.getThumbnailUrl(images["square"])
            elif "default" in images:
                print(">>> Using default:", images["default"])
                return self.getThumbnailUrl(images["default"])

        print(">>> No valid thumbnail found, using DEFAULT_ICON_URL")
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
            print("Error parsing program details: " + str(e))
            return None

    def getProgramItems(self, url):
        """Retrieve a list of program elements (episodes), including metadata and thumbnails."""
        # url = self.prepare_url(url)
        url = self.getFullUrl(url)
        data = Utils.getUrlSiVer(url)
        if not data:
            return []

        try:
            response = loads(data)
            items = response.get("items", [])
            result = []

            for item in items:
                icon_url = self.getThumbnailUrl2(item)
                video_info = {
                    'title': item.get("name", ""),
                    'subtitle': item.get("subtitle", ""),
                    'description': item.get("description", ""),
                    'url': item.get("pathID", ""),
                    'icon': icon_url,
                    'duration': item.get("duration", 0),
                    'date': item.get("date", "")
                }

                # For TV series: add season and episode info if present
                if "season" in item and "episode" in item:
                    video_info['season'] = item["season"]
                    video_info['episode'] = item["episode"]

                result.append(video_info)

            return result
        except BaseException:
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
            print("Error fetching TG archive: {}".format(str(e)))
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
            print("Error fetching TG content: {}".format(str(e)))
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
            print("Error getting sports categories:", str(e))
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
            print("Error getting sport subcategories:", str(e))
            traceback.print_exc()
            return []

    def find_category_by_unique_name(self, node, unique_name):
        """Helper function to find category by unique name"""
        if node.get("uniqueName") == unique_name:
            return node
        for child in node.get("children", []):
            result = self.find_category_by_unique_name(child, unique_name)
            if result:
                return result
        return None

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
            if config.plugins.raiplay.debug.value:
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

            print("[Relinker] Final URL: " + content_url)
            print("[Relinker] License key: " + str(license_key))
            return content_url, license_key

        except Exception as e:
            print("[Relinker] Error: " + str(e))
            return url, None

    def debug_images(self, item):
        """Log all possible image paths in an item for debugging"""
        print("\n[DEBUG] Starting image debug for item:")

        # 1. Log the full item structure first
        try:
            import json
            print("Full item structure:")
            print(json.dumps(item, indent=2, ensure_ascii=False))
        except BaseException:
            print("Could not serialize item for debug")

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
                print("Found image at '" + path + "': " + str(current))
                found_images.append(current)

        if not found_images:
            print("No images found in any known paths!")

        print("Total images found: " + str(len(found_images)) + "\n")
        return found_images


class RaiPlayMain(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)

        self.program_categories = []
        self.categories_loaded = False

        self.loading_counter = 0
        self.loading_timer = eTimer()

        self.loading_timer.callback.append(self.update_loading_status)
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(_("Rai Play Main"))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
            'ok': self.okRun,
            'cancel': self.close,
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
            (_("Programs"), "programs", "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"),
        ]
        categories += [(_("On Air Programs"), "on_air",
                        "https://www.rai.it/dl/img/2016/06/10/1465549191335_icon_live.png"), ]
        categories += [
            (_("Search"), "search", png_search)
        ]

        for name, url, icon in categories:
            self.names.append(name)
            self.urls.append(url)
            self.icons.append(icon)

        show_list(self.names, self['text'])
        self['info'].setText(_('Loading program data...'))

        self.loading_timer.start(1000, True)

        threading.Thread(target=self.load_program_categories).start()

        self.updatePoster()

        restored = self.restore_state()
        if restored:
            self["text"].moveToIndex(self.state_index)
        else:
            if self.names:
                self["text"].moveToIndex(0)
        self.selectionChanged()

    def load_program_categories(self):
        """Load categories synchronously"""
        try:
            raw_categories = self.api.getOnDemandMenu()
            self.program_categories = []

            for cat in raw_categories:
                # Prepara l'URL
                prepared_url = self.api.prepare_url(cat['url'])
                self.program_categories.append({
                    'title': cat['title'],
                    'url': prepared_url,
                    'icon': cat['icon'],
                    'sub-type': cat.get('sub-type', '')
                })

            self.categories_loaded = True

        except Exception as e:
            print("Error loading program categories: {}".format(str(e)))
            self.categories_loaded = True  # Considera comunque completato

    def update_loading_status(self):
        """Update upload status"""
        self.loading_counter += 1

        if self.categories_loaded:
            self['info'].setText(_('Loading complete! Select an option'))
            self.loading_timer.stop()
        else:
            status = _('Loading') + ' ' + ('.' *
                                           (self.loading_counter % 4)) + ' ' + _('Please wait!')
            self['info'].setText(status)
            self.loading_timer.start(1000, True)

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
            date_str = item.get('date', '')  # dovrebbe essere già formattata
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
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)


class RaiPlayLiveRadio(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)


class RaiPlayReplayDates(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        print("DEBUG: Converted date for API comparison:", date_api)

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
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        video_url = self.urls[idx]
        # print("DEBUG: Selected name:", name)
        # print("DEBUG: Original video_url:", video_url)
        if not video_url:
            print("DEBUG: Video URL is empty")
            self.session.open(
                MessageBox,
                _("Video URL not available"),
                MessageBox.TYPE_ERROR)
            return

        url = video_url
        if url is None or url.endswith(".json"):
            print("DEBUG: URL is invalid or ends with .json")
            self.session.open(
                MessageBox,
                _("Video not available or invalid URL"),
                MessageBox.TYPE_ERROR)
            return

        print("DEBUG: Launching playback for:", url)
        self.playDirect(name, url)


class RaiPlayReplayChannels(SafeScreen):
    def __init__(self, session, date_info):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
            print("DEBUG: No data returned from URL")
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

                if config.plugins.raiplay.debug.value:
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

            if config.plugins.raiplay.debug.value:
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
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        video = self.videos[idx]
        self.playDirect(video['title'], video['url'])


class RaiPlayOnDemandCategory(SafeScreen):
    def __init__(self, session, name, url, sub_type):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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

        elif sub_type == "PLR programma Page":
            program_data = self.api.getProgramDetails(url)
            if program_data:
                is_movie = False
                for typology in program_data['info'].get("typologies", []):
                    if typology.get("name") == "Film":
                        is_movie = True
                        break

                if is_movie and program_data['info'].get("first_item_path"):
                    self.playDirect(
                        name, program_data['info']["first_item_path"])
                else:
                    self.session.open(
                        RaiPlayProgramBlocks,
                        name,
                        program_data
                    )

        elif sub_type == "RaiPlay Video Item":
            # Direct play from okRun without intermediate screen
            pathId = self.api.getFullUrl(url)
            data = Utils.getUrlSiVer(pathId)
            if not data:
                self['info'].setText(_('Error loading video data'))
                return

            try:
                response = loads(data)
                video_url = response.get("video", {}).get("content_url", None)
                if video_url:
                    self.playDirect(name, video_url)
                else:
                    self['info'].setText(_('No video URL found'))
            except Exception:
                self['info'].setText(_('Error parsing video data'))

        else:
            self.session.open(RaiPlayOnDemandCategory, name, url, sub_type)


class RaiPlayOnDemandAZ(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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


class RaiPlayOnDemandProgram(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        Load the program details and prepare the UI for seasons or direct playback
        """
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrlSiVer(pathId)
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

            if program_info['is_movie'] and program_info['first_item_path']:
                # Open playback screen (replace Playstream1 with your player)
                self.playDirect(
                    program_info['name'],
                    program_info['first_item_path'])
                return

            # Otherwise show seasons or blocks
            items = []
            for block in response.get("blocks", []):
                for set_item in block.get("sets", []):
                    label = set_item.get("name", "")
                    if not label:
                        continue

                    # Extract season number if present (default 1)

                    season_match = search(
                        r"Stagione\s+(\d+)", label, IGNORECASE)
                    if season_match:
                        season = season_match.group(1)
                    else:
                        season = "1"

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
                        # Fallback to debug_images if no image found
                        icon_url = self.api.getThumbnailUrl2(set_item)

                    if config.plugins.raiplay.debug.value:
                        self.api.debug_images(set_item)

                    item_data = {
                        'name': label,
                        'url': set_item.get("path_id", ""),
                        'season': season,
                        'icon': icon_url,
                    }
                    items.append(item_data)

            if not items:
                self['info'].setText(_('No seasons available'))
                return

            self.items = items
            self.names = [item['name'] for item in items]
            show_list(self.names, self['text'])
            self['info'].setText(_('Select season'))

            restored = self.restore_state()
            if restored:
                self["text"].moveToIndex(self.state_index)
            else:
                if self.names:
                    self["text"].moveToIndex(0)
            self.selectionChanged()
        except Exception as e:
            print("Error loading program details: %s" % str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        item = self.items[idx]
        self.session.open(RaiPlayBlockItems, item['name'], item['url'])


class RaiPlayOnDemandProgramItems(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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

            if config.plugins.raiplay.debug.value:
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
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        video = self.videos[idx]
        self.playDirect(video['title'], video['url'])


class RaiPlayOnAir(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        url = "https://www.raiplay.it/palinsesto/onAir.json"
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
                time_str = f"[{channel_name}] {start_time} " if channel_name and start_time else ""

                # Get image
                icon = current_item.get("image", "")
                if icon and not icon.startswith("http"):
                    icon = "https://www.raiplay.it" + icon

                self.programs.append({
                    "title": f"{time_str}{title}",
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
            self.selectionChanged()

        except Exception as e:
            print("Error loading onAir data: " + str(e))
            self['info'].setText(_('Error loading data: {}').format(str(e)))

    def okRun(self):
        if not self.programs:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.programs):
            return

        program = self.programs[idx]
        self.playDirect(program["title"], program["url"])


class RaiPlayTG(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        self.channel = channel
        self.names = []
        self.urls = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(f"Rai {channel.upper()}")
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
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        if self.urls[idx] == "archive":
            # Open the full archive
            self.session.open(RaiPlayTGArchive, self.channel)
        else:
            # Play the selected edition
            video = {
                "title": self.names[idx],
                "url": self.urls[idx]
            }
            self.playDirect(video["title"], video["url"])


class RaiPlayTGArchive(SafeScreen):
    def __init__(self, session, channel):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.channel = channel
        self.current_page = 1
        self.total_pages = 1
        self.videos = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading data... Please wait'))
        self['title'] = Label(f"{channel.upper()} Archive")
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
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

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        video = self.videos[idx]

        # Prima prova con content_url diretto
        if video.get("content_url"):
            self.playDirect(video['title'], video['content_url'])
            return

        # Usa content_url se disponibile, altrimenti fallback alla pagina
        video_url = self.api.get_video_url_from_page(video['page_url'])
        if video_url:
            self.playDirect(video['title'], video_url)
        else:
            self.session.open(
                MessageBox,
                _("Could not retrieve video URL"),
                MessageBox.TYPE_ERROR
            )

    def nextPage(self):
        """Passa alla pagina successiva"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.loadData()

    def prevPage(self):
        """Torna alla pagina precedente"""
        if self.current_page > 1:
            self.current_page -= 1
            self.loadData()


class RaiPlayTGR(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        self.name = name
        self.url = url
        self.current_page = 1
        self.videos = []
        self['poster'] = Pixmap()
        self['info'] = Label(_('Loading archive...'))
        self['title'] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions', 'ChannelSelectEPGActions'], {
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
                        display_title = f"{dt.strftime('%d/%m/%Y')} - {display_title}"
                    except BaseException:
                        pass
                if video.get("duration"):
                    display_title += f" ({video['duration']})"

                self.names.append(display_title)

            show_list(self.names, self['text'])
            self['info'].setText(_('Select video'))

            if self.names:
                self["text"].moveToIndex(0)
            self.selectionChanged()

        except Exception as e:
            print("Error loading archive: " + str(e))
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
                print("Error parsing JSON archive: " + str(e))

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

    def okRun(self):
        if not self.videos:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.videos):
            return

        video = self.videos[idx]
        # Prefer content_url if available, otherwise use page_url
        if video.get("content_url"):
            self.playDirect(video['title'], video['content_url'])
        else:
            # Extract the video URL from the page
            self.extractAndPlay(video)

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
            print("Error extracting video URL: " + str(e))
            self['info'].setText(_('Error extracting video URL'))

    def nextPage(self):
        # These archives don't support pagination
        self['info'].setText(_('Pagination not supported for this archive'))

    def prevPage(self):
        # These archives don't support pagination
        self['info'].setText(_('Pagination not supported for this archive'))


class tgrRai2(SafeScreen):
    def __init__(self, session, name, url):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
            print(f'Error parsing TGR content: {str(e)}')
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
            print(f'Error parsing video content: {str(e)}')
            self['info'].setText(_('Error parsing data'))

    def okRun(self):
        if not self.names:
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.names):
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)


class RaiPlaySport(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        print("[Sport] Loading subcategories for: " + category['title'])
        self.navigation_stack.append({
            'type': 'category',
            'data': category
        })

        self.subcategories = self.api.getSportSubcategories(category['key'])
        print("[Sport] Found {} subcategories".format(len(self.subcategories)))

        if not self.subcategories:
            print("[Sport] No subcategories found, loading videos directly")
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
            print("[Sport] Loading ALL videos for key: " + str(self.key))
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
            print("[Sport] Total unique videos: " + str(len(unique_videos)))

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
                print("[Sport] Sorting error: " + str(e))

            self.all_videos = unique_videos
            self.total_pages = (len(self.all_videos) +
                                self.page_size - 1) // self.page_size

            # Show the first page
            self.showCurrentPage()
        except Exception as e:
            print("[Sport] Error loading videos: " + str(e))
            self.session.open(
                MessageBox,
                _("Error loading videos: ") + str(e),
                MessageBox.TYPE_ERROR
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
        if self.restore_state():
            self["text"].moveToIndex(self.state_index)
        else:
            self["text"].moveToIndex(0)

        # 8. Update poster
        self.updatePoster()

        # 9. Update status
        self['info'].setText(_('Select a video'))

    def get_video_icon(self, video):
        """Return the URL of the icon for a video"""
        images = video.get("images", {})

        for image_type in ["square", "landscape", "portrait", "default"]:
            if image_type in images and images[image_type]:
                return self.api.getFullUrl(images[image_type])

        return self.api.DEFAULT_ICON_URL

    def okRun(self):
        if not self.displayed_videos or self.displayed_videos[0].get(
                "is_empty"):
            return

        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.displayed_videos):
            return

        item = self.displayed_videos[idx]

        if item.get("is_page"):
            self.current_page = item["page"]
            self.showCurrentPage()

        else:
            self.playVideo(item)

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
                MessageBox.TYPE_ERROR
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


class RaiPlayPrograms(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
            print("Search error: " + str(e))
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
            print("[Player] Starting: {}".format(self.name))
            print("[Player] URL: {}".format(self.url))

            # If the URL is a relinker, extract URL and license key
            if 'relinkerServlet' in self.url:
                self.url, self.license_key = self.api.process_relinker(
                    self.url)
                print("[Player] Processed URL: {}".format(self.url))
                print("[Player] DRM: {}".format(self.license_key is not None))

            # If Widevine DRM content
            if self.license_key:
                if not check_widevine_ready():
                    print(
                        "[Player] Widevine not ready or installed, trying to install...")
                """
                # h = Helper(protocol="mpd", drm="widevine")
                # if not h.check_inputstream():
                    # print("[Player] Widevine not ready or installed, trying to install...")
                    # if not h.install_widevine():
                        # raise Exception("Widevine installation failed")
                # At this point Widevine is ready
                """
                print("[Player] Using ServiceApp for DRM playback")
                self.play_with_serviceapp()
                return

            if is_serviceapp_available():
                print("[Player] Using ServiceApp for playback")
                self.use_serviceapp()
            else:
                print("[Player] Using standard playback")
                self.use_standard_method()

        except Exception as e:
            error_msg = "Playback error: {}".format(str(e))
            print("[Player] {}".format(error_msg))
            self.show_error(error_msg)

    def play_with_serviceapp(self):
        """DRM playback with ServiceApp"""
        try:
            print("[ServiceApp-DRM] Starting playback: {}".format(self.url))

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
                    print("License passed as {}".format(data_format))
                    license_passed = True
                    break  # Stop at first success
                except Exception as e:
                    print(
                        "Error passing license as {}: {}".format(
                            data_format, e))

            if not license_passed:
                raise RuntimeError("Failed to pass license key to ServiceRef")

            print("[ServiceApp-DRM] ServiceRef: {}".format(ref.toString()))

            self.session.nav.stopService()
            self.session.nav.playService(ref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[ServiceApp-DRM] Playback started")

        except Exception as e:
            error_msg = "ServiceApp DRM error: " + str(e)
            print("[Player] {}".format(error_msg))
            self.show_error(error_msg)

    def use_serviceapp(self):
        """Standard playback with ServiceApp"""
        try:
            print("[ServiceApp] Playing: {}".format(self.url))

            ref = eServiceReference(4097, 0, self.url)
            ref.setName(self.name)

            print("[ServiceApp] ServiceRef: {}".format(ref.toString()))

            self.session.nav.stopService()
            self.session.nav.playService(ref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[ServiceApp] Playback started")

        except Exception as e:
            error_msg = "ServiceApp error: {}".format(str(e))
            print("[Player] {}".format(error_msg))
            self.show_error(error_msg)

    def use_standard_method(self):
        """Standard playback without ServiceApp"""
        try:
            print("[Standard] Playing: {}".format(self.url))

            # Format URL for standard playback
            if '://' in self.url:
                url = self.url.replace(':', '%3a').replace(' ', '%20')
                ref = "4097:0:1:0:0:0:0:0:0:0:{}".format(url)
            else:
                ref = self.url

            sref = eServiceReference(ref)
            sref.setName(self.name)

            print("[Standard] ServiceRef: {}".format(sref.toString()))

            self.session.nav.stopService()
            self.session.nav.playService(sref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[Standard] Playback started")

        except Exception as e:
            error_msg = "Standard playback error: {}".format(str(e))
            print("[Player] {}".format(error_msg))
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
        print("Switching stream type to: {}".format(self.servicetype))
        self.openTest(self.servicetype, self.url)

    def playpauseService(self):
        """Toggle play/pause"""
        service = self.session.nav.getCurrentService()
        if not service:
            print("Warning: No current service")
            return

        pauseable = service.pause()
        if pauseable is None:
            print("Warning: Service is not pauseable")
            # Instead of failing, just stop and restart the service
            if self.state == self.STATE_PLAYING:
                current_ref = self.session.nav.getCurrentlyPlayingServiceReference()
                if current_ref:
                    self.session.nav.stopService()
                    self.state = self.STATE_PAUSED
                    print("Info: Playback stopped (pause not supported)")
            elif self.state == self.STATE_PAUSED:
                current_ref = self.session.nav.getCurrentlyPlayingServiceReference()
                if current_ref:
                    self.session.nav.playService(current_ref)
                    self.state = self.STATE_PLAYING
                    print("Info: Playback resumed (pause not supported)")
            return

        try:
            if self.state == self.STATE_PLAYING:
                if hasattr(pauseable, "pause"):
                    pauseable.pause()
                    self.state = self.STATE_PAUSED
                    print("Info: Playback paused")
            elif self.state == self.STATE_PAUSED:
                if hasattr(pauseable, "play"):
                    pauseable.play()
                    self.state = self.STATE_PLAYING
                    print("Info: Playback resumed")
        except Exception as e:
            print("Error: Play/pause error: " + str(e))
            self.show_error(_("Play/pause not supported for this stream"))

    def show_error(self, message):
        """Show error message and close player"""
        self.session.openWithCallback(
            self.leavePlayer,
            MessageBox,
            message,
            MessageBox.TYPE_ERROR
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


class RaiPlayInfo(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'info.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
            "",
            "------- Usage -------",
            " Press OK to play the selected video",
            " Press Back to return",
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


def main(session, **kwargs):
    try:
        session.open(RaiPlayMain)
    except Exception as e:
        print("Error starting plugin:", str(e))
        traceback.print_exc()
        session.open(
            MessageBox,
            _("Error starting plugin"),
            MessageBox.TYPE_ERROR)


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

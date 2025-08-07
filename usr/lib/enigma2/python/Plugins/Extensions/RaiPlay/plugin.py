# -*- coding: utf-8 -*-
from __future__ import print_function

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


# Standard library
import codecs
import sys
from json import loads, dumps
from os import remove
from os.path import join, exists
from re import search, match, compile, findall, DOTALL, IGNORECASE
from datetime import date, datetime, timedelta
import requests

# Enigma2 Components
from Components.ActionMap import ActionMap
from Components.Button import Button
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

# Enigma2 Tools
from Tools.Directories import SCOPE_PLUGINS, resolveFilename
import traceback
try:
    from Components.AVSwitch import AVSwitch
except ImportError:
    from Components.AVSwitch import eAVControl as AVSwitch

# from six.moves.urllib.parse import urlparse
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
from .lib.html_conv import html_unescape


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

currversion = '1.3'
plugin_path = '/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay'
DEFAULT_ICON = join(plugin_path, "res/pics/icon.png")
pluglogo = join(plugin_path, "res/pics/logo.png")
pngx = join(plugin_path, "res/pics/plugins.png")
pngl = join(plugin_path, "res/pics/plugin.png")
pngs = join(plugin_path, "res/pics/setting.png")
png_sport = join(plugin_path, "res/pics/rai_sports.png")
png_search = join(plugin_path, "res/pics/search_rai.png")
png_tgr = join(plugin_path, "res/pics/tgr.png")
desc_plugin = '..:: TiVu Rai Play by Lululla %s ::.. ' % currversion
name_plugin = 'TiVu Rai Play'
ntimeout = 10

screenwidth = getDesktop(0).size()
skin_path = join(plugin_path, "res/skins/")
if screenwidth.width() == 1920:
    skin_path = join(plugin_path, "res/skins/fhd/")
elif screenwidth.width() == 2560:
    skin_path = join(plugin_path, "res/skins/uhd/")

if not exists(join(skin_path, "settings.xml")):
    skin_path = join(plugin_path, "res/skins/hd/")
    print("Skin non trovata, uso il fallback:", skin_path)


def is_openpli():
    """Verifica se siamo su un'immagine OpenPLi"""
    return exists('/usr/lib/enigma2/python/Plugins/PLi')


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
    """Mostra informazioni IMDB/TMDB per il contenuto"""
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
        obj = str.__new__(cls, value)
        obj.meta = {}
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
    """Extracts the real video URL from RaiPlay JSON page"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
            "Referer": "https://www.raiplay.it/"}
        response = requests.get(page_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        paths = [
            ["video", "content_url"],
            ["props", "pageProps", "contentItem", "video", "contentUrl"],
            ["props", "pageProps", "program", "video", "contentUrl"],
            ["props", "pageProps", "data", "items", 0, "video", "contentUrl"]
        ]

        for path in paths:
            current = data
            for key in path:
                if isinstance(key, int):
                    if isinstance(current, list) and len(current) > key:
                        current = current[key]
                    else:
                        current = None
                        break
                elif isinstance(current, dict):
                    current = current.get(key)
                else:
                    current = None
                    break
            if current:
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
        # name = data[icount]
        name = str(data[icount])
        plist.append(RaiPlaySetListEntry(name))
        icount += 1
        listas.setList(plist)


class SafeScreen(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.onClose.append(self.cleanup)
        self.closing = False
        self.last_index = -1

        # Initialize picload only once
        self.picload = ePicLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except BaseException:
            self.picload_conn = self.picload.PictureData.connect(
                self.setPoster)

        # Get poster widget dimensions
        self.poster_width = 390
        self.poster_height = 510
        self.onLayoutFinish.append(self.onLayoutFinished)
        self.onShown.append(self.firstSelection)

    def firstSelection(self):
        """Force refresh on first view"""
        try:
            if hasattr(self, "names") and len(self.names) > 0:
                self["text"].moveToIndex(0)
                self.selectionChanged()
        except Exception as e:
            print("Error in firstSelection:", str(e))

    def onLayoutFinished(self):
        try:
            size = self["poster"].instance.size()
            self.poster_width = size.width()
            self.poster_height = size.height()
            print("Poster dimensions: %dx%d" %
                  (self.poster_width, self.poster_height))
        except BaseException:
            pass

    def ensure_icons_list(self):
        """Ensure icons list exists and has proper length"""
        if not hasattr(self, "icons"):
            self.icons = []

        # Ensure we have at least as many icons as menu items
        if hasattr(self, "names") and len(self.icons) < len(self.names):
            # Fill missing icons with default
            self.icons += [DEFAULT_ICON] * (len(self.names) - len(self.icons))

    def selectionChanged(self):
        """Handle selection changes and update poster"""
        try:
            self.ensure_icons_list()
            current_index = self["text"].getSelectionIndex()
            print("Selection changed: %s -> %s" %
                  (str(self.last_index), str(current_index)))

            if current_index != self.last_index:
                self.last_index = current_index
                self.setPoster()
        except Exception as e:
            print("Error in selectionChanged: " + str(e))
            self.setFallbackPoster()

    def updatePoster(self):
        """Update poster based on current selection"""
        try:
            # Safety check 1: screen is closing
            if self.closing:
                print("Cannot update poster - screen closing")
                return

            # Safety check 2: icon list does not exist or is empty
            if not hasattr(self, "icons") or not self.icons:
                print("No icons available, using default")
                self.setFallbackPoster()
                return

            idx = self["text"].getSelectionIndex()

            # Safety check 3: invalid index
            if idx is None or idx < 0 or idx >= len(self.icons):
                print("Invalid index: %s (icons: %d)" %
                      (str(idx), len(self.icons)))
                self.setFallbackPoster()
                return

            icon_url = self.icons[idx]
            print("Updating poster for index %d: %s" % (idx, str(icon_url)))

            # URL handling
            final_url = icon_url
            if not final_url.startswith("http"):
                final_url = self.api.getFullUrl(
                    final_url) if hasattr(self, "api") else final_url

            # Safety check 4: invalid URL
            if not final_url or not final_url.startswith("http"):
                print("Using default icon - invalid URL:", final_url)
                # final_url = DEFAULT_ICON
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

            self.picload.startDecode(final_url)

        except Exception as e:
            print("Error updating poster: " + str(e))
            self.setFallbackPoster()

    def setPoster(self, data=None):
        """Callback when image is ready"""
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

            if self.pixim == DEFAULT_ICON:
                self.setFallbackPoster()
                return

            # Check if local path (ad esempio se inizia con plugin_path)
            if self.pixim.startswith(plugin_path):
                # Percorso locale, decodifica direttamente
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
        if exists(pictmp):
            try:
                self.decodeImage(pictmp)
            except Exception as e:
                print("* error ** %s" % e)

    def decodeImage(self, png):
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
        try:
            if self["poster"].instance:
                self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
                self['poster'].show()
            print('error download: ', error)
        except Exception as e:
            print('error downloadError poster', e)
            self.setFallbackPoster()

    def setFallbackPoster(self):
        """Set default poster when image loading fails"""
        try:
            self.picload.setPara((
                self.poster_width,
                self.poster_height,
                1, 1, False, 1, "#FF000000"
            ))
            self.picload.startDecode(DEFAULT_ICON)
        except BaseException:
            try:
                self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
            except BaseException:
                pass

    def cleanup(self):
        if self.closing:
            return
        self.closing = True

        try:
            if hasattr(self, 'pic_timer'):
                self.pic_timer.stop()
                # del self.pic_timer

            # if hasattr(self, 'picload') and self.has_poster:
            if hasattr(self, 'picload'):
                del self.picload

            # Clear common resources
            for attr in [
                'videos',
                'names',
                'urls',
                '_history',
                'items',
                    'blocks']:
                if hasattr(self, attr):
                    delattr(self, attr)

            import gc
            gc.collect()
        except Exception as e:
            print("Cleanup error: " + str(e))

    def force_close(self):
        """Force close if normal close fails"""
        if not self.closing and self.execing:
            print("Force closing screen due to timeout")
            try:
                self.close()
            except BaseException:
                print("Force close failed")
                # Last resort - delete references
                for key in list(self.__dict__.keys()):
                    if key not in ['session', 'desktop', 'instance']:
                        delattr(self, key)
                try:
                    super(Screen, self).close()
                except BaseException:
                    pass

    def close(self, *args, **kwargs):
        """Override close method with safe handling"""
        self.cleanup()
        super(SafeScreen, self).close(*args, **kwargs)


class RaiPlayAPI:
    def __init__(self):
        self.MAIN_URL = 'https://www.raiplay.it/'
        self.MENU_URL = "http://www.rai.it/dl/RaiPlay/2016/menu/PublishingBlock-20b274b1-23ae-414f-b3bf-4bdc13b86af2.html?homejson"

        # self.LOCALIZEURL = "http://mediapolisgs.rai.it/relinker/relinkerServlet.htm?cont=201342"

        self.CHANNELS_URL = "https://www.raiplay.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"

        self.CHANNELS_RADIO_URL = "http://www.raiplaysound.it/dirette.json"
        # self.NOTHUMB_RADIO_URL = "http://www.raiplayradio.it/dl/components/img/radio/player/placeholder_img.png"
        # self.BASEURL = "http://www.raiplayradio.it/"

        self.EPG_URL = "https://www.rai.it/dl/palinsesti/Page-e120a813-1b92-4057-a214-15943d95aa68-json.html?canale={}&giorno={}"
        self.EPG_REPLAY_URL = "https://www.raiplay.it/palinsesto/app/old/{}/{}.json"

        self.TG_URL = "https://www.tgr.rai.it/dl/tgr/mhp/home.xml"

        self.DEFAULT_ICON_URL = "https://images-eu.ssl-images-amazon.com/images/I/41%2B5P94pGPL.png"
        self.NOTHUMB_URL = "https://www.rai.it/cropgd/256x144/dl/components/img/imgPlaceholder.png"

        self.RELINKER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
        self.HTTP_HEADER = {'User-Agent': self.RELINKER_USER_AGENT}

        # PALINSESTO_URL_HTML = "https://www.raiplay.it/palinsesto/guidatv/lista/[idCanale]/[dd-mm-yyyy].html"
        # ON_AIR_URL = "https://www.raiplay.it/palinsesto/onAir.json"
        # RAIPLAY_AZ_TV_SHOW_PATH = "https://www.raiplay.it/dl/RaiTV/RaiPlayMobile/Prod/Config/programmiAZ-elenco.json"
        # RAIPLAY_AZ_RADIO_SHOW_PATH = "https://www.raiplay.it/dl/RaiTV/RaiRadioMobile/Prod/Config/programmiAZ-elenco.json"
        # PALINSESTO_URL = "http://www.raiplaysound.it/dl/palinsesti/Page-a47ba852-d24f-44c2-8abb-0c9f90187a3e-json.html?canale=[nomeCanale]&giorno=[dd-mm-yyyy]&mode=light"
        # Rai Sport urls
        self.RaiSportMainUrl = 'https://www.raisport.rai.it'
        self.RaiSportCategoriesUrl = "https://www.rainews.it/category/6dd7493b-f116-45de-af11-7d28a3f33dd2.json"
        self.RaiSportSearchUrl = "https://www.rainews.it/atomatic/news-search-service/api/v3/search"
        self.RaiSportDominio = "RaiNews|Category-6dd7493b-f116-45de-af11-7d28a3f33dd2"

    def getPage(self, url):
        try:
            print("[DEBUG] Fetching URL: %s" % url)
            response = requests.get(url, headers=self.HTTP_HEADER, timeout=15)
            response.raise_for_status()
            print("[DEBUG] Response status: %d" % response.status_code)
            return True, response.text
        except Exception as e:
            print("[ERROR] Error fetching page: %s" % str(e))
            return False, None

    def getFullUrl(self, url):
        """Ensure URL is complete and valid"""
        if not url:
            return ""

        if url.startswith('http'):
            return url

        if url.startswith("//"):
            return "https:" + url

        return urljoin(self.MAIN_URL, url)

    def getMainMenu(self):
        data = Utils.getUrl(self.MENU_URL)
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

    def getLiveTVChannels(self):
        data = Utils.getUrl(self.CHANNELS_URL)
        if not data:
            return []

        try:
            response = loads(data)
            channels = response.get("dirette", [])
            result = []
            for channel in channels:
                result.append({
                    'title': channel.get("channel", ""),
                    'url': channel.get("video", {}).get("contentUrl", ""),
                    # 'icon': self.getFullUrl(channel.get("icon", "")),
                    'icon': self.getThumbnailUrl2(channel),
                    'desc': channel.get("description", ""),
                    'category': 'live_tv'
                })
            return result
            """
            # for channel in channels:
                # icon_url = self.api.getThumbnailUrl2(channel)
                # result.append({
                    # 'title': channel.get("channel", ""),
                    # 'url': channel.get("video", {}).get("contentUrl", ""),
                    # 'icon': icon_url if icon_url else self.getFullUrl(channel.get("icon", "")),
                    # 'desc': channel.get("description", ""),
                    # 'category': 'live_tv'
                # })
            # return result
            """
        except BaseException:
            return []

    def getLiveRadioChannels(self):
        data = Utils.getUrl(self.CHANNELS_RADIO_URL)
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

                # Prefer "image" (external) or fallback to internal poster
                # icon = channel.get("image") or audio.get("poster", "")

                icon = self.getThumbnailUrl2(channel)
                if not icon or icon == self.NOTHUMB_URL:
                    icon = self.getThumbnailUrl2(audio)

                result.append({
                    "title": title,
                    "url": url,
                    "icon": icon,  # self.getFullUrl(icon),
                    "desc": channel.get("track_info", {}).get("title", ""),
                    "category": "live_radio"
                })

            return result
        except Exception as e:
            print("[getLiveRadioChannels] JSON parse error:", e)
            return []

    def getEPGDates(self):
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
        data = Utils.getUrl(self.CHANNELS_URL)
        if not data:
            return []

        try:
            response = loads(data)
            channels = response.get("direfte", [])
            result = []

            for channel in channels:
                # icon_url = self.getThumbnailUrl2(channel)
                result.append({
                    'title': channel.get("channel", ""),
                    'date': date,
                    # 'icon': icon_url if icon_url else self.getFullUrl(channel.get("icon", ""))
                    # 'icon': self.getFullUrl(channel.get("icon", ""))
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
            data = Utils.getUrl(url)
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

        special_mapping = {
            "/raiplay/fiction/?json": "/tipologia/serieitaliane/index.json",
            "/raiplay/serietv/?json": "/tipologia/serieinternazionali/index.json",
            "/raiplay/bambini//?json": "/tipologia/bambini/index.json",
            "/raiplay/bambini/?json": "/tipologia/bambini/index.json",
            "/raiplay/programmi/?json": "/tipologia/programmi/index.json",
            "/raiplay/film/?json": "/tipologia/film/index.json",
            "/raiplay/documentari/?json": "/tipologia/documentari/index.json",
            # "/raiplay/musica/?json": "tipologia/musica/index.json"
        }

        if old_url in special_mapping:
            new_url = self.MAIN_URL + special_mapping[old_url]
            print("[DEBUG] Special mapping: " + old_url + " -> " + new_url)
            return new_url

        # Generic conversion
        matched = search(r'/raiplay/([^/]+)/?\?json', old_url)
        if matched:
            category = matched.group(1)
            new_url = "https://www.raiplay.it/tipologia/" + category + "/index.json"
            print("[DEBUG] Generic conversion: " + old_url + " -> " + new_url)
            return new_url

        print("[DEBUG] No conversion for " + old_url + ", returning as is")
        return old_url

    def getOnDemandMenu(self):
        url = "https://www.rai.it/dl/RaiPlay/2016/menu/PublishingBlock-20b274b1-23ae-414f-b3bf-4bdc13b86af2.html?homejson"
        data = Utils.getUrl(url)
        if not data:
            return []

        try:
            response = loads(data)
            result = []

            # Fixed categories
            # https://www.raiplay.it/raiplay/tipologia/musica-e-teatro/index.json
            result.append({
                "title": "Theatre",
                "url": "https://www.raiplay.it/raiplay/tipologia/musica-e-teatro/index.json",
                # "icon": "https://www.rai.it/dl/img/2018/06/04/1528115285089_ico-teatro.png",
                "icon": self.getFullUrl("/dl/img/2018/06/04/1528115285089_ico-teatro.png"),
                "sub-type": "RaiPlay Tipologia Page"
            })

            # Extract categories from JSON
            for item in response.get("menu", []):
                if item.get("sub-type") in ("RaiPlay Tipologia Page",
                                            "RaiPlay Genere Page",
                                            "RaiPlay Tipologia Editoriale Page"):
                    name = item.get("name", "")

                    # Filter out unwanted categories
                    if name in (
                        "Home",
                        "TV Guide / Replay",
                        "Live",
                        "Login / Register",
                        "Recently Watched",
                        "My Favorites",
                        "Watch Later",
                        "Watch Offline",
                        "Tutorial",
                        "FAQ",
                        "Contact Us",
                        "Privacy Policy"
                    ):
                        continue

                    path_id = item.get("PathID", "")
                    # Convert old URLs to new format
                    converted_url = self.convert_old_url(path_id)

                    # For "Kids and Teens" add two subcategories
                    if name == "Kids and Teens":
                        result.append({
                            "title": "Kids",
                            "url": self.convert_old_url("/raiplay/bambini//?json"),
                            # "icon": self.getFullUrl(item.get("image", "")),
                            "icon": self.getThumbnailUrl2(item),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                        result.append({
                            "title": "Teen",
                            "url": "https://www.raiplay.it/tipologia/teen/index.json",
                            # "icon": self.getFullUrl(item.get("image", "")),
                            "icon": self.getThumbnailUrl2(item),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                    # For "Fiction" add two subcategories
                    elif name == "Fiction":
                        result.append({
                            "title": "Italian Series",
                            "url": self.convert_old_url("/raiplay/fiction/?json"),
                            # "icon": self.getFullUrl(item.get("image", "")),
                            "icon": self.getThumbnailUrl2(item),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                        result.append({
                            "title": "Original",
                            "url": "https://www.raiplay.it/tipologia/original/index.json",
                            # "icon": self.getFullUrl(item.get("image", "")),
                            "icon": self.getThumbnailUrl2(item),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                    # For "International Series"
                    elif name == "International Series":
                        result.append({
                            "title": "International Series",
                            "url": self.convert_old_url("/raiplay/serietv/?json"),
                            # "icon": self.getFullUrl(item.get("image", "")),
                            "icon": self.getThumbnailUrl2(item),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                    else:
                        result.append({
                            "title": name,
                            "url": converted_url,
                            # "icon": self.getFullUrl(item.get("image", "")),
                            "icon": self.getThumbnailUrl2(item),
                            "sub-type": item.get("sub-type", "")
                        })

            # Add search functionality
            result.append({
                "title": "Search",
                "url": "search",
                "icon": str(png_search) or "",
                "sub-type": "search"
            })

            return result
        except Exception as e:
            print("Error in getOnDemandMenu: " + str(e))
            return []

    def fixPath(self, path):
        if not path:
            return ""

        if match(r"^/tipologia/[^/]+/PublishingBlock-", path):
            return path

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

    def getOnDemandCategory(self, url):
        print("[DEBUG] getOnDemandCategory for URL: " + url)
        data = Utils.getUrl(url)
        if not data:
            print("[ERROR] No data received for URL: " + url)
            return []

        try:
            response = loads(data)
            print("[DEBUG] JSON response keys: " + str(list(response.keys())))
            items = []

            # Case 1: Direct items array
            if "items" in response and isinstance(response["items"], list):
                for i, item in enumerate(response["items"]):
                    print(
                        "[DEBUG] Item #" +
                        str(i) +
                        ": " +
                        item.get(
                            "name",
                            "no-name"))
                    raw_url = item.get("path_id") or item.get(
                        "url") or item.get("PathID") or ""
                    url_fixed = self.fixPath(raw_url) if raw_url else None

                    # Get thumbnail using the debugged method
                    icon_url = self.getThumbnailUrl2(item)

                    item_data = {
                        "name": item.get("name", ""),
                        "url": url_fixed,
                        "icon": icon_url,
                        "sub-type": item.get("type", item.get("sub_type", ""))}
                    items.append(item_data)

            # Case 2: Blocks structure
            elif "blocks" in response and isinstance(response["blocks"], list):
                print("[DEBUG] Found 'blocks' structure")
                for block in response["blocks"]:
                    block_type = block.get("type", "")
                    print(
                        "[DEBUG] Processing block type: {}".format(block_type))
                    # Genre slider block
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
                            print("[DEBUG] Adding genre item: " +
                                  item_data["name"] +
                                  "\n" +
                                  str(item_data["url"]) +
                                  "\n" +
                                  str(item_data["icon"]))
                            items.append(item_data)

                    # Multimedia block with sets
                    elif block_type == "RaiPlay Multimedia Block":
                        for j, item in enumerate(block.get("sets", [])):
                            print(
                                "[DEBUG] Set #" +
                                str(j) +
                                ": " +
                                item.get(
                                    "name",
                                    "no-name"))
                            icon_url = self.getThumbnailUrl2(item)
                            raw_url = item.get(
                                "path_id") or item.get("url") or ""
                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None
                            item_data = {
                                "name": item.get("name", ""),
                                "url": url_fixed,
                                "icon": icon_url,
                                "sub-type": item.get("type", "")}
                            items.append(item_data)

                    # Program list block
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

            # Case 3: Contents array (nested structure)
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
                                "sub-type": item.get("type", "")}
                            items.append(item_data)

            # Case 4: AZ list (on demand index)
            elif any(key in response for key in ["A", "B", "0-9"]):  # AZ list
                print("[DEBUG] Found AZ list structure")
                az_keys = ['0-9'] + [chr(ord('A') + i) for i in range(26)]

                for key in az_keys:
                    if key in response and response[key]:
                        for item in response[key]:
                            # Extract program details
                            name = item.get("name", "")
                            if not name:
                                continue

                            raw_url = item.get("PathID") or ""
                            url_fixed = self.fixPath(
                                raw_url) if raw_url else None

                            # Get thumbnail from multiple possible locations
                            icon_url = self.getThumbnailUrl2(item)

                            item_data = {
                                'name': name,
                                'url': url_fixed,
                                'icon': icon_url,
                                'sub-type': "PLR programma Page"}
                            items.append(item_data)

            print("[DEBUG] Found {} items in category".format(len(items)))
            return items

        except Exception as e:
            print("[ERROR] in getOnDemandCategory: " + str(e))
            traceback.print_exc()
            return []

    def getThumbnailUrl(self, pathId):
        if pathId == "":
            url = self.NOTHUMB_URL
        else:
            url = self.getFullUrl(pathId)
            url = url.replace("[RESOLUTION]", "256x-")
        return url

    def getThumbnailUrl2(self, item):
        print(">>> getThumbnailUrl2 - item keys:", item.keys())

        # Check for 'transparent-icon' first
        if "transparent-icon" in item:
            icon_url = item["transparent-icon"]
            if "[an error occurred" not in icon_url:  # filtro anti-errore
                print(">>> Using transparent-icon:", icon_url)
                return self.getThumbnailUrl(icon_url)
            else:
                print(">>> Skipping invalid transparent-icon:", icon_url)

        if "chImage" in item:
            ch_image_url = item["chImage"]
            print(">>> Using chImage:", ch_image_url)
            return self.getThumbnailUrl(ch_image_url)

        # Fallback: check standard images
        if "images" in item and isinstance(item["images"], dict):
            images = item["images"]
            print(">>> Available image keys:", images.keys())

            if "landscape" in images:
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

        print(">>> No valid thumbnail found, using NOTHUMB_URL")
        return self.NOTHUMB_URL

    def getThumbnailUrl2xxx(self, item):
        """Get thumbnail URL from various possible locations in the JSON"""
        # First try: item's direct images
        images = item.get("images", {})
        if images.get("landscape_logo", ""):
            return self.getFullUrl(images["landscape_logo"])
        elif images.get("landscape", ""):
            return self.getFullUrl(images["landscape"])
        elif images.get("portrait_logo", ""):
            return self.getFullUrl(images["portrait_logo"])
        elif images.get("portrait", ""):
            return self.getFullUrl(images["portrait"])
        elif images.get("square", ""):
            return self.getFullUrl(images["square"])

        # Second try: isPartOf section (for program relationships)
        is_part_of = item.get("isPartOf", {})
        if is_part_of:
            part_images = is_part_of.get("images", {})
            if part_images.get("portrait", ""):
                return self.getFullUrl(part_images["portrait"])
            elif part_images.get("landscape", ""):
                return self.getFullUrl(part_images["landscape"])

        # Third try: program block images
        program = item.get("program", {})
        if program:
            program_images = program.get("images", {})
            if program_images.get("portrait", ""):
                return self.getFullUrl(program_images["portrait"])
            elif program_images.get("landscape", ""):
                return self.getFullUrl(program_images["landscape"])

        # Fourth try: contentItem images
        content_item = item.get("contentItem", {})
        if content_item:
            content_images = content_item.get("images", {})
            if content_images.get("portrait", ""):
                return self.getFullUrl(content_images["portrait"])
            elif content_images.get("landscape", ""):
                return self.getFullUrl(content_images["landscape"])
        print(">>> No valid thumbnail found, using NOTHUMB_URL")
        # Final fallback
        return self.NOTHUMB_URL

    def getProgramDetails(self, url):
        """Retrieve program details"""
        url = self.getFullUrl(url)
        data = Utils.getUrl(url)
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

            # Check if it's a movie
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
        """Retrieve program elements (episodes)"""
        data = Utils.getUrl(url)
        if not data:
            return []

        try:
            response = loads(data)
            items = response.get("items", [])
            result = []

            for item in items:
                icon_url = self.api.getThumbnailUrl2(item)
                video_info = {
                    'title': item.get("name", ""),
                    'subtitle': item.get("subtitle", ""),
                    'description': item.get("description", ""),
                    'url': item.get("pathID", ""),
                    'icon': icon_url,
                    'duration': item.get("duration", 0),
                    'date': item.get("date", "")}

                # Per serie TV: aggiunge informazioni su stagione/episodio
                if "season" in item and "episode" in item:
                    video_info['season'] = item["season"]
                    video_info['episode'] = item["episode"]

                result.append(video_info)

            return result
        except BaseException:
            return []

    def getProgramInfo(self, pathID):
        url = self.getFullUrl(pathID)
        data = Utils.getUrl(url)
        if not data:
            return None

        try:
            response = loads(data)
            return response
        except BaseException:
            return None

    def getVideoUrl(self, pathID):
        program_info = self.getProgramInfo(pathID)
        if not program_info:
            return None

        return program_info.get("video", {}).get("contentUrl", None)

    def getTGRContent(self, url=None):
        if not url:
            url = self.TG_URL

        data = Utils.getUrl(url)
        if not data:
            return []

        content = data.replace("\r", "").replace("\n", "").replace("\t", "")
        items = []

        # Search for directories
        dirs = findall(
            '<item behaviour="(?:region|list)">(.*?)</item>',
            content,
            DOTALL)
        for item in dirs:
            title = search('<label>(.*?)</label>', item)
            url = search('<url type="list">(.*?)</url>', item)
            image = search('<url type="image">(.*?)</url>', item)
            if title and url:
                items.append({
                    'title': title.group(1),
                    'url': self.getFullUrl(url.group(1)),
                    'icon': self.getFullUrl(image.group(1)) if image else self.NOTHUMB_URL,
                    'category': 'tgr'
                })

        # Search for videos
        videos = findall(
            '<item behaviour="video">(.*?)</item>',
            content,
            DOTALL)
        for item in videos:
            title = search('<label>(.*?)</label>', item)
            url = search('<url type="video">(.*?)</url>', item)
            image = search('<url type="image">(.*?)</url>', item)

            if title and url:
                items.append({
                    'title': title.group(1),
                    'url': url.group(1),
                    'icon': self.getFullUrl(image.group(1)) if image else self.NOTHUMB_URL,
                    'category': 'video_link'
                })

        return items

    def getSportCategories(self):
        """Get main sports categories"""
        try:
            data = Utils.getUrl(self.RaiSportCategoriesUrl)
            if not data:
                return []

            response = loads(data)
            categories = []

            # Find the main sport category
            sport_category = None
            if response.get("name") == "Sport":
                sport_category = response
            else:
                # Search for sport category in children
                for category in response.get("children", []):
                    if category.get("name") == "Sport":
                        sport_category = category
                        break

            if not sport_category:
                return []

            # Get subcategories of sport
            for category in sport_category.get("children", []):
                title = category.get("name", "")
                unique_name = category.get("uniqueName", "")

                if title and unique_name:
                    # Get thumbnail if available
                    thumbnail = ""
                    images = category.get("images", {})
                    if images:
                        thumbnail = self.getThumbnailUrl2(images)
                    categories.append({
                        'title': title,
                        'key': unique_name,
                        'icon': thumbnail
                    })

            return categories
        except Exception as e:
            print("Error getting sports categories:", str(e))
            traceback.print_exc()
            return []

    def getSportSubcategories(self, category_key):
        """Get subcategories for a specific sport category"""
        try:
            data = Utils.getUrl(self.RaiSportCategoriesUrl)
            if not data:
                return []

            response = loads(data)

            # Find the requested category
            target_category = None
            for category in response.get("children", []):
                if category.get("uniqueName") == category_key:
                    target_category = category
                    break

            if not target_category:
                return []

            # Get subcategories
            subcategories = []
            for subcategory in target_category.get("children", []):
                title = subcategory.get("name", "")
                unique_name = subcategory.get("uniqueName", "")
                if title and unique_name:
                    # Get thumbnail if available
                    thumbnail = ""
                    images = subcategory.get("images", {})
                    if images:
                        thumbnail = self.getThumbnailUrl2(images)
                    subcategories.append({
                        'title': title,
                        'key': unique_name,
                        'icon': thumbnail
                    })

            return subcategories
        except Exception as e:
            print("Error getting sport subcategories:", str(e))
            traceback.print_exc()
            return []

    def getSportVideos(self, key, page=0):
        """Get sport videos for a category"""
        try:
            print(f"[DEBUG] Getting sport videos for key: {key}, page: {page}")
            pageSize = 50

            # Dominio specifico per lo sport
            dominio = "RaiNews|Category-60bbaf3f-99b8-4aac-8a6d-69a98e11bfc1"

            payload = {
                "page": page,
                "pageSize": pageSize,
                "mode": "archive",
                "filters": {
                    "tematica": [key],
                    "dominio": dominio
                }
            }
            postData = dumps(payload)
            print(f"[DEBUG] Payload: {postData}")

            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Content-Type': 'application/json; charset=UTF-8',
                'Origin': 'https://www.raisport.rai.it',
                'Referer': 'https://www.raisport.rai.it/archivio.html',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest'}

            print(f"[DEBUG] Sending request to: {self.RaiSportSearchUrl}")
            response = requests.post(
                self.RaiSportSearchUrl,
                headers=headers,
                data=postData,
                timeout=15
            )

            print(f"[DEBUG] Response status: {response.status_code}")
            response.raise_for_status()

            try:
                data = response.json()
            except Exception as e:
                print(f"[ERROR] JSON decode error: {str(e)}")
                print(f"[DEBUG] Response content: {response.text[:500]}...")
                return []

            print(f"[DEBUG] Response keys: {list(data.keys())}")

            videos = data.get("hits", [])
            total = data.get("total", 0)
            print(f"[DEBUG] Found {len(videos)} videos, total: {total}")

            result = []

            for video in videos:
                if video.get("data_type") == "video":
                    media = video.get('media', {})
                    video_url = media.get('mediapolis', '')
                    if not video_url:
                        continue

                    title = video.get("title", "Untitled")
                    create_date = video.get("create_date", "")

                    result.append({
                        'title': title,
                        'url': video_url,
                        'date': create_date
                    })

            items_so_far = (page * pageSize) + len(result)
            has_next_page = items_so_far < total

            if has_next_page and result:
                result.append({
                    'title': "Next page",
                    'url': '',
                    'page': page + 1,
                    'is_page': True
                })

            return result

        except Exception as e:
            print(f"[ERROR] getSportVideos exception: {str(e)}")
            traceback.print_exc()
            return []

    def getVideoUrlFromDetailPage(self, detail_url):
        """Extract the actual video URL from a detail page using regex"""
        try:
            print("Extracting video URL from:", detail_url)
            response = requests.get(
                detail_url, headers=self.HTTP_HEADER, timeout=15)
            response.raise_for_status()
            html_content = response.text

            # First try: look for video tag
            video_match = search(r'<video[^>]+src="([^"]+)"', html_content)
            if video_match:
                return video_match.group(1)

            # Second try: look for JSON-LD data
            json_ld_match = search(
                r'<script type="application/ld\+json">(.*?)</script>',
                html_content,
                DOTALL)
            if json_ld_match:
                json_data = json_ld_match.group(1)
                try:
                    data = loads(json_data)
                    if data.get(
                            '@type') == 'VideoObject' and data.get('contentUrl'):
                        return data['contentUrl']
                except BaseException:
                    pass

            # Third try: look for iframe embed
            iframe_match = search(r'<iframe[^>]+src="([^"]+)"', html_content)
            if iframe_match:
                embed_url = iframe_match.group(1)
                if not embed_url.startswith('http'):
                    embed_url = "https:" + embed_url
                return self.getVideoUrlFromEmbed(embed_url)

            # Fourth try: look for relinker URL
            relinker_match = search(
                r'relinkerServlet\.htm\?cont=(\d+)', html_content)
            if relinker_match:
                cont_id = relinker_match.group(1)
                return "https://mediapolis.rai.it/relinker/relinkerServlet.htm?cont=" + cont_id

            return None
        except Exception as e:
            print("Error extracting video URL:", str(e))
            return None

    def getVideoUrlFromEmbed(self, embed_url):
        """Extract video URL from embedded player using regex"""
        try:
            print("Extracting from embed URL:", embed_url)
            response = requests.get(
                embed_url, headers=self.HTTP_HEADER, timeout=15)
            response.raise_for_status()
            embed_content = response.text

            # Look for video source in the embed page
            file_match = search(r'file:\s*"([^"]+\.mp4)"', embed_content)
            if file_match:
                return file_match.group(1)

            # Look for HLS manifest
            hls_match = search(r'file:\s*"([^"]+\.m3u8)"', embed_content)
            if hls_match:
                return hls_match.group(1)

            # Look for JSON configuration
            json_match = search(r'mediapolis:(\{.*?\})', embed_content)
            if json_match:
                try:
                    json_data = loads(json_match.group(1))
                    if json_data.get('contentUrl'):
                        return json_data['contentUrl']
                except BaseException:
                    pass

            return None
        except Exception as e:
            print("Error extracting from embed:", str(e))
            return None

    def process_relinker(self, url):
        """Process relinker URL to extract playback URL and license key"""
        try:
            if 'relinkerServlet' not in url:
                print("[Relinker] Not a relinker URL, skipping processing")
                return url, None

            print(f"[Relinker] Processing URL: {url}")

            # Modify URL to get XML response
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query['output'] = ['56']  # Request XML format
            new_query = urlencode(query, doseq=True)
            new_url = urlunparse(parsed._replace(query=new_query))

            print(f"[Relinker] Fetching XML from: {new_url}")
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
            print(f"[Relinker] Raw content URL: {content_url}")

            # Extract URL from CDATA if present
            if '<![CDATA[' in content_url:
                cdata_match = search(r'<!\[CDATA\[(.*?)\]\]>', content_url)
                if cdata_match:
                    content_url = cdata_match.group(1)
                    print(f"[Relinker] Extracted CDATA URL: {content_url}")

            # Check for DRM license
            license_key = None
            license_match = search(
                r'<license_url>(.*?)</license_url>', content)
            if license_match:
                license_json_str = license_match.group(1)
                print(f"[Relinker] Raw license JSON: {license_json_str}")

                if '<![CDATA[' in license_json_str:
                    cdata_match = search(
                        r'<!\[CDATA\[(.*?)\]\]>', license_json_str)
                    if cdata_match:
                        license_json_str = cdata_match.group(1)
                        print(
                            f"[Relinker] Extracted CDATA license JSON: {license_json_str}")

                try:
                    license_data = loads(license_json_str)
                    print(f"[Relinker] License data: {license_data}")

                    for item in license_data.get('drmLicenseUrlValues', []):
                        if item.get('drm') == 'WIDEVINE':
                            license_key = item.get('licenceUrl')
                            print(
                                f"[Relinker] Found Widevine license: {license_key}")
                            break
                except Exception as e:
                    print(f"[Relinker] License parse error: {str(e)}")

            print(f"[Relinker] Final URL: {content_url}")
            print(f"[Relinker] License key: {license_key}")
            return content_url, license_key

        except Exception as e:
            print(f"[Relinker] Error: {str(e)}")
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
        SafeScreen.__init__(self, session)
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        self.Update = False
        self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(_("Rai Play Main"))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.closerm,
        }, -1)

        self.picload = ePicLoad()
        self._gotPageLoad()

        try:
            self.picload.PictureData.get().append(self.setCover)
        except BaseException:
            self.picload_conn = self.picload.PictureData.connect(self.setCover)
        self.poster_width = 390
        self.poster_height = 510
        self.onLayoutFinish.append(self.onLayoutFinished)

    def onLayoutFinished(self):
        try:
            size = self["poster"].instance.size()
            self.poster_width = size.width()
            self.poster_height = size.height()
            print("Poster dimensions: %dx%d" %
                  (self.poster_width, self.poster_height))
        except BaseException:
            pass

    def selectionChanged(self):
        """Handle selection changes and update poster"""
        try:
            current_index = self["text"].getSelectionIndex()
            print("Selection changed: %s -> %s" %
                  (str(self.last_index), str(current_index)))

            if current_index != self.last_index:
                self.last_index = current_index
                self.setCover()
        except Exception as e:
            print("Error in selectionChanged: " + str(e))

    def setFallbackPoster(self):
        """Set default poster when image loading fails"""
        try:
            self.picload.setPara((
                self.poster_width,
                self.poster_height,
                1, 1, False, 1, "#FF000000"
            ))
            self.picload.startDecode(DEFAULT_ICON)
        except BaseException:
            try:
                self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
            except BaseException:
                pass

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []

        # Main categories
        categories = [
            (_("Live TV"),
             "live_tv",
             "https://www.rai.it/dl/img/2016/06/10/1465549191335_icon_live.png"),
            (_("Live Radio"),
             "live_radio",
             "https://www.rai.it/dl/img/2018/06/08/1528459668481_ico-musica.png"),
            (_("Replay TV"),
             "replay",
             "https://www.rai.it/dl/img/2018/06/08/1528459923094_ico-programmi.png"),
            (_("On Demand"),
             "ondemand",
             "https://www.raiplay.it/dl/img/2018/06/04/1528115285089_ico-teatro.png"),
            (_("TV News"),
             "tg",
             "https://www.rai.it/dl/img/2018/06/08/1528459744316_ico-documentari.png"),
            (_("Sports"),
             "sport",
             png_sport)]

        for name, url, icon in categories:
            self.names.append(name)
            self.urls.append(url)
            self.icons.append(icon)

        show_list(self.names, self['text'])
        self['info'].setText(_('Please select ...'))
        self.updatePoster()

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        category = self.urls[idx]
        if category == "live_tv":
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
        else:
            self.session.open(
                MessageBox,
                _("Functionality not yet implemented"),
                MessageBox.TYPE_INFO)

    def setCover(self):
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

            if self.pixim == DEFAULT_ICON:
                self.setFallbackPoster()
                return

            # Check if local path (ad esempio se inizia con plugin_path)
            if self.pixim.startswith(plugin_path):
                # Percorso locale, decodifica direttamente
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
        if exists(pictmp):
            try:
                self.decodeImage(pictmp)
            except Exception as e:
                print("* error ** %s" % e)

    def decodeImage(self, png):
        self["poster"].hide()
        if exists(png):
            size = self['poster'].instance.size()
            self.picload = ePicLoad()
            self.scale = AVSwitch().getFramebufferScale()
            self.picload.setPara(
                [size.width(), size.height(), self.scale[0], self.scale[1], 0, 1, '#00000000'])
            if exists('/var/lib/dpkg/status'):
                self.picload.startDecode(png, False)
            else:
                self.picload.startDecode(png, 0, 0, False)
            ptr = self.picload.getData()
            if ptr is not None:
                self['poster'].instance.setPixmap(ptr)
                self['poster'].show()
            return

    def downloadError(self, error=""):
        try:
            if self["poster"].instance:
                self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
                self['poster'].show()
            print('error download: ', error)
        except Exception as e:
            print('error downloadError poster', e)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayLiveTV(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self['title'] = Label(_("Rai Play Live"))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        # self._gotPageLoad()
        self.onLayoutFinish.append(self._gotPageLoad)

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []

        channels = self.api.getLiveTVChannels()
        for channel in channels:
            self.names.append(channel['title'])
            self.urls.append(channel['url'])
            self.icons.append(channel['icon'])

        show_list(self.names, self['text'])
        self['info'].setText(_('Select channel'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayLiveRadio(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self['title'] = Label(_("Rai Play Live Radio"))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
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

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayReplayDates(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(_("Rai Play Replay TV"))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.dates = []

        today = date.today()
        for i in range(8):  # Ultimi 8 giorni
            day = today - timedelta(days=i)
            day_str = day.strftime("%A %d %B")
            # Es: 060825 per il 6 agosto 2025
            api_date = day.strftime("%d%m%y")
            self.names.append(day_str)
            self.dates.append(api_date)

        show_list(self.names, self['text'])
        self['info'].setText(_('Select date'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        print("DEBUG: Selected index:", idx)
        if idx is None:
            print("DEBUG: No selection made")
            return
        date_info = self.dates[idx]
        print("DEBUG: Selected date_info:", date_info)
        self.session.open(RaiPlayReplayChannels, date_info)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayReplayPrograms(SafeScreen):
    def __init__(self, session, channel_info, date):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)

        self.channel_info = channel_info
        self.date = date
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.names = []
        self.urls = []
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))
        # display_date = datetime.strptime(date, "%d-%m-%Y").strftime("%d/%m/%Y")
        # self['title'] = Label(_("Rai Play Replay: ") + f"{self.channel_info['display']} - {display_date}")
        self['title'] = Label(_("Rai Play Replay: ") +
                              f"{self.channel_info['display']} - {self.date}")
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
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
            print("DEBUG: Programs added:", len(self.names))
            show_list(self.names, self['text'])
            self['info'].setText(_('Select program'))
        else:
            print("DEBUG: No valid programs found for this day")
            self['info'].setText(_('No programs available for this day'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        print("DEBUG: Selected index:", idx)

        if idx is None:
            print("DEBUG: No selection made")
            return

        name = self.names[idx]
        video_url = self.urls[idx]
        print("DEBUG: Selected name:", name)
        print("DEBUG: Original video_url:", video_url)

        if not video_url:
            print("DEBUG: Video URL is empty")
            self.session.open(
                MessageBox,
                _("Video URL not available"),
                MessageBox.TYPE_ERROR)
            return

        url = normalize_url(video_url)
        print("DEBUG: Normalized URL:", url)

        if url is None or url.endswith(".json"):
            print("DEBUG: URL is invalid or ends with .json")
            self.session.open(
                MessageBox,
                _("Video not available or invalid URL"),
                MessageBox.TYPE_ERROR)
            return

        print("DEBUG: Launching playback for:", url)
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.show_error = False
        self.date = date_info
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(_("Rai Play Replay TV") + " " + str(self.date))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()
        self.error_shown = False

    def _gotPageLoad(self):
        url = "https://www.rai.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        data = Utils.getUrl(url)
        if not data:
            print("DEBUG: No data returned from URL")
            self['info'].setText(_('Error loading data'))
            return
        try:
            response = loads(data)
            # channels = response.get("dirette", []) or response.get("direfte", [])
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
                # self.icons.append(self.api.getFullUrl(channel.get("icon", "")))

            if not self.names:
                print("DEBUG: No channels added to list")
                self['info'].setText(_('No TV channels available'))
            else:
                print("DEBUG: Total channels added:", len(self.names))
                show_list(self.names, self['text'])
                self['info'].setText(_('Select channel'))

        except Exception as e:
            print('Error loading TV channels:', str(e))
            traceback.print_exc()
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        print("DEBUG: Selected index:", idx)

        if idx is None:
            print("DEBUG: No selection made")
            return

        channel_info = self.channels[idx]
        print("DEBUG: Selected channel_info:", channel_info)
        print("DEBUG: Selected date:", self.date)

        self.session.open(RaiPlayReplayPrograms, channel_info, self.date)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(_("Rai Play On Demand"))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.categories = self.api.getOnDemandMenu()
        if not self.categories:
            self['info'].setText(_('No categories available'))
            return

        self.names = [cat['title'] for cat in self.categories]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.categories):
            return

        category = self.categories[idx]

        if category['url'] == "search":
            # inserire qui la ricerca -
            self.session.open(
                MessageBox,
                _("Functionality not yet implemented"),
                MessageBox.TYPE_INFO)
        else:
            title = category.get("title") or ""
            url = category.get("url") or ""
            subtype = category.get("sub-type") or ""
            self.session.open(
                RaiPlayOnDemandCategory,
                str(title),
                str(url),
                str(subtype))

    def doClose(self):
        try:
            self.close()
        except Exception:
            pass

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        self.program_data = program_data
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
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
                    # Fallback to debug_images if no image found
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

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        block = self.blocks[idx]
        self.session.open(RaiPlayBlockItems, block['name'], block['url'])

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        items = self.api.getProgramItems(self.url)
        self.videos = []

        for item in items:
            title = item['title']
            if item.get('subtitle'):
                title = title + " (" + item['subtitle'] + ")"

            # icon_url = self.api.getThumbnailUrl2(item)
            if config.plugins.raiplay.debug.value:
                self.api.debug_images(item)

            self.videos.append({
                'title': title,
                'url': item['url'],
                'icon': item.get('icon', ""),
                # 'icon': self.api.getThumbnailUrl2(item),
                'desc': item.get('description', '')
            })

        self.names = [video['title'] for video in self.videos]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select video'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        video = self.videos[idx]
        self.playDirect(video['title'], video['url'])

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        print("[DEBUG] Loading category: %s" % self.name)
        print("[DEBUG] Category URL: %s" % self.url)
        print("[DEBUG] Sub-type: %s" % self.sub_type)

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
                # icon_url = self.api.getThumbnailUrl2(item)
                icon_url = item.get('icon', "")
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

            # Force update of poster
            self.last_index = -1
            self.selectionChanged()

        except Exception as e:
            print("[ERROR] in _gotPageLoad: %s" % str(e))
            self['info'].setText(str(_('Error loading data: %s') % str(e)))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.items):
            return

        item = self.items[idx]
        name = item['name']
        url = item['url']
        sub_type = item.get('sub-type', '')

        if sub_type == "Raiplay Tipologia Item":
            self.session.open(RaiPlayOnDemandAZ, name, url)

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
            data = Utils.getUrl(pathId)
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

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.picload = ePicLoad()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.items = []
        self.items.append({'title': "0-9", 'name': "0-9", 'url': self.url})

        for i in range(26):
            letter = chr(ord('A') + i)
            self.items.append(
                {'title': letter, 'name': letter, 'url': self.url})

        self.names = [item['title'] for item in self.items]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select letter'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        item = self.items[idx]
        self.session.open(RaiPlayOnDemandIndex, item['name'], item['url'])

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrl(pathId)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        response = loads(data)
        self.items = []
        items = response.get(self.name, [])
        icon_url = ""
        for item in items:
            """
            if item.get("images", {}).get("portrait", ""):
                icon_url = self.api.getThumbnailUrl(item["images"]["portrait"])
            elif item.get("images", {}).get("landscape", ""):
                icon_url = self.api.getThumbnailUrl(item["images"]["landscape"])
            elif item.get("images", {}).get("square", ""):
                icon_url = self.api.getThumbnailUrl(item["images"]["square"])
            elif item.get("images", {}).get("landscape_logo", ""):
                icon_url = self.api.getThumbnailUrl(item["images"]["landscape_logo"])
            else:
                # Fallback to debug_images if no image found
                icon_url = self.api.getThumbnailUrl2(item)
            if config.plugins.raiplay.debug.value:
                self.api.debug_images(item)
            """
            self.items.append({
                'name': item.get("name", ""),
                'url': item.get("PathID", ""),
                'sub-type': 'PLR programma Page',
                'icon': icon_url,
            })

        self.names = [item['name'] for item in self.items]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select program'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        item = self.items[idx]
        self.session.open(RaiPlayOnDemandProgram, item['name'], item['url'])

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrl(pathId)
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
                    program_info['first_item_path']
                )
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

        except Exception as e:
            print("Error loading program details: %s" % str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        """
        For movies, we have a direct play item
        """
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        item = self.items[idx]
        self.session.open(RaiPlayBlockItems, item['name'], item['url'])

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrl(pathId)
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

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        video = self.videos[idx]
        self.playDirect(video['title'], video['url'])

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)


class RaiPlayTG(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.names = []
        self.urls = []
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(name_plugin)
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []

        # Main TG categories
        self.names.append("TG1")
        self.urls.append("tg1")
        self.icons.append(pngx)

        self.names.append("TG2")
        self.urls.append("tg2")
        self.icons.append(pngx)

        self.names.append("TG3")
        self.urls.append("tg3")
        self.icons.append(pngx)

        self.names.append("Regional TGR")
        self.urls.append("tgr")
        self.icons.append(str(png_tgr))

        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        category = self.urls[idx]

        if category in ["tg1", "tg2", "tg3"]:
            self.session.open(RaiPlayTGList, category)
        elif category == "tgr":
            self.session.open(RaiPlayTGR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayTGList(SafeScreen):
    def __init__(self, session, category):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.category = category
        self.names = []
        self.urls = []
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self['title'] = Label(category)
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        # Updated URL for the news broadcasts
        url_map = {
            "tg1": "https://www.raiplay.it/programmi/tg1",
            "tg2": "https://www.raiplay.it/programmi/tg2",
            "tg3": "https://www.raiplay.it/programmi/tg3"
        }

        if self.category not in url_map:
            self['info'].setText(_('Invalid category'))
            return

        try:
            data = Utils.getUrl(url_map[self.category])
            if not data:
                self['info'].setText(_('Error loading data'))
                return

            # Extract JSON elements from the page
            matched = search(
                r'<script type="application/json" id="__NEXT_DATA__">(.*?)</script>',
                data,
                DOTALL)
            if not matched:
                self['info'].setText(_('Data format not recognized'))
                return

            json_data = matched.group(1)
            response = loads(json_data)

            # Navigates through the JSON structure to find the elements
            items = response.get(
                "props",
                {}).get(
                "pageProps",
                {}).get(
                "data",
                {}).get(
                "items",
                [])
            for item in items:
                title = item.get("name", "")
                if not title:
                    continue

                # URL video
                video_url = item.get("pathID", "")
                if not video_url:
                    continue

                icon_url = ""
                if item.get("images", {}).get("portrait", ""):
                    icon_url = self.api.getThumbnailUrl(
                        item["images"]["portrait"])
                elif item.get("images", {}).get("landscape", ""):
                    icon_url = self.api.getThumbnailUrl(
                        item["images"]["landscape"])
                else:
                    icon_url = self.api.getThumbnailUrl2(item)

                if config.plugins.raiplay.debug.value:
                    self.api.debug_images(item)
                self.names.append(title)
                self.urls.append(video_url)
                self.icons.append(icon_url)

            if not self.names:
                self['info'].setText(_('No editions available'))
            else:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select edition'))

        except Exception as e:
            print('Error loading TG:', str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayTGR(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.names = []
        self.urls = []
        self.icons = []
        # self.last_index = -1
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(_("Regional TGR"))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []
        # self.urls.append("http://www.tgr.rai.it/dl/tgr/mhp/home.xml")
        self.names.append("TG")
        self.urls.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?tgr")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/tgr.png")
        self.names.append("METEO")
        self.urls.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?meteo")
        self.icons.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/immagini/meteo.png")
        self.names.append("BUONGIORNO ITALIA")
        self.urls.append(
            "http://www.tgr.rai.it/dl/rai24/tgr/rubriche/mhp/ContentSet-88d248b5-6815-4bed-92a3-60e22ab92df4.html")
        self.icons.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/immagini/buongiorno%20italia.png")
        self.names.append("BUONGIORNO REGIONE")
        self.urls.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?buongiorno")
        self.icons.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/immagini/buongiorno%20regione.png")
        self.names.append("IL SETTIMANALE")
        self.urls.append(
            "http://www.tgr.rai.it/dl/rai24/tgr/rubriche/mhp/ContentSet-b7213694-9b55-4677-b78b-6904e9720719.html")
        self.icons.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/immagini/il%20settimanale.png")
        self.names.append("RUBRICHE")
        self.urls.append(
            "http://www.tgr.rai.it/dl/rai24/tgr/rubriche/mhp/list.xml")
        self.icons.append(
            "http://www.tgr.rai.it/dl/tgr/mhp/immagini/rubriche.png")
        show_list(self.names, self['text'])
        self['info'].setText(_('Please select ...'))
        self['key_green'].show()

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        name = self.names[idx]
        url = self.urls[idx]
        self.session.open(tgrRai2, name, url)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        name = self.name
        url = self.url
        content = Utils.getUrl(url)
        content = content.replace("\r", "").replace("\t", "").replace("\n", "")
        try:
            if 'type="video">' in content:
                # relinker
                regexcat = '<label>(.*?)</label>.*?type="video">(.*?)</url>'
                self["key_green"].setText('Play')
            elif 'type="list">' in content:
                regexcat = '<label>(.*?)</label>.*?type="list">(.*?)</url>'
            else:
                print('passsss')
                pass
            matched = compile(regexcat, DOTALL).findall(content)
            for name, url in matched:
                if url.startswith('http'):
                    url1 = url
                else:
                    url1 = "http://www.tgr.rai.it" + url
                url = url1
                # name = html_unescape(name)
                self.names.append(str(name))
                self.urls.append(url)
            self['info'].setText(_('Please select ...'))
            self['key_green'].show()
            show_list(self.names, self['text'])
        except Exception as e:
            print('error: ', str(e))
            pass

    def okRun(self):
        i = len(self.names)
        if i < 1:
            return
        idx = self["text"].getSelectionIndex()
        name = self.names[idx]
        url = self.urls[idx]
        if 'relinker' in url:
            self.playDirect(name, url)
        else:
            self.session.open(tgrRai3, name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


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
        self.icons = []
        # self.last_index = -1
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        name = self.name
        url = self.url
        content = Utils.getUrl(url)
        content = content.replace("\r", "").replace("\t", "").replace("\n", "")
        try:
            if 'type="video">' in content:
                # relinker
                regexcat = '<label>(.*?)</label>.*?type="video">(.*?)</url>'
                self["key_green"].setText('Play')

            elif 'type="list">' in content:
                regexcat = '<label>(.*?)</label>.*?type="list">(.*?)</url>'
            else:
                print('passsss')
                pass
            matched = compile(regexcat, DOTALL).findall(content)
            for name, url in matched:
                if url.startswith('http'):
                    url1 = url
                else:
                    url1 = "http://www.tgr.rai.it" + url
                url = url1
                # name = html_unescape(name)
                self.names.append(str(name))
                self.urls.append(url)
                self.icons.append(str(png_tgr))
            self['info'].setText(_('Please select ...'))
            self['key_green'].show()
            show_list(self.names, self['text'])
        except Exception as e:
            print('error: ', str(e))
            pass

    def okRun(self):
        i = len(self.names)
        if i < 1:
            return
        idx = self["text"].getSelectionIndex()
        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class tvRai2(SafeScreen):
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
        self.icons = []
        # self.last_index = -1
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.close,
        }, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        url = self.url
        name = self.name
        content = Utils.getUrl(url)
        try:
            regexcat = 'data-video-json="(.*?).json".*?<img alt="(.*?)"'
            matched = compile(regexcat, DOTALL).findall(content)
            for url, name in matched:
                url1 = "http://www.raiplay.it" + url + '.html'
                content2 = Utils.getUrl(url1)
                regexcat2 = '"/video/(.*?)",'
                match2 = compile(regexcat2, DOTALL).findall(content2)
                url2 = match2[0].replace("json", "html")
                url3 = "http://www.raiplay.it/video/" + url2
                name = name.replace('-', '').replace('RaiPlay', '')
                """
                # item = name + "###" + url3
                # items.append(item)
            # items.sort()
            # for item in items:
                # if item not in items:
                    # name = item.split("###")[0]
                    # url3 = item.split("###")[1]
                """
                self.names.append(str(name))
                self.urls.append(url3)
                self.icons.append(str(png_tgr))
        except Exception as e:
            print('error: ', str(e))
        show_list(self.names, self['text'])
        self['info'].setText(_('Please select ...'))
        self['key_green'].show()

    def okRun(self):
        i = len(self.names)
        if i < 1:
            return
        idx = self["text"].getSelectionIndex()
        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class tvRai3(SafeScreen):
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
        self.icons = []
        # self.last_index = -1
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
        }, -1)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        name = self.name
        url = self.url
        content = Utils.getUrl(url)
        try:
            if content.find('behaviour="list">'):
                regexcat = '<label>(.*?)</label>.*?type="list">(.*?).html</url>'
                matched = compile(regexcat, DOTALL).findall(content)
                for name, url in matched:
                    url = "http://www.tgr.rai.it/" + url + '.html'
                    # name = html_unescape(name)
                    self.names.append(str(name))
                    self.urls.append(url)
                    self.icons.append(str(png_tgr))
        except Exception as e:
            print('error: ', str(e))
        self['info'].setText(_('Please select ...'))
        self['key_green'].show()
        show_list(self.names, self['text'])

    def okRun(self):
        i = len(self.names)
        if i < 1:
            return
        idx = self["text"].getSelectionIndex()
        name = self.names[idx]
        url = self.urls[idx]
        try:
            self.session.open(tvRai4, name, url)
        except Exception as e:
            print('error: ', str(e))

    def closerm(self):
        Utils.deletetmp()
        self.close()


class tvRai4(SafeScreen):
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
        self.icons = []
        # self.last_index = -1
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))

        self["title"] = Label(str(name))
        self['actions'] = ActionMap(
            ['OkCancelActions'], {
                'ok': self.okRun, 'cancel': self.close}, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        url = self.url
        name = self.name
        content = Utils.getUrl(url)
        regexcat = 'data-video-json="(.*?)".*?<img alt="(.*?)"'
        matched = compile(regexcat, DOTALL).findall(content)
        try:
            for url, name in matched:
                url1 = "http://www.raiplay.it" + url
                content2 = Utils.getUrl(url1)
                regexcat2 = '"/video/(.*?)"'
                match2 = compile(regexcat2, DOTALL).findall(content2)
                url2 = match2[0].replace("json", "html")
                url3 = "http://www.raiplay.it/video/" + url2
                # name = html_unescape(name)
                self.names.append(str(name))
                self.urls.append(url3)
                self.icons.append(str(png_tgr))
        except Exception as e:
            print('error: ', str(e))
        self['info'].setText(_('Please select ...'))
        self['key_green'].show()
        show_list(self.names, self['text'])

    def okRun(self):
        i = len(self.names)
        if i < 1:
            return
        idx = self["text"].getSelectionIndex()
        name = self.names[idx]
        url = self.urls[idx]
        self.playDirect(name, url)

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlaySport(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.navigation_stack = []
        self.api = RaiPlayAPI()
        self.names = []
        self.urls = []
        self.icons = []
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))

        self['title'] = Label(_("Rai Sport"))
        self['actions'] = ActionMap(['OkCancelActions'], {
            'ok': self.okRun,
            'cancel': self.goBack,
        }, -2)
        self.onLayoutFinish.append(self.loadCategories)

    def loadCategories(self):
        """Load the main sports categories"""
        self.navigation_stack = []
        self.categories = self.api.getSportCategories()
        if not self.categories:
            self['info'].setText(_('No sports categories available'))
            return

        self.names = [cat['title'] for cat in self.categories]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select category'))
        self['title'].setText(_("Rai Sport - Categories"))
        self.current_level = "categories"

    def loadSubcategories(self, category):
        """Load subcategories for a specific category"""
        self.navigation_stack.append({
            'type': 'category',
            'data': category
        })

        self.subcategories = self.api.getSportSubcategories(category['key'])
        if not self.subcategories:
            self.loadVideos(category)
            return

        self.names = [subcat['title'] for subcat in self.subcategories]
        show_list(self.names, self['text'])
        self['info'].setText(_('Select subcategory'))
        self['title'].setText(_("Rai Sport - Subcategories"))
        self.current_level = "subcategories"
        self.current_category = category

    def loadVideos(self, category, subcategory=None):
        if subcategory:
            key = subcategory['key']
            title = subcategory['title']
        else:
            key = category['key']
            title = category['title']

        self.session.open(
            RaiPlaySportVideos,
            title,
            key,
            0
        )

    def okRun(self):
        """Manages user selection"""
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        if self.current_level == "categories":
            category = self.categories[idx]
            self.loadSubcategories(category)

        elif self.current_level == "subcategories":
            subcategory = self.subcategories[idx]
            self.loadVideos(self.current_category, subcategory)

    def goBack(self):
        """Manages backward navigation"""
        if not self.navigation_stack:
            self.close()
            return

        last_state = self.navigation_stack.pop()

        if last_state['type'] == 'category':
            self.loadCategories()
        else:
            self.close()


class RaiPlaySportVideos(SafeScreen):
    def __init__(self, session, name, key, page=0):
        SafeScreen.__init__(self, session)
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.session = session
        self.name = name
        self.key = key
        self.page = page
        self._history = []
        self.videos = []
        self.names = []
        self.urls = []
        self.icons = []
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))
        self["title"] = Label(str(name))
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
            "back": self.goBack,
        }, -1)

        self._gotPageLoad()

    def _gotPageLoad(self):
        try:
            self.videos = self.api.getSportVideos(self.key, self.page)

            if not self.videos:
                self['info'].setText(_('No videos available'))
                return

            self.names = []
            for video in self.videos:
                title = video['title']
                if video.get('is_page'):
                    title = _("Next page") + " (" + str(video['page']) + ")"
                elif video.get('date'):
                    title = video['date'] + " - " + title
                self.names.append(title)

            show_list(self.names, self['text'])
            self['info'].setText(_('Select video'))

        except Exception as e:
            print("Error loading videos: " + str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None or idx >= len(self.videos):
            return

        video = self.videos[idx]

        if video.get('is_page'):
            self._history.append({
                'page': self.page,
                'selection': self['text'].getSelectionIndex()
            })

            self.page = video['page']
            self._gotPageLoad()
        else:
            self.playDirect(video['title'], video['url'])

    def playDirect(self, name, url):
        """Direct playback with provided URL"""
        try:
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(
                MessageBox,
                _("Error playing stream"),
                MessageBox.TYPE_ERROR)

    def goBack(self):
        if self.page > 0 and not self._history:
            self.page = 0
            self._gotPageLoad()
        elif self._history:
            prev_state = self._history.pop()
            self.page = prev_state['page']
            self._gotPageLoad()
            if prev_state['selection'] is not None:
                self['text'].setIndex(prev_state['selection'])
        else:
            self.close()


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

    """
    def toggleShow(self):
        if self.skipToggleShow:
            self.skipToggleShow = False
            return
        if self.__state == self.STATE_HIDDEN:
            self.show()
            self.hideTimer.stop()
        else:
            self.hide()
            self.startHideTimer()
    """

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
                "info": self.cicleStreamType,
                "tv": self.cicleStreamType,
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
            print(f"[Player] Starting: {self.name}")
            print(f"[Player] URL: {self.url}")

            # Processa URL relinker se necessario
            if 'relinkerServlet' in self.url:
                self.url, self.license_key = self.api.process_relinker(
                    self.url)
                print(f"[Player] Processed URL: {self.url}")
                print(f"[Player] DRM: {self.license_key is not None}")

            # Gestione contenuti DRM (richiede ServiceApp)
            if self.license_key:
                print("[Player] DRM content detected")
                if not is_serviceapp_available():
                    error_msg = "DRM requires ServiceApp (not installed)"
                    print(f"[Player] {error_msg}")
                    raise Exception(error_msg)

                print("[Player] Using ServiceApp for DRM playback")
                self.play_with_serviceapp()
                return

            # Per contenuti non-DRM, usa ServiceApp se disponibile
            if is_serviceapp_available():
                print("[Player] Using ServiceApp for playback")
                self.use_serviceapp()
            else:
                print("[Player] Using standard playback")
                self.use_standard_method()

        except Exception as e:
            error_msg = f"Playback error: {str(e)}"
            print(f"[Player] {error_msg}")
            self.show_error(error_msg)

    def play_with_serviceapp(self):
        """Riproduzione DRM con ServiceApp"""
        try:
            print(f"[ServiceApp-DRM] Playing: {self.url}")

            ref = eServiceReference(4097, 0, self.url)
            ref.setName(self.name)

            # Aggiungi informazioni DRM
            ref.setData(0, 4097)   # Tipo servizio
            ref.setData(1, 0)      # Flags
            ref.setData(2, self.license_key)  # Chiave di licenza

            print(f"[ServiceApp-DRM] ServiceRef: {ref.toString()}")

            self.session.nav.stopService()
            self.session.nav.playService(ref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[ServiceApp-DRM] Playback started")

        except Exception as e:
            error_msg = f"ServiceApp DRM error: {str(e)}"
            print(f"[Player] {error_msg}")
            self.show_error(error_msg)

    def use_serviceapp(self):
        """Riproduzione standard con ServiceApp"""
        try:
            print(f"[ServiceApp] Playing: {self.url}")

            ref = eServiceReference(4097, 0, self.url)
            ref.setName(self.name)

            print(f"[ServiceApp] ServiceRef: {ref.toString()}")

            self.session.nav.stopService()
            self.session.nav.playService(ref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[ServiceApp] Playback started")

        except Exception as e:
            error_msg = f"ServiceApp error: {str(e)}"
            print(f"[Player] {error_msg}")
            self.show_error(error_msg)

    def use_standard_method(self):
        """Riproduzione standard senza ServiceApp"""
        try:
            print(f"[Standard] Playing: {self.url}")

            # Formatta l'URL per la riproduzione standard
            if '://' in self.url:
                url = self.url.replace(':', '%3a').replace(' ', '%20')
                ref = f"4097:0:1:0:0:0:0:0:0:0:{url}"
            else:
                ref = self.url

            sref = eServiceReference(ref)
            sref.setName(self.name)

            print(f"[Standard] ServiceRef: {sref.toString()}")

            self.session.nav.stopService()
            self.session.nav.playService(sref)

            self.show()
            self.state = self.STATE_PLAYING
            print("[Standard] Playback started")

        except Exception as e:
            error_msg = f"Standard playback error: {str(e)}"
            print(f"[Player] {error_msg}")
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

    def cicleStreamType(self):
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
        print(f"Switching stream type to: {self.servicetype}")
        self.openTest(self.servicetype, self.url)

    """ #standard playpause
    # def playpauseService(self):
        # if self.service:
            # try:
                # # Try standard pause/resume
                # if self.state == self.STATE_PLAYING:
                    # self.service.pause()
                    # self.state = self.STATE_PAUSED
                # else:
                    # self.service.play()
                    # self.state = self.STATE_PLAYING
            # except:
                # # Fallback: restart the stream
                # current_ref = self.session.nav.getCurrentlyPlayingServiceReference()
                # if current_ref:
                    # self.session.nav.stopService()
                    # if self.state == self.STATE_PAUSED:
                        # self.session.nav.playService(current_ref)
                        # self.state = self.STATE_PLAYING
    """

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

    def cancel(self):
        if exists('/tmp/hls.avi'):
            remove('/tmp/hls.avi')
        self.session.nav.stopService()
        if self.srefInit:
            self.session.nav.playService(self.srefInit)
        aspect_manager.restore_aspect
        self.close()

    def leavePlayer(self):
        self.session.nav.stopService()
        if self.srefInit:
            self.session.nav.playService(self.srefInit)
        self.close()


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

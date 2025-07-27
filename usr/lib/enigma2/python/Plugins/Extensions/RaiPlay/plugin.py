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
from os.path import join, exists, splitext
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
from Components.config import config
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
    from urllib.parse import quote
    from urllib.parse import urljoin
except ImportError:
    from urllib import quote
    from urlparse import urljoin

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
# from .Console import Console as xConsole

aspect_manager = Utils.AspectManager()

PY3 = False
PY3 = sys.version_info.major >= 3
if sys.version_info >= (2, 7, 9):
    try:
        import ssl
        sslContext = ssl._create_unverified_context()
    except:
        sslContext = None

currversion = '1.0'
plugin_path = '/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay'
pluglogo = join(plugin_path, "res/pics/logo.png")
pngx = join(plugin_path, "res/pics/plugins.png")
pngl = join(plugin_path, "res/pics/plugin.png")
pngs = join(plugin_path, "res/pics/setting.png")
desc_plugin = '..:: TiVu Rai Play by Lululla %s ::.. ' % currversion
name_plugin = 'TiVu Rai Play'
DEFAULT_ICON = join(plugin_path, "res/pics/icon.png")
screenwidth = getDesktop(0).size()
skin_path = join(plugin_path, "res/skins/")
if screenwidth.width() == 1920:
    skin_path = join(plugin_path, "res/skins/fhd/")
elif screenwidth.width() == 2560:
    skin_path = join(plugin_path, "res/skins/uhd/")

if not exists(join(skin_path, "settings.xml")):
    skin_path = join(plugin_path, "res/skins/hd/")
    print("Skin non trovata, uso il fallback:", skin_path)


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


def returnIMDB(text_clear):
    text = html_unescape(text_clear)

    if Utils.is_TMDB and Utils.TMDB:
        try:
            _session.open(Utils.TMDB.tmdbScreen, text, 0)
        except Exception as e:
            print("[XCF] TMDB error:", str(e))
        return True

    elif Utils.is_tmdb and Utils.tmdb:
        try:
            _session.open(Utils.tmdb.tmdbScreen, text, 0)
        except Exception as e:
            print("[XCF] tmdb error:", str(e))
        return True

    elif Utils.is_imdb and Utils.imdb:
        try:
            Utils.imdb(_session, text)
        except Exception as e:
            print("[XCF] IMDb error:", str(e))
        return True

    _session.open(MessageBox, text, MessageBox.TYPE_INFO)
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


def extract_real_video_url(page_url):
    """Extracts the real video URL from RaiPlay JSON page"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
            "Referer": "https://www.raiplay.it/"
        }
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
    pngx = resolveFilename(SCOPE_PLUGINS, "Extensions/{}/res/pics/setting.png".format('RaiPlay'))
    if screenwidth.width() == 2560:
        res.append(MultiContentEntryPixmapAlphaTest(pos=(10, 15), size=(40, 40), png=loadPNG(pngx)))
        res.append(MultiContentEntryText(pos=(80, 0), size=(2000, 60), font=0, text=name, color=0xa6d1fe, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    elif screenwidth.width() == 1920:
        res.append(MultiContentEntryPixmapAlphaTest(pos=(5, 5), size=(40, 40), png=loadPNG(pngx)))
        res.append(MultiContentEntryText(pos=(70, 0), size=(1150, 50), font=0, text=name, color=0xa6d1fe, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    else:
        res.append(MultiContentEntryPixmapAlphaTest(pos=(3, 10), size=(40, 40), png=loadPNG(pngx)))
        res.append(MultiContentEntryText(pos=(50, 0), size=(500, 50), font=0, text=name, color=0xa6d1fe, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    return res


def show_list(data, listas):
    icount = 0
    plist = []
    for line in data:
        name = data[icount]
        plist.append(RaiPlaySetListEntry(name))
        icount += 1
        listas.setList(plist)


class SafeScreen(Screen):
    def __init__(self, session):
        super().__init__(session)
        self.onClose.append(self.cleanup)
        self.closing = False

        # self.safety_timer = eTimer()
        # try:
            # self.safety_timer.timeout.connect(self.force_close)
        # except AttributeError:
            # self.safety_timer.callback.append(self.force_close)
        # self.safety_timer.start(1000, False)
        
        # Variables for poster handling
        self.last_index = -1
        self.has_poster = hasattr(self, "poster")
        
        # Timer for poster update
        self.pic_timer = eTimer()
        try:
            self.pic_timer.timeout.connect(self.updatePoster)
        except AttributeError:
            self.pic_timer.callback.append(self.updatePoster)
        
        # Initialize picload only if poster exists
        if self.has_poster:
            self.picload = ePicLoad()
            try:
                self.picload.PictureData.get().append(self.setPoster)
            except:
                self.picload_conn = self.picload.PictureData.connect(self.setPoster)
            
            # Default size (will be updated after layout)
            self.poster_width = 390
            self.poster_height = 510
            self.onLayoutFinish.append(self.onLayoutFinished)
    
    def onLayoutFinished(self):
        """Called when layout is complete and we can get actual widget size"""
        if self.has_poster:
            try:
                # Get real dimensions of the poster widget
                size = self["poster"].instance.size()
                self.poster_width = size.width()
                self.poster_height = size.height()
                print("Poster size: %dx%d" % (self.poster_width, self.poster_height))
            except Exception as e:
                print("Error getting poster size:", e)
    
    def selectionChanged(self):
        """Called when the selection in the list changes"""
        current_index = self["text"].getSelectionIndex()
        if current_index != self.last_index:
            self.last_index = current_index
            if self.has_poster:
                self.pic_timer.start(200, True)  # Update poster after short delay
    
    def updatePoster(self):
        """Update the poster based on current selection"""
        try:
            if not self.has_poster or self.closing or not hasattr(self, "icons"):
                return
            
            idx = self["text"].getSelectionIndex()
            if idx is None or idx < 0 or idx >= len(self.icons):
                return
                
            icon_url = self.icons[idx]
            
            # If URL is a dict, extract actual URL
            # if isinstance(icon_url, dict) and "url" in icon_url:
                # final_url = icon_url["url"]
            # else:
                # final_url = self.api.getFullUrl(icon_url) if hasattr(self, "api") else icon_url

            api = getattr(self, "api", None)
            if api and hasattr(api, "getFullUrl"):
                final_url = api.getFullUrl(icon_url)
            else:
                final_url = icon_url

            # Safety check on URL
            if not final_url or not final_url.startswith("http"):
                final_url = DEFAULT_ICON
            
            # Configure and start image decoding
            self.picload.setPara((
                self.poster_width,
                self.poster_height,
                1, 1, False, 1, "#FF000000"
            ))
            self.picload.startDecode(final_url)
        except Exception as e:
            print("Error updating poster:", e)
            # Fallback to default icon
            try:
                self.picload.setPara((
                    self.poster_width,
                    self.poster_height,
                    1, 1, False, 1, "#FF000000"
                ))
                self.picload.startDecode(DEFAULT_ICON)
            except:
                try:
                    self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
                    self["poster"].show()
                except:
                    pass
    
    def setPoster(self, picInfo=None):
        """Callback when image is ready"""
        if not self.has_poster or self.closing:
            return
            
        try:
            ptr = self.picload.getData()
            if ptr:
                self["poster"].instance.setPixmap(ptr)
                self["poster"].show()
        except:
            pass
    
    def cleanup(self):
        if self.closing:
            return
        self.closing = True
        
        try:
            self.pic_timer.stop()
            if hasattr(self, 'picload') and self.has_poster:
                del self.picload

            # Clear common resources
            for attr in ['videos', 'names', 'urls', '_history', 'items', 'blocks']:
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
            except:
                print("Force close failed")
                # Last resort - delete references
                for key in list(self.__dict__.keys()):
                    if key not in ['session', 'desktop', 'instance']:
                        delattr(self, key)
                try:
                    super(Screen, self).close()
                except:
                    pass

    def close(self, *args, **kwargs):
        """Override close method with safe handling"""
        self.cleanup()
        super(SafeScreen, self).close(*args, **kwargs)


class RaiPlayAPI:
    def __init__(self):
        self.MAIN_URL = 'https://www.raiplay.it/'
        self.MENU_URL = "http://www.rai.it/dl/RaiPlay/2016/menu/PublishingBlock-20b274b1-23ae-414f-b3bf-4bdc13b86af2.html?homejson"

        self.CHANNELS_URL = "https://www.raiplay.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        self.EPG_URL = "https://www.rai.it/dl/palinsesti/Page-e120a813-1b92-4057-a214-15943d95aa68-json.html?canale={}&giorno={}"
        self.TG_URL = "https://www.tgr.rai.it/dl/tgr/mhp/home.xml"
        self.DEFAULT_ICON_URL = "https://images-eu.ssl-images-amazon.com/images/I/41%2B5P94pGPL.png"
        self.NOTHUMB_URL = "https://www.rai.it/cropgd/256x144/dl/components/img/imgPlaceholder.png"
        self.RELINKER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
        self.HTTP_HEADER = {'User-Agent': self.RELINKER_USER_AGENT}

        palinsestoUrl = "https://www.raiplay.it/palinsesto/app/old/[nomeCanale]/[dd-mm-yyyy].json"
        palinsestoUrlHtml = "https://www.raiplay.it/palinsesto/guidatv/lista/[idCanale]/[dd-mm-yyyy].html"
        onAirUrl = "https://www.raiplay.it/palinsesto/onAir.json"
        RaiPlayAzTvShowPath = "/dl/RaiTV/RaiPlayMobile/Prod/Config/programmiAZ-elenco.json"

        # Raiplay RADIO
        self.CHANNELS_RADIO_URL = "http://www.raiplaysound.it/dirette.json"
        noThumbUrl = "http://www.raiplayradio.it/dl/components/img/radio/player/placeholder_img.png"
        baseUrl = "http://www.raiplayradio.it/"
        localizeUrl = "http://mediapolisgs.rai.it/relinker/relinkerServlet.htm?cont=201342"
        palinsestoUrl = "http://www.raiplaysound.it/dl/palinsesti/Page-a47ba852-d24f-44c2-8abb-0c9f90187a3e-json.html?canale=[nomeCanale]&giorno=[dd-mm-yyyy]&mode=light"
        RaiRadioAzTvShowPath = "/dl/RaiTV/RaiRadioMobile/Prod/Config/programmiAZ-elenco.json"

        # Rai Sport urls
        self.RaiSportMainUrl = 'https://www.rainews.it/archivio/sport'
        self.RaiSportCategoriesUrl = "https://www.rainews.it/category/6dd7493b-f116-45de-af11-7d28a3f33dd2.json"
        self.RaiSportSearchUrl = "https://www.rainews.it/atomatic/news-search-service/api/v3/search"

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
                if item.get("sub-type") in ("RaiPlay Tipologia Page", "RaiPlay Genere Page"):
                    result.append({
                        'title': item.get("name", ""),
                        'url': self.getFullUrl(item.get("PathID", "")),
                        'icon': self.getFullUrl(item.get("image", "")),
                        'sub-type': item.get("sub-type", "")
                    })
            return result
        except:
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
                    'icon': self.getFullUrl(channel.get("icon", "")),
                    'desc': channel.get("description", ""),
                    'category': 'live_tv'
                })
            return result
        except:
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
                icon = channel.get("image") or audio.get("poster", "")

                result.append({
                    "title": title,
                    "url": url,
                    "icon": self.getFullUrl(icon),
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
                result.append({
                    'title': channel.get("channel", ""),
                    'date': date,
                    'icon': self.getFullUrl(channel.get("icon", ""))
                })
            return result
        except:
            return []

    def getEPGPrograms(self, channel, date):
        url = self.EPG_URL.format(quote(channel), date)
        data = Utils.getUrl(url)
        if not data:
            return []

        try:
            response = loads(data)
            programs = []

            for item in response:
                if item.get("nome") == channel:
                    programs = item.get("palinsesto", [{}])[0].get("programmi", [])
                    break

            result = []
            for program in programs:
                if not program:
                    continue

                title = program.get("name", "")
                timex = program.get("timePublished", "")
                desc = program.get("testoBreve", "") or program.get("description", "")
                video_url = program.get("pathID", "") if program.get("hasVideo", False) else None

                if program.get("images", {}).get("portrait", ""):
                    thumb = self.getThumbnailUrl(program["images"]["portrait"])
                elif program.get("images", {}).get("landscape", ""):
                    thumb = self.getThumbnailUrl(program["images"]["landscape"])
                elif program.get("isPartOf", {}).get("images", {}).get("portrait", ""):
                    thumb = self.getThumbnailUrl(program["isPartOf"]["images"]["portrait"])
                elif program.get("isPartOf", {}).get("images", {}).get("landscape", ""):
                    thumb = self.getThumbnailUrl(program["isPartOf"]["images"]["landscape"])
                else:
                    thumb = self.NOTHUMB_URL

                result.append({
                    'title': (timex + " " if timex else "") + title,
                    'url': video_url,
                    'icon': thumb,
                    'desc': desc,
                    'category': 'program' if video_url else 'nop'
                })
            return result
        except:
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
            result.append({
                "title": "Theatre",
                "url": "https://www.raiplay.it/performing-arts/index.json",
                "icon": self.getFullUrl("/dl/img/2018/06/04/1528115285089_ico-teatro.png"),
                "sub-type": "RaiPlay Tipologia Page"
            })

            # Extract categories from JSON
            for item in response.get("menu", []):
                if item.get("sub-type") in ("RaiPlay Tipologia Page", "RaiPlay Genere Page", "RaiPlay Tipologia Editoriale Page"):
                    name = item.get("name", "")

                    # Filter out unwanted categories
                    if name in ("Home", "TV Guide / Replay", "Live", "Login / Register",
                                "Recently Watched", "My Favorites", "Watch Later", "Watch Offline",
                                "Tutorial", "FAQ", "Contact Us", "Privacy Policy"):
                        continue

                    path_id = item.get("PathID", "")
                    # Convert old URLs to new format
                    converted_url = self.convert_old_url(path_id)

                    # For "Kids and Teens" add two subcategories
                    if name == "Kids and Teens":
                        result.append({
                            "title": "Kids",
                            "url": self.convert_old_url("/raiplay/bambini//?json"),
                            "icon": self.getFullUrl(item.get("image", "")),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                        result.append({
                            "title": "Teen",
                            "url": "https://www.raiplay.it/tipologia/teen/index.json",
                            "icon": self.getFullUrl(item.get("image", "")),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                    # For "Fiction" add two subcategories
                    elif name == "Fiction":
                        result.append({
                            "title": "Italian Series",
                            "url": self.convert_old_url("/raiplay/fiction/?json"),
                            "icon": self.getFullUrl(item.get("image", "")),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                        result.append({
                            "title": "Original",
                            "url": "https://www.raiplay.it/tipologia/original/index.json",
                            "icon": self.getFullUrl(item.get("image", "")),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                    # For "International Series"
                    elif name == "International Series":
                        result.append({
                            "title": "International Series",
                            "url": self.convert_old_url("/raiplay/serietv/?json"),
                            "icon": self.getFullUrl(item.get("image", "")),
                            "sub-type": "RaiPlay Tipologia Page"
                        })
                    else:
                        result.append({
                            "title": name,
                            "url": converted_url,
                            "icon": self.getFullUrl(item.get("image", "")),
                            "sub-type": item.get("sub-type", "")
                        })

            # Add search functionality
            result.append({
                "title": "Search",
                "url": "search",
                "icon": "",
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
            print("[DEBUG] fixPath: fixed malformed path: " + path + " -> " + fixed)
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

            if "items" in response and isinstance(response["items"], list):
                for i, item in enumerate(response["items"]):
                    print("[DEBUG] Item #" + str(i) + ": " + item.get("name", "no-name"))
                    raw_url = item.get("path_id") or item.get("url") or ""
                    url_fixed = self.fixPath(raw_url) if raw_url else None

                    item_data = {
                        "name": item.get("name", ""),
                        "url": url_fixed,
                        "icon": self.getFullUrl(item.get("images", {}).get("landscape", "")),
                        "sub-type": item.get("type", "")
                    }
                    print("[DEBUG] Adding item: " + item_data["name"] + " " + str(item_data["url"]))
                    items.append(item_data)

                print("[DEBUG] Total items found: " + str(len(items)))
                return items

            if "contents" in response and isinstance(response["contents"], list):
                # Case: list of categories
                for block in response["contents"]:
                    print("[DEBUG] Processing block: " + block.get("name", "no-name"))
                    nested_contents = block.get("contents", [])
                    print("[DEBUG] Nested contents count: " + str(len(nested_contents)))

                    for i, item in enumerate(nested_contents):
                        print("[DEBUG] Item #" + str(i) + ": " + item.get("name", "no-name"))
                        raw_url = item.get("path_id") or item.get("url") or ""
                        url_fixed = self.fixPath(raw_url) if raw_url else None

                        item_data = {
                            "name": item.get("name", ""),
                            "url": url_fixed,
                            "icon": self.getFullUrl(item.get("images", {}).get("landscape", "")),
                            "sub-type": item.get("type", "")
                        }
                        print("[DEBUG] Adding item: " + item_data["name"] + " " + str(item_data["url"]))
                        items.append(item_data)

            else:
                for i, block in enumerate(response.get("blocks", [])):
                    print("[DEBUG] Processing blocks block #" + str(i) + " type: " + str(block.get("type")))
                    block_type = block.get("type")

                    # Case: genres
                    if block_type == "RaiPlay Slider Generi Block":
                        for j, item in enumerate(block.get("contents", [])):
                            raw_url = item.get("path_id") or item.get("url") or ""
                            url_fixed = self.fixPath(raw_url) if raw_url else None

                            item_data = {
                                "name": item.get("name", ""),
                                "url": url_fixed,
                                "icon": self.getFullUrl(item.get("image", "")),
                                "sub-type": item.get("sub_type", "")
                            }
                            print("[DEBUG] Adding genre item: " + item_data["name"] + " " + str(item_data["url"]))
                            items.append(item_data)

                    # Case: multimedia block with `sets`
                    elif block_type == "RaiPlay Multimedia Block":
                        for j, item in enumerate(block.get("sets", [])):
                            print("[DEBUG] Set #" + str(j) + ": " + item.get("name", "no-name"))
                            raw_url = item.get("path_id") or item.get("url") or ""
                            url_fixed = self.fixPath(raw_url) if raw_url else None

                            item_data = {
                                "name": item.get("name", ""),
                                "url": url_fixed,
                                "icon": self.getFullUrl(item.get("images", {}).get("landscape", "")),
                                "sub-type": item.get("type", "")
                            }
                            print("[DEBUG] Adding set item: " + item_data["name"] + " " + str(item_data["url"]))
                            items.append(item_data)

                    else:
                        print("[DEBUG] Skipping unknown block type: " + str(block_type))

            print("[DEBUG] Total items found: " + str(len(items)))
            return items

        except Exception as e:
            print("[ERROR] in getOnDemandCategory: " + str(e))
            traceback.print_exc()
            return []

    def getThumbnailUrl(self, pathId):
        if not pathId:
            return self.NOTHUMB_URL
        url = self.getFullUrl(pathId)
        return url.replace("[RESOLUTION]", "256x-")

    def getThumbnailUrl2(self, item):
        """Get thumbnail URL from various possible locations in the JSON"""
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
        else:
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
        """Recupera gli elementi di un programma (episodi)"""
        data = Utils.getUrl(url)
        if not data:
            return []

        try:
            response = loads(data)
            items = response.get("items", [])
            result = []

            for item in items:
                video_info = {
                    'title': item.get("name", ""),
                    'subtitle': item.get("subtitle", ""),
                    'description': item.get("description", ""),
                    'url': item.get("pathID", ""),
                    'icon': self.getFullUrl(item.get("images", {}).get("landscape", "")),
                    'duration': item.get("duration", 0),
                    'date': item.get("date", "")
                }

                # Per serie TV: aggiunge informazioni su stagione/episodio
                if "season" in item and "episode" in item:
                    video_info['season'] = item["season"]
                    video_info['episode'] = item["episode"]

                result.append(video_info)

            return result
        except:
            return []

    def getProgramInfo(self, pathID):
        url = self.getFullUrl(pathID)
        data = Utils.getUrl(url)
        if not data:
            return None

        try:
            response = loads(data)
            return response
        except:
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
        dirs = findall('<item behaviour="(?:region|list)">(.*?)</item>', content, DOTALL)
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
        videos = findall('<item behaviour="video">(.*?)</item>', content, DOTALL)
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

    def getSportSubcategories(self, category_key):
        """Get subcategories for a specific sport category"""
        try:
            print("Getting subcategories for key:", category_key)
            data = Utils.getUrl(self.RaiSportCategoriesUrl)
            if not data:
                print("No data received")
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
            print("Found category:", target_category.get("name"))
            subcategories = []
            for subcategory in target_category.get("children", []):
                title = subcategory.get("name", "")
                unique_name = subcategory.get("uniqueName", "")
                print("Processing subcategory:", title, unique_name)
                if title and unique_name:
                    # Get thumbnail if available
                    thumbnail = ""
                    images = subcategory.get("images", {})
                    if images:
                        if images.get("landscape", ""):
                            thumbnail = images["landscape"]
                        elif images.get("portrait", ""):
                            thumbnail = images["portrait"]
                        elif images.get("square", ""):
                            thumbnail = images["square"]

                    subcategories.append({
                        'title': title,
                        'key': unique_name,
                        'icon': thumbnail
                    })
            print("Subcategories extracted:", subcategories)
            return subcategories
        except Exception as e:
            print("Error getting sport subcategories:", str(e))
            traceback.print_exc()
            return []

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
                        if images.get("landscape", ""):
                            thumbnail = images["landscape"]
                        elif images.get("portrait", ""):
                            thumbnail = images["portrait"]
                        elif images.get("square", ""):
                            thumbnail = images["square"]

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

    def getSportVideos(self, key, dominio, page=0):
        # print("[DEBUG] === START getSportVideos (Kodi replica) ===")
        # print("[DEBUG] Key: " + str(key))
        # print("[DEBUG] Dominio: " + str(dominio))
        # print("[DEBUG] Page: " + str(page))

        pageSize = 50
        payload = {
            "page": page,
            "pageSize": pageSize,
            "mode": "archive",
            "filters": {
                "category": [key],
                "dominio": dominio
            }
        }
        postData = dumps(payload)
        print("[DEBUG] Payload:", postData)

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/json; charset=UTF-8',
            'Origin': 'https://www.raisport.rai.it',
            'Referer': 'https://www.raisport.rai.it/archivio.html',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        }

        try:
            url = "https://www.rainews.it/atomatic/news-search-service/api/v3/search"

            # Invia la richiesta POST
            req = requests.Request('POST', url, headers=headers, data=postData)
            prepared = req.prepare()
            print("[DEBUG] Sending request to:", prepared.url)
            print("[DEBUG] Headers:", prepared.headers)
            print("[DEBUG] Body:", prepared.body)

            s = requests.Session()
            response = s.send(prepared, timeout=15)

            print("[DEBUG] === RESPONSE RECEIVED ===")
            print("[DEBUG] Status code: {response.status_code}")

            if response.status_code != 200:
                print("[ERROR] API status: " + str(response.status_code))
                print("[DEBUG] Response: " + response.text[:500])
                return []

            data = response.json()
            videos = []
            hits = data.get("hits", [])

            print("[DEBUG] Found " + str(len(hits)) + " items in response")

            for h in hits:
                if h.get("data_type") == "video":
                    media = h.get('media', {})
                    video_url = media.get('mediapolis', '')
                    if not video_url:
                        continue

                    # Get title
                    title = h.get("title", "")

                    # Get date if available
                    create_date = h.get("create_date", "")

                    # Append video
                    videos.append({
                        'title': title,
                        'url': video_url,
                        'date': create_date
                    })

            total = data.get("total", 0)
            print("[DEBUG] Total items: " + str(total) + ", pageSize: " + str(pageSize))

            items_so_far = (page * pageSize) + len(videos)
            has_next_page = items_so_far < total

            # Only add "Next page" if there are more items and we have videos
            if has_next_page and videos and len(videos) > 0:
                videos.append({
                    'title': "Next page",
                    'url': '',
                    'page': page + 1,
                    'is_page': True
                })

            return videos

        except Exception as e:
            print("[ERROR] getSportVideos exception: " + str(e))
            import traceback
            traceback.print_exc()
            return []

    def getVideoUrlFromDetailPage(self, detail_url):
        """Extract the actual video URL from a detail page using regex"""
        try:
            print("Extracting video URL from:", detail_url)
            response = requests.get(detail_url, headers=self.HTTP_HEADER, timeout=15)
            response.raise_for_status()
            html_content = response.text

            # First try: look for video tag
            video_match = search(r'<video[^>]+src="([^"]+)"', html_content)
            if video_match:
                return video_match.group(1)

            # Second try: look for JSON-LD data
            json_ld_match = search(r'<script type="application/ld\+json">(.*?)</script>', html_content, DOTALL)
            if json_ld_match:
                json_data = json_ld_match.group(1)
                try:
                    data = loads(json_data)
                    if data.get('@type') == 'VideoObject' and data.get('contentUrl'):
                        return data['contentUrl']
                except:
                    pass

            # Third try: look for iframe embed
            iframe_match = search(r'<iframe[^>]+src="([^"]+)"', html_content)
            if iframe_match:
                embed_url = iframe_match.group(1)
                if not embed_url.startswith('http'):
                    embed_url = "https:" + embed_url
                return self.getVideoUrlFromEmbed(embed_url)

            # Fourth try: look for relinker URL
            relinker_match = search(r'relinkerServlet\.htm\?cont=(\d+)', html_content)
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
            response = requests.get(embed_url, headers=self.HTTP_HEADER, timeout=15)
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
                except:
                    pass

            return None
        except Exception as e:
            print("Error extracting from embed:", str(e))
            return None

    def getreplay(self):
        self.videos = []
        url = "https://www.raiplay.it/programmi/"
        data = self.download_url(url)
        programs = findall(r'<a href="(/programmi/[^"]+)"', data)
        titles = findall(r'<span class="title">(.*?)</span>', data)
        for i in range(len(programs)):
            if i < len(titles):
                title = titles[i].strip()
            else:
                title = programs[i].split("/")[-1].replace("-", " ").title()
            self.videos.append({
                "title": title,
                "url": "https://www.raiplay.it" + programs[i],
                "mode": "getvideos"
            })

    def getvideos(self):
        self.videos = []
        data = self.download_url(self.url)
        matched = findall(r'data-video-json="([^"]+)"', data)
        for item in matched:
            item = item.replace("&quot;", "\"")
            try:
                info = loads(item)
                title = info.get("title", "No Title")
                streaming_url = info.get("content_url", "")
                if streaming_url:
                    self.videos.append({
                        "title": title,
                        "url": streaming_url,
                        "mode": "getvideo"
                    })
            except Exception:
                continue


class RaiPlayMain(SafeScreen):
    def __init__(self, session):
        SafeScreen.__init__(self, session)
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        self.Update = False
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Rai Play Main"))
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.closerm}, -1)

        self.picload = ePicLoad()
        self._gotPageLoad()

        # self.pic_timer = eTimer()
        # try:
            # self.pic_timer.timeout.connect(self.updatePoster)
        # except AttributeError:
            # self.pic_timer.callback.append(self.updatePoster)

        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)
        self.poster_width = 390
        self.poster_height = 510

    def selectionChanged(self):
        """Called when the selection in the list changes"""
        current_index = self["text"].getSelectionIndex()
        if current_index != self.last_index:
            self.last_index = current_index
            if self.has_poster:
                self.pic_timer.start(200, True)  # Update poster after short delay
    
    def updatePoster(self):
        """Update the poster based on current selection"""
        try:
            if not self.has_poster or self.closing or not hasattr(self, "icons"):
                return
            
            idx = self["text"].getSelectionIndex()
            if idx is None or idx < 0 or idx >= len(self.icons):
                return
                
            icon_url = self.icons[idx]
            
            # If URL is a dict, extract actual URL
            if isinstance(icon_url, dict) and "url" in icon_url:
                final_url = icon_url["url"]
            else:
                final_url = self.api.getFullUrl(icon_url) if hasattr(self, "api") else icon_url

            # api = getattr(self, "api", None)
            # if api and hasattr(api, "getFullUrl"):
                # final_url = api.getFullUrl(icon_url)
            # else:
                # final_url = icon_url

            # Safety check on URL
            if not final_url or not final_url.startswith("http"):
                final_url = DEFAULT_ICON
            
            # Configure and start image decoding
            self.picload.setPara((
                self.poster_width,
                self.poster_height,
                1, 1, False, 1, "#FF000000"
            ))
            self.picload.startDecode(final_url)
        except Exception as e:
            print("Error updating poster:", e)
            # Fallback to default icon
            try:
                self.picload.setPara((
                    self.poster_width,
                    self.poster_height,
                    1, 1, False, 1, "#FF000000"
                ))
                self.picload.startDecode(DEFAULT_ICON)
            except:
                try:
                    self["poster"].instance.setPixmapFromFile(DEFAULT_ICON)
                    self["poster"].show()
                except:
                    pass
    
    def setPoster(self, picInfo=None):
        """Callback when image is ready"""
        if not self.has_poster or self.closing:
            return
            
        try:
            ptr = self.picload.getData()
            if ptr:
                self["poster"].instance.setPixmap(ptr)
                self["poster"].show()
        except:
            pass

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []

        # Main categories
        self.names.append(_("Live TV"))
        self.urls.append("live_tv")
        self.icons.append(DEFAULT_ICON)

        self.names.append(_("Live Radio"))
        self.urls.append("live_radio")
        self.icons.append(DEFAULT_ICON)

        self.names.append(_("Replay TV"))
        self.urls.append("replay")
        self.icons.append(DEFAULT_ICON)

        self.names.append(_("On Demand"))
        self.urls.append("ondemand")
        self.icons.append(DEFAULT_ICON)

        self.names.append(_("TV News"))
        self.urls.append("tg")
        self.icons.append(DEFAULT_ICON)

        # Add Sports category
        self.names.append(_("Sports"))
        self.urls.append("sport")
        self.icons.append(DEFAULT_ICON)

        show_list(self.names, self['text'])
        self['info'].setText(_('Please select ...'))
        self['key_green'].show()
        self.updatePoster()
        # self.pic_timer.start(200, True)

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
            self.session.open(MessageBox, _("Functionality not yet implemented"), MessageBox.TYPE_INFO)

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Rai Play Live"))
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
        self.session.open(Playstream1, name, url)

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Rai Play Live Radio"))
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
        self.session.open(Playstream1, name, url)

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
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Rai Play Replay TV"))
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self._gotPageLoad()

    def _gotPageLoad(self):
        self.names = []
        self.dates = []

        today = date.today()
        for i in range(8):
            day = today - timedelta(days=i)
            day_str = day.strftime("%A %d %B")
            self.names.append(day_str)
            self.dates.append(day.strftime("%d%m%Y"))

        show_list(self.names, self['text'])
        self['info'].setText(_('Select date'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        date = self.dates[idx]
        self.session.open(RaiPlayReplayChannels, date)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayReplayPrograms(SafeScreen):
    def __init__(self, session, channel, date):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.channel = channel
        self.date = date
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(date)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []

        channel_encoded = self.channel.replace(" ", "")
        url = "https://www.rai.it/dl/palinsesti/Page-e120a813-1b92-4057-a214-15943d95aa68-json.html?canale=" + channel_encoded + "&giorno=" + self.date

        data = Utils.getUrl(url)
        if not data:
            self['info'].setText(_("Error loading data"))
            return

        try:
            response = loads(data)
            # Use the exact key
            channel_key = self.channel

            # Check if the key exists in the response
            if channel_key in response:
                palinsesto_list = response[channel_key]
                if palinsesto_list and isinstance(palinsesto_list, list) and len(palinsesto_list) > 0:
                    programs = palinsesto_list[0].get("palinsesto", [])
                    if programs and isinstance(programs, list) and len(programs) > 0:
                        programs = programs[0].get("programmi", [])
                    else:
                        programs = []
                else:
                    programs = []
            else:
                # Attempt with alternative key
                alt_channel_key = channel_encoded
                if alt_channel_key in response:
                    palinsesto_list = response[alt_channel_key]
                    if palinsesto_list and isinstance(palinsesto_list, list) and len(palinsesto_list) > 0:
                        programs = palinsesto_list[0].get("palinsesto", [])
                        if programs and isinstance(programs, list) and len(programs) > 0:
                            programs = programs[0].get("programmi", [])
                        else:
                            programs = []
                    else:
                        programs = []
                else:
                    programs = []
                    print("Channel key '" + channel_key + "' or '" + alt_channel_key + "' not found in response keys: " + str(list(response.keys())))

            for program in programs:
                if not program:
                    continue

                title = program.get("name", "")
                start_time = program.get("timePublished", "")
                has_video = program.get("hasVideo", False)

                if title and has_video:
                    if start_time:
                        full_title = start_time + " " + title
                    else:
                        full_title = title

                    # Get the URL from the video.contentUrl field as in the JSON
                    video_info = program.get("video", {})
                    video_url = video_info.get("contentUrl", "")

                    if not video_url:
                        # Fallback to pathID if necessary
                        video_url = program.get("pathID", "")

                    if video_url:
                        if not video_url.startswith("http"):
                            video_url = "https:" + video_url if video_url.startswith("//") else self.api.getFullUrl(video_url)

                        # Get thumbnail
                        if program.get("images", {}).get("portrait", ""):
                            icon_url = self.api.getThumbnailUrl(program["images"]["portrait"])
                        elif program.get("images", {}).get("landscape", ""):
                            icon_url = self.api.getThumbnailUrl(program["images"]["landscape"])
                        else:
                            icon_url = self.api.NOTHUMB_URL
                        # print("RaiPlayReplayPrograms full_title:", str(full_title))
                        # print("RaiPlayReplayPrograms video_url:", str(video_url))
                        # print("RaiPlayReplayPrograms icon_url:", str(icon_url))
                        self.names.append(full_title)
                        self.urls.append(video_url)
                        self.icons.append(icon_url)

            if not self.names:
                self['info'].setText(_('No programs available for this day'))
            else:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select program'))
        except Exception as e:
            print("Error loading replay programs:", str(e))
            traceback.print_exc()
            self['info'].setText(_("Error loading data"))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        name = self.names[idx]
        video_url = self.urls[idx]
        if not video_url:
            self.session.open(MessageBox, _("Video URL not available"), MessageBox.TYPE_ERROR)
            return

        url = normalize_url(video_url)

        if url is None or url.endswith(".json"):
            self.session.open(MessageBox, _("Video not available or invalid URL"), MessageBox.TYPE_ERROR)
            return

        print("Playing video URL: {}".format(url))
        self.session.open(Playstream1, name, url)

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlayReplayChannels(SafeScreen):
    def __init__(self, session, date):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
        self.items = []
        self.names = []
        self.channels = []
        self.show_error = False
        self.date = date
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(date)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self._gotPageLoad()
        self.error_shown = False
        self.picload = ePicLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        url = "https://www.rai.it/dl/RaiPlay/2016/PublishingBlock-9a2ff311-fcf0-4539-8f8f-c4fee2a71d58.html?json"
        data = Utils.getUrl(url)
        if not data:
            self['info'].setText(_('Error loading data'))
            return
        try:
            response = loads(data)
            print("RaiPlayReplayChannels Raw response:", response)
            tv_stations = response.get("dirette", [])
            for station in tv_stations:
                title = station.get("channel", "")
                icon = station.get("icon", "")
                if title:
                    self.names.append(title)
                    self.channels.append(title)
                    self.icons.append(self.api.getFullUrl(icon))

            if not self.names:
                self['info'].setText(_('No TV channels available'))
            else:
                show_list(self.names, self['text'])
                self['info'].setText(_('Select channel'))

        except Exception as e:
            print('Error loading TV channels:', str(e))
            self['info'].setText(_('Error loading data'))

    def okRun(self):
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        channel = self.channels[idx]
        self.session.open(RaiPlayReplayPrograms, channel, self.date)

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.icons = []
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Rai Play On Demand"))
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
            self.session.open(MessageBox, _("Functionality not yet implemented"), MessageBox.TYPE_INFO)
        else:
            self.session.open(RaiPlayOnDemandCategory, category['title'], category['url'], category['sub-type'])

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
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        self.blocks = []
        for block in self.program_data.get("blocks", []):
            for set_item in block.get("sets", []):
                self.blocks.append({
                    'name': set_item.get("name", ""),
                    'url': set_item.get("path_id", "")
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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        items = self.api.getProgramItems(self.url)
        self.videos = []

        for item in items:
            title = item['title']
            if item.get('subtitle'):
                title = title + " (" + item['subtitle'] + ")"

            self.videos.append({
                'title': title,
                'url': item['url'],
                'icon': item['icon'],
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
        self.session.open(Playstream1, video['title'], video['url'])

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        # print("[DEBUG] Loading category: %s" % self.name)
        # print("[DEBUG] Category URL: %s" % self.url)
        # print("[DEBUG] Sub-type: %s" % self.sub_type)
        try:
            items = self.api.getOnDemandCategory(self.url)
            self.items = []

            print("[DEBUG] Received %d items from API" % len(items))

            for item in items:
                url = item.get("url", "") or item.get("path_id", "")
                if not url:
                    print("[WARNING] Skipping item '%s' because url is empty" % item.get("name", ""))
                    continue

                # ensure full URL here, assuming api.getFullUrl exists
                url_full = self.api.getFullUrl(url)

                item_data = {
                    'name': item.get('name', ""),
                    'url': url_full,
                    'icon': item.get('icon', ""),
                    'sub-type': item.get('sub-type', "")
                }
                print("[DEBUG] _gotPageLoad Adding item: %s url: %s" % (item_data['name'], item_data['url']))
                self.items.append(item_data)

            if not self.items:
                print("[DEBUG]_gotPageLoad No items available")
                self['info'].setText(_('No items available'))
            else:
                self.names = [item['name'] for item in self.items]
                show_list(self.names, self['text'])
                self['info'].setText(_('Select item'))

        except Exception as e:
            print("[ERROR] in _gotPageLoad: %s" % str(e))
            self['info'].setText(_('Error loading data: %s') % str(e))

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
                    self.session.open(
                        Playstream1,
                        name,
                        program_data['info']["first_item_path"]
                    )
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
                    self.session.open(Playstream1, name, video_url)
                else:
                    self['info'].setText(_('No video URL found'))
            except Exception:
                self['info'].setText(_('Error parsing video data'))

        else:
            self.session.open(RaiPlayOnDemandCategory, name, url, sub_type)

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self.picload = ePicLoad()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        self.items = []
        self.items.append({'title': "0-9", 'name': "0-9", 'url': self.url})

        for i in range(26):
            letter = chr(ord('A') + i)
            self.items.append({'title': letter, 'name': letter, 'url': self.url})

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrl(pathId)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        response = loads(data)
        self.items = []
        items = response.get(self.name, [])

        for item in items:
            self.items.append({
                'name': item.get("name", ""),
                'url': item.get("PathID", ""),
                'sub-type': 'PLR programma Page'
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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        pathId = self.api.getFullUrl(self.url)
        data = Utils.getUrl(pathId)
        if not data:
            self['info'].setText(_('Error loading data'))
            return

        try:
            response = loads(data)
            program_info = {
                'name': response.get("name", ""),
                'description': response.get("vanity", response.get("description", "")),
                'year': response.get("year", ""),
                'country': response.get("country", ""),
                'first_item_path': response.get("first_item_path", ""),
                'is_movie': False
            }

            # Check if it's a movie
            for typology in response.get("typologies", []):
                if typology.get("name") == "Film":
                    program_info['is_movie'] = True
                    break

            if program_info['is_movie'] and program_info['first_item_path']:
                # Open playback screen (replace Playstream1 with your player)
                self.session.open(
                    Playstream1,
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
                    season_match = search(r"Stagione\s+(\d+)", label, IGNORECASE)
                    if season_match:
                        season = season_match.group(1)
                    else:
                        season = "1"

                    item_data = {
                        'name': label,
                        'url': set_item.get("path_id", ""),
                        'season': season
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
        # For movies, we have a direct play item
        # if self['text'].isHidden():
            # idx = 0  # Only one item (the movie)
            # self.session.open(Playstream1, self.name, self.url)
            # return
        """
        idx = self["text"].getSelectionIndex()
        if idx is None:
            return

        item = self.items[idx]
        self.session.open(RaiPlayBlockItems, item['name'], item['url'])

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
            images = item.get("images", {})

            if images.get("portrait", ""):
                icon_url = self.api.getThumbnailUrl(images["portrait"])
            elif images.get("landscape", ""):
                icon_url = self.api.getThumbnailUrl(images["landscape"])
            else:
                icon_url = self.api.NOTHUMB_URL

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
        self.session.open(Playstream1, video['title'], video['url'])


class RaiPlayTG(SafeScreen):
    def __init__(self, session):
        self.session = session
        skin = join(skin_path, 'settings.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()
        SafeScreen.__init__(self, session)
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
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name_plugin)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
        self.icons.append(pngx)

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(category)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
            matched = search(r'<script type="application/json" id="__NEXT_DATA__">(.*?)</script>', data, DOTALL)
            if not matched:
                self['info'].setText(_('Data format not recognized'))
                return

            json_data = matched.group(1)
            response = loads(json_data)

            # Navigates through the JSON structure to find the elements
            items = response.get("props", {}).get("pageProps", {}).get("data", {}).get("items", [])
            for item in items:
                title = item.get("name", "")
                if not title:
                    continue

                # URL video
                video_url = item.get("pathID", "")
                if not video_url:
                    continue

                # Immagine
                if item.get("images", {}).get("portrait", ""):
                    icon_url = self.api.getThumbnailUrl(item["images"]["portrait"])
                elif item.get("images", {}).get("landscape", ""):
                    icon_url = self.api.getThumbnailUrl(item["images"]["landscape"])
                else:
                    icon_url = self.api.NOTHUMB_URL

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
        self.session.open(Playstream1, name, url)

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
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Regional TGR"))
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []
        # self.urls.append("http://www.tgr.rai.it/dl/tgr/mhp/home.xml")
        self.names.append("TG")
        self.urls.append("http://www.tgr.rai.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?tgr")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/tgr.png")
        self.names.append("METEO")
        self.urls.append("http://www.tgr.rai.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?meteo")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/meteo.png")
        self.names.append("BUONGIORNO ITALIA")
        self.urls.append("http://www.tgr.rai.it/dl/rai24/tgr/rubriche/mhp/ContentSet-88d248b5-6815-4bed-92a3-60e22ab92df4.html")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/buongiorno%20italia.png")
        self.names.append("BUONGIORNO REGIONE")
        self.urls.append("http://www.tgr.rai.it/dl/tgr/mhp/regioni/Page-0789394e-ddde-47da-a267-e826b6a73c4b.html?buongiorno")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/buongiorno%20regione.png")
        self.names.append("IL SETTIMANALE")
        self.urls.append("http://www.tgr.rai.it/dl/rai24/tgr/rubriche/mhp/ContentSet-b7213694-9b55-4677-b78b-6904e9720719.html")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/il%20settimanale.png")
        self.names.append("RUBRICHE")
        self.urls.append("http://www.tgr.rai.it/dl/rai24/tgr/rubriche/mhp/list.xml")
        self.icons.append("http://www.tgr.rai.it/dl/tgr/mhp/immagini/rubriche.png")
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
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        self.names = []
        self.urls = []
        self.icons = []
        name = self.name
        url = self.url
        content = Utils.getUrl(url)
        content = content.replace("\r", "").replace("\t", "").replace("\n", "")
        try:
            if 'type="video">' in content:
                regexcat = '<label>(.*?)</label>.*?type="video">(.*?)</url>'  # relinker
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
                name = html_unescape(name)
                self.names.append(str(name))
                self.urls.append(url)
                # self.icons.append(pic)
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
            self.session.open(Playstream1, name, url)
        else:
            self.session.open(tgrRai3, name, url)

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
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        name = self.name
        url = self.url
        content = Utils.getUrl(url)
        content = content.replace("\r", "").replace("\t", "").replace("\n", "")
        try:
            if 'type="video">' in content:
                regexcat = '<label>(.*?)</label>.*?type="video">(.*?)</url>'  # relinker
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
                name = html_unescape(name)
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
        self.session.open(Playstream1, name, url)

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
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
                url3 = "http://www.raiplay.it/video/" + url2  # (url2.replace('json', 'html'))
                name = html_unescape(name)
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
        try:
            self.session.open(Playstream1, name, url)
        except Exception as e:
            print('error tvr4 e  ', str(e))

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
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
                    name = html_unescape(name)
                    self.names.append(str(name))
                    self.urls.append(url)
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
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading data... Please wait'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Play'))
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(name)
        self['actions'] = ActionMap(['OkCancelActions',], {'ok': self.okRun,
                                                           'cancel': self.close}, -2)
        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
                name = html_unescape(name)
                url3 = url3
                self.names.append(str(name))
                self.urls.append(url3)
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
            self.session.open(Playstream1, name, url)
        except Exception as e:
            print('error: ', str(e))

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
        self['key_yellow'] = Button()
        self['key_yellow'].hide()
        self['title'] = Label(_("Rai Sport"))
        self['actions'] = ActionMap(['OkCancelActions',], {
            'ok': self.okRun,
            'cancel': self.goBack,
        }, -2)
        self.onLayoutFinish.append(self.loadCategories)
        self.picload = ePicLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

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
        dominio = "RaiNews|Category-60bbaf3f-99b8-4aac-8a6d-69a98e11bfc1"

        if subcategory:
            key = subcategory['key']
            self.current_subcategory_key = key
        else:
            key = category['key']
            self.current_subcategory_key = None

        self.session.open(
            RaiPlaySportVideos,
            subcategory['title'] if subcategory else category['title'],
            key,
            dominio,
            0
        )

    def showNoVideosMessage(self):
        """Display a message when there are no videos available"""
        self.session.openWithCallback(
            self.handleNoVideosCallback,
            MessageBox,
            _("No videos available"),
            MessageBox.TYPE_INFO
        )

    def handleNoVideosCallback(self, result=None):
        """Handles the callback after the 'no video' message"""
        self.goBack()

    def returnFromVideos(self, last_page):
        print("Returned from videos, last page was " + str(last_page))

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

        if last_state['type'] == 'subcategory':
            self.loadSubcategories(last_state['parent'])
        elif last_state['type'] == 'category':
            self.loadCategories()
        else:
            self.close()

    def closerm(self):
        Utils.deletetmp()
        self.close()


class RaiPlaySportVideos(SafeScreen):
    def __init__(self, session, name, key, dominio, page=0, parent=None):
        SafeScreen.__init__(self, session)

        self.skin = """
            <screen name="RaiPlaySportVideos" position="center,center" size="1280,720" title="..::RaiPlay Sport Videos::.." backgroundColor="#20000000" flags="wfNoBorder">
                <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1280,720" zPosition="-2" />
                <widget name="title" position="0,6" size="1280,58" font="Regular;30" halign="left" valign="center" foregroundColor="#002a79b8" backgroundColor="black" transparent="1" zPosition="5" />
                <widget name="info" position="1,78" size="1280,50" font="Regular;30" halign="center" valign="center" foregroundColor="yellow" backgroundColor="#202020" transparent="0" zPosition="5" />
                <widget name="poster" position="896,132" size="390,510" zPosition="4" backgroundColor="#30000000" transparent="1" borderWidth="3" borderColor="#00ffffff" flags="wfBorder" alphatest="blend" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay/res/pics/sep.png" position="0,68" size="1280,8" zPosition="5" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay/res/pics/sep.png" position="0,626" size="1280,8" zPosition="5" />
                <widget name="text" position="0,135" size="1280,491" scrollbarMode="showOnDemand" transparent="1" zPosition="5" foregroundColor="#00a0a0a0" foregroundColorSelected="#ffffff" backgroundColor="#20000000" backgroundColorSelected="#0b2049" selectionPixmap="/usr/lib/enigma2/python/Plugins/Extensions/RaiPlay/res/pics/sliderb.png" />
                <eLabel backgroundColor="red" position="31,685" size="300,6" zPosition="10" />
                <eLabel backgroundColor="green" position="947,687" size="300,6" zPosition="10" />
                <widget name="key_red" position="29,643" size="300,40" font="Regular;30" halign="center" valign="center" backgroundColor="#20000000" zPosition="5" transparent="1" />
                <widget name="key_green" position="945,643" size="300,40" font="Regular;30" halign="center" valign="center" backgroundColor="#20000000" zPosition="5" transparent="1" />
            </screen>
        """
        self.session = session
        self.name = name
        self.key = key
        self.dominio = dominio
        self.page = page
        self._history = []
        self.videos = []
        self.names = []
        self.urls = []
        self.icons = []
        self.show_error = False
        list = self.videos
        self.api = RaiPlayAPI()
        self['poster'] = Pixmap()
        self['text'] = setPlaylist([])
        self["text"].onSelectionChanged.append(self.selectionChanged)
        self['info'] = Label(_('Loading...'))
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['title'] = Label(name)
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.okRun,
            "cancel": self.close,
            "back": self.goBack,
        }, -1)

        self.picload = ePicLoad()
        self._gotPageLoad()
        try:
            self.picload.PictureData.get().append(self.setPoster)
        except:
            self.picload_conn = self.picload.PictureData.connect(self.setPoster)

    def _gotPageLoad(self):
        try:
            self.videos = self.api.getSportVideos(self.key, self.dominio, self.page)

            if not self.videos:
                self.show_error = True
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
            self.show_error = False

        except Exception as e:
            print("Error loading videos: " + str(e))
            self['info'].setText(_('Error loading data'))
            self.show_error = True

    def okRun(self):
        if self.show_error:
            self.goBack()
            return

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
            self.session.open(Playstream1, video['title'], video['url'])

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
        self.hideTimer = eTimer()
        try:
            self.hideTimer_conn = self.hideTimer.timeout.connect(self.doTimerHide)
        except:
            self.hideTimer.callback.append(self.doTimerHide)
        self.hideTimer.start(5000, True)
        self.onShow.append(self.__onShow)
        self.onHide.append(self.__onHide)

    def OkPressed(self):
        self.toggleShow()

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

    def serviceStarted(self):
        if self.execing:
            if config.usage.show_infobar_on_zap.value:
                self.doShow()

    def __onShow(self):
        self.__state = self.STATE_SHOWN
        self.startHideTimer()

    def startHideTimer(self):
        if self.__state == self.STATE_SHOWN and not self.__locked:
            self.hideTimer.stop()
            idx = config.usage.infobar_timeout.index
            if idx:
                self.hideTimer.start(idx * 1500, True)

    def __onHide(self):
        self.__state = self.STATE_HIDDEN

    def doShow(self):
        self.hideTimer.stop()
        self.show()
        self.startHideTimer()

    def doTimerHide(self):
        self.hideTimer.stop()
        if self.__state == self.STATE_SHOWN:
            self.hide()

    def lockShow(self):
        try:
            self.__locked += 1
        except:
            self.__locked = 0
        if self.execing:
            self.show()
            self.hideTimer.stop()
            self.skipToggleShow = False

    def unlockShow(self):
        try:
            self.__locked -= 1
        except:
            self.__locked = 0
        if self.__locked < 0:
            self.__locked = 0
        if self.execing:
            self.startHideTimer()

    def debug(obj, text=""):
        print(text + " %s\n" % obj)


class Playstream1(SafeScreen):
    def __init__(self, session, name, url):

        SafeScreen.__init__(self, session)
        self.session = session
        global _session
        _session = session

        skin = join(skin_path, 'Playstream1.xml')
        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.name = Utils.cleanName(name)
        self.url = url
        self.setTitle(name)

        self['list'] = setPlaylist([])
        self['info'] = Label('Select Player Stream')
        self['key_red'] = Button(_('Back'))
        self['key_green'] = Button(_('Select'))
        self['actions'] = ActionMap(['OkCancelActions',
                                     'InfobarShowHideActions',
                                     'InfobarActions',
                                     'InfobarSeekActions'], {'red': self.cancel,
                                                             'green': self.okClicked,
                                                             'back': self.cancel,
                                                             'cancel': self.cancel,
                                                             'leavePlayer': self.cancel,
                                                             # 'yellow': self.taskManager,
                                                             # 'rec': self.runRec,
                                                             # 'instantRecord': self.runRec,
                                                             # 'ShortRecord': self.runRec,
                                                             'ok': self.okClicked}, -2)

        self.srefInit = self.session.nav.getCurrentlyPlayingServiceReference()
        self.onLayoutFinish.append(self.openTest)

    def openTest(self):
        self.names = []
        self.urls = []
        self.names.append('Play Direct')
        self.urls.append(self.url)
        self.names.append('Play HLS')
        self.urls.append(self.url)
        self.names.append('Play TS')
        self.urls.append(self.url)
        show_list(self.names, self['list'])

    def okClicked(self):
        idx = self['list'].getSelectionIndex()
        if idx is not None and idx != -1:
            self.name = self.name
            url = self.urls[idx]
            # url = normalize_url(url)
            if idx == 0:
                self.playDirect(url)
            elif idx == 1:  # HLS
                self.playHLS(url)
            elif idx == 2:  # TS
                self.playTS(url)

    def playDirect(self, url):
        """Direct playback with provided URL"""
        try:
            if ".m3u8" in url:
                self.playHLS(url)
            else:
                url = strwithmeta(url, {
                    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                    'Referer': 'https://www.raiplay.it/'
                })
                self.session.open(Playstream2, self.name, url)
        except Exception as e:
            print('Error playing direct: ' + str(e))
            self.session.open(MessageBox, _("Error playing stream"), MessageBox.TYPE_ERROR)

    def playHLS(self, url):
        """Playback via HLS client"""
        try:
            if "raiplay.it/raiplay/video" in url and (".html" in url or "?json" in url):
                url = url.replace('.html?json', '.json')
                video_url = extract_real_video_url(url)
                if video_url:
                    url = video_url

            if "relinkerServlet" in url:
                url = self.add_relinker_param(url, "64")
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            self.session.open(Playstream2, self.name, url)
        except Exception as e:
            print('Error playing HLS: ' + str(e))
            self.session.open(MessageBox, _("Error playing HLS stream"), MessageBox.TYPE_ERROR)

    def playTS(self, url):
        """Playback via TS client (fallback)"""
        try:
            if "raiplay.it/raiplay/video" in url and (".html" in url or "?json" in url):
                video_url = extract_real_video_url(url)
                url = url.replace('.html?json', '.json')
                if video_url:
                    url = video_url

            if "relinkerServlet" in url:
                url = self.add_relinker_param(url, "47")
            url = strwithmeta(url, {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                'Referer': 'https://www.raiplay.it/'
            })
            ref = "4097:0:1:0:0:0:0:0:0:0:{}".format(quote(url))
            sref = eServiceReference(ref)
            sref.setName(self.name)
            self.session.nav.playService(sref)
        except Exception as e:
            print('Error playing TS: ' + str(e))
            self.session.open(MessageBox, _("Error playing TS stream"), MessageBox.TYPE_ERROR)

    def cancel(self):
        try:
            self.session.nav.stopService()
            self.session.nav.playService(self.srefInit)
            self.close()
        except:
            pass


class Playstream2(Screen, InfoBarMenu, InfoBarBase, InfoBarSeek, InfoBarNotifications, InfoBarAudioSelection, TvInfoBarShowHide, InfoBarSubtitleSupport):
    STATE_IDLE = 0
    STATE_PLAYING = 1
    STATE_PAUSED = 2
    ENABLE_RESUME_SUPPORT = True
    ALLOW_SUSPEND = True
    screen_timeout = 5000

    def __init__(self, session, name, url):
        global streaml, _session
        Screen.__init__(self, session)
        self.session = session
        self.skinName = 'MoviePlayer'
        _session = session
        streaml = False
        InfoBarMenu.__init__(self)
        InfoBarNotifications.__init__(self)
        InfoBarBase.__init__(self, steal_current_service=True)
        TvInfoBarShowHide.__init__(self)
        InfoBarAudioSelection.__init__(self)
        InfoBarSubtitleSupport.__init__(self)
        self['actions'] = ActionMap(['WizardActions', 'MoviePlayerActions', 'MovieSelectionActions', 'MediaPlayerActions', 'EPGSelectActions', 'MediaPlayerSeekActions', 'ColorActions',
                                     'ButtonSetupActions', 'InfobarShowHideActions', 'InfobarActions', 'InfobarSeekActions'], {
            'leavePlayer': self.cancel,
            # 'epg': self.showIMDB,
            # 'info': self.showIMDB,
            # 'info': self.cicleStreamType,
            'tv': self.cicleStreamType,
            'stop': self.leavePlayer,
            'cancel': self.cancel,
            'back': self.cancel
        }, -1)
        self.allowPiP = False
        self.service = None
        InfoBarSeek.__init__(self, actionmap='InfobarSeekActions')
        self.url = url
        self.name = html_unescape(name)
        self.state = self.STATE_PLAYING
        self.srefInit = self.session.nav.getCurrentlyPlayingServiceReference()
        if '8088' in str(self.url):
            self.onFirstExecBegin.append(self.slinkPlay)
        else:
            self.onFirstExecBegin.append(self.cicleStreamType)
        return

    def showIMDB(self):
        text_clear = self.name
        if returnIMDB(text_clear):
            print('show imdb/tmdb')

    def slinkPlay(self):
        ref = str(self.url)
        ref = ref.replace(':', '%3a').replace(' ', '%20')
        print('final reference: 1', ref)
        sref = eServiceReference(ref)
        sref.setName(self.name)
        self.session.nav.stopService()
        self.session.nav.playService(sref)

    def openTest(self, servicetype, url):
        url = url.replace(':', '%3a').replace(' ', '%20')
        ref = str(servicetype) + ':0:1:0:0:0:0:0:0:0:' + str(url)
        if streaml is True:
            ref = str(servicetype) + ':0:1:0:0:0:0:0:0:0:http%3a//127.0.0.1%3a8088/' + str(url)
        print('final reference 2:   ', ref)
        sref = eServiceReference(ref)
        sref.setName(self.name)
        self.session.nav.stopService()
        self.session.nav.playService(sref)

    def cicleStreamType(self):
        from itertools import cycle, islice
        self.servicetype = '4097'
        print('servicetype1: ', self.servicetype)
        url = str(self.url)
        if str(splitext(url)[-1]) == ".m3u8":
            if self.servicetype == "1":
                self.servicetype = "4097"
        currentindex = 0
        streamtypelist = ["4097"]
        for index, item in enumerate(streamtypelist, start=0):
            if str(item) == str(self.servicetype):
                currentindex = index
                break
        nextStreamType = islice(cycle(streamtypelist), currentindex + 1, None)
        self.servicetype = str(next(nextStreamType))
        print('servicetype2: ', self.servicetype)
        self.openTest(self.servicetype, url)

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
        self.session.nav.playService(self.srefInit)
        aspect_manager.restore_aspect
        self.close()

    def leavePlayer(self):
        self.session.nav.stopService()
        self.session.nav.playService(self.srefInit)
        self.close()


def main(session, **kwargs):
    try:
        session.open(RaiPlayMain)
    except Exception as e:
        print("Error starting plugin:", str(e))
        import traceback
        traceback.print_exc()
        session.open(MessageBox, _("Error starting plugin"), MessageBox.TYPE_ERROR)


def Plugins(**kwargs):
    from Plugins.Plugin import PluginDescriptor
    ico_path = 'logo.png'
    if not exists('/var/lib/dpkg/status'):
        ico_path = plugin_path + '/res/pics/logo.png'
    extensions_menu = PluginDescriptor(name=name_plugin, description=desc_plugin, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=main, needsRestart=True)
    result = [PluginDescriptor(name=name_plugin, description=desc_plugin, where=PluginDescriptor.WHERE_PLUGINMENU, icon=ico_path, fnc=main)]
    result.append(extensions_menu)
    return result

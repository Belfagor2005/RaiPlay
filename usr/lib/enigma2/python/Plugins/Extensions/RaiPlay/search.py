# -*- coding: utf-8 -*-

import sys
import json
import urllib
import sys
import datetime

PY3 = sys.version_info.major >= 3

if PY3:
    import urllib.request as urllib2

else:
    import urllib2

try:
    unicode = unicode
except NameError:
    unicode = str


def sortedDictKeys(adict):
    keys = list(adict.keys())
    keys.sort()
    return keys


def daterange(start_date, end_date):
    for n in range((end_date - start_date).days + 1):
        yield end_date - datetime.timedelta(n)


def checkStr(txt):
    # convert variable to type str both in Python 2 and 3

    if PY3:
        # Python 3
        if isinstance(txt, type(bytes())):
            txt = txt.decode('utf-8')
    else:
        # Python 2
        if isinstance(txt, type(unicode())):
            txt = txt.encode('utf-8')

    return txt


class Search:
    baseUrl = "http://www.rai.it"

    newsArchives = {"TG1": "NomeProgramma:TG1^Tematica:Edizioni integrali",
                    "TG2": "NomeProgramma:TG2^Tematica:Edizione integrale",
                    "TG3": "NomeProgramma:TG3^Tematica:Edizioni del TG3"}

    newsProviders = {
        "TG1": "Tematica:TG1",
        "TG2": "Tematica:TG2",
        "TG3": "Tematica:TG3",
        "Rai News": "Tematica:Rai News",
        "Rai Sport": "Tematica:spt",
        "Rai Parlamento": "PageOB:Page-f3f817b3-1d55-4e99-8c36-464cea859189"}

    tematiche = [
        "Attualità",
        "Bianco e Nero",
        "Cinema",
        "Comici",
        "Cronaca",
        "Cucina",
        "Cultura",
        "Cultura e Spettacoli",
        "Economia",
        "Fiction",
        "Hi tech",
        "Inchieste",
        "Incontra",
        "Interviste",
        "Istituzioni",
        "Junior",
        "Moda",
        "Musica",
        "News",
        "Politica",
        "Promo",
        "Reality",
        "Salute",
        "Satira",
        "Scienza",
        "Società",
        "Spettacolo",
        "Sport",
        "Storia",
        "Telefilm",
        "Tempo libero",
        "Viaggi"]

    def getLastContentByTag(self, tags="", numContents=16):
        try:
            tags = urllib.quote(tags)
        except BaseException:
            tags = urllib.parse.quote(tags)

        domain = "RaiTv"
        xsl = "rai_tv-statistiche-raiplay-json"

        url = self.baseUrl + "/StatisticheProxy/proxyPost.jsp?action=getLastContentByTag&numContents=%s&tags=%s&domain=%s&xsl=%s" % \
            (str(numContents), tags, domain, xsl)

        data = urllib2.urlopen(url).read()
        data = checkStr(data)
        try:
            response = json.loads(data)
            return response["list"]
        except BaseException:
            # xbmc.log(data)
            return {}

    def getMostVisited(self, tags, days=7, numContents=16):
        try:
            tags = urllib.quote(tags)
        except BaseException:
            tags = urllib.parse.quote(tags)
        domain = "RaiTv"
        xsl = "rai_tv-statistiche-raiplay-json"
        url = self.baseUrl + "/StatisticheProxy/proxyPost.jsp?action=mostVisited&days=%s&state=1&records=%s&tags=%s&domain=%s&xsl=%s" % \
            (str(days), str(numContents), tags, domain, xsl)
        response = json.loads(checkStr(urllib2.urlopen(url).read()))
        return response["list"]

#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import

__author__ = "Lululla"
__email__ = "ekekaz@gmail.com"
__copyright__ = "Copyright (c) 2024 Lululla"
__license__ = "GPL-v2"
__version__ = "1.0.0"

from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
import gettext
from os import environ as os_environ
import os

PluginLanguageDomain = 'RaiPlay'
PluginLanguagePath = 'Extensions/RaiPlay/res/locale'


def paypal():
	conthelp = "If you like what I do you\n"
	conthelp += "can contribute with a coffee\n"
	conthelp += "scan the qr code and donate € 1.00"
	return conthelp


isDreambox = os.path.exists("/usr/bin/apt-get")


def localeInit():
	if isDreambox:
		lang = language.getLanguage()[:2]
		os_environ["LANGUAGE"] = lang
	if PluginLanguageDomain and PluginLanguagePath:
		gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


if isDreambox:
	def _(txt):
		return gettext.dgettext(PluginLanguageDomain, txt) if txt else ""

else:
	def _(txt):
		translated = gettext.dgettext(PluginLanguageDomain, txt)
		if translated:
			return translated
		else:
			print("[%s] fallback to default translation for %s" % (PluginLanguageDomain, txt))
											   
			return gettext.gettext(txt)

localeInit()
language.addCallback(localeInit)

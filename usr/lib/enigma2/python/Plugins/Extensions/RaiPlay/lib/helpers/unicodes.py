# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals

"""Implements Unicode Helper functions (Python 3 only)"""
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


def to_unicode(text, encoding="utf-8", errors="strict"):
    """Force text to unicode (Python 3: str)"""
    if isinstance(text, bytes):
        return text.decode(encoding, errors)
    return text


def from_unicode(text, encoding="utf-8", errors="strict"):
    """Convert unicode (str) to bytes if needed"""
    if isinstance(text, str):
        return text.encode(encoding, errors)
    return text


def compat_path(path, encoding="utf-8", errors="strict"):
    """Return path as is – Python 3 handles Unicode paths natively"""
    return path

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

"""Implements Unicode Helper functions"""


def to_unicode(text, encoding="utf-8", errors="strict"):
    """Force text to unicode"""
    if isinstance(text, bytes):
        return text.decode(encoding, errors)
    return text


def from_unicode(text, encoding="utf-8", errors="strict"):
    """Force unicode to text"""
    import sys
    if sys.version_info.major == 2 and isinstance(
        text, unicode  # noqa: F821; pylint: disable=undefined-variable,useless-suppression
    ):
        return text.encode(encoding, errors)
    return text


def compat_path(path, encoding="utf-8", errors="strict"):
    """Convert unicode path to bytestring if needed"""
    import sys
    if (
        sys.version_info.major == 2
        and isinstance(
            path, unicode  # noqa: F821; pylint: disable=undefined-variable,useless-suppression
        )
        and not sys.platform.startswith("win")
    ):
        return path.encode(encoding, errors)
    return path

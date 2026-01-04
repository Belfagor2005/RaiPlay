#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
###########################################################
#  RaiPlay for Enigma2                                    #
#  Created by: Lululla                                    #
###########################################################
Last Updated: 2025-12-26
Credits: Lululla (modifications)
Homepage: www.corvoboys.org www.linuxsat-support.com
###########################################################
"""
from __future__ import print_function
import os
import re
import sys
import subprocess
import codecs
from xml.etree import ElementTree as ET

PLUGIN_NAME = "RaiPlay"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(PLUGIN_DIR, 'res', "locale")
POT_FILE = os.path.join(LOCALE_DIR, "%s.pot" % PLUGIN_NAME)


# =========================================================
# SUBPROCESS HELPER (Py2 / Py3)
# =========================================================
def run_cmd(cmd):
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        out, err = p.communicate()
        return p.returncode, out, err
    except Exception as e:
        return 1, b"", str(e).encode("utf-8")


# =========================================================
# XML STRINGS
# =========================================================
def extract_xml_strings():
    xml_file = os.path.join(PLUGIN_DIR, "setup.xml")

    if not os.path.exists(xml_file):
        print("ERROR: %s not found!" % xml_file)
        return []

    strings = []
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        for elem in root.findall(".//*[@text]"):
            text = elem.get("text", "").strip()
            if text and not re.match(r'^#[0-9a-fA-F]{6,8}$', text):
                strings.append(text)

        for elem in root.findall(".//*[@description]"):
            desc = elem.get("description", "").strip()
            if desc and not re.match(r'^#[0-9a-fA-F]{6,8}$', desc):
                strings.append(desc)

        for elem in root.findall(".//*[@title]"):
            title = elem.get("title", "").strip()
            if title:
                strings.append(title)

    except Exception as e:
        print("ERROR parsing XML:", e)
        return []

    unique = sorted(set(strings))
    print("XML: found %d unique strings" % len(unique))
    return unique


# =========================================================
# PYTHON STRINGS (xgettext)
# =========================================================
def extract_python_strings():
    py_strings = []
    temp_pot = os.path.join(PLUGIN_DIR, "temp_python.pot")

    py_files = []
    for root_dir, _, files in os.walk(PLUGIN_DIR):
        for f in files:
            if f.endswith(".py") and not f.startswith("test_"):
                py_files.append(os.path.join(root_dir, f))

    if not py_files:
        print("No .py files found")
        return []

    cmd = [
        "xgettext",
        "--no-wrap",
        "-L", "Python",
        "--from-code=UTF-8",
        "-kpgettext:1c,2",
        "--add-comments=TRANSLATORS:",
        "-d", PLUGIN_NAME,
        "-s",
        "-o", temp_pot
    ] + py_files

    ret, out, err = run_cmd(cmd)
    if ret != 0:
        print("ERROR xgettext:", err)
        return []

    if os.path.exists(temp_pot):
        with codecs.open(temp_pot, "r", "utf-8") as f:
            content = f.read()
            for m in re.finditer(r'msgid "([^"]+)"', content):
                txt = m.group(1).strip()
                if txt:
                    py_strings.append(txt)
        os.remove(temp_pot)

    print("Python: found %d strings" % len(py_strings))
    return sorted(set(py_strings))


# =========================================================
# POT FILE
# =========================================================
def update_pot_file(xml_strings, py_strings):
    if not os.path.exists(LOCALE_DIR):
        os.makedirs(LOCALE_DIR)

    all_strings = sorted(set(xml_strings + py_strings))
    print("TOTAL: %d unique strings" % len(all_strings))

    existing = {}
    header = ""

    if os.path.exists(POT_FILE):
        with codecs.open(POT_FILE, "r", "utf-8") as f:
            content = f.read()
            parts = content.split('msgid "')
            if len(parts) > 1:
                header = parts[0]
            for m in re.finditer(r'msgid "([^"]+)"\s*\nmsgstr "([^"]*)"', content):
                existing[m.group(1)] = m.group(2)

    with codecs.open(POT_FILE, "w", "utf-8") as f:
        if header:
            f.write(header)
        else:
            f.write('# %s translations\n' % PLUGIN_NAME)
            f.write('msgid ""\nmsgstr ""\n')
            f.write('"Project-Id-Version: %s\\n"\n' % PLUGIN_NAME)
            f.write('"Content-Type: text/plain; charset=UTF-8\\n"\n\n')

        for msgid in all_strings:
            f.write('\nmsgid "%s"\n' % msgid)
            f.write('msgstr "%s"\n' % existing.get(msgid, ""))

    print("Updated .pot file:", POT_FILE)
    return len(all_strings)


# =========================================================
# PO FILES
# =========================================================
def update_po_files():
    if not os.path.exists(POT_FILE):
        print("ERROR: .pot file not found")
        return

    for lang in os.listdir(LOCALE_DIR):
        lang_path = os.path.join(LOCALE_DIR, lang)

        # ✅ SKIP: non directory
        if not os.path.isdir(lang_path):
            continue

        # ✅ SKIP: cartelle non-lingua
        if lang in ("templates", ".git", ".svn"):
            continue

        po_dir = os.path.join(lang_path, "LC_MESSAGES")
        po_file = os.path.join(po_dir, "%s.po" % PLUGIN_NAME)

        if os.path.exists(po_file):
            print("Updating:", lang)
            cmd = ["msgmerge", "--update", "--no-wrap", "-s", po_file, POT_FILE]
            ret, out, err = run_cmd(cmd)
            if ret != 0:
                print("  ERROR:", err)
        else:
            if not os.path.exists(po_dir):
                os.makedirs(po_dir)
            cmd = ["msginit", "-i", POT_FILE, "-o", po_file, "-l", lang]
            run_cmd(cmd)
            print("Created:", lang)



# =========================================================
# MO FILES
# =========================================================
def compile_mo_files():
    for lang in os.listdir(LOCALE_DIR):
        lang_path = os.path.join(LOCALE_DIR, lang)

        if not os.path.isdir(lang_path):
            continue

        po_dir = os.path.join(lang_path, "LC_MESSAGES")
        po_file = os.path.join(po_dir, "%s.po" % PLUGIN_NAME)
        mo_file = os.path.join(po_dir, "%s.mo" % PLUGIN_NAME)

        if os.path.exists(po_file):
            cmd = ["msgfmt", po_file, "-o", mo_file]
            ret, out, err = run_cmd(cmd)
            if ret == 0:
                print("Compiled:", lang)
            else:
                print("ERROR compiling:", lang, err)



# =========================================================
# MAIN
# =========================================================
def main():
    print("=" * 50)
    print("UPDATING TRANSLATIONS:", PLUGIN_NAME)
    print("=" * 50)

    xml_strings = extract_xml_strings()
    py_strings = extract_python_strings()

    if not xml_strings and not py_strings:
        print("No strings found!")
        return

    total = update_pot_file(xml_strings, py_strings)
    update_po_files()
    compile_mo_files()

    print("=" * 50)
    print("COMPLETED:", total, "strings")
    print("=" * 50)


if __name__ == "__main__":
    main()
    
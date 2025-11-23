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
# 🧩 ENIGMA2 COMPONENTS
from Components.Label import Label

# 🪟 ENIGMA2 SCREENS
# from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

# 🧰 ENIGMA2 TOOLS
# from Tools.Notifications import AddNotification

# 📺 ENIGMA2 CORE
from enigma import eTimer

# 🌐 EXTERNAL / SYSTEM
# import NavigationInstance


class SimpleNotifyWidget(Screen):
    """Simple notification widget for Enigma2 plugins"""

    skin = """
    <screen name="SimpleNotifyWidget" position="center,30" zPosition="10" size="600,80" title=" " backgroundColor="#201F1F1F" flags="wfNoBorder">
        <widget name="notification_text" font="Regular;20" position="5,5" zPosition="2" valign="center" halign="center" size="585,70" foregroundColor="#00FF00" backgroundColor="#201F1F1F" transparent="1" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.skin = SimpleNotifyWidget.skin
        self["notification_text"] = Label("")
        self.onLayoutFinish.append(self._setupUI)

    def _setupUI(self):
        """Setup UI after layout completion"""
        # Safe method call - only call if the method exists
        try:
            # Check if the method exists before calling it
            if hasattr(self.instance, 'setAnimationMode'):
                self.instance.setAnimationMode(0)  # Disable animations
            else:
                print(
                    "[NOTIFY] setAnimationMode not available in this Enigma2 version")
        except Exception as e:
            print(f"[NOTIFY] Error in _setupUI: {e}")
        # Animation mode is not critical, so we continue even if it fails

    def updateMessage(self, text):
        """Update notification text"""
        self["notification_text"].setText(text)


class HybridNotificationManager:
    """Hybrid notification manager - works both inside and outside plugin"""

    def __init__(self):
        self.notification_window = None
        self.hide_timer = eTimer()
        self.hide_timer.callback.append(self._hideNotification)
        self.is_initialized = False

    def initialize(self, session):
        """Initialize manager with session"""
        if not self.is_initialized:
            self.notification_window = session.instantiateDialog(
                SimpleNotifyWidget)
            self.is_initialized = True

    def _hideNotification(self):
        """Hide notification (timer callback)"""
        if self.notification_window:
            self.notification_window.hide()

    def _show_global_notification(self, message, duration=3000):
        """Show global notification - THE ORIGINAL VERSION"""
        try:
            # Check if we can use screen notification first
            if self.notification_window and self.is_initialized:
                self.hide_timer.stop()
                self.notification_window.updateMessage(message)
                self.notification_window.show()
                self.hide_timer.start(duration, True)
                print(f"[SCREEN NOTIFY] {message}")
                return True

            # Fallback for outside plugin - only for download messages
            if not self.is_initialized:
                allowed_messages = [
                    'Download completed',
                    'Download error',
                    'Download failed']
                if any(allowed in message for allowed in allowed_messages):
                    # Use screen notification even outside plugin for important
                    # messages
                    if self.notification_window:
                        self.hide_timer.stop()
                        self.notification_window.updateMessage(message)
                        self.notification_window.show()
                        self.hide_timer.start(duration, True)
                        print(f"[SCREEN NOTIFY - OUTSIDE] {message}")
                        return True

            return False

        except Exception as e:
            print(f"[NOTIFY ERROR] {e}")
            return False

    def _show_global_notification_all(self, message, timeout=5000):
        """Show global Enigma2 notification - USING SCREEN"""
        try:
            if self.notification_window:
                self.hide_timer.stop()
                self.notification_window.updateMessage(message)
                self.notification_window.show()
                self.hide_timer.start(timeout, True)
                print(f"[HYBRID NOTIFY] Screen notification: {message}")
                return True
            return False
        except Exception as e:
            print(f"[HYBRID NOTIFY] Screen notification error: {e}")
            return False

    def showMessage(self, message, duration=3000):
        """The original version you had"""
        self._show_global_notification(message, duration)

    """
    def showMessage(self, message, duration=3000):
        # If we are OUTSIDE the plugin, only show important download
        # notifications
        if not self.is_initialized:
            allowed_messages = [
                'Download completed',
                'Download error',
                'Download failed']
            if not any(allowed in message for allowed in allowed_messages):
                print(f"[NOTIFY FILTER] Skipped (outside plugin): {message}")
                return

        # NOTIFICATION PLUGIN ONLY - NO GLOBAL!
        if self.is_initialized and self.notification_window:
            try:
                # Stop any previous timer
                self.hide_timer.stop()

                # Update and show message
                self.notification_window.updateMessage(message)
                self.notification_window.show()

                # Start auto-hide timer
                self.hide_timer.start(duration, True)
                print(f"[HYBRID NOTIFY] Plugin notification: {message}")

            except Exception as e:
                print(f"[HYBRID NOTIFY] Plugin notification error: {e}")
        else:
            print("[HYBRID NOTIFY] Plugin not initialized - NO NOTIFICATION")
    """

    def show_download_status(self, title, status, file_size=0):
        """Display a download status notification"""
        icons = {
            'completed': '✅',
            'error': '❌',
            'downloading': '🚀',
            'paused': '⏸️',
            'queued': '📥'
        }

        icon = icons.get(status, 'ℹ️')

        if status == 'completed' and file_size > 0:
            size_mb = file_size / (1024 * 1024)
            message = f"{icon} {title}\nCompleted - {size_mb:.1f}MB"
        elif status == 'downloading':
            message = f"{icon} Downloading\n{title}"
        elif status == 'error':
            message = f"{icon} Download error\n{title}"
        elif status == 'paused':
            message = f"{icon} Download paused\n{title}"
        else:
            message = f"{icon} {title}"

        # self._show_global_notification(message, 5000)
        self.showMessage(message, 5000)  # 5 seconds for download notifications

    def show(self, message, seconds=3):
        """Simplified version with duration in seconds"""
        self.showMessage(message, seconds * 1000)

    def hide(self):
        """Hide notification immediately"""
        self.hide_timer.stop()
        self._hideNotification()


# Global hybrid notification manager instance
_hybrid_notification_manager = HybridNotificationManager()


def cleanup_notifications():
    """Clean up notifications when plugin closes"""
    _hybrid_notification_manager.hide()
    print("[NOTIFY] Cleanup on plugin exit")


# Public API functions
def init_notification_system(session):
    """
    Initialize notification system (call this once in your plugin)

    Args:
        session: Enigma2 session object
    """
    _hybrid_notification_manager.initialize(session)


def show_notification(message, duration=3000):
    """
    Show a hybrid notification message (works everywhere)

    Args:
        message (str): Text to display
        duration (int): Display duration in milliseconds (default: 3000)
    """
    _hybrid_notification_manager.showMessage(message, duration)


def show_download_notification(title, status, file_size=0):
    """Show plugin-only notification for download status."""
    icons = {
        'completed': '✅',
        'error': '❌',
        'downloading': '🚀',
        'paused': '⏸️'
    }
    icon = icons.get(status, 'ℹ️')

    if status == 'completed' and file_size > 0:
        size_mb = file_size / (1024 * 1024)
        message = f"{icon} {title}\nCompleted - {size_mb:.1f}MB"
    else:
        message = f"{icon} {title}"

    # USE PLUGIN NOTIFICATION ONLY – NO GLOBAL NOTIFICATION!
    if _hybrid_notification_manager.is_initialized and _hybrid_notification_manager.notification_window:
        try:
            _hybrid_notification_manager.hide_timer.stop()
            _hybrid_notification_manager.notification_window.updateMessage(
                message)
            _hybrid_notification_manager.notification_window.show()
            _hybrid_notification_manager.hide_timer.start(5000, True)
            print(f"[DOWNLOAD NOTIFY] Plugin notification: {message}")
        except Exception as e:
            print(f"[DOWNLOAD NOTIFY] Error: {e}")


def show_download_notification_all(title, status, file_size=0):
    """
    Show download-specific notification

    Args:
        title (str): Download title
        status (str): download status
        file_size (int): file size in bytes
    """
    icons = {
        'completed': '✅',
        'error': '❌',
        'downloading': '🚀',
        'paused': '⏸️'}
    icon = icons.get(status, 'ℹ️')

    if status == 'completed' and file_size > 0:
        size_mb = file_size / (1024 * 1024)
        message = f"{icon} {title}\nCompleted - {size_mb:.1f}MB"
    else:
        message = f"{icon} {title}"

    _hybrid_notification_manager.showMessage(message, 5000)


def quick_notify(message, seconds=3):
    """
    Quick notification with duration in seconds

    Args:
        message (str): Text to display
        seconds (int): Display duration in seconds (default: 3)
    """
    _hybrid_notification_manager.show(message, seconds)


def hide_current_notification():
    """Hide the current notification immediately"""
    _hybrid_notification_manager.hide()


# =============================================================================
# USAGE EXAMPLES - How to use in your plugins
# =============================================================================

"""
from .notification_system import init_notification_system, quick_notify, show_notification

# 1. INITIALIZATION (in your main plugin class)
class MyPlugin(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        # Initialize notification system once
        init_notification_system(session)

# 2. BASIC USAGE
# Show 3-second notification
show_notification("Processing completed!")

# Show 5-second notification
show_notification("Download finished", 5000)

# Simplified version (seconds instead of milliseconds)
quick_notify("File saved successfully")

# Longer notification
quick_notify("Backup completed successfully", 5)

# Hide manually if needed
hide_current_notification()

# 3. AFTER OPERATIONS
def on_download_finished(self, success, filename):
    if success:
        quick_notify(f"Downloaded: {filename}")
    else:
        quick_notify("Download failed!", 5)

def on_processing_done(self, result):
    quick_notify(f"Processed {result.file_count} files")

# 4. ERROR NOTIFICATIONS
def handle_error(self, error_message):
    quick_notify(f"Error: {error_message}", 5)
"""

# -*- coding: utf-8 -*-

from __future__ import (absolute_import, unicode_literals, division,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2020, Jim Miller'
__docformat__ = 'restructuredtext en'

import re
from functools import partial

import logging
logger = logging.getLogger(__name__)


from datetime import datetime

from PyQt5 import QtWidgets as QtGui
from PyQt5 import QtCore
from PyQt5.Qt import (QApplication, QDialog, QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                      QHBoxLayout, QGridLayout, QPushButton, QFont, QLabel, QCheckBox, QIcon,
                      QLineEdit, QComboBox, QProgressDialog, QTimer, QDialogButtonBox,
                      QScrollArea, QPixmap, Qt, QAbstractItemView, QTextEdit,
                      pyqtSignal, QGroupBox, QFrame, QTextCursor)
try:
    # qt6 Calibre v6+
    QTextEditNoWrap = QTextEdit.LineWrapMode.NoWrap
    MoveOperations = QTextCursor.MoveOperation
    MoveMode = QTextCursor.MoveMode
except:
    # qt5 Calibre v2-5
    QTextEditNoWrap = QTextEdit.NoWrap
    MoveOperations = QTextCursor
    MoveMode = QTextCursor

from calibre.gui2 import gprefs
show_download_options = 'fff:add new/update dialogs:show_download_options'
from calibre.gui2.dialogs.confirm_delete import confirm
from calibre.gui2.complete2 import EditWithComplete
from fanficfare.six import text_type as unicode, ensure_text

# pulls in translation files for _() strings
try:
    load_translations()
except NameError:
    pass # load_translations() added in calibre 1.9

from calibre_plugins.fanficfare_plugin.common_utils import (
    ReadOnlyTableWidgetItem, ReadOnlyTextIconWidgetItem,
    SizePersistedDialog, EditableTableWidgetItem,
    ImageTitleLayout, get_icon)

from fanficfare.geturls import get_urls_from_mime
from fanficfare.adapters import getNormalStoryURL

from fanficfare.configurable import (
    get_valid_sections, get_valid_entries,
    get_valid_keywords, get_valid_entry_keywords)

from .inihighlighter import IniHighlighter

## moved to prefs.py so they can be included in jobs.py.
from calibre_plugins.fanficfare_plugin.prefs import (
    SKIP,
    ADDNEW,
    UPDATE,
    UPDATEALWAYS,
    OVERWRITE,
    OVERWRITEALWAYS,
    CALIBREONLY,
    CALIBREONLYSAVECOL,
    collision_order,
    save_collisions,
    anthology_collision_order,
    )

gpstyle='QGroupBox {border:0; padding-top:10px; padding-bottom:0px; margin-bottom:0px;}' #  background-color:red;

class RejectUrlEntry:

    matchpat=re.compile(r"^(?P<url>[^,]+?)(,(?P<fullnote>(((?P<title>.+?) by (?P<auth>.+?)( - (?P<note>.+))?)|.*)))?$")

    def __init__(self,url_or_line,note=None,title=None,auth=None,
                 addreasontext=None,fromline=False,book_id=None,
                 normalize=True):

        self.url=url_or_line
        self.note=note
        self.title=title
        self.auth=auth
        self.valid=False
        self.book_id=book_id

        if fromline:
            mc = re.match(self.matchpat,url_or_line)
            if mc:
                #print("mc:%s"%mc.groupdict())
                (url,title,auth,note) = mc.group('url','title','auth','note')
                if not mc.group('title'):
                    title=''
                    auth=''
                    note=mc.group('fullnote')
                self.url=url
                self.note=note
                self.title=title
                self.auth=auth

        if not self.note:
            if addreasontext:
                self.note = addreasontext
            else:
                self.note = ''
        else:
            if addreasontext:
                self.note = self.note + ' - ' + addreasontext

        if normalize and self.url:
            self.url = getNormalStoryURL(self.url)

        self.valid = self.url != None

    def to_line(self):
        # always 'url,'
        return "%s,%s"%(self.url,self.fullnote())

    @classmethod
    def from_data(cls,data):
        rue = cls('')
        rue.url=data['url']
        rue.title=data['title']
        rue.auth=data['auth']
        rue.note=data['note']
        rue.valid=True
        # rue.book_id=book_id
        return rue

    def to_data(self):
        return { 'url': self.url,
                 'title': self.title,
                 'auth': self.auth,
                 'note': self.note,
                 }

    def fullnote(self):
        retval = ""
        if self.title and self.auth:
            # don't translate--ends up being saved and confuses regex above.
            retval = retval + "%s by %s"%(self.title,self.auth)
            if self.note:
                retval = retval + " - "

        if self.note:
            retval = retval + self.note

        return retval

class NotGoingToDownload(Exception):
    def __init__(self,error,icon='dialog_error.png',showerror=True):
        self.error=error
        self.icon=icon
        self.showerror=showerror

    def __str__(self):
        return self.error

class DroppableQTextEdit(QTextEdit):
    def __init__(self,parent):
        QTextEdit.__init__(self,parent)
        self.setTabChangesFocus(True)

    def dropEvent(self,event):
        # logger.debug("dropEvent")
        urllist = get_urls_from_mime(event.mimeData())
        if urllist:
            self.append("\n".join(urllist))
            return None
        return QTextEdit.dropEvent(self,event)

    def insertFromMimeData(self, mime_data):
        # logger.debug("insertFromMimeData")
        # logger.debug(mime_data)
        urllist = None
        if mime_data.hasFormat('text/html'):
            urllist = get_urls_from_mime(mime_data)
            # logger.debug(urllist)
        if urllist:
            [ self.append(url) for url in urllist ]
        else:
            return QTextEdit.insertFromMimeData(self, mime_data)

class HotKeyedSizePersistedDialog(SizePersistedDialog):

    def __init__(self, gui, save_size_name):
        super(HotKeyedSizePersistedDialog,self).__init__(gui, save_size_name)
        self.keys=dict()

    def addCtrlKeyPress(self,key,func):
        # print("addKeyPress: key(0x%x)"%key)
        # print("control: 0x%x"%QtCore.Qt.ControlModifier)
        self.keys[key]=func

    def keyPressEvent(self, event):
        # print("event: key(0x%x) modifiers(0x%x)"%(event.key(),event.modifiers()))
        if (event.modifiers() & QtCore.Qt.ControlModifier) and event.key() in self.keys:
            func = self.keys[event.key()]
            return func()
        else:
            return super(HotKeyedSizePersistedDialog,self).keyPressEvent(event)

class AddNewDialog(HotKeyedSizePersistedDialog):

    go_signal = pyqtSignal(object, object, object, object)

    def __init__(self, gui, prefs, icon):
        super(AddNewDialog,self).__init__(gui, 'fff:add new dialog')

        self.prefs = prefs

        self.setMinimumWidth(300)
        self.l = QVBoxLayout()
        self.setLayout(self.l)

        self.setWindowTitle('FanFicFare')
        self.setWindowIcon(icon)

        self.merge = self.newmerge = False
        self.extraoptions = {}

        # elements to hide when doing merge.
        self.mergehide = []
        self.mergeshow = []
        # elements to show again when doing *update* merge
        self.mergeupdateshow = []

        self.toplabel=QLabel("Toplabel")
        self.l.addWidget(self.toplabel)

        ## scrollable area for lengthy series comments.
        scrollable = QScrollArea()
        scrollcontent = QWidget()
        scrollable.setWidget(scrollcontent)
        scrollable.setWidgetResizable(True)
        self.l.addWidget(scrollable)

        grid = QGridLayout()
        scrollcontent.setLayout(grid)
        self.mergeshow.append(scrollable)

        row = 0
        label = QLabel('<b>'+_('Series')+':</b>')
        grid.addWidget(label,row,0)
        self.mergedname=QLabel("mergedname")
        tt = _('This name will be used with the %s setting to set the title of the new book.')%'<i>anthology_title_pattern</i>'
        label.setToolTip(tt)
        self.mergedname.setToolTip(tt)
        grid.addWidget(self.mergedname,row,1,1,-1)

        row+=1
        label = QLabel('<b>'+_('Comments')+':</b>')
        grid.addWidget(label,row,0)
        self.mergeddesc=QLabel("mergeddesc")
        tt = _('These comments about the series will be included in the Comments of the new book.')+'<i></i>' # for html for auto-wrap
        label.setToolTip(tt)
        self.mergeddesc.setToolTip(tt)
        self.mergeddesc.setWordWrap(True)
        grid.addWidget(self.mergeddesc,row,1,1,-1)
        grid.setColumnStretch(1,1)

        self.url = DroppableQTextEdit(self)
        self.url.setToolTip("UrlTooltip")
        self.url.setLineWrapMode(QTextEditNoWrap)
        self.l.addWidget(self.url,1) # 1 higher 'stretch'==higher priority

        self.groupbox = QGroupBox(_("Show Download Options"))
        self.groupbox.setCheckable(True)
        self.groupbox.setFlat(True)
        #print("style:%s"%self.groupbox.styleSheet())
        self.groupbox.setStyleSheet(gpstyle)

        self.gbf = QFrame()
        self.gbl = QVBoxLayout()
        self.gbl.addWidget(self.gbf)
        self.groupbox.setLayout(self.gbl)
        self.gbl = QVBoxLayout()
        self.gbf.setLayout(self.gbl)
        self.l.addWidget(self.groupbox)

        self.groupbox.setChecked(gprefs.get(show_download_options,False))
        self.gbf.setVisible(gprefs.get(show_download_options,False))
        self.groupbox.toggled.connect(self.click_show_download_options)

        horz = QHBoxLayout()
        label = QLabel(_('Output &Format:'))
        self.mergehide.append(label)

        self.fileform = QComboBox(self)
        self.fileform.addItem('epub')
        self.fileform.addItem('mobi')
        self.fileform.addItem('html')
        self.fileform.addItem('txt')
        self.fileform.setToolTip(_('Choose output format to create.  May set default from plugin configuration.'))
        self.fileform.activated.connect(self.set_collisions)

        horz.addWidget(label)
        label.setBuddy(self.fileform)
        horz.addWidget(self.fileform)
        self.gbl.addLayout(horz)
        self.mergehide.append(self.fileform)

        horz = QHBoxLayout()
        self.collisionlabel = QLabel("CollisionLabel")
        horz.addWidget(self.collisionlabel)
        self.collision = QComboBox(self)
        self.collision.setToolTip("CollisionToolTip")
        # add collision options
        self.set_collisions()
        i = self.collision.findText(save_collisions[self.prefs['collision']])
        if i > -1:
            self.collision.setCurrentIndex(i)
        self.collisionlabel.setBuddy(self.collision)
        horz.addWidget(self.collision)
        self.gbl.addLayout(horz)
        self.mergehide.append(self.collisionlabel)
        self.mergehide.append(self.collision)
        self.mergeupdateshow.append(self.collisionlabel)
        self.mergeupdateshow.append(self.collision)

        horz = QHBoxLayout()
        self.updatemeta = QCheckBox(_('Update Calibre &Metadata?'),self)
        self.updatemeta.setToolTip(_("Update metadata for existing stories in Calibre from web site?\n(Columns set to 'New Only' in the column tabs will only be set for new books.)"))
        self.updatemeta.setChecked(self.prefs['updatemeta'])
        horz.addWidget(self.updatemeta)
        self.mergehide.append(self.updatemeta)
        self.mergeupdateshow.append(self.updatemeta)

        self.gbl.addLayout(horz)

        ## bgmeta not used with Add New because of stories that change
        ## story URL and for title/author collision matching.
        # horz = QHBoxLayout()
        # self.bgmeta = QCheckBox(_('Background Metadata?'),self)
        # self.bgmeta.setToolTip(_("Collect Metadata from sites in a Background process.<br />This returns control to you quicker while updating, but you won't be asked for username/passwords or if you are an adult--stories that need those will just fail."))
        # self.bgmeta.setChecked(self.prefs['bgmeta'])
        # horz.addWidget(self.bgmeta)
        # self.mergehide.append(self.bgmeta)
        # self.mergeupdateshow.append(self.bgmeta)

        # self.gbl.addLayout(horz)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.ok_clicked)
        self.button_box.rejected.connect(self.reject)
        self.l.addWidget(self.button_box)

        self.addCtrlKeyPress(QtCore.Qt.Key_Return,self.ok_clicked)
        self.addCtrlKeyPress(QtCore.Qt.Key_Enter,self.ok_clicked) # num pad

    def click_show_download_options(self,x):
        self.gbf.setVisible(x)
        gprefs[show_download_options] = x

    # invoke the
    def ok_clicked(self):
        self.dialog_closing(None) # save persistent size.
        self.hide()
        self.go_signal.emit( self.get_fff_options(),
                             self.get_urlstext(),
                             self.merge,
                             self.extrapayload )

    def show_dialog(self,
                    url_list_text,
                    callback,
                    show=True,
                    merge=False,
                    newmerge=True,
                    extraoptions={},
                    extrapayload=None):
        # rather than mutex in fff_plugin, just bail here if it's
        # already in use.
        if self.isVisible():
            if url_list_text: # add to open box.
               self.url.setText( '\n'.join([self.get_urlstext(), url_list_text]) )
            return

        try:
            self.go_signal.disconnect()
        except:
            pass # if not already connected.
        self.go_signal.connect(callback)

        self.merge = merge
        self.newmerge = newmerge
        self.extraoptions = extraoptions
        self.extrapayload = extrapayload

        self.groupbox.setVisible(not(self.merge and self.newmerge))

        if self.merge:
            count=""
            if url_list_text:
                count = " " + _("(%s URLs found)")%len(url_list_text.split()) # count lines
            self.toplabel.setText('<b>'+_('Story URLs for anthology, one per line:') + count + '</b>')
            self.url.setToolTip(_('URLs for stories to include in the anthology, one per line.\nWill take URLs from clipboard, but only valid URLs.'))
            self.collisionlabel.setText(_('If Story Already Exists in Anthology?'))
            self.collision.setToolTip(_("What to do if there's already an existing story with the same URL in the anthology."))
            for widget in self.mergehide:
                widget.setVisible(False)
            for widget in self.mergeshow:
                widget.setVisible(True)
            if not self.newmerge:
                for widget in self.mergeupdateshow:
                    widget.setVisible(True)
            n = extraoptions.get('frompage',{}).get('name',None)
            if n:
                self.mergedname.setText(n)
            else:
                self.mergedname.setVisible(False)
            d = extraoptions.get('frompage',{}).get('desc',None)
            if d:
                self.mergeddesc.setText(unicode(d))
            else:
                self.mergeddesc.setVisible(False)
        else:
            for widget in self.mergehide:
                widget.setVisible(True)
            for widget in self.mergeshow:
                widget.setVisible(False)
            self.toplabel.setText(_('Story URLs, one per line:'))
            self.url.setToolTip(_('URLs for stories, one per line.\nWill take URLs from clipboard, but only valid URLs.\nAdd [1,5] after the URL to limit the download to chapters 1-5.'))
            self.collisionlabel.setText(_('If Story Already Exists?'))
            self.collision.setToolTip(_("What to do if there's already an existing story with the same URL or title and author."))
            self.groupbox.setChecked(gprefs.get(show_download_options,False))
            self.gbf.setVisible(gprefs.get(show_download_options,False))
            self.groupbox.toggled.connect(self.click_show_download_options)

        # Need to re-able after hiding/showing
        self.setAcceptDrops(True)
        self.url.setFocus()

        if self.prefs['adddialogstaysontop']:
            QDialog.setWindowFlags ( self, Qt.Dialog | Qt.WindowStaysOnTopHint )
        else:
            QDialog.setWindowFlags ( self, Qt.Dialog )

        if not self.merge:
            self.fileform.setCurrentIndex(self.fileform.findText(self.prefs['fileform']))
        else:
            # always epub on self.merge (anthology)
            self.fileform.setCurrentIndex(self.fileform.findText('epub'))

        # add collision options
        self.set_collisions()
        if 'collision' in extraoptions:
            use_collision = extraoptions['collision']
            # self.collision.setDisabled(True)
            # self.collision.setToolTip(_("Update Mode set by menu/shortcut choice."))
        else:
            use_collision = save_collisions[self.prefs['collision']]
            # self.collision.setDisabled(False)
        i = self.collision.findText(use_collision)
        if i > -1:
            self.collision.setCurrentIndex(i)

        self.updatemeta.setChecked(self.prefs['updatemeta'])
        # self.bgmeta.setChecked(self.prefs['bgmeta'])

        self.url.setText(url_list_text)
        if url_list_text:
            self.button_box.button(QDialogButtonBox.Ok).setFocus()
        # restore saved size.
        self.resize_dialog()

        if show: # so anthology update can be modal still.
            self.show()
        #self.resize(self.sizeHint())

    def set_collisions(self):
        prev=self.collision.currentText()
        self.collision.clear()
        if self.merge:
            order = list(anthology_collision_order)
        else:
            order = list(collision_order)
            ## Remove options that aren't valid.
            if self.fileform.currentText() != 'epub':
                order.remove(UPDATE)
                order.remove(UPDATEALWAYS)
            if self.prefs['savemetacol'] == '':
                order.remove(CALIBREONLYSAVECOL)

        for o in order:
            self.collision.addItem(o)

        i = self.collision.findText(prev)
        if i > -1:
            self.collision.setCurrentIndex(i)

    def get_fff_options(self):
        retval = dict(self.extraoptions)
        retval.update( {
                'fileform': unicode(self.fileform.currentText()),
                'collision': unicode(self.collision.currentText()),
                'updatemeta': self.updatemeta.isChecked(),
                'bgmeta': False, # self.bgmeta.isChecked(),
                'smarten_punctuation':self.prefs['smarten_punctuation'],
                'do_wordcount':self.prefs['do_wordcount'],
                } )

        if self.merge:
            retval['fileform']=='epub'
            if self.newmerge:
                retval['updatemeta']=True
                retval['collision']=ADDNEW

        logger.debug("self.extraoptions['anthology_url']:%s"%self.extraoptions.get('anthology_url','NOT FOUND'))
        retval.update(self.extraoptions)
        return retval

    def get_urlstext(self):
        return unicode(self.url.toPlainText())

class FakeLineEdit():
    def __init__(self):
        pass

    def text(self):
        pass

class CollectURLDialog(SizePersistedDialog):
    '''
    Collect single url for get urls.
    '''
    def __init__(self, gui, title, url_text, anthology=False, indiv=True):
        SizePersistedDialog.__init__(self, gui, 'fff:get story urls')
        self.status=False
        self.anthology=False

        self.setMinimumWidth(300)

        self.l = QVBoxLayout()
        self.setLayout(self.l)

        self.setWindowTitle(title)
        self.l.addWidget(QLabel(title))

        horz = QHBoxLayout()
        self.l.addLayout(horz)

        horz.addWidget(QLabel("URL:"))
        self.url = QLineEdit(self)
        self.url.setText(url_text)
        horz.addWidget(self.url)

        horz = QHBoxLayout()
        self.l.addLayout(horz)

        if indiv:
            self.indiv_button = QPushButton(_('For Individual Books'), self)
            self.indiv_button.setToolTip(_('Get URLs and go to dialog for individual story downloads.'))
            self.indiv_button.clicked.connect(self.indiv)
            horz.addWidget(self.indiv_button)

        if anthology:
            self.merge_button = QPushButton(_('For Anthology Epub'), self)
            self.merge_button.setToolTip(_('Get URLs and go to dialog for Anthology download.\nRequires %s plugin.')%'EpubMerge 1.3.1+')
            self.merge_button.clicked.connect(self.merge)
            horz.addWidget(self.merge_button)

        self.cancel_button = QPushButton(_('Cancel'), self)
        self.cancel_button.clicked.connect(self.cancel)
        horz.addWidget(self.cancel_button)

        # restore saved size.
        self.resize_dialog()

    def indiv(self):
        self.status=True
        self.accept()

    def merge(self):
        self.status=True
        self.anthology=True
        self.accept()

    def cancel(self):
        self.status=False
        self.reject()

class UserPassDialog(QDialog):
    '''
    Need to collect User/Pass for some sites.
    '''
    def __init__(self, gui, site, exception=None):
        QDialog.__init__(self, gui)
        self.status=False

        self.l = QVBoxLayout()
        self.setLayout(self.l)

        grid = QGridLayout()
        self.l.addLayout(grid)

        if exception and exception.passwdonly:
            self.setWindowTitle(_('Password'))
            grid.addWidget(QLabel(_("Author requires a password for this story(%s).")%exception.url),0,0,1,2)
            # user isn't used, but it's easier to still have it for
            # post processing.
            self.user = FakeLineEdit()
        else:
            self.setWindowTitle(_('User/Password'))
            grid.addWidget(QLabel(_("%s requires you to login to download this story.")%site),0,0,1,2)

            grid.addWidget(QLabel(_("User:")),1,0)
            self.user = QLineEdit(self)
            grid.addWidget(self.user,1,1)

        grid.addWidget(QLabel(_("Password:")),2,0)
        self.passwd = QLineEdit(self)
        self.passwd.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.passwd,2,1)

        horz = QHBoxLayout()
        self.l.addLayout(horz)

        self.ok_button = QPushButton(_('OK'), self)
        self.ok_button.clicked.connect(self.ok)
        horz.addWidget(self.ok_button)

        self.cancel_button = QPushButton(_('Cancel'), self)
        self.cancel_button.clicked.connect(self.cancel)
        horz.addWidget(self.cancel_button)

        self.resize(self.sizeHint())

    def ok(self):
        self.status=True
        self.hide()

    def cancel(self):
        self.status=False
        self.hide()

class TOTPDialog(QDialog):
    '''
    Need to collect Timebased One Time Password(TOTP) for some sites.
    '''
    def __init__(self, gui, site, exception=None):
        QDialog.__init__(self, gui)
        self.status=False

        self.l = QVBoxLayout()
        self.setLayout(self.l)

        grid = QGridLayout()
        self.l.addLayout(grid)

        self.setWindowTitle(_('Time-based One Time Password(TOTP)'))
        grid.addWidget(QLabel(_("Site requires a Time-based One Time Password(TOTP) for this url:\n%s")%exception.url),0,0,1,2)

        grid.addWidget(QLabel(_("TOTP:")),2,0)
        self.totp = QLineEdit(self)
        grid.addWidget(self.totp,2,1)

        horz = QHBoxLayout()
        self.l.addLayout(horz)

        self.ok_button = QPushButton(_('OK'), self)
        self.ok_button.clicked.connect(self.ok)
        horz.addWidget(self.ok_button)

        self.cancel_button = QPushButton(_('Cancel'), self)
        self.cancel_button.clicked.connect(self.cancel)
        horz.addWidget(self.cancel_button)

        self.resize(self.sizeHint())

    def ok(self):
        self.status=True
        self.hide()

    def cancel(self):
        self.status=False
        self.hide()

def LoopProgressDialog(gui,
                       book_list,
                       foreach_function,
                       finish_function,
                       init_label=_("Fetching metadata for stories..."),
                       win_title=_("Downloading metadata for stories"),
                       status_prefix=_("Fetched metadata for"),
                       disable_cancel=False):
    ld = _LoopProgressDialog(gui,
                             book_list,
                             foreach_function,
                             init_label,
                             win_title,
                             status_prefix,
                             disable_cancel)

    # Mac OS X gets upset if the finish_function is called from inside
    # the real _LoopProgressDialog class.

    # reflect old behavior.
    if not ld.wasCanceled():
        finish_function(book_list)

class _LoopProgressDialog(QProgressDialog):
    '''
    ProgressDialog displayed while fetching metadata for each story.
    '''
    def __init__(self, gui,
                 book_list,
                 foreach_function,
                 init_label=_("Fetching metadata for stories..."),
                 win_title=_("Downloading metadata for stories"),
                 status_prefix=_("Fetched metadata for"),
                 disable_cancel=False):
        QProgressDialog.__init__(self,
                                 init_label,
                                 _('Cancel'), 0, len(book_list), gui)
        self.gui = gui
        self.setWindowTitle(win_title)
        self.setMinimumWidth(500)
        self.book_list = book_list
        self.foreach_function = foreach_function
        self.status_prefix = status_prefix
        self.i = 0
        self.start_time = datetime.now()

        # can't import at file load.
        from calibre_plugins.fanficfare_plugin.prefs import prefs
        self.show_est_time = prefs['show_est_time']

        self.setLabelText('%s %d / %d' % (self.status_prefix, self.i, len(self.book_list)))
        self.setValue(self.i)

        if disable_cancel:
            self.setCancelButton(None)
            self.reject = self.disabled_reject
            self.closeEvent = self.disabled_closeEvent

        ## self.do_loop does QTimer.singleShot on self.do_loop also.
        ## A weird way to do a loop, but that was the example I had.
        ## 100 instead of 0 on the first go due to Win10(and later
        ## qt6) not displaying dialog properly.
        QTimer.singleShot(100, self.do_loop)
        self.exec_()

    # used when disable_cancel = True
    def disabled_reject(self):
        pass

    # used when disable_cancel = True
    def disabled_closeEvent(self, event):
        if event.spontaneous():
            event.ignore()

    def updateStatus(self):
        remaining_time_string = ''
        if self.show_est_time and self.i > -1:
            time_spent = (datetime.now() - self.start_time).total_seconds()
            estimated_remaining = (time_spent/(self.i+1)) * len(self.book_list) - time_spent
            remaining_time_string = _(' - %s estimated until done') % ( time_duration_format(estimated_remaining))

        self.setLabelText('%s %d / %d%s' % (self.status_prefix, self.i+1, len(self.book_list), remaining_time_string))
        self.setValue(self.i+1)
        #print(self.labelText())

    def do_loop(self):

        book = self.book_list[self.i]
        try:
            ## collision spec passed into getadapter by partial from fff_plugin
            ## no retval only if it exists, but collision is SKIP
            self.foreach_function(book)

        except NotGoingToDownload as d:
            book['status']=_('Skipped')
            book['good']=False
            book['showerror']=d.showerror
            book['comment']=unicode(d)
            book['icon'] = d.icon

        except Exception as e:
            book['good']=False
            book['status']=_("Error")
            book['comment']=unicode(e)
            logger.error("Exception: %s:%s"%(book,book['comment']),exc_info=True)

        self.updateStatus()
        self.i += 1

        if self.i >= len(self.book_list) or self.wasCanceled():
            return self.do_when_finished()
        else:
            QTimer.singleShot(0, self.do_loop)

    def do_when_finished(self):
        self.hide()

def time_duration_format(seconds):
    """
    Convert seconds into a string describing the duration in larger time units (seconds, minutes, hours, days)
    Only returns the two largest time divisions (eg, will drop seconds if there's hours remaining)

    :param seconds: number of seconds
    :return: string description of the duration
    """
    periods = [
        (_('%d day'),_('%d days'),       60*60*24),
        (_('%d hour'),_('%d hours'),     60*60),
        (_('%d minute'),_('%d minutes'), 60),
        (_('%d second'),_('%d seconds'), 1)
        ]

    strings = []
    for period_label, period_plural_label, period_seconds in periods:
        if seconds > period_seconds:
            period_value, seconds = divmod(seconds,period_seconds)
            if period_value == 1:
                strings.append( period_label % period_value)
            else:
                strings.append(period_plural_label % period_value)
            if len(strings) == 2:
                break

    if len(strings) == 0:
        return _('less than 1 second')
    else:
        return ', '.join(strings)

class AboutDialog(QDialog):

    def __init__(self, parent, icon, text):
        QDialog.__init__(self, parent)
        #self.resize(400, 250)
        self.l = QGridLayout()
        self.setLayout(self.l)
        self.logo = QLabel()
        self.logo.setMaximumWidth(110)
        self.logo.setPixmap(QPixmap(icon.pixmap(100,100)))
        self.label = QLabel(text)
        self.label.setOpenExternalLinks(True)
        self.label.setWordWrap(True)
        self.setWindowTitle(_('About FanFicFare'))
        self.setWindowIcon(icon)
        self.l.addWidget(self.logo, 0, 0)
        self.l.addWidget(self.label, 0, 1)
        self.bb = QDialogButtonBox(self)
        b = self.bb.addButton(_('OK'), self.bb.AcceptRole)
        b.setDefault(True)
        self.l.addWidget(self.bb, 2, 0, 1, -1)
        self.bb.accepted.connect(self.accept)

class IconWidgetItem(ReadOnlyTextIconWidgetItem):
    def __init__(self, text, icon, sort_key):
        ReadOnlyTextIconWidgetItem.__init__(self, text, icon)
        self.sort_key = sort_key

    #Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other):
        return self.sort_key < other.sort_key

class AuthorTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, text, sort_key):
        ReadOnlyTableWidgetItem.__init__(self, text)
        self.sort_key = sort_key

    #Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other):
        return self.sort_key.lower() < other.sort_key.lower()

class UpdateExistingDialog(SizePersistedDialog):
    def __init__(self, gui, header, prefs, icon, books,
                 extraoptions={},
                 save_size_name='fff:update list dialog'):
        SizePersistedDialog.__init__(self, gui, save_size_name)

        self.prefs = prefs
        self.setWindowTitle(header)
        self.setWindowIcon(icon)

        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png',
                                        header)
        layout.addLayout(title_layout)
        books_layout = QHBoxLayout()
        layout.addLayout(books_layout)

        self.books_table = StoryListTableWidget(self)
        books_layout.addWidget(self.books_table)

        button_layout = QVBoxLayout()
        books_layout.addLayout(button_layout)

        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        button_layout.addItem(spacerItem)
        self.remove_button = QtGui.QToolButton(self)
        self.remove_button.setToolTip(_('Remove selected books from the list'))
        self.remove_button.setIcon(get_icon('list_remove.png'))
        self.remove_button.clicked.connect(self.remove_from_list)
        button_layout.addWidget(self.remove_button)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        button_layout.addItem(spacerItem1)

        options_layout = QHBoxLayout()

        groupbox = QGroupBox(_("Show Download Options"))
        groupbox.setCheckable(True)
        groupbox.setChecked(gprefs.get(show_download_options,False))
        groupbox.setFlat(True)
        groupbox.setStyleSheet(gpstyle)

        self.gbf = QFrame()
        gbl = QVBoxLayout()
        gbl.addWidget(self.gbf)
        groupbox.setLayout(gbl)
        gbl = QVBoxLayout()
        self.gbf.setLayout(gbl)
        options_layout.addWidget(groupbox)

        self.gbf.setVisible(gprefs.get(show_download_options,False))
        groupbox.toggled.connect(self.click_show_download_options)

        horz = QHBoxLayout()
        gbl.addLayout(horz)

        label = QLabel(_('Output &Format:'))
        horz.addWidget(label)
        self.fileform = QComboBox(self)
        self.fileform.addItem('epub')
        self.fileform.addItem('mobi')
        self.fileform.addItem('html')
        self.fileform.addItem('txt')
        self.fileform.setCurrentIndex(self.fileform.findText(self.prefs['fileform']))
        self.fileform.setToolTip(_('Choose output format to create.  May set default from plugin configuration.'))
        self.fileform.activated.connect(self.set_collisions)
        label.setBuddy(self.fileform)
        horz.addWidget(self.fileform)

        label = QLabel(_('Update Mode:'))
        horz.addWidget(label)
        self.collision = QComboBox(self)
        self.collision.setToolTip(_("What sort of update to perform.  May set default from plugin configuration."))
        # add collision options
        self.set_collisions()
        if 'collision' in extraoptions:
            use_collision = extraoptions['collision']
            # self.collision.setDisabled(True)
            # self.collision.setToolTip(_("Update Mode set by menu/shortcut choice."))
        else:
            use_collision = save_collisions[self.prefs['collision']]
            # self.collision.setDisabled(False)
        i = self.collision.findText(use_collision)
        if i > -1:
            self.collision.setCurrentIndex(i)
        label.setBuddy(self.collision)
        horz.addWidget(self.collision)

        horz = QHBoxLayout()
        gbl.addLayout(horz)

        self.updatemeta = QCheckBox(_('Update Calibre &Metadata?'),self)
        self.updatemeta.setToolTip(_("Update metadata for existing stories in Calibre from web site?\n(Columns set to 'New Only' in the column tabs will only be set for new books.)"))
        self.updatemeta.setChecked(self.prefs['updatemeta'])
        horz.addWidget(self.updatemeta)

        self.bgmeta = QCheckBox(_('Background Metadata?'),self)
        self.bgmeta.setToolTip(_("Collect Metadata from sites in a Background process.<br />This returns control to you quicker while updating, but you won't be asked for username/passwords or if you are an adult--stories that need those will just fail."))
        self.bgmeta.setChecked(self.prefs['bgmeta'])
        horz.addWidget(self.bgmeta)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        options_layout.addWidget(button_box)

        layout.addLayout(options_layout)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()
        self.books_table.populate_table(books)

    def click_show_download_options(self,x):
        self.gbf.setVisible(x)
        gprefs[show_download_options] = x

    def set_collisions(self):
        prev=self.collision.currentText()
        self.collision.clear()
        order = list(collision_order)
        order.remove(ADDNEW)
        order.remove(SKIP)
        if self.fileform.currentText() != 'epub':
            order.remove(UPDATE)
            order.remove(UPDATEALWAYS)
        if self.prefs['savemetacol'] == '':
            order.remove(CALIBREONLYSAVECOL)

        for o in order:
            self.collision.addItem(o)

        i = self.collision.findText(prev)
        if i > -1:
            self.collision.setCurrentIndex(i)

    def remove_from_list(self):
        self.books_table.remove_selected_rows()

    def get_books(self):
        return self.books_table.get_books()

    def get_fff_options(self):
        return {
            'fileform': unicode(self.fileform.currentText()),
            'collision': unicode(self.collision.currentText()),
            'updatemeta': self.updatemeta.isChecked(),
            'bgmeta': self.bgmeta.isChecked(),
            'smarten_punctuation':self.prefs['smarten_punctuation'],
            'do_wordcount':self.prefs['do_wordcount'],
            }

class StoryListTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def populate_table(self, books):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = ['',_('Title'), _('Author'), 'URL', _('Comment')]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.horizontalHeader().setStretchLastSection(True)
        #self.verticalHeader().setDefaultSectionSize(24)
        self.verticalHeader().hide()

        self.books={}
        for row, book in enumerate(books):
            self.populate_table_row(row, book)
            self.books[row] = book

        # turning True breaks up/down.  Do we need either sorting or up/down?
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()
        self.setMinimumColumnWidth(1, 100)
        self.setMinimumColumnWidth(2, 100)
        self.setMinimumColumnWidth(3, 100)
        self.setMinimumSize(300, 0)
        # if len(books) > 0:
        #     self.selectRow(0)
        self.sortItems(1)
        self.sortItems(0)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book):
        if book['good']:
            icon = get_icon('ok.png')
            val = 0
        else:
            icon = get_icon('minus.png')
            val = 1
        if 'icon' in book:
            icon = get_icon(book['icon'])

        status_cell = IconWidgetItem(None,icon,val)
        status_cell.setData(Qt.UserRole, val)
        self.setItem(row, 0, status_cell)

        title_cell = ReadOnlyTableWidgetItem(book['title'])
        title_cell.setData(Qt.UserRole, row)
        self.setItem(row, 1, title_cell)

        self.setItem(row, 2, AuthorTableWidgetItem(", ".join(book['author']), ", ".join(book['author_sort'])))

        url_cell = ReadOnlyTableWidgetItem(book['url'])
        self.setItem(row, 3, url_cell)

        comment_cell = ReadOnlyTableWidgetItem(book['comment'])
        self.setItem(row, 4, comment_cell)

    def get_books(self):
        books = []
        #print("=========================\nbooks:%s"%self.books)
        for row in range(self.rowCount()):
            rnum = self.item(row, 1).data(Qt.UserRole)
            book = self.books[rnum]
            books.append(book)
        return books

    def remove_selected_rows(self):
        self.setFocus()
        rows = self.selectionModel().selectedRows()
        rows = sorted(rows, key=lambda x: x.row(), reverse=True)
        if len(rows) == 0:
            return
        message = '<p>'+_('Are you sure you want to remove this book from the list?')
        if len(rows) > 1:
            message = '<p>'+_('Are you sure you want to remove the selected %d books from the list?')%len(rows)
        if not confirm(message,'fff_delete_item', self):
            return
        first_sel_row = self.currentRow()
        for selrow in rows:
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

## Added to allow sorting by Notes column
class NotesWidgetItem(QTableWidgetItem):
    def __init__(self,content):
        QTableWidgetItem.__init__(self)
        self.content=content

    def currentText(self):
        return self.content.currentText()

    def __lt__(self, other):
        return (unicode(self.currentText()).lower().strip() <
                unicode(other.currentText()).lower().strip())

class RejectListTableWidget(QTableWidget):

    def __init__(self, parent,rejectreasons=[]):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rejectreasons = rejectreasons

    def populate_table(self, reject_list):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(reject_list))
        header_labels = ['URL', _('Title'), _('Author'), _('Note')]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.horizontalHeader().setStretchLastSection(True)
        #self.verticalHeader().setDefaultSectionSize(24)
        #self.verticalHeader().hide()

        # it's generally recommended to enable sort after pop, not
        # before.  But then it needs to be sorted on a column and I'd
        # rather keep the order given.
        self.setSortingEnabled(True)
        # row is just row number.
        for row, rejectrow in enumerate(reject_list):
            #print("populating table:%s"%rejectrow.to_line())
            self.populate_table_row(row,rejectrow)

        self.resizeColumnsToContents()
        self.setMinimumColumnWidth(0, 100)
        self.setMinimumColumnWidth(3, 100)
        self.setMinimumSize(300, 0)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, rej):

        url_cell = ReadOnlyTableWidgetItem(rej.url)
        url_cell.setData(Qt.UserRole, rej.book_id)
        self.setItem(row, 0, url_cell)
        self.setItem(row, 1, EditableTableWidgetItem(rej.title))
        self.setItem(row, 2, EditableTableWidgetItem(rej.auth))

        # sort_func orders dropdown-constant to preserve user order.
        note_cell = EditWithComplete(self,sort_func=lambda x:1)

        items = [rej.note]+self.rejectreasons
        note_cell.update_items_cache(items)
        note_cell.show_initial_value(rej.note)
        note_cell.set_separator(None)
        note_cell.setToolTip(_('Select or Edit Reject Note.'))
        self.setItem(row, 3, NotesWidgetItem(note_cell))
        self.setCellWidget(row, 3, note_cell)
        note_cell.setCursorPosition(0)

    def remove_selected_rows(self):
        self.setFocus()
        rows = self.selectionModel().selectedRows()
        rows = sorted(rows, key=lambda x: x.row(), reverse=True)
        if len(rows) == 0:
            return
        message = '<p>'+_('Are you sure you want to remove this URL from the list?')
        if len(rows) > 1:
            message = '<p>'+_('Are you sure you want to remove the %d selected URLs from the list?')%len(rows)
        if not confirm(message,'fff_rejectlist_delete_item_again', self):
            return
        first_sel_row = self.currentRow()
        for selrow in rows:
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

class RejectListDialog(SizePersistedDialog):
    def __init__(self, gui, reject_list,
                 rejectreasons=[],
                 header=_("List of Books to Reject"),
                 icon='rotate-right.png',
                 show_delete=True,
                 show_all_reasons=True,
                 save_size_name='fff:reject list dialog'):
        SizePersistedDialog.__init__(self, gui, save_size_name)

        self.setWindowTitle(header)
        self.setWindowIcon(get_icon(icon))

        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, icon, header,
                                        '<i></i>'+_('FFF will remember these URLs and display the note and offer to reject them if you try to download them again later.'))
        layout.addLayout(title_layout)
        rejects_layout = QHBoxLayout()
        layout.addLayout(rejects_layout)

        self.rejects_table = RejectListTableWidget(self,rejectreasons=rejectreasons)
        rejects_layout.addWidget(self.rejects_table)

        button_layout = QVBoxLayout()
        rejects_layout.addLayout(button_layout)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        button_layout.addItem(spacerItem)

        self.remove_button = QtGui.QToolButton(self)
        self.remove_button.setToolTip(_('Remove selected URLs from the list'))
        self.remove_button.setIcon(get_icon('list_remove.png'))
        self.remove_button.clicked.connect(self.remove_from_list)
        button_layout.addWidget(self.remove_button)

        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        button_layout.addItem(spacerItem1)

        if show_all_reasons:
            self.reason_edit = EditWithComplete(self,sort_func=lambda x:1)

            items = ['']+rejectreasons
            self.reason_edit.update_items_cache(items)
            self.reason_edit.show_initial_value('')
            self.reason_edit.set_separator(None)
            self.reason_edit.setToolTip(_("This will be added to whatever note you've set for each URL above."))

            horz = QHBoxLayout()
            label = QLabel(_("Add this reason to all URLs added:"))
            label.setToolTip(_("This will be added to whatever note you've set for each URL above."))
            horz.addWidget(label)
            horz.addWidget(self.reason_edit)
            self.reason_edit.setCursorPosition(0)
            horz.insertStretch(-1)
            layout.addLayout(horz)

        options_layout = QHBoxLayout()

        if show_delete:
            # can't import at file load.
            from calibre_plugins.fanficfare_plugin.prefs import prefs

            self.deletebooks = QCheckBox(_('Delete Books (including books without FanFiction URLs)?'),self)
            self.deletebooks.setToolTip(_("Delete the selected books after adding them to the Rejected URLs list."))
            self.deletebooks.setChecked(prefs['reject_delete_default'])
            options_layout.addWidget(self.deletebooks)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        options_layout.addWidget(button_box)

        layout.addLayout(options_layout)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()
        self.rejects_table.populate_table(reject_list)

    def remove_from_list(self):
        self.rejects_table.remove_selected_rows()

    def get_reject_list(self):
        rejectrows = []
        for row in range(self.rejects_table.rowCount()):
            url = unicode(self.rejects_table.item(row, 0).text()).strip()
            book_id =self.rejects_table.item(row, 0).data(Qt.UserRole)
            title = unicode(self.rejects_table.item(row, 1).text()).strip()
            auth = unicode(self.rejects_table.item(row, 2).text()).strip()
            note = unicode(self.rejects_table.cellWidget(row, 3).currentText()).strip()
            rejectrows.append(RejectUrlEntry(url,note,title,auth,self.get_reason_text(),book_id=book_id,normalize=False))
        return rejectrows

    def get_reject_list_ids(self):
        rejectrows = []
        for row in range(self.rejects_table.rowCount()):
            book_id = self.rejects_table.item(row, 0).data(Qt.UserRole)
            if book_id:
                rejectrows.append(book_id)
        return rejectrows

    def get_reason_text(self):
        try:
            return unicode(self.reason_edit.currentText()).strip()
        except:
            # doesn't have self.reason_edit when editing existing list.
            return None

    def get_deletebooks(self):
        return self.deletebooks.isChecked()

class EditTextDialog(SizePersistedDialog):

    def __init__(self, parent, text,
                 icon=None, title=None, label=None, tooltip=None,
                 read_only=False,
                 rejectreasons=[],reasonslabel=None,
                 save_size_name='fff:edit text dialog',
                 ):
        SizePersistedDialog.__init__(self, parent, save_size_name)

        self.l = QVBoxLayout()
        self.setLayout(self.l)
        self.label = QLabel(label)
        if title:
            self.setWindowTitle(title)
        if icon:
            self.setWindowIcon(icon)
        self.l.addWidget(self.label)

        self.textedit = QTextEdit(self)
        self.textedit.setLineWrapMode(QTextEditNoWrap)
        self.textedit.setReadOnly(read_only)
        self.textedit.setText(text)
        self.l.addWidget(self.textedit)

        if tooltip:
            self.label.setToolTip(tooltip)
            self.textedit.setToolTip(tooltip)

        if rejectreasons or reasonslabel:
            self.reason_edit = EditWithComplete(self,sort_func=lambda x:1)

            items = ['']+rejectreasons
            self.reason_edit.update_items_cache(items)
            self.reason_edit.show_initial_value('')
            self.reason_edit.set_separator(None)
            self.reason_edit.setToolTip(reasonslabel)

            if reasonslabel:
                horz = QHBoxLayout()
                label = QLabel(reasonslabel)
                label.setToolTip(reasonslabel)
                horz.addWidget(label)
                horz.addWidget(self.reason_edit)
                self.l.addLayout(horz)
            else:
                self.l.addWidget(self.reason_edit)
            self.reason_edit.setCursorPosition(0)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.l.addWidget(button_box)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def get_plain_text(self):
        return unicode(self.textedit.toPlainText())

    def get_reason_text(self):
        return unicode(self.reason_edit.currentText()).strip()

class QTextEditPlainPaste(QTextEdit):
    def insertFromMimeData(self, mimeData):
        # logger.debug("insertFromMimeData called")
        #Ensure it is text.
        if (mimeData.hasText()):
            text = mimeData.text()
            self.insertPlainText(text)
        #In case not text.
        else:
            QTextEdit.insertFromMimeData(self, mimeData)

class IniTextDialog(HotKeyedSizePersistedDialog):

    def __init__(self, parent, text,
                 icon=None, title=None, label=None,
                 use_find=False,
                 read_only=False,
                 save_size_name='fff:ini text dialog',
                 ):
        super(IniTextDialog,self).__init__(parent, save_size_name)

        self.l = QVBoxLayout()
        self.setLayout(self.l)
        self.label = QLabel(label)
        if title:
            self.setWindowTitle(title)
        if icon:
            self.setWindowIcon(icon)
        self.l.addWidget(self.label)

        self.textedit = QTextEditPlainPaste(self)

        highlighter = IniHighlighter(self.textedit,
                                     sections=get_valid_sections(),
                                     keywords=get_valid_keywords(),
                                     entries=get_valid_entries(),
                                     entry_keywords=get_valid_entry_keywords(),
                                     )

        self.textedit.setLineWrapMode(QTextEditNoWrap)
        try:
            self.textedit.setFont(QFont("Courier",
                                   parent.font().pointSize()+1))
        except Exception as e:
            logger.error("Couldn't get font: %s"%e)

        self.textedit.setReadOnly(read_only)

        self.textedit.setText(ensure_text(text))
        self.l.addWidget(self.textedit)

        self.lastStart = 0

        if use_find:

            findtooltip=_('Search for string in edit box.')

            horz = QHBoxLayout()
            label = QLabel(_('Find:'))

            label.setToolTip(findtooltip)

            # Button to search the document for something
            self.findButton = QtGui.QPushButton(_('Find'),self)
            self.findButton.clicked.connect(self.find)
            self.findButton.setToolTip(findtooltip)

            # The field into which to type the query
            self.findField = QLineEdit(self)
            self.findField.setToolTip(findtooltip)
            self.findField.returnPressed.connect(self.findButton.setFocus)

            # Case Sensitivity option
            self.caseSens = QtGui.QCheckBox(_('Case sensitive'),self)
            self.caseSens.setToolTip(_("Search for case sensitive string; don't treat Harry, HARRY and harry all the same."))

            horz.addWidget(label)
            horz.addWidget(self.findField)
            horz.addWidget(self.findButton)
            horz.addWidget(self.caseSens)

            self.l.addLayout(horz)

            self.addCtrlKeyPress(QtCore.Qt.Key_F,self.findFocus)
            self.addCtrlKeyPress(QtCore.Qt.Key_G,self.find)

        self.addCtrlKeyPress(QtCore.Qt.Key_Return,self.accept)
        self.addCtrlKeyPress(QtCore.Qt.Key_Enter,self.accept) # num pad
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.l.addWidget(button_box)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def accept(self):
        from .fff_util import test_config

        # print("in accept")
        errors = test_config(self.get_plain_text())

        retry = False
        if errors:
            d = ViewLog(self,
                        _('Go back to fix errors?'),
                        errors)
            retry = d.exec_() == d.Accepted

            # print("retry:%s"%retry)

        if retry:
            lineno=d.get_lineno()
            if lineno:
                # print("go to lineno (%s) here"%lineno)
                self.select_line(lineno)
        else:
            # print("call parent accept")
            return SizePersistedDialog.accept(self)

    def get_plain_text(self):
        return unicode(self.textedit.toPlainText())

    def findFocus(self):
        # print("findFocus called")
        self.findField.setFocus()
        self.findField.selectAll()

    def find(self):

        #print("find self.lastStart:%s"%self.lastStart)

        # Grab the parent's text
        text = self.textedit.toPlainText()

        # And the text to find
        query = self.findField.text()

        if not self.caseSens.isChecked():
            text = text.lower()
            query = query.lower()

        # Use normal string search to find the query from the
        # last starting position
        self.lastStart = text.find(query,self.lastStart + 1)
        # If the find() method didn't return -1 (not found)

        if self.lastStart >= 0:
            end = self.lastStart + len(query)
            self.moveCursor(self.lastStart,end)
        else:
            # Make the next search start from the begining again
            self.lastStart = 0
            self.textedit.moveCursor(MoveOperations.Start)

    def moveCursor(self,start,end):

        # We retrieve the QTextCursor object from the parent's QTextEdit
        cursor = self.textedit.textCursor()

        # Then we set the position to the beginning of the last match
        cursor.setPosition(start)

        # Next we move the Cursor by over the match and pass the KeepAnchor parameter
        # which will make the cursor select the match's text
        cursor.movePosition(MoveOperations.Right,
                            MoveMode.KeepAnchor,end - start)

        # And finally we set this new cursor as the parent's
        self.textedit.setTextCursor(cursor)

    def select_line(self,lineno):

        # We retrieve the QTextCursor object from the parent's QTextEdit
        cursor = self.textedit.textCursor()

        # Then we set the position to the beginning of the buffer
        cursor.setPosition(0)

        # Next we move the Cursor down lineno times
        cursor.movePosition(MoveOperations.Down,MoveMode.MoveAnchor,lineno-1)

        # Next we move the Cursor to the end of the line
        cursor.movePosition(MoveOperations.EndOfLine,MoveMode.KeepAnchor,1)

        # And finally we set this new cursor as the parent's
        self.textedit.setTextCursor(cursor)

class ViewLog(SizePersistedDialog):

    def label_clicked(self, event, lineno=None):
        self.lineno = lineno
        # print("lineno set to: %s"%lineno)
        self.accept()

    def get_lineno(self):
        return self.lineno

    def __init__(self, parent, title, errors,
                 save_size_name='fff:view log dialog',):
        SizePersistedDialog.__init__(self, parent,save_size_name)
        self.l = l = QVBoxLayout()
        self.setLayout(l)

        label = QLabel(_('Click an error below to return to Editing directly on that line:'))
        label.setWordWrap(True)
        self.l.addWidget(label)

        self.lineno = None

        scrollable = QScrollArea()
        scrollcontent = QWidget()
        scrollable.setWidget(scrollcontent)
        scrollable.setWidgetResizable(True)
        self.l.addWidget(scrollable)

        self.sl = QVBoxLayout()
        scrollcontent.setLayout(self.sl)

        ## error = (lineno, msg)
        for (lineno, error_msg) in errors:
            # print('adding label for error:%s: %s'%(lineno, error_msg))
            if len(error_msg) > 200:
                error_msg=error_msg[:200]+" ..."
            label = QLabel('%s: %s'%(lineno, error_msg))
            label.setWordWrap(True)
            if( hasattr(QApplication.instance(),'is_dark_theme')
                and QApplication.instance().is_dark_theme ):
                label.setStyleSheet("QLabel { margin-left: 2em; color : aqua; } QLabel:hover { color: red; }");
            else:
                label.setStyleSheet("QLabel { margin-left: 2em; color : blue; } QLabel:hover { color: red; }");
            label.setToolTip(_('Click to go to line %s')%lineno)
            label.mouseReleaseEvent = partial(self.label_clicked, lineno=lineno)
            self.sl.addWidget(label)

        # html='<p>'+'</p><p>'.join([ '(lineno: %s) %s'%e for e in errors ])+'</p>'

        # self.tb = QTextBrowser(self)
        # self.tb.setFont(QFont("Courier",
        #                       parent.font().pointSize()+1))
        # self.tb.setHtml(html)
        # l.addWidget(self.tb)

        self.sl.insertStretch(-1)

        horz = QHBoxLayout()

        editagain = QPushButton(_('Return to Editing'), self)
        editagain.clicked.connect(self.accept)
        horz.addWidget(editagain)

        saveanyway = QPushButton(_('Save Anyway'), self)
        saveanyway.clicked.connect(self.reject)
        horz.addWidget(saveanyway)

        l.addLayout(horz)
        self.setModal(False)
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(I('debug.png')))
        #self.show()

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def copy_to_clipboard(self):
        txt = self.tb.toPlainText()
        QApplication.clipboard().setText(txt)

class EmailPassDialog(QDialog):
    '''
    Need to collect Pass for imap.
    '''
    def __init__(self, gui, user):
        QDialog.__init__(self, gui)
        self.status=False

        self.l = QVBoxLayout()
        self.setLayout(self.l)

        grid = QGridLayout()
        self.l.addLayout(grid)

        self.setWindowTitle(_('Password'))
        grid.addWidget(QLabel(_("Enter Email Password for %s:")%user),0,0,1,2)

        # grid.addWidget(QLabel(_("Password:")),1,0)
        self.passwd = QLineEdit(self)
        self.passwd.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.passwd,1,0,1,2)

        horz = QHBoxLayout()
        self.l.addLayout(horz)

        self.ok_button = QPushButton(_('OK'), self)
        self.ok_button.clicked.connect(self.ok)
        horz.addWidget(self.ok_button)

        self.cancel_button = QPushButton(_('Cancel'), self)
        self.cancel_button.clicked.connect(self.cancel)
        horz.addWidget(self.cancel_button)

        self.resize(self.sizeHint())

    def ok(self):
        self.status=True
        self.hide()

    def cancel(self):
        self.status=False
        self.hide()

    def get_pass(self):
        return u"%s"%self.passwd.text()

    def get_remember(self):
        return self.remember_pass.isChecked()

def question_dialog_all(parent, title, msg, det_msg='', show_copy_button=False,
    default_yes=True,
    # Skippable dialogs
    # Set skip_dialog_name to a unique name for this dialog
    # Set skip_dialog_msg to a message displayed to the user
    skip_dialog_name=None, skip_dialog_msg=_('Show this confirmation again'),
    skip_dialog_skipped_value=True, skip_dialog_skip_precheck=True,
    # Override icon (QIcon to be used as the icon for this dialog or string for I())
    override_icon=None,
    # Change the text/icons of the yes and no buttons.
    # The icons must be QIcon objects or strings for I()
    yes_text=None, no_text=None, yes_icon=None, no_icon=None,
    # for yes/no to all memory:
    question_name=None,
    question_cache=None,
):

    # print(question_cache)
    if isinstance(question_cache,dict) and question_name and question_name in question_cache:
        return question_cache[question_name]
    from calibre.gui2.dialogs.message_box import MessageBox

    if not isinstance(skip_dialog_name, unicode):
        skip_dialog_name = None
    try:
        auto_skip = set(gprefs.get('questions_to_auto_skip', ()))
    except Exception:
        auto_skip = set()
    if (skip_dialog_name is not None and skip_dialog_name in auto_skip):
        return bool(skip_dialog_skipped_value)

    ## There's almost certainly a more elegant way to do this, but
    ## this works and I understand it.  all_flag is a contain so the
    ## click connect can change the contents.
    all_flag = []
    def set_all_flag(a,s):
        a.append(s)

    d = MessageBox(MessageBox.QUESTION, title, msg, det_msg, parent=parent,
                   show_copy_button=show_copy_button, default_yes=default_yes,
                   q_icon=override_icon, yes_text=yes_text, no_text=no_text,
                   yes_icon=yes_icon, no_icon=no_icon)

    d.bb.setStandardButtons(d.bb.Yes|d.bb.No|d.bb.YesToAll|d.bb.NoToAll)
    d.bb.button(d.bb.YesToAll).setIcon(d.bb.button(d.bb.Yes).icon())
    d.bb.button(d.bb.NoToAll ).setIcon(d.bb.button(d.bb.No ).icon())
    d.bb.button(d.bb.YesToAll).clicked.connect(partial(set_all_flag,all_flag,'yes_all'))
    d.bb.button(d.bb.NoToAll ).clicked.connect(partial(set_all_flag,all_flag,'no_all'))
#    d.bb.button(d.bb.NoToAll ).clicked.connect(lambda x:no_all = True)

    if skip_dialog_name is not None and skip_dialog_msg:
        tc = d.toggle_checkbox
        tc.setVisible(True)
        tc.setText(skip_dialog_msg)
        tc.setChecked(bool(skip_dialog_skip_precheck))
        d.resize_needed.emit()

    ret = d.exec_() == d.Accepted

    # print("yes/no_all:")
    # print(all_flag)
    if all_flag and isinstance(question_cache,dict) and question_name:
        question_cache[question_name] = (all_flag[0] == 'yes_all')
    # print(question_cache)

    if skip_dialog_name is not None and not d.toggle_checkbox.isChecked():
        auto_skip.add(skip_dialog_name)
        gprefs.set('questions_to_auto_skip', list(auto_skip))

    return ret

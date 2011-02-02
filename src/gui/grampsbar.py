#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2011       Nick Hall
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# $Id$

"""
Module that implements the sidebar and bottombar fuctionality.
"""
#-------------------------------------------------------------------------
#
# Python modules
#
#-------------------------------------------------------------------------
from gen.ggettext import gettext as _
import time
import os

#-------------------------------------------------------------------------
#
# GNOME modules
#
#-------------------------------------------------------------------------
import gtk
gtk.rc_parse_string("""
    style "tab-button-style" {
       GtkWidget::focus-padding = 0
       GtkWidget::focus-line-width = 0
       xthickness = 0
       ythickness = 0
    }
    widget "*.tab-button" style "tab-button-style"
    """)

#-------------------------------------------------------------------------
#
# Gramps modules
#
#-------------------------------------------------------------------------
import ConfigParser
import const
import ManagedWindow
import GrampsDisplay
from gui.widgets.grampletpane import (AVAILABLE_GRAMPLETS,
                                      GET_AVAILABLE_GRAMPLETS,
                                      get_gramplet_opts,
                                      get_gramplet_options_by_name,
                                      make_requested_gramplet,
                                      GuiGramplet)
from gui.widgets.undoablebuffer import UndoableBuffer
from ListModel import ListModel, NOSORT

#-------------------------------------------------------------------------
#
# Constants
#
#-------------------------------------------------------------------------
WIKI_HELP_PAGE = const.URL_MANUAL_PAGE + '_-_Gramplets'
NL = "\n"

#-------------------------------------------------------------------------
#
# GrampsBar class
#
#-------------------------------------------------------------------------
class GrampsBar(gtk.Notebook):
    """
    A class which defines the graphical representation of the GrampsBar.
    """
    def __init__(self, dbstate, uistate, pageview, configfile, defaults):
        gtk.Notebook.__init__(self)

        self.dbstate = dbstate
        self.uistate = uistate
        self.pageview = pageview
        self.configfile = os.path.join(const.VERSION_DIR, "%s.ini" % configfile)
        self.detached_gramplets = []
        self.empty = False

        self.set_group_id(1)
        self.set_show_border(False)
        self.set_scrollable(True)
        self.connect('switch-page', self.__switch_page)
        self.connect('page-added', self.__page_added)
        self.connect('page-removed', self.__page_removed)
        self.connect('create-window', self.__create_window)
        self.connect('button-press-event', self.__button_press)

        config_settings, opts_list = self.__load(defaults)

        opts_list.sort(key=lambda opt: opt["page"])
        for opts in opts_list:
            all_opts = get_gramplet_opts(opts["name"], opts)
            gramplet = make_requested_gramplet(TabGramplet, self, all_opts, 
                                               self.dbstate, self.uistate)
            self.__add_tab(gramplet)

        if len(opts_list) == 0:
            self.empty = True
            self.__create_empty_tab()

        if config_settings[0]:
            self.show()
        self.set_current_page(config_settings[1])

    def __load(self, defaults):
        """
        Load the gramplets from the configuration file.
        """
        retval = []
        visible = False
        default_page = 0
        filename = self.configfile
        if filename and os.path.exists(filename):
            cp = ConfigParser.ConfigParser()
            cp.read(filename)
            for sec in cp.sections():
                if sec == "Bar Options":
                    if "visible" in cp.options(sec):
                        visible = cp.get(sec, "visible") == "True"
                    if "page" in cp.options(sec):
                        default_page = int(cp.get(sec, "page"))
                else:
                    data = {"title": sec}
                    for opt in cp.options(sec):
                        if opt.startswith("data["):
                            temp = data.get("data", {})
                            #temp.append(cp.get(sec, opt).strip())
                            pos = int(opt[5:-1])
                            temp[pos] = cp.get(sec, opt).strip()
                            data["data"] = temp
                        else:
                            data[opt] = cp.get(sec, opt).strip()
                    if "data" in data:
                        data["data"] = [data["data"][key]
                                        for key in sorted(data["data"].keys())]
                    if "name" not in data:
                        data["name"] = "Unnamed Gramplet"
                        data["tname"] = _("Unnamed Gramplet")
                    retval.append(data)
        else:
            # give defaults as currently known
            for name in defaults:
                if name in AVAILABLE_GRAMPLETS():
                    retval.append(GET_AVAILABLE_GRAMPLETS(name))
        return ((visible, default_page), retval)

    def __save(self):
        """
        Save the gramplet configuration.
        """
        filename = self.configfile
        try:
            fp = open(filename, "w")
        except IOError:
            print "Failed writing '%s'; gramplets not saved" % filename
            return
        fp.write(";; Gramps bar configuration file" + NL)
        fp.write((";; Automatically created at %s" %
                                 time.strftime("%Y/%m/%d %H:%M:%S")) + NL + NL)
        fp.write("[Bar Options]" + NL)
        fp.write(("visible=%s" + NL) % self.get_property('visible'))
        fp.write(("page=%d" + NL) % self.get_current_page())
        fp.write(NL) 

        if self.empty:
            gramplet_list = []
        else:
            gramplet_list = [self.get_nth_page(page_num)
                             for page_num in range(self.get_n_pages())]

        for page_num, gramplet in enumerate(gramplet_list):
            opts = get_gramplet_options_by_name(gramplet.gname)
            if opts is not None:
                base_opts = opts.copy()
                for key in base_opts:
                    if key in gramplet.__dict__:
                        base_opts[key] = gramplet.__dict__[key]
                fp.write(("[%s]" + NL) % gramplet.title)
                for key in base_opts:
                    if key in ["content", "title", "row", "column", "page",
                               "version", "gramps"]: # don't save
                        continue
                    elif key == "data":
                        if not isinstance(base_opts["data"], (list, tuple)):
                            fp.write(("data[0]=%s" + NL) % base_opts["data"])
                        else:
                            cnt = 0
                            for item in base_opts["data"]:
                                fp.write(("data[%d]=%s" + NL) % (cnt, item))
                                cnt += 1
                    else:
                        fp.write(("%s=%s" + NL)% (key, base_opts[key]))
                fp.write(("page=%d" + NL) % page_num)
                fp.write(NL)

        fp.close()

    def set_active(self):
        """
        Called with the view is set as active.
        """
        if not self.empty:
            gramplet = self.get_nth_page(self.get_current_page())
            if gramplet and gramplet.pui:
                gramplet.pui.active = True
                if gramplet.pui.dirty:
                    gramplet.pui.update()

    def set_inactive(self):
        """
        Called with the view is set as inactive.
        """
        if not self.empty:
            gramplet = self.get_nth_page(self.get_current_page())
            if gramplet and gramplet.pui:
                gramplet.pui.active = False

    def on_delete(self):
        """
        Called when the view is closed.
        """
        map(self.__dock_gramplet, self.detached_gramplets)
        if not self.empty:
            for page_num in range(self.get_n_pages()):
                gramplet = self.get_nth_page(page_num)
                # this is the only place where the gui runs user code directly
                if gramplet.pui:
                    gramplet.pui.on_save()
        self.__save()

    def add_gramplet(self, gname):
        """
        Add a gramplet by name.
        """
        if self.has_gramplet(gname):
            return
        all_opts = get_gramplet_options_by_name(gname)
        gramplet = make_requested_gramplet(TabGramplet, self, all_opts,
                                           self.dbstate, self.uistate)
        if not gramplet:
            print "Problem creating ", gname
            return

        page_num = self.__add_tab(gramplet)
        self.set_current_page(page_num)

    def remove_gramplet(self, gname):
        """
        Remove a gramplet by name.
        """
        for gramplet in self.detached_gramplets:
            if gramplet.gname == gname:
                self.__dock_gramplet(gramplet)
                self.remove_page(self.page_num(gramplet))
                return

        for page_num in range(self.get_n_pages()):
            gramplet = self.get_nth_page(page_num)
            if gramplet.gname == gname:
                self.remove_page(page_num)
                return

    def has_gramplet(self, gname):
        """
        Return True if the GrampsBar contains the gramplet, else False.
        """
        return gname in self.all_gramplets()

    def all_gramplets(self):
        """
        Return a list of names of all the gramplets in the GrampsBar.
        """
        if self.empty:
            return self.detached_gramplets
        else:
            return [gramplet.gname for gramplet in self.get_children() +
                                                   self.detached_gramplets]

    def __create_empty_tab(self):
        """
        Create an empty tab to be displayed when the GrampsBar is empty.
        """
        tab_label = gtk.Label(_('Gramps Bar'))
        tab_label.show()
        msg = _('Right-click to the right of the tab to add a gramplet.')
        content = gtk.Label(msg)
        content.show()
        self.append_page(content, tab_label)
        return content

    def __add_clicked(self):
        """
        Called when the add button is clicked.
        """
        skip = self.all_gramplets()
        names = [name for name in AVAILABLE_GRAMPLETS() if name not in skip]
        gramplet_list = [(GET_AVAILABLE_GRAMPLETS(name)["tname"], name)
                         for name in names]
        gramplet_list.sort()

        dialog = ChooseGrampletDialog(_("Select Gramplet"), gramplet_list)
        name = dialog.run()
        if name:
            self.add_gramplet(name)

    def __add_tab(self, gramplet):
        """
        Add a tab to the notebook for the given gramplet.
        """
        gramplet.set_size_request(gramplet.width, gramplet.height)
        page_num = self.append_page(gramplet)
        return page_num

    def __create_tab_label(self, gramplet):
        """
        Create a tab label consisting of a label and a close button.
        """
        hbox = gtk.HBox(False, 4)
        label = gtk.Label(gramplet.title)
        label.set_tooltip_text(gramplet.tname)
        closebtn = gtk.Button()
        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
        closebtn.connect("clicked", self.__delete_clicked, gramplet)
        closebtn.set_image(image)
        closebtn.set_relief(gtk.RELIEF_NONE)

        # The next three lines adjust the close button to the correct size.
        closebtn.set_name('tab-button')
        size = gtk.icon_size_lookup_for_settings(closebtn.get_settings(),
                                                 gtk.ICON_SIZE_MENU)
        closebtn.set_size_request(size[0] + 2, size[1] + 2)

        hbox.pack_start(label, True, True)
        hbox.pack_end(closebtn, False, False)
        hbox.show_all()
        return hbox

    def __delete_clicked(self, button, gramplet):
        """
        Called when the delete button is clicked.
        """
        page_num = self.page_num(gramplet)
        self.remove_page(page_num)

    def __switch_page(self, notebook, unused, new_page):
        """
        Called when the user has switched to a new GrampsBar page.
        """
        old_page = notebook.get_current_page()
        if old_page >= 0:
            gramplet = self.get_nth_page(old_page)
            if gramplet and gramplet.pui:
                gramplet.pui.active = False

        gramplet = self.get_nth_page(new_page)
        if not self.empty:
            if gramplet and gramplet.pui:
                gramplet.pui.active = True
                if gramplet.pui.dirty:
                    gramplet.pui.update()

    def __page_added(self, notebook, unused, new_page):
        """
        Called when a new page is added to the GrampsBar.
        """
        gramplet = self.get_nth_page(new_page)
        if self.empty:
            if isinstance(gramplet, TabGramplet):
                self.remove_page(0)
                self.empty = False
            else:
                return
        label = self.__create_tab_label(gramplet)
        self.set_tab_label(gramplet, label)
        self.set_tab_reorderable(gramplet, True)
        self.set_tab_detachable(gramplet, True)
        if gramplet in self.detached_gramplets:
            self.detached_gramplets.remove(gramplet)
            self.reorder_child(gramplet, gramplet.page)

    def __page_removed(self, notebook, unused, page_num):
        """
        Called when a page is removed to the GrampsBar.
        """
        if self.get_n_pages() == 0:
            self.empty = True
            self.__create_empty_tab()
        
    def __create_window(self, grampsbar, gramplet, x_pos, y_pos):
        """
        Called when the user has switched to a new GrampsBar page.
        """
        gramplet.page = self.page_num(gramplet)
        self.detached_gramplets.append(gramplet)
        win = DetachedWindow(grampsbar, gramplet, x_pos, y_pos)
        gramplet.detached_window = win
        return win.get_notebook()

    def __dock_gramplet(self, gramplet):
        """
        Dock a detached gramplet.
        """
        gramplet.detached_window.close()
        gramplet.detached_window = None

    def __button_press(self, widget, event):
        """
        Called when a button is pressed in the tabs section of the GrampsBar.
        """
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            # TODO: We will probably want a context menu here.
            self.__add_clicked()

#-------------------------------------------------------------------------
#
# TabGramplet class
#
#-------------------------------------------------------------------------
class TabGramplet(gtk.ScrolledWindow, GuiGramplet):
    """
    Class that handles the plugin interfaces for the GrampletBar.
    """
    def __init__(self, pane, dbstate, uistate, title, **kwargs):
        """
        Internal constructor for GUI portion of a gramplet.
        """
        gtk.ScrolledWindow.__init__(self)
        GuiGramplet.__init__(self, pane, dbstate, uistate, title, **kwargs)

        self.scrolledwindow = self
        self.textview = gtk.TextView()
        self.buffer = UndoableBuffer()
        self.text_length = 0
        self.textview.set_buffer(self.buffer)
        self.textview.connect("key-press-event", self.on_key_press_event)
        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.add(self.textview)
        self.show_all()

    def get_container_widget(self):
        """
        Return the top level container widget.
        """
        return self

#-------------------------------------------------------------------------
#
# DetachedWindow class
#
#-------------------------------------------------------------------------
class DetachedWindow(ManagedWindow.ManagedWindow):
    """
    Class for showing a detached gramplet.
    """
    def __init__(self, grampsbar, gramplet, x_pos, y_pos):
        """
        Construct the window.
        """
        self.title = gramplet.title + " " + _("Gramplet")
        self.grampsbar = grampsbar
        self.gramplet = gramplet

        ManagedWindow.ManagedWindow.__init__(self, gramplet.uistate, [],
                                             self.title)
        self.set_window(gtk.Dialog("", gramplet.uistate.window,
                                   gtk.DIALOG_DESTROY_WITH_PARENT,
                                   (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)),
                        None,
                        self.title)
        self.window.move(x_pos, y_pos)
        self.window.set_size_request(gramplet.detached_width,
                                     gramplet.detached_height)
        self.window.add_button(gtk.STOCK_HELP, gtk.RESPONSE_HELP)
        self.window.connect('response', self.handle_response)

        self.notebook = gtk.Notebook()
        self.notebook.set_show_tabs(False)
        self.notebook.set_show_border(False)
        self.notebook.show()
        self.window.vbox.add(self.notebook)
        self.show()

    def handle_response(self, object, response):
        """
        Callback for taking care of button clicks.
        """
        if response in [gtk.RESPONSE_CLOSE, gtk.STOCK_CLOSE]:
            self.close()
        elif response == gtk.RESPONSE_HELP:
            # translated name:
            if self.gramplet.help_url:
                if self.gramplet.help_url.startswith("http://"):
                    GrampsDisplay.url(self.gramplet.help_url)
                else:
                    GrampsDisplay.help(self.gramplet.help_url)
            else:
                GrampsDisplay.help(WIKI_HELP_PAGE, 
                                   self.gramplet.tname.replace(" ", "_"))

    def get_notebook(self):
        """
        Return the notebook.
        """
        return self.notebook

    def build_menu_names(self, obj):
        """
        Part of the GRAMPS window interface.
        """
        return (self.title, 'Gramplet')

    def get_title(self):
        """
        Returns the window title.
        """
        return self.title

    def close(self, *args):
        """
        Dock the detached gramplet back in the GrampsBar from where it came.
        """
        size = self.window.get_size()
        self.gramplet.detached_width = size[0]
        self.gramplet.detached_height = size[1]
        self.gramplet.detached_window = None
        self.gramplet.reparent(self.grampsbar)
        ManagedWindow.ManagedWindow.close(self, *args)

#-------------------------------------------------------------------------
#
# Choose Gramplet Dialog
#
#-------------------------------------------------------------------------
class ChooseGrampletDialog(object):
    """
    A dialog to choose a gramplet
    """
    def __init__(self, title, names):
        self.title = title
        self.names = names
        self.namelist = None
        self.namemodel = None
        self.top = self._create_dialog()

    def run(self):
        """
        Run the dialog and return the result.
        """
        self._populate_model()
        response = self.top.run()
        result = None
        if response == gtk.RESPONSE_OK:
            store, iter_ = self.namemodel.get_selected()
            if iter_:
                result = store.get_value(iter_, 1)
        self.top.destroy()
        return result

    def _populate_model(self):
        """
        Populate the model.
        """
        self.namemodel.clear()
        for name in self.names:
            self.namemodel.add(name)
        
    def _create_dialog(self):
        """
        Create a dialog box to organize tags.
        """
        # pylint: disable-msg=E1101
        title = _("%(title)s - Gramps") % {'title': self.title}
        top = gtk.Dialog(title)
        top.set_default_size(400, 350)
        top.set_modal(True)
        top.set_has_separator(False)
        top.vbox.set_spacing(5)
        label = gtk.Label('<span size="larger" weight="bold">%s</span>'
                          % self.title)
        label.set_use_markup(True)
        top.vbox.pack_start(label, 0, 0, 5)
        box = gtk.HBox()
        top.vbox.pack_start(box, 1, 1, 5)
        
        name_titles = [(_('Name'), NOSORT, 200),
                       ('', NOSORT, 200)]
        self.namelist = gtk.TreeView()
        self.namemodel = ListModel(self.namelist, name_titles)

        slist = gtk.ScrolledWindow()
        slist.add_with_viewport(self.namelist)
        slist.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        box.pack_start(slist, 1, 1, 5)
        bbox = gtk.VButtonBox()
        bbox.set_layout(gtk.BUTTONBOX_START)
        bbox.set_spacing(6)
        top.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
        top.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        box.pack_start(bbox, 0, 0, 5)
        top.show_all()
        return top

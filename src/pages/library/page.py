from gettext import gettext as _

from gi.repository import Adw, Gio, GObject, Gtk

from ...components import Grid
from ...components.formats import type_title


def compare(first, second):
    return (first > second) - (first < second)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/library/page.ui')
class LibraryPage(Adw.Bin):
    __gtype_name__ = "ChelseaLibraryPage"

    stack = Gtk.Template.Child()
    empty_page = Gtk.Template.Child()
    sign_in_button = Gtk.Template.Child()
    type_dropdown = Gtk.Template.Child()
    sort_dropdown = Gtk.Template.Child()
    grid = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.types = [""]
        self.filter = Gtk.CustomFilter.new(self.filter_func)
        self.sorter = Gtk.CustomSorter.new(self.sort_func)
        self.type_dropdown.set_model(Gtk.StringList.new([_("All")]))
        filtered = Gtk.FilterListModel(model=self.integration.library, filter=self.filter)
        self.model = Gtk.SortListModel(model=filtered, sorter=self.sorter)
        self.grid.bind_model(self.model, get_meta=lambda item: item.meta)
        self.model.connect("items-changed", lambda *args: self.update_state())

        self.integration.bind_property("signed-in", self.sign_in_button, "visible",
                                       GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN)
        self.integration.connect("notify::library-revision", lambda *args: self.on_library_changed())
        self.on_library_changed()

    def on_library_changed(self):
        types = [""]
        for item in self.integration.savedItems():
            if item.type not in types:
                types.append(item.type)
        if types != self.types:
            selected = self.types[self.type_dropdown.get_selected()] if self.types else ""
            self.types = types
            labels = [type_title(item) if item else _("All") for item in types]
            self.type_dropdown.set_model(Gtk.StringList.new(labels))
            self.type_dropdown.set_selected(types.index(selected) if selected in types else 0)
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)
        self.update_state()

    def update_state(self):
        self.stack.set_visible_child_name("grid" if self.model.get_n_items() else "empty")

    def filter_func(self, item):
        if not item.in_library:
            return False
        index = self.type_dropdown.get_selected()
        wanted = self.types[index] if 0 <= index < len(self.types) else ""
        return not wanted or item.type == wanted

    def sort_func(self, first, second, *args):
        key = self.sort_dropdown.get_selected()
        if key == 0:
            return compare(second.last_watched or second.modified_at, first.last_watched or first.modified_at)
        if key == 1:
            return compare(second.added_at, first.added_at)
        return compare(first.name.lower(), second.name.lower())

    @Gtk.Template.Callback()
    def on_filter_changed(self, dropdown, pspec):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    @Gtk.Template.Callback()
    def on_sort_changed(self, dropdown, pspec):
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

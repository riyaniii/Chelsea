from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

ICON_SIZE = 96
CELL_WIDTH = 120


def file_icon(name: str, is_folder: bool = False) -> Gio.Icon:
    if is_folder:
        return Gio.ThemedIcon.new("folder")
    content_type, uncertain = Gio.content_type_guess(name, None)
    return Gio.content_type_get_icon(content_type)


class FileCell(Gtk.Box):
    __gtype_name__ = "ChelseaFileCell"

    def __init__(self, grid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START,
                         width_request=CELL_WIDTH, css_classes=["file-cell"])
        self.grid = grid
        self.position = 0
        self.handlers = []

        self.icon = Gtk.Image(pixel_size=ICON_SIZE, css_classes=["file-icon"])
        self.progress = Gtk.ProgressBar(visible=False, margin_start=12, margin_end=12)
        self.name = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, lines=3,
                              ellipsize=Pango.EllipsizeMode.MIDDLE, justify=Gtk.Justification.CENTER,
                              width_chars=12, max_width_chars=12)
        self.caption = Gtk.Label(visible=False, css_classes=["dimmed", "caption", "numeric"],
                                 wrap=True, justify=Gtk.Justification.CENTER,
                                 width_chars=12, max_width_chars=12)
        for widget in (self.icon, self.progress, self.name, self.caption):
            self.append(widget)

        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", lambda gesture, presses, x, y: self.open_menu(x, y))
        self.add_controller(right_click)
        long_press = Gtk.GestureLongPress(touch_only=True)
        long_press.connect("pressed", lambda gesture, x, y: self.open_menu(x, y))
        self.add_controller(long_press)

    def show_file(self, name: str, icon: Gio.Icon):
        self.name.set_label(name)
        self.set_tooltip_text(name)
        self.icon.set_from_gicon(icon)

    def show_status(self, caption: str = "", progress: float | None = None):
        self.caption.set_label(caption)
        self.caption.set_visible(bool(caption))
        self.progress.set_visible(progress is not None)
        if progress is not None:
            self.progress.set_fraction(progress)

    def watch(self, item: GObject.Object, signal: str, callback):
        self.handlers.append((item, item.connect(signal, callback)))

    def release(self):
        for item, handler in self.handlers:
            item.disconnect(handler)
        self.handlers = []
        self.show_status()

    def open_menu(self, x: float, y: float):
        menu = self.grid.prepare_menu(self.position)
        if menu is None:
            return
        popover = Gtk.PopoverMenu(menu_model=menu, has_arrow=False, halign=Gtk.Align.START)
        popover.set_parent(self)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.connect("closed", lambda popover: GLib.idle_add(popover.unparent))
        popover.popup()


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/file_grid.ui')
class FileGrid(Adw.Bin):
    __gtype_name__ = "ChelseaFileGrid"

    grid = Gtk.Template.Child()

    __gsignals__ = {
        "activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "menu-opening": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind_cell = None
        self.selection = None
        self.menu = None
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda factory, list_item: list_item.set_child(FileCell(self)))
        factory.connect("bind", self.on_bind)
        factory.connect("unbind", lambda factory, list_item: list_item.get_child().release())
        self.grid.set_factory(factory)

    def set_files(self, model: Gio.ListModel, bind_cell):
        self.bind_cell = bind_cell
        self.selection = Gtk.MultiSelection(model=model)
        self.grid.set_model(self.selection)

    def set_menu(self, menu: Gio.MenuModel):
        self.menu = menu

    def selected_items(self) -> list:
        if self.selection is None:
            return []
        selected = self.selection.get_selection()
        return [self.selection.get_item(selected.get_nth(index)) for index in range(selected.get_size())]

    def prepare_menu(self, position: int):
        if self.menu is None:
            return None
        if not self.selection.is_selected(position):
            self.selection.select_item(position, True)
        self.emit("menu-opening")
        return self.menu

    def on_bind(self, factory, list_item):
        cell = list_item.get_child()
        cell.position = list_item.get_position()
        self.bind_cell(cell, list_item.get_item())

    @Gtk.Template.Callback()
    def on_activate(self, grid, position):
        self.emit("activated", self.selection.get_item(position))

from gi.repository import Adw, Gio, GObject, Gtk

from ..pages.addons import AddonsPage
from .avatars import load_avatar
from ..pages.discover import DiscoverPage
from ..pages.downloads import DownloadsPage
from ..pages.home import HomePage
from ..pages.library import LibraryPage
from ..pages.search import SearchPage


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/main_view.ui')
class ChelseaMainView(Adw.BreakpointBin):
    __gtype_name__ = 'ChelseaMainView'

    main_stack = Gtk.Template.Child()
    main_nav_view = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    home_page = Gtk.Template.Child()
    discover_page = Gtk.Template.Child()
    library_page = Gtk.Template.Child()
    search_page = Gtk.Template.Child()
    addons_page = Gtk.Template.Child()
    downloads_page = Gtk.Template.Child()
    menu_avatar = Gtk.Template.Child()

    active_downloads = GObject.Property(type=int, default=0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = Gio.Application.get_default()
        app.downloads.bind_property("active", self, "active-downloads", GObject.BindingFlags.SYNC_CREATE)
        app.integration.bind_property("profile-name", self.menu_avatar, "text", GObject.BindingFlags.SYNC_CREATE)
        app.integration.connect("notify::avatar-url",
                                lambda integration, pspec: load_avatar(self.menu_avatar, integration.avatar_url))


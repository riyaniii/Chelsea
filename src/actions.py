from gettext import gettext as _

from gi.repository import Adw, Gtk

from .integrations import IntegrationError


def get_window(app):
    return app.get_active_window() or app.window


def switch_page(app, name: str):
    window = get_window(app)
    if window.main_nav_view.get_visible_page().get_tag() != "main":
        window.main_nav_view.pop_to_tag("main")
    window.main_stack.set_visible_child_name(name)


def open_home_page(app):
    switch_page(app, 'home')


def open_discover_page(app):
    switch_page(app, 'discover')


def open_library_page(app):
    switch_page(app, 'library')


def open_downloads_page(app):
    switch_page(app, 'downloads')


def open_addons_page(app):
    switch_page(app, 'addons')


def open_search_page(app):
    switch_page(app, 'search')
    get_window(app).search_page.focus_entry()


def show_catalog(app, key: str):
    switch_page(app, 'discover')
    get_window(app).discover_page.select_catalog(key)


def show_page(app, page: Adw.NavigationPage):
    get_window(app).main_nav_view.push(page)


def show_dialog(app, dialog: Adw.Dialog):
    dialog.present(get_window(app))


def show_toast(app, message: str):
    window = get_window(app)
    if window.window_stack.get_visible_child_name() != "main":
        window.toast(message)
        return
    toast_overlay = window.toast_overlay
    toast_overlay.dismiss_all()
    toast_overlay.add_toast(Adw.Toast(title=message, timeout=3, use_markup=False))


def open_uri(app, uri: str):
    Gtk.UriLauncher.new(uri).launch(get_window(app), None, None)


def open_link(app, uri: str):
    target = app.integration.parseLink(uri)
    if target is None:
        show_toast(app, _("Chelsea can't open this link"))
        return None
    page = target["page"]
    if page == "details":
        return show_meta(app, target["type"], target["id"])
    if page == "addon":
        switch_page(app, "addons")
        get_window(app).addons_page.show_link(target["url"])
    elif page == "search":
        switch_page(app, "search")
        get_window(app).search_page.search_for(target["query"])
    else:
        switch_page(app, page)
    return None


def switch_profile(app):
    get_window(app).show_profiles()


def sign_in(app):
    from .pages.setup import SetupDialog
    show_dialog(app, SetupDialog(login_only=True))


async def play_meta(app, meta_type: str, meta_id: str):
    await show_meta(app, meta_type, meta_id, play=True)


async def show_meta(app, meta_type: str, meta_id: str, play: bool = False):
    from .pages.details import DetailsPage
    meta = app.integration.getModel('Meta', (meta_type, meta_id))
    if meta is None:
        try:
            meta = await app.integration.getMeta(meta_type, meta_id)
        except IntegrationError as error:
            show_toast(app, str(error))
            return
    show_page(app, DetailsPage(meta, play=play))

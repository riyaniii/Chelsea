Thanks for your interest in contributing to Chelsea!


## Code contributions

Pull requests are welcome!

If you're interested in taking on [an open issue](https://github.com/riyaniii/Chelsea/issues), please comment on it so others are aware.
You do not need to ask for permission nor an assignment.

Your name will be added to the list of contributors in the app's about dialog.


## Project layout

- `src/integrations/` talks to services. `stremio.py` is the Stremio wrapper, `nuvio.py` the torrent engine, and `models.py` holds the models every page uses.
- `src/pages/` has one folder per page, each with its `page.py`, `page.blp` and the widgets only that page uses.
- `src/components/` has the widgets shared between pages, like `card`, `row`, `grid` and `hero`.
- Interfaces are written in [Blueprint](https://gnome.pages.gitlab.gnome.org/blueprint-compiler/) (`.blp`).


## Translations

Copy `po/chelsea.pot` to `po/<language code>.po`, translate it with a tool like [Poedit](https://poedit.net), add the language code to `po/LINGUAS` and open a pull request.

When strings change, regenerate the template with:

```sh
meson setup _build
meson compile -C _build chelsea-pot
```


## Code of Conduct

This project follows the [GNOME Code of Conduct](https://conduct.gnome.org/).

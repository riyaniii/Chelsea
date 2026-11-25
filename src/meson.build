pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'chelsea'
gnome = import('gnome')

blueprint_compiler = find_program('blueprint-compiler', version: '>= 0.18.0')
src_dir = meson.current_source_dir()

python = import('python')
python3 = python.find_installation('python3')

conf = configuration_data()
conf.set('PYTHON', python3.full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'chelsea.in',
  output: 'chelsea',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

chelsea_sources = [
  '__init__.py',
  'actions.py',
  'constants.py',
  'downloads.py',
  'languages.py',
  'main.py',
  'gpu.py',
  'mpris.py',
  'passwords.py',
  'profiles.py',
]

install_data(chelsea_sources, install_dir: moduledir)

subdir('integrations')
subdir('components')
subdir('pages')

blueprint_files = [
  'components/card.blp',
  'components/donate.blp',
  'components/grid.blp',
  'components/hero.blp',
  'components/file_grid.blp',
  'components/link_dialog.blp',
  'components/magnet_dialog.blp',
  'components/main_view.blp',
  'components/row.blp',
  'components/shortcuts.blp',
  'components/window.blp',
  'pages/addons/addon_row.blp',
  'pages/addons/page.blp',
  'pages/details/episode_row.blp',
  'pages/details/page.blp',
  'pages/details/panel.blp',
  'pages/details/stream_card.blp',
  'pages/details/streams_view.blp',
  'pages/discover/page.blp',
  'pages/downloads/page.blp',
  'pages/home/page.blp',
  'pages/library/page.blp',
  'pages/player/options.blp',
  'pages/player/page.blp',
  'pages/preferences/dialog.blp',
  'pages/profiles/page.blp',
  'pages/search/page.blp',
  'pages/setup/dialog.blp',
]

blueprints = custom_target('blueprints',
  input: files(blueprint_files),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', src_dir, '@INPUT@'],
  build_always_stale: true,
)

gnome.compile_resources('chelsea',
  'chelsea.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: [blueprints, appstream_file],
  source_dir: [meson.current_source_dir(), meson.project_build_root() / 'data'],
)

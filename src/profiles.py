import uuid
from gettext import gettext as _

from gi.repository import GLib

GUEST = 'guest'
ACCOUNT = 'stremio'


def load_profiles(settings) -> list:
    return [dict(profile) for profile in settings.get_value('profiles').unpack()]


def save_profiles(settings, profiles: list) -> None:
    settings.set_value('profiles', GLib.Variant('aa{ss}', profiles))


def find_profile(settings, profile_id: str) -> dict | None:
    for profile in load_profiles(settings):
        if profile['id'] == profile_id:
            return profile
    return None


def default_name(email: str) -> str:
    local = email.split('@')[0] if email else ''
    return local.replace('.', ' ').replace('_', ' ').title() or _('Profile')


def ensure_guest(settings) -> dict:
    profiles = load_profiles(settings)
    for profile in profiles:
        if profile['kind'] == GUEST:
            return profile
    guest = {'id': GUEST, 'name': _('Guest'), 'kind': GUEST, 'email': ''}
    profiles.insert(0, guest)
    save_profiles(settings, profiles)
    return guest


def add_account(settings, email: str, name: str = '', avatar: str = '') -> dict:
    profiles = load_profiles(settings)
    for profile in profiles:
        if profile['kind'] == ACCOUNT and profile['email'].lower() == email.lower():
            if avatar and profile.get('avatar') != avatar:
                profile['avatar'] = avatar
                save_profiles(settings, profiles)
            return profile
    profile = {
        'id': uuid.uuid4().hex,
        'name': name or default_name(email),
        'kind': ACCOUNT,
        'email': email,
        'avatar': avatar,
    }
    profiles.append(profile)
    save_profiles(settings, profiles)
    return profile


def update_profile(settings, profile_id: str, **values) -> None:
    profiles = load_profiles(settings)
    for profile in profiles:
        if profile['id'] == profile_id:
            profile.update({key: str(value) for key, value in values.items()})
    save_profiles(settings, profiles)


def remove_profile(settings, secrets, profile_id: str) -> None:
    kept = []
    for profile in load_profiles(settings):
        if profile['id'] == profile_id:
            if profile['kind'] == ACCOUNT:
                secrets.forget(profile['email'])
        else:
            kept.append(profile)
    save_profiles(settings, kept)
    if settings.get_string('last-profile') == profile_id:
        settings.set_string('last-profile', '')

import asyncio

from gi.repository import Gio


def load_avatar(avatar, url: str):
    avatar.set_custom_image(None)
    if not url:
        return None

    async def load():
        try:
            avatar.set_custom_image(await Gio.Application.get_default().images.getPaintable(url))
        except Exception as error:
            print(f"avatar {url}: {error}")

    return asyncio.create_task(load())

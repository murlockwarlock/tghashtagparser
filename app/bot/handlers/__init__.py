from aiogram import Router

from app.bot.handlers import accounts, common, filters, posts, settings, tags


def build_router() -> Router:
    router = Router()
    router.include_router(common.router)
    router.include_router(tags.router)
    router.include_router(filters.router)
    router.include_router(accounts.router)
    router.include_router(settings.router)
    router.include_router(posts.router)
    return router

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import SimpleEventIsolation
from telethon import errors

from app.config import DATA, Config, ConfigurationError
from app.database.repository import Repository
from app.handlers import channels, history, search, settings, start
from app.services.search_service import SearchService
from app.services.telegram_client import PersonalTelegram

log = logging.getLogger(__name__)


async def on_error(event):
    log.warning("Ошибка обработки события (%s)", type(event.exception).__name__)
    message = event.update.message
    if event.update.callback_query:
        message = event.update.callback_query.message
    if message and message.chat.type == "private":
        try:
            await message.answer("Не удалось выполнить действие. Попробуйте ещё раз или отправьте /start.")
        except Exception as error:
            log.warning("Ошибка уведомления (%s)", type(error).__name__)
    return True


def build_dispatcher(owner_id):
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    access = start.OwnerOnly(owner_id)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)
    dispatcher.errors.register(on_error)
    dispatcher.include_routers(start.router, settings.router, channels.router, history.router, search.router)
    return dispatcher


async def main():
    config = Config.load()
    DATA.mkdir(mode=0o700, exist_ok=True)
    repo = Repository(DATA / "bot.sqlite")
    telegram = PersonalTelegram(config, repo)
    jobs = search.SearchJobs(SearchService(telegram, repo))
    dispatcher = build_dispatcher(config.owner_id)

    async with Bot(config.bot_token) as bot:
        try:
            await bot.get_me()
            await telegram.login()
            await bot.delete_webhook()
            log.info("Бот запущен. Откройте его в Telegram и отправьте /start.")
            await dispatcher.start_polling(
                bot, repo=repo, telegram=telegram, jobs=jobs, close_bot_session=False,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
        finally:
            await jobs.close()
            await telegram.client.disconnect()


def run():
    # Library diagnostics may contain transport details. Emit application-level descriptions only.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in ("aiogram", "telethon", "aiohttp"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        asyncio.run(main())
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    except ConfigurationError as error:
        log.error("%s", error)
    except TelegramUnauthorizedError:
        log.error("Telegram отклонил BOT_TOKEN. Проверьте токен в .env.")
    except errors.FloodWaitError as error:
        log.error("Telegram ограничил запросы. Повторите через %s сек.", error.seconds)
    except (errors.ApiIdInvalidError, errors.PhoneNumberInvalidError, errors.PhoneCodeInvalidError,
            errors.PhoneCodeExpiredError, errors.PasswordHashInvalidError) as error:
        log.error("Telegram отклонил данные входа (%s). Проверьте их и перезапустите бота.",
                  type(error).__name__)
    except (errors.UnauthorizedError, errors.AuthKeyError):
        log.error("Не удалось использовать сессию личного аккаунта. См. раздел об отзыве сессии в README.md.")
    except (TelegramNetworkError, ConnectionError, TimeoutError):
        log.error("Не удалось связаться с Telegram. Проверьте интернет и перезапустите бота.")
    except EOFError:
        log.error("Запустите бота в интерактивном терминале для первого входа.")
    except Exception as error:
        log.error("Не удалось запустить бота (%s). Проверьте настройки, сеть и другие запущенные копии.",
                  type(error).__name__)
    return 1


if __name__ == "__main__":
    raise SystemExit(run())

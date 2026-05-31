from aiogram.fsm.state import State, StatesGroup


class AddTag(StatesGroup):
    value = State()


class RemoveTag(StatesGroup):
    value = State()


class AddKeyword(StatesGroup):
    value = State()


class RemoveKeyword(StatesGroup):
    value = State()


class AddProxy(StatesGroup):
    title = State()
    proxy_type = State()
    host = State()
    port = State()
    username = State()
    password = State()


class AddAccount(StatesGroup):
    title = State()
    api_id = State()
    api_hash = State()
    phone = State()
    code = State()
    password = State()


class DelAccount(StatesGroup):
    acc_id = State()


class SetSetting(StatesGroup):
    key = State()
    value = State()


class AddChannel(StatesGroup):
    title = State()
    channel_id = State()
    username = State()


class SetAi(StatesGroup):
    api_key = State()
    model = State()


class SetBingX(StatesGroup):
    api_key = State()
    api_secret = State()
    referral = State()

class EditPost(StatesGroup):
    value = State()


class EditMedia(StatesGroup):
    value = State()

class FilterHashtag(StatesGroup):
    value = State()


class FilterSource(StatesGroup):
    value = State()

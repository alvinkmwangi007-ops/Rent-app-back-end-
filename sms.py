from auth import Fail


async def send(phone, message):
    raise Fail(501, "sms_not_configured", "SMS is not set up yet. Add your SMS provider code in sms.py.")

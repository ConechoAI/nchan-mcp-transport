import httpx
import logging


async def fetchUserInfo(token):
    try:
        response = httpx.get("https://api.conecho.ai/api/account", headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        response.raise_for_status()
        result = response.json()
        if result["code"] == 0 and result["data"]:
            return result, None
        else:
            raise ValueError(result["msg"])
    except Exception as e:
        return None, str(e)


async def addCount(token):
    try:
        response = httpx.get("https://api.conecho.ai/api/calltool", headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        response.raise_for_status()
        result = response.json()
        if result["code"] == 0 and result["data"] is not None:
            return result, None
        else:
            raise ValueError(result["msg"])
    except Exception as e:
        return None, str(e)


async def fetchRequest(api_base, headers, data, timeout=30):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                api_base,
                json=data,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetch request {api_base}: {str(e)}")
            return False

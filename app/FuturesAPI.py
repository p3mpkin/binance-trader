# -*- coding: UTF-8 -*-
# Binance USD-M Futures API wrapper

import time
import hashlib
import hmac
import requests
import config

try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode


class FuturesAPI:
    BASE_URL = "https://fapi.binance.com/fapi/v1"
    BASE_URL_V2 = "https://fapi.binance.com/fapi/v2"
    REQUEST_TIMEOUT = 30
    REQUEST_RETRIES = 3
    REQUEST_RETRY_WAIT = 0.5

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret

    def ping(self):
        return self._request_json('GET', f"{self.BASE_URL}/ping")

    def get_exchange_info(self):
        return self._request_json('GET', f"{self.BASE_URL}/exchangeInfo")

    def get_klines(self, market, interval, startTime, endTime, limit=None):
        params = {
            "symbol": market,
            "interval": interval,
            "startTime": startTime,
            "endTime": endTime,
        }
        if limit:
            params["limit"] = limit
        return self._get_no_sign(f"{self.BASE_URL}/klines", params)

    def get_ticker(self, market):
        return self._get_no_sign(f"{self.BASE_URL}/ticker/24hr", {"symbol": market})

    def get_tickers(self):
        return self._get_no_sign(f"{self.BASE_URL}/ticker/24hr", {})

    def get_order_books(self, market, limit=50):
        return self._get_no_sign(f"{self.BASE_URL}/depth", {"symbol": market, "limit": limit})

    def get_balance(self):
        return self._get(f"{self.BASE_URL_V2}/balance", {})

    def change_leverage(self, market, leverage):
        return self._post(f"{self.BASE_URL}/leverage", {"symbol": market, "leverage": leverage})

    def market_order(self, market, side, quantity, reduce_only=False):
        params = {
            "symbol": market,
            "side": side,
            "type": "MARKET",
            "quantity": "%.8f" % quantity,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._post(f"{self.BASE_URL}/order", params)

    def _get_no_sign(self, path, params=None):
        params = params or {}
        query = urlencode(params)
        return self._request_json('GET', f"{path}?{query}")

    def _sign(self, params=None):
        data = (params or {}).copy()
        data.update({"timestamp": int(1000 * time.time())})
        query = urlencode(data)
        secret = bytearray()
        secret.extend(self.secret.encode())
        signature = hmac.new(secret, msg=query.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
        data.update({"signature": signature})
        return data

    def _get(self, path, params=None):
        params = params or {}
        params.update({"recvWindow": config.recv_window})
        query = urlencode(self._sign(params))
        headers = {"X-MBX-APIKEY": self.key}
        return self._request_json('GET', f"{path}?{query}", headers=headers)

    def _post(self, path, params=None):
        params = params or {}
        params.update({"recvWindow": config.recv_window})
        query = urlencode(self._sign(params))
        headers = {"X-MBX-APIKEY": self.key}
        return self._request_json('POST', path, headers=headers, data=query)

    def _request_json(self, method, url, **kwargs):
        last_error = None
        for attempt in range(self.REQUEST_RETRIES):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                    verify=True,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_error = exc
                if attempt < self.REQUEST_RETRIES - 1:
                    time.sleep(self.REQUEST_RETRY_WAIT * (attempt + 1))
                    continue
                raise

        raise last_error

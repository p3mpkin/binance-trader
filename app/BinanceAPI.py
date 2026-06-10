import time
import hashlib
import requests
import hmac
import config

try:
    from urllib import urlencode
# python3
except ImportError:
    from urllib.parse import urlencode
 
class BinanceAPI:
    
    BASE_URL = "https://www.binance.com/api/v1"
    BASE_URL_V3 = "https://api.binance.com/api/v3"
    PUBLIC_URL = "https://www.binance.com/exchange/public/product"
    REQUEST_TIMEOUT = 30
    REQUEST_RETRIES = 3
    REQUEST_RETRY_WAIT = 0.5

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret

    def ping(self):
        path = "%s/ping" % self.BASE_URL_V3
        return self._request_json("GET", path)
    
    def get_history(self, market, limit=50):
        path = "%s/historicalTrades" % self.BASE_URL
        params = {"symbol": market, "limit": limit}
        return self._get_no_sign(path, params)
        
    def get_trades(self, market, limit=50):
        path = "%s/trades" % self.BASE_URL
        params = {"symbol": market, "limit": limit}
        return self._get_no_sign(path, params)
        
    def get_klines(self, market, interval, startTime, endTime):
        path = "%s/klines" % self.BASE_URL_V3
        params = {"symbol": market, "interval":interval, "startTime":startTime, "endTime":endTime}
        return self._get_no_sign(path, params)
        
    def get_ticker(self, market):
        path = "%s/ticker/24hr" % self.BASE_URL
        params = {"symbol": market}
        return self._get_no_sign(path, params)

    def get_tickers(self):
        path = "%s/ticker/24hr" % self.BASE_URL_V3
        return self._get_no_sign(path, {})

    def get_order_books(self, market, limit=50):
        path = "%s/depth" % self.BASE_URL
        params = {"symbol": market, "limit": limit}
        return self._get_no_sign(path, params)

    def get_account(self):
        path = "%s/account" % self.BASE_URL_V3
        return self._get(path, {})

    def get_products(self):
        return self._request_json("GET", self.PUBLIC_URL)
   
    def get_server_time(self):
        path = "%s/time" % self.BASE_URL_V3
        return self._request_json("GET", path)
    
    def get_exchange_info(self):
        path = "%s/exchangeInfo" % self.BASE_URL
        return self._request_json("GET", path)

    def get_open_orders(self, market, limit = 100):
        path = "%s/openOrders" % self.BASE_URL_V3
        params = {"symbol": market}
        return self._get(path, params)
    
    def get_my_trades(self, market, limit = 50):
        path = "%s/myTrades" % self.BASE_URL_V3
        params = {"symbol": market, "limit": limit}
        return self._get(path, params)

    def buy_limit(self, market, quantity, rate):
        path = "%s/order" % self.BASE_URL_V3
        params = self._order(market, quantity, "BUY", rate)
        return self._post(path, params)

    def sell_limit(self, market, quantity, rate):
        path = "%s/order" % self.BASE_URL_V3
        params = self._order(market, quantity, "SELL", rate)
        return self._post(path, params)

    def buy_market(self, market, quantity):
        path = "%s/order" % self.BASE_URL_V3
        params = self._order(market, quantity, "BUY")
        return self._post(path, params)

    def sell_market(self, market, quantity):
        path = "%s/order" % self.BASE_URL_V3
        params = self._order(market, quantity, "SELL")
        return self._post(path, params)

    def query_order(self, market, orderId):
        path = "%s/order" % self.BASE_URL_V3
        params = {"symbol": market, "orderId": orderId}
        return self._get(path, params)

    def cancel(self, market, order_id):
        path = "%s/order" % self.BASE_URL_V3
        params = {"symbol": market, "orderId": order_id}
        return self._delete(path, params)

    def _get_no_sign(self, path, params={}):
        query = urlencode(params)
        url = "%s?%s" % (path, query)
        return self._request_json("GET", url)
    
    def _sign(self, params={}):
        data = params.copy()

        ts = int(1000 * time.time())
        data.update({"timestamp": ts})
        h = urlencode(data)
        b = bytearray()
        b.extend(self.secret.encode())
        signature = hmac.new(b, msg=h.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()
        data.update({"signature": signature})
        return data

    def _get(self, path, params={}):
        params.update({"recvWindow": config.recv_window})
        query = urlencode(self._sign(params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.key}
        return self._request_json("GET", url, headers=header)

    def _post(self, path, params={}):
        params.update({"recvWindow": config.recv_window})
        query = urlencode(self._sign(params))
        url = "%s" % (path)
        header = {"X-MBX-APIKEY": self.key}
        return self._request_json("POST", url, headers=header, data=query)

    def _order(self, market, quantity, side, rate=None):
        params = {}
         
        if rate is not None:
            params["type"] = "LIMIT"
            params["price"] = self._format(rate)
            params["timeInForce"] = "GTC"
        else:
            params["type"] = "MARKET"

        params["symbol"] = market
        params["side"] = side
        params["quantity"] = '%.8f' % quantity
        
        return params
           
    def _delete(self, path, params={}):
        params.update({"recvWindow": config.recv_window})
        query = urlencode(self._sign(params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.key}
        return self._request_json("DELETE", url, headers=header)

    def _format(self, price):
        return "{:.8f}".format(price)

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

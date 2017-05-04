
"""A small and simple client library for the twitch.tv API"""

__requires__ = ['requests']


import re
from uuid import uuid4


import requests


def urljoin(base, *args):
	return '/'.join([base.rstrip('/')] + [arg.strip('/') for arg in args])


class TwitchClient(object):
	base_url = 'https://api.twitch.tv/kraken/'
	default_client_id = 'jzkbprff40iqj646a697cyrvl0zt2m6'

	def __init__(self, oauth=None, client_id=None):
		"""May authenticate with an oauth token. May set a custom client id."""
		self.oauth = oauth
		self.client_id = client_id or self.default_client_id

	def _request(self, method, endpoint, version=None, data={}, headers={}, json=True, oauth=True):
		"""Method should be a string 'get', 'post', etc.
		Endpoint should be the path from the base url, eg. '/channels'.
		version should be an integer.
		"""
		version_data = '' if version is None else '.v{}'.format(version)
		headers.setdefault('Accept', 'application/vnd.twitchtv{}+json'.format(version_data))
		if self.oauth and oauth:
			headers.setdefault("Authorization", "OAuth {}".format(self.oauth))
		headers.setdefault("Client-ID", self.client_id)
		if endpoint.startswith('https://'):
			url = endpoint
		else:
			url = urljoin(self.base_url, endpoint)
		data_arg = 'json' if method == 'POST' else 'params'
		response = requests.request(method, url, headers=headers, **{data_arg: data})
		response.raise_for_status()
		if json:
			return response.json()
		else:
			return response

	def request(self, method, *path, **data):
		"""Does a http request with given method to path based on *args, eg. ('GET', 'foo', 'bar')
		goes a GET /foo/bar. Any kwargs become parameters / data sent.
		Other kwargs that are special:
			version: API version as integer.
			headers: Dict of extra headers to use.
			json: If false, don't try to parse a json result (returns the response object)
		"""
		headers = data.pop('headers', {})
		version = data.pop('version', None)
		json = data.pop('json', True)
		path = urljoin(*path)
		return self._request(method, path, version, data, headers, json)

	def get(self, *path, **data):
		"""As request(), but with method GET"""
		return self.request('GET', *path, **data)

	def post(self, *path, **data):
		"""As request(), but with method POST"""
		return self.request('POST', *path, **data)

	def get_all(self, key, *path, **data):
		"""Some get endpoints return paginated lists. This function will yield
		results from the list over all pages.
		Please note that data may only apply to the first request. This is useful for eg. setting
		start offset.
		key must be the name of the key in the result containing the list entries.
		"""
		while True:
			response = self.get(*path, **data)
			items = response[key]
			if not items:
				return
			for item in items:
				yield item
			if '_links' not in response or 'next' not in response['_links']:
				return
			path = [response['_links']['next']]
			data = {}

	def channel(self, name):
		return Channel(self, name)

	def user(self, name):
		return User(self, name)

	def cheer(self, user_id, channel_id, message, cookie):
		"""Send a chat message involving cheers. No guarentee this will continue to work. Requires a cookie
		for auth, can't use oauth.
		Important: THIS WILL COST YOU BITS. The number of bits is dependent on the message text.
		Returns new bits balance.
		"""
		cheer_amount = sum(map(int, [match.group(1) for match in re.finditer(r'cheer(\d+)', message)]))
		resp = self._request('POST', 'https://api.twitch.tv/bits/events', version=4, oauth=False, data={
			'user_id': user_id,
			'channel_id': channel_id,
			'amount': cheer_amount,
			'event_id': str(uuid4()),
			'message': message,
		}, headers={'cookie': cookie})
		return resp['balance']


class HasData(object):
	"""Generic class for an object described by the api.
	Loads data on first access (or load() is called). Keys accessible by getattr."""
	_data = None

	def __init__(self, client, *args):
		self._client = client
		self._args = args

	def get_endpoint(self, *args):
		"""Subclasses should implement this to return data endpoint as a list of parts.
		*args is same as given to __init__"""
		raise NotImplementedError

	def load(self):
		path = self.get_endpoint(*self._args)
		self._data = self._client.get(*path)

	def __getattr__(self, attr):
		if self._data is None:
			self.load()
		if attr in self._data:
			return self._data[attr]
		raise AttributeError(attr)


class Channel(HasData):
	@property
	def name(self):
		name, = self._args
		return name

	def get_endpoint(self, name):
		return "channels", name

	@property
	def stream(self):
		"""Returns a dict of stream info if streaming, else None.
		Note: fetches fresh every time."""
		data = self._client.get("streams", self.name)['stream']
		if data is not None:
			data.pop('channel', None)
		return data


class User(HasData):
	@property
	def name(self):
		name, = self._args
		return name

	def get_endpoint(self, name):
		return "users", name

	@property
	def follows(self):
		"""Returns a dict {name: Channel object}.
		Note: fetches fresh every time."""
		results = {}
		for follow in self._client.get_all('follows', 'users', self.name, 'follows', 'channels', limit=100):
			# note: this channel data is NOT reliable, apart from name. it is stale data.
			ch_name = follow['channel']['name']
			results[ch_name] = self._client.channel(ch_name)
		return results

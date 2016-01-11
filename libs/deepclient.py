
"""Client library for interacting with deepbot's websocket API"""

import json
import logging
import weakref

import gevent.lock
import pytz
from websocket import create_connection


__requires__ = ['gevent', 'websocket-client', 'pytz']


class DeepClientError(Exception):
	pass


class ProtocolError(DeepClientError):
	"""Errors in the protocol, eg. a malformed response"""


class RequestFailed(DeepClientError):
	"""Raised when a request fails in some way"""


class AuthenticationFailed(RequestFailed):
	"""api secret was not correct"""


class UserNotFound(RequestFailed):
	"""The requested user does not exist"""


class InvalidPoints(RequestFailed):
	"""A points arg was not a positive integer"""


class NotEnoughPoints(RequestFailed):
	"""User did not have enough points to complete the operation"""


class NoEscrow(RequestFailed):
	"""User was not holding any points in escrow"""


class DeepClient(object):
	def __init__(self, url, api_secret):
		self.logger = logging.getLogger("deepclient").getChild("{:x}".format(id(self)))
		self.conn = create_connection(url)
		self.lock = gevent.lock.RLock()
		self.authenticate(api_secret)

	def request(self, method, *args):
		send_msg = '|'.join(('api', method) + map(str, args))
		self.logger.debug("Waiting to send {!r}".format(send_msg))
		with self.lock:
			self.logger.debug("Sending: {!r}".format(send_msg))
			self.conn.send(send_msg)
			response = self.conn.recv()
			self.logger.debug("Got response: {!r}".format(response))
		try:
			response = json.loads(response)
		except ValueError as ex:
			raise ProtocolError("Could not decode json response {!r}: {}".format(response, ex))
		if not isinstance(response, dict):
			raise ProtocolError("Response was {!r}, expected dict".format(response))
		missing = {'function', 'param', 'msg'} - response.keys()
		if missing:
			raise ProtocolError("Response {} missing required keys: {}".format(response, missing))
		if response['function'] != method:
			raise ProtocolError("Response {} is wrong method, expected {!r}".format(response, method))
		self.logger.info("Request {!r} returned {!r}".format(send_msg, response))
		return response['msg']

	def authenticate(self, api_secret):
		response = self.request('register', api_secret)
		if response != 'success':
			raise AuthenticationFailed()

	def get_user(self, name):
		response = self.request('get_user', name)
		if response == "user not found":
			raise UserNotFound(name)
		return User(response)

	def get_users(self, offset=0, limit=None):
		args = offset,
		if limit is not None:
			args += limit,
		response = self.request('get_users', *args)
		return map(User, response)

	def _points_op(self, method, name, points):
		"""Shared code for methods that take (user, points)"""
		response = self.request(method, name, points)
		if response == "user not found":
			raise UserNotFound(name)
		if response == "points should be a positive number":
			raise InvalidPoints(points)
		if response == "Not enough points":
			raise NotEnoughPoints(points)
		if response != 'success':
			raise RequestFailed("Unknown response for {}: {!r}".format(method, response))

	def set_points(self, name, points):
		return self._points_op('set_points', name, points)

	def add_points(self, name, points):
		return self._points_op('add_points', name, points)

	def del_points(self, name, points):
		return self._points_op('del_points', name, points)

	def add_to_escrow(self, name, points):
		return self._points_op('add_to_escrow', name, points)

	def end_escrow(self, name, commit):
		"""Commit should be True or False to either commit or cancel escrow.
		Generally, you should use commit_escrow() instead of end_escrow(True).
		This form is more useful for variables: end_escrow(success)"""
		method = 'commit_user_escrow' if commit else 'cancel_escrow'
		response = self.request(method, name)
		if response == "user not found":
			raise UserNotFound(name)
		if response == "No points in escrow":
			raise NoEscrow(name)
		if response != 'success':
			raise RequestFailed("Unknown response for {}: {!r}".format(method, response))

	def commit_escrow(self, name):
		self.end_escrow(True)

	def cancel_escrow(self, name):
		self.end_escrow(False)

	def set_vip(self, name, level, days):
		response = self.request('set_vip', name, level, days)
		if response == "user not found":
			raise UserNotFound(name)
		if response != 'success':
			raise RequestFailed("Unknown response for set_vip: {!r}".format(response))

	def escrow(self, name, points):
		"""Gives an Escrow() object associated with this instance"""
		return Escrow(self, name, points)


class User(object):
	def __init__(self, data):
		self.name = data['user']
		self.points = data['points']
		self.watch_time = data['watch_time']
		self.vip = data['vip'] # 0 (or 10?) for normal, 1,2,3 for bronze/silver/gold
		self.mod = data['mod'] # Not sure what this number means. Example just says 5?
		self.joined = self._parsetime(data['join_date'])
		self.last_seen = self._parsetime(data['last_seen'])
		self.vip_expiry = self._parsetime(data['vip_expiry'])

	@staticmethod
	def _parsetime(value):
		# ugh, shitty timestamps, local time, and shitty python date modules
		import datetime, time
		value = datetime.parser.parse(value) # guesses format
		value = value.astimezone(pytz.utc) # converts to UTC. would you believe this requires a 3rd party lib?
		value = time.mktime(value.timetuple()) # converts to epoch by way of python's time tuples, because providing a direct interface to the only sane way of counting time would be too much to ask
		return value

	def __str__(self):
		return "<User {self.name!r} {self.points} points>".format(self=self)


class Escrow(object):
	"""Context manager for putting points into escrow.
	On entry, reserves the points or raises if some error occurs (eg. NotEnoughPoints).
	On successful exit, commits the points. If the block raises, cancels the points.
	Note that since escrow is a single value per user, multiple escrow blocks for one user
	cannot run simultaniously. The second will block until the first one resolves.
	"""
	# This code will not do the right thing in the presence of multiple processes interacting
	# with the same users on the same deepbot instance. However, we have no way to check for that.

	# global dict {username: lock}. Note that if no-one is holding or requesting the lock, there will be
	# no references and so it will be GC'd.
	_locks = weakref.WeakValueDictionary()
	lock = None

	def __init__(self, client, name, points):
		self.client = client
		self.name = name
		self.points = points
		self.logger = self.client.logger.getChild('escrow').getChild(self.name)

	def __enter__(self):
		self.logger.info("Putting {} into escrow".format(self.points))
		self.lock = self._locks.get(self.name, gevent.lock.BoundedSemaphore())
		self.lock.acquire()
		self.logger.debug("Acquired lock")

		# Left over state from a crash or other interference may have caused some left-over escrow
		try:
			self.client.cancel_escrow(self.name)
		except NoEscrow:
			self.logger.debug("User had no unexpected escrow")
		else:
			self.logger.warning("User had unexpected escrow, cancelled")

		self.client.add_to_escrow(self.name, self.points)
		self.logger.debug("Put {} into escrow".format(self.points))

	def __exit__(self, *exc_info):
		success = (exc_info == (None, None, None))
		self.logger.info("{} {} from escrow".format('committing' if success else 'cancelling', self.points))
		self.client.end_escrow(self.name, success)
		self.logger.debug("Escrow ended")
		self.lock.release()
		self.logger.debug("Lock released")
		self.lock = None # this removes the reference, so if no-one is attempting to take the lock it will get GC'd

	def __repr__(self):
		return "<Escrow({self.name!r}, {self.points}), lock {lock}>".format(
			self=self,
			lock='not set' if self.lock is None else self.lock.locked()
		)

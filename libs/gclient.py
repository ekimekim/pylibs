
"""A basic async socket client for gevent

It implements connection management, send and receive functionality.
Subclass the _start, _send, _receive and _stop methods to create a client.
Send messages asyncronously by calling client.send(), this adds it to a send queue
and a seperate greenlet calls _send for each message in order.
_receive should implement a loop that receives data and acts on it
"""

__REQUIRES__ = ['gevent']

import gevent
from gevent.event import AsyncResult, Event
from gevent.pool import Group
from gevent.queue import Queue

class GClient(object):
	"""
	A generic gevent-based network client, that implements common send and receive functionality.
	Useful members:
		group: A gevent.pool.Group() tied to the lifetime of the client. When stopping, all greenlets
		       in the group will be killed.
		started: True if the client has been started
		stopped: True if the client has been stopped
		running: True if the client has been started but not stopped
	"""

	def __init__(self):
		self.group = Group()
		self.started = False
		self._send_queue = Queue()
		self._stopping = False
		self._stopped = AsyncResult()

	def start(self):
		"""Start the client, performing some connection step and beginning processing."""
		if self.started:
			raise Exception("Already started")
		self.started = True
		self._start()
		self._send_loop_worker = self.group.spawn(self._send_loop)
		self._recv_loop_worker = self.group.spawn(self._recv_loop)

	def _start(self):
		"""Override this with code that creates and initializes a connection"""

	def stop(self, ex=None):
		"""Stop the client, optionally referencing some exception.
		This will kill all greenlets in group and do any specific stop handling.
		Anyone waiting on the client stopping will have the exception raised, if any.
		"""
		if self._stopping:
			self.wait_for_stop()
			return
		if not self.started:
			self.started = True
		self._stopping = True

		# since the greenlet calling stop() might be in self.group, we make a new greenlet to do the work
		@gevent.spawn
		def stop_worker():
			self.group.kill(block=True)
			while not self._send_queue.empty():
				msg, event = self._send_queue.get(block=False)
				event.set()
			self._stop(ex)
			if ex:
				self._stopped.set_exception(ex)
			else:
				self._stopped.set(None)

		stop_worker.get()

	def _stop(self, ex=None):
		"""Optionally override this with specific cleanup code for stopping the client,
		such as closing the connection."""
		pass

	def wait_for_stop(self):
		"""Block until the client has stopped, re-raising the exception it was stopped with, if any."""
		self._stopped.get()

	@property
	def stopped(self):
		return self._stopped.ready()

	@property
	def running(self):
		return self.started and not self.stopped

	def send(self, msg, block=False):
		"""Enqueue some kind of message to be sent. If block=True, block until actually sent.
		If block=False, returns a gevent.event.Event() that will be set when actually sent,
		or the client is stopped.
		Note that messages are sent in order, so using either of these shouldn't often be needed.
		"""
		if self._stopping:
			raise Exception("Can't send to stopped client")
		event = Event()
		self._send_queue.put((msg, event))
		if block:
			event.wait()
		else:
			return event

	def _send_loop(self):
		try:
			for msg, event in self._send_queue:
				self._send(msg)
				event.set()
		except Exception as ex:
			self.stop(ex)

	def _send(self, msg):
		"""Override this with specific code for sending a message. It may raise to indicate a failure
		that will stop the client."""

	def _recv_loop(self):
		try:
			self._receive()
		except Exception as ex:
			self.stop(ex)
		else:
			self.stop()

	def _receive(self):
		"""Override this with code that receives data. It may return to indicate a graceful close,
		or raise to indicate a failure that will stop the client."""


class GSocketClient(GClient):
	"""A GClient with some additional boilerplate for dealing with sending/receiving from sockets.
	Does not implement _start(). Expects a subclass to set self._socket to a socket-like object.
	"""

	def _stop(self):
		self._socket.close()

	def _send(self, msg):
		msg = self._encode(msg)
		self._socket.sendall(msg)

	def _encode(self, msg):
		"""Take some message object and convert it to a string to be sent on the wire.
		By default, does nothing."""
		return msg

	def _receive(self):
		buf = ''
		while True:
			data = self._socket.read()
			if not data:
				# connection closed
				return
			buf += data
			while True:
				ret = self._decode(buf)
				if not ret:
					break
				msg, buf = ret
				self._handle(msg)

	def _decode(self, data):
		"""Take some string and decode it into a message object. Should return either (message, remaining data)
		or None to indicate no full message could be decoded.
		By default, splits into lines.
		"""
		if '\n' in data:
			return data.split('\n', 1)

	def _handle(self, msg):
		"""Called for each received message. Note that no further messages will be read until
		the _handle() for the previous message returns.
		"""
		raise NotImplementedError

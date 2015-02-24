
"""A simple library for implementing a pinentry program

Uses the Assuan pinentry protocol for prompting the user for a password.

Usage: Inherit from Pinentry and implement the appropriate methods for your specific means of entry.
Note that much of the protocol is chatter designed to set specific strings and other options.
This is all communicated and stored, and can be accessed when the more special methods are called.
When ready, begin communications with the remote client with the serve method.

Example:
	>>> class MyPinentry(Pinentry):
	... 	def getpin(self):
	... 		# ask user for pin based on self.options
	... 
	... pinentry = MyPinentry(in_pipe, out_pipe)
	... pinentry.serve_forever()
	... # pin was entered and returned, and client cleanly closed connection

As a simple example case, a GetpassPinentry implementation is also provided.
"""


class PinentryError(Exception):
	pass


class Pinentry(object):

	# list of defined options for SET* commands (eg. SETDESC, SETTITLE)
	ALLOWED_OPTIONS = {'desc', 'prompt', 'error', 'title', 'ok', 'cancel'}

	# defaults for options
	# these are mostly lowercase versions of the SETDESC, SETTITLE etc commands
	# but there are two special cases:
	# SETQUALITYBAR sets the 'quality' option to True (default False), and SETQUALITYBAR_TT sets 'quality_tt'.
	# OPTION key=value sets key to value.
	defaults = {
		'desc': 'Please insert your password',
		'prompt': 'Password',
		'title': 'Enter password',
		'ok': 'OK',
		'cancel': 'Cancel',
		'quality': False,
		'quality_tt': 'Password quality',
	}

	def __init__(self, input=None, output=None):
		"""Input and output should be two file-like or socket-like objects on which commands are recieved
		and sent.
		Input defaults to sys.stdin. Output defaults to input, unless input is sys.stdin (in which case
		it defaults to sys.stdout).
		"""
		if input is None:
			input = sys.stdin
		if output is None:
			output = sys.stdout if input == sys.stdin else input
		self.input = input
		self.output = output

		self.buffer = ''
		self.options = self.defaults.copy()

	def serve(self):
		try:
			while True:
				line = self.readline().strip()
				# XXX Docs didn't say how to reply with an error or what error codes exist,
				# so instead we always reply OK and disconnect on error.
				cmd, arg = line.split(' ', 1) if ' ' in line else (line, '')
				if cmd == 'SETQUALITYBAR':
					self.set_option('quality', True)
				elif cmd == 'SETQUALITYBAR_TT':
					self.set_option('quality_tt', decode(arg))
				elif cmd.startswith('SET') and cmd[3:].lower() in self.ALLOWED_OPTIONS:
					self.set_option(cmd[3:].lower(), decode(arg))
				elif cmd == 'CONFIRM':
					if not self.confirm(one_button=(arg == '--one-button')):
						raise PinentryError('failed to confirm')
				elif cmd == 'MESSAGE':
					self.message()
				elif cmd == 'GETPIN':
					pin = self.getpin()
					self.sendline(self.encode(pin))
				else:
					raise PinentryError("Unknown command: {}".format(cmd))
				self.sendline('OK')
		except PinentryError as ex:
			# XXX this is not correct error handling
			self.sendline("ERROR: ".format(self.encode(ex)))
			self.output.close()

	def encode(self, s):
		"""Given a string s, returns the string with % escapes and (if s is unicode) encoded as utf-8"""
		if isinstance(s, unicode):
			s = s.encode('utf-8')
		out = ''
		for c in s:
			if ord(c) > 0x20 and c not in ('%', '\x7f'):
				# numbers, letters, symbols, space and all unicode range
				out += c
			else:
				# non-printing ASCII characters (or '%')
				out += '%{:02x}'.format(ord(c))
		return out

	def decode(self, s):
		"""Given an encoded string s, interprets as utf-8 and processes % escapes"""
		if not isinstance(s, unicode):
			try:
				s.decode('utf-8')
			except UnicodeDecodeError as ex:
				raise PinentryError(str(ex))
		out = ''
		while s:
			if s[0] == '%':
				if len(s) < 3:
					raise PinentryError("Incomplete percent-escape: {}".format(s))
				n = s[1:3]
				try:
					n = int(n, 16)
				except ValueError as ex:
					raise PinentryError("Invalid percent-escape: %{}".format(n))
				out += chr(n)
				s = s[3:]
			else:
				out += s[0]
				s = s[1:]
		return out

	def readline(self):
		if '\n' in self.buffer:
			line, self.buffer = self.buffer.split('\n')
			return line
		# sockets and files are read from differently
		if hasattr(self.input, 'readline'):
			read = self.input.readline()
		else:
			read = self.input.recv(4096)
		if not read:
			raise EOFError
		self.buffer += read

	def sendline(self, line):
		# sockets and files are written to differently
		if hasattr(self.output, 'sendall'):
			# socket
			self.output.sendall(line + '\n')
		else:
			# file
			self.output.writeline(line)
			self.output.flush()

	def set_option(self, option, value):
		"""This method is called when SET* commands are recieved, for example SETTITLE, SETDESC.
		option is always lowercase. value is a unicode string without % escapes.
		The default is to store them in the self.options dict."""
		self.options[option] = value

	def message(self):
		"""Display self.desc to the user. This is expected to be overridden - the default implementation
		does nothing."""
		pass

	def confirm(self, one_button=False):
		"""Display self.desc to the user, asking them to respond yes/no
		(these texts should be self.ok, self.cancel). Should return True or False.
		If one_button=True, no cancel option should be allowed.
		This is expected to be overridden - the default implementation always returns True."""
		return True

	def getpin(self):
		"""The actual important part. Ask the user for the PIN and return it."""
		raise NotImplementedError


# TODO PinentryGetpass

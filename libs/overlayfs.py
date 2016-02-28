
import functools
import errno
import itertools
import os
from StringIO import StringIO

from fuse import FUSE, Operations, FuseOSError, LoggingMixIn

__REQUIRES__ = ['fusepy']


def with_source(fn):
	"""Decorator that wraps a function like fn(path, ...)
	so that path is the source path (see get_source_path())"""
	@functools.wraps(fn)
	def wrapped(self, path, *args, **kwargs):
		source = self.get_source_path(path)
		if not source:
			raise FuseOSError(errno.ENOENT)
		return fn(self, source, *args, **kwargs)
	return wrapped


class OverlayFS(LoggingMixIn, Operations):
	"""
	This class forms a base layer on which subclasses can create a FUSE filesystem
	which mimics an existing directory, but with some specific changes.
	Note that the overlay FS will automatically resolve all symlinks in the target
	directory. This means no file in the overlay FS will ever be a symlink.
	This filesystem is read only.
	"""

	def __init__(self, original):
		self.original = original
		self.open_files = {} # maps fh to (file-like object, offset)

	def get_source_path(self, input_path):
		"""Resolve a path to the underlying file for that path,
		or None if path does not exist."""
		path = input_path.lstrip('/')
		path = os.path.join(self.original, path)
		path = os.path.realpath(path) # no symlinks
		path = self._get_source_path(path)
		if path is None:
			return
		path = os.path.realpath(path) # transformed path may have re-introduced a symlink
		self.log.debug("get_source_path(%r) = %r", input_path, path)
		return path

	def _get_source_path(self, path):
		"""Takes a path in the original target directory (or outside it depending on symlinks followed),
		which may or may not exist.
		Should return a path (which may be the same one) that corresponds to the underlying file
		we should use for most operations (eg. stat). This path must exist.
		This is useful when you wish to create a virtual file which backs to a similar but different file.
		This function may return None to indicate the given path should appear to not exist.

		For example, suppose we wished to create an overlay FS which transformed the original directory
		so that files beginning with "x" were the only ones that existed, but they existed with the leading
		"x" stripped, so that a directory like: ["abc", "xyz", "xxx"] became ["yz", "xx"].
		Then we would implement this as:
			def _get_source_path(self, path):
				if path.startswith('x'):
					return path[1:]
				else:
					return None

		By default, this function will pass all paths unchanged, as long as they exist.
		"""
		return path if os.path.exists(path) else None

	def get_fs_paths(self, path):
		ret = ['/' + os.path.relpath(p, self.original) for p in self._get_fs_paths(path)]
		self.log.debug("get_fs_paths(%r) = %r", path, ret)
		return ret

	def _get_fs_paths(self, path):
		"""Given a path in the original directory, return a list of paths in the original directory which
		use that path as a source path. This is the inverse of _get_source_path, and it should
		always be the case that all(_get_source_path(p) == path for p in _get_fs_paths(path)).
		If you omit a path from the list, it will be accessible by open() or similar, but not visible when
		reading a directory.
		"""
		return [path]

	# fs operations

	@with_source
	def access(self, path, mode):
		if not os.access(path, mode):
			raise FuseOSError(errno.EACCES)

	@with_source
	def getattr(self, path, fh=None):
		stat = os.lstat(path)
		return {key: getattr(stat, key) for key in ('st_atime', 'st_ctime', 'st_gid', 'st_mode',
		                                            'st_nlink', 'st_size', 'st_uid')}

	def readdir(self, path, fh=None):
		"""You may need to override this function.
		By default, it will list contents of the source path corresponding to the directory,
		then pass each of those paths to get_fs_path to resolve them to new names.
		It will then return all paths that (after transform) are still children of the directory.
		HOWEVER, it has no way of detecting any paths that pre-transform ARE NOT in the directory,
		but post-transform ARE.
		You will need to override in this case.
		"""
		source_path = self.get_source_path(path)
		if not source_path:
			raise FuseOSError(errno.ENOENT)
		names = os.listdir(source_path)
		paths = [os.path.join(source_path, name) for name in names]
		transforms = sum([self.get_fs_paths(p) for p in paths], [])
		names = [os.path.basename(p) for p in transforms if p and os.path.dirname(p) == path]
		return ['.', '..'] + names

	def readlink(self, path):
		raise FuseOSError(errno.EINVAL) # not a symlink

	# file operations

	def open(self, path, flags):
		"""You should not override this function. Instead, see _open()."""
		if (os.O_WRONLY | os.O_RDWR) & flags:
			raise FuseOSError(errno.EROFS)
		source_path = self.get_source_path(path)
		if not source_path:
			if os.O_CREAT & flags:
				raise FuseOSError(errno.EROFS)
			raise FuseOSError(errno.ENOENT)
		fileobj = self._open(path, source_path)
		fh = (n for n in itertools.count() if n not in self.open_files).next()
		self.open_files[fh] = (fileobj, 0)
		return fh

	def _open(self, path, source_path):
		"""Takes the requested path, and the source path it was resolved to.
		Should return a file-like object, or otherwise if you are also overriding _read().
		By default, opens the source_path and returns the file object."""
		return open(source_path)

	def read(self, path, length, offset, fh):
		"""You should not override this function. Instead, see _read()."""
		fileobj, current_offset = self.open_files[fh]

		if offset != current_offset:
			try:
				fileobj.seek(offset)
			except (AttributeError, OSError, IOError):
				# not seekable
				raise FuseOSError(errno.EIO)
			self.open_files[fh] = fileobj, offset

		content = self._read(fileobj, length)
		if len(content) != length:
			self.log.warning("did not read enough: got %d, expected %d", len(content), length)
		self.open_files[fh] = fileobj, offset + length
		return content

	def _read(self, fileobj, length):
		"""Should return length bytes from fileobj. You should only need to subclass this
		if you want to associate something besides a file-like object with an open file,
		in which case you need to provide a means to read given this other object instead."""
		return fileobj.read(length)

	def release(self, path, fh):
		"""You should not override this function. Instead, see _release()."""
		fileobj, offset = self.open_files.pop(fh)
		self._release(fileobj)

	def _release(self, fileobj):
		"""Finalize and close fileobj. You should only need to subclass this if you want to associate
		something besides a file-like object with an open file, or otherwise have additional cleanup
		to do in addition to closing it."""
		fileobj.close()


class ReverseFS(OverlayFS):
	"""Intended as an example and test of OverlayFS, this FS reverses all filenames and file contents.
	For simplicity, it does not reverse directory names.
	"""

	def _get_source_path(self, path):
		if os.path.isdir(path):
			return path
		dirname = os.path.dirname(path)
		name = os.path.basename(path)
		newpath = os.path.join(dirname, name[::-1])
		if os.path.exists(newpath) and not os.path.isdir(newpath):
			return newpath

	def _get_fs_paths(self, path):
		if os.path.isfile(path):
			dirname = os.path.dirname(path)
			name = os.path.basename(path)
			path = os.path.join(dirname, name[::-1])
		return [path]

	def _open(self, path, source_path):
		with open(source_path) as f:
			content = f.read()
		return StringIO(content[::-1])


def fuse_main(operations, mountpoint):
	FUSE(operations, mountpoint, foreground=True, nothreads=True)


if __name__ == '__main__':
	import logging
	import importlib
	import sys

	logging.basicConfig(level='DEBUG')
	target, origin, mountpoint = sys.argv[1:4]
	target_parts = target.split('.')
	target_import, target_name = target_parts[:-1], target_parts[-1]
	target_import = '.'.join(target_import)

	target_module = importlib.import_module(target_import)
	target_class = getattr(target_module, target_name)
	fuse_main(target_class(origin), mountpoint)

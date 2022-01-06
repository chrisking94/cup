#!/usr/bin/env python
# encoding: utf-8
#
# Copyright (c) 2017 Dean Jackson <deanishe@deanishe.net>
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2017-07-16
#

"""defaults.py (save|delete) <dimensionality> <unit>

Save/delete default units for given dimensionality.

Usage:
    defaults.py save <dimensionality> <unit>
    defaults.py delete <dimensionality> <unit>
    defaults.py --help

Options:
    -h, --help  Show this message

"""

from __future__ import print_function, absolute_import

from collections import defaultdict


log = None


class Defaults(object):
    """Manage default units for dimensionalities.

    Saves default units in workflow's settings file.

    """

    def __init__(self, settings):
        """Create new `Defaults` for workflow.

        Args:
            settings (dict): Active Workflow3 object.
        """
        self._settings = settings
        self._defs = self._load()

    def defaults(self, dimensionality):
        """Default units for dimensionality.

        Args:
            dimensionality (str): Dimensionality to return units for

        Returns:
            list: Sequence of default units

        """
        return self._defs[dimensionality][:]

    def add(self, dimensionality, unit):
        """Save ``unit`` as default for ``dimensionality``.

        Args:
            dimensionality (str): Dimensionality
            unit (str): Unit

        """
        if not self.is_default(dimensionality, unit):
            self._defs[dimensionality].append(unit)
            self._save()

    def remove(self, dimensionality, unit):
        """Remove ``unit`` as default for ``dimensionality``.

        Args:
            dimensionality (str): Dimensionality
            unit (str): Unit

        """
        if self.is_default(dimensionality, unit):
            self._defs[dimensionality].remove(unit)
            self._save()

    def is_default(self, dimensionality, unit):
        """Check whether ``unit`` is a default for ``dimensionality``.

        Args:
            dimensionality (str): Dimensionality
            unit (str): Unit

        Returns:
            bool: ``True`` if ``unit`` is a default.

        """
        return unit in self._defs[dimensionality]

    def _load(self):
        defs = defaultdict(list)
        defs.update(self._settings.get('default_units', {}))
        return defs

    def _save(self):
        self._settings['default_units'] = dict(self._defs)

